import os, re, time, math, json, threading
from datetime import datetime
import requests
from flask import Flask, jsonify, request, send_from_directory

# ----- Passio settings (your working format) -----
URL = "https://passiogo.com/mapGetData.php?getBuses=1&deviceId=124212705&speed=1"
HEADERS = {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
DATA = {"json": '{"s0":"3994","sA":1}'}

POLL_S = 5

# Movement heuristics
STOP_RADIUS_M = 35.0
SPEED_MOVING_MPS = 1.0
MOVE_MOVING_M = 12.0

STOPMAP_DIR = "stopmaps"
STOPMAP_INDEX = os.path.join(STOPMAP_DIR, "_index.json")

app = Flask(__name__)

# Global state updated by poller
STATE = {
    "ok": False,
    "updated": None,
    "routes": [],            # list of routes (routeId, name, color, count)
    "buses_by_route": {},    # routeId -> list[bus objects]
    "error": None,
}

last_pos = {}  # deviceId -> (lat, lon)


# ---------- helpers ----------
def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))

def norm_name(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", "", s)
    return s

def load_stopmap_index():
    if not os.path.exists(STOPMAP_INDEX):
        return {}
    with open(STOPMAP_INDEX, "r", encoding="utf-8") as f:
        idx = json.load(f)
    # Normalize keys for robust matching
    return {norm_name(k): v for k, v in idx.items()}

STOPMAP_IDX = load_stopmap_index()

def load_stops_for_route_name(route_name: str):
    """Returns list of stops or None."""
    if not STOPMAP_IDX:
        return None
    rn = norm_name(route_name)
    if not rn:
        return None

    fname = STOPMAP_IDX.get(rn)
    if not fname:
        # fallback: substring match
        for k, v in STOPMAP_IDX.items():
            if rn in k or k in rn:
                fname = v
                break
    if not fname:
        return None

    path = os.path.join(STOPMAP_DIR, fname)
    if not os.path.exists(path):
        return None

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("stops")

def nearest_stop_index(lat, lon, stops):
    dists = [haversine_m(lat, lon, s["lat"], s["lon"]) for s in stops]
    i = min(range(len(stops)), key=dists.__getitem__)
    return i, dists[i], dists

def label_location(lat, lon, is_moving, stops):
    if not stops:
        return "(no stop map)"

    i, d_i, dists = nearest_stop_index(lat, lon, stops)

    if (not is_moving) and d_i <= STOP_RADIUS_M:
        return "AT: " + stops[i]["name"]

    left = i - 1 if i - 1 >= 0 else None
    right = i + 1 if i + 1 < len(stops) else None

    if left is None and right is None:
        return stops[i]["name"]
    if left is None:
        return f"BETWEEN: {stops[i]['name']} → {stops[right]['name']}"
    if right is None:
        return f"BETWEEN: {stops[left]['name']} → {stops[i]['name']}"

    j = left if dists[left] <= dists[right] else right
    a, b = sorted([i, j])
    return f"BETWEEN: {stops[a]['name']} → {stops[b]['name']}"

def fetch_all_buses():
    r = requests.post(URL, data=DATA, headers=HEADERS, timeout=10)
    r.raise_for_status()
    j = r.json()

    buses = []
    for _, arr in j.get("buses", {}).items():
        if not arr:
            continue
        b = arr[0]
        if b.get("outOfService") == 1 or b.get("outdated") == 1:
            continue
        buses.append(b)
    return buses


# ---------- poller ----------
def poll_loop():
    global STATE, STOPMAP_IDX
    # Reload index on startup (in case you add files while running)
    STOPMAP_IDX = load_stopmap_index()

    while True:
        try:
            buses_raw = fetch_all_buses()

            # Build route list
            routes_map = {}  # routeId -> {routeId,name,color,count}
            buses_by_route_raw = {}  # routeId -> list of raw bus records

            for b in buses_raw:
                rid = str(b.get("routeId"))
                rname = (b.get("route") or "").strip()
                rcolor = b.get("color")

                routes_map.setdefault(rid, {"routeId": rid, "name": rname, "color": rcolor, "count": 0})
                routes_map[rid]["count"] += 1

                buses_by_route_raw.setdefault(rid, []).append(b)

            routes_list = sorted(routes_map.values(), key=lambda x: (x["name"], x["routeId"]))

            # Precompute stop lists per route name (cached per poll)
            stops_cache = {}  # routeId -> stops or None
            for r in routes_list:
                stops_cache[r["routeId"]] = load_stops_for_route_name(r["name"])

            # Build per-route processed bus objects
            buses_by_route = {}

            for rid, blist in buses_by_route_raw.items():
                stops = stops_cache.get(rid)

                out = []
                for b in blist:
                    dev = int(b["deviceId"])
                    bus_name = b.get("busName", str(dev))

                    lat = float(b["latitude"])
                    lon = float(b["longitude"])

                    sp = b.get("speed", None)
                    speed = float(sp) if sp not in (None, "") else None

                    moved_m = None
                    if dev in last_pos:
                        moved_m = haversine_m(last_pos[dev][0], last_pos[dev][1], lat, lon)

                    moving_by_speed = (speed is not None and speed >= SPEED_MOVING_MPS)
                    moving_by_move = (moved_m is not None and moved_m >= MOVE_MOVING_M)
                    is_moving = moving_by_speed or moving_by_move

                    loc = label_location(lat, lon, is_moving, stops)

                    out.append({
                        "busName": bus_name,
                        "status": "DRIVING" if is_moving else "STOPPED",
                        "location": loc,
                        "reported": b.get("createdTime") or "n/a",
                    })

                    last_pos[dev] = (lat, lon)

                out.sort(key=lambda x: x["busName"])
                buses_by_route[rid] = out

            STATE = {
                "ok": True,
                "updated": datetime.now().strftime("%H:%M:%S"),
                "routes": routes_list,
                "buses_by_route": buses_by_route,
                "error": None,
            }

        except Exception as e:
            STATE = {
                "ok": False,
                "updated": datetime.now().strftime("%H:%M:%S"),
                "routes": [],
                "buses_by_route": {},
                "error": str(e),
            }

        time.sleep(POLL_S)


# ---------- endpoints ----------
@app.get("/api/routes")
def api_routes():
    return jsonify({
        "ok": STATE.get("ok", False),
        "updated": STATE.get("updated"),
        "routes": STATE.get("routes", []),
        "error": STATE.get("error"),
    })

@app.get("/api/state")
def api_state():
    route_id = request.args.get("routeId")
    buses_by_route = STATE.get("buses_by_route", {})
    routes = STATE.get("routes", [])

    # Default route: first in list
    if not route_id:
        route_id = routes[0]["routeId"] if routes else None

    return jsonify({
        "ok": STATE.get("ok", False),
        "updated": STATE.get("updated"),
        "routeId": route_id,
        "routes": routes,
        "buses": buses_by_route.get(route_id, []) if route_id else [],
        "error": STATE.get("error"),
    })

@app.get("/")
def index():
    base = os.path.dirname(os.path.abspath(__file__))
    return send_from_directory(base, "index.html")


if __name__ == "__main__":
    threading.Thread(target=poll_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=False)
