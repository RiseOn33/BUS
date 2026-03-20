import time, math, threading, json
from datetime import datetime
import requests
from flask import Flask, jsonify, send_from_directory
import os

# ----- Passio settings -----
URL = "https://passiogo.com/mapGetData.php?getBuses=1&deviceId=124212705&speed=1"
HEADERS = {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
DATA = {"json": '{"s0":"3994","sA":1}'}

TARGET_LIVE_ROUTE_ID = "64201"
POLL_S = 5

# Movement tuning
STOP_RADIUS_M = 35
SPEED_MOVING_MPS = 1.0
MOVE_MOVING_M = 12.0

app = Flask(__name__)

# Load stops
with open("north_south_stops.json", "r", encoding="utf-8") as f:
    stop_data = json.load(f)

STOPS = stop_data["stops"]
N = len(STOPS)

state = {"ok": False, "buses": []}
last_pos = {}

def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def nearest_stop_index(lat, lon):
    dists = [haversine_m(lat, lon, s["lat"], s["lon"]) for s in STOPS]
    i = min(range(N), key=dists.__getitem__)
    return i, dists[i], dists

def label_position(lat, lon, is_moving):
    i, d_i, dists = nearest_stop_index(lat, lon)

    if not is_moving and d_i <= STOP_RADIUS_M:
        return "AT: " + STOPS[i]["name"]

    left = i - 1 if i - 1 >= 0 else None
    right = i + 1 if i + 1 < N else None

    if left is None and right is None:
        return STOPS[i]["name"]

    if left is None:
        return f"{STOPS[i]['name']} → {STOPS[right]['name']}"

    if right is None:
        return f"{STOPS[left]['name']} → {STOPS[i]['name']}"

    j = left if dists[left] <= dists[right] else right
    a, b = sorted([i, j])
    return f"{STOPS[a]['name']} → {STOPS[b]['name']}"

def fetch_buses():
    r = requests.post(URL, data=DATA, headers=HEADERS, timeout=10)
    r.raise_for_status()
    j = r.json()
    out = []
    for _, arr in j.get("buses", {}).items():
        if not arr:
            continue
        b = arr[0]
        if str(b.get("routeId")) != TARGET_LIVE_ROUTE_ID:
            continue
        if b.get("outOfService") == 1 or b.get("outdated") == 1:
            continue
        out.append(b)
    return out

def poll_loop():
    global state
    while True:
        try:
            buses_raw = fetch_buses()
            buses_out = []

            for b in buses_raw:
                dev = int(b["deviceId"])
                name = b.get("busName", str(dev))

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

                direction_label = label_position(lat, lon, is_moving)

                buses_out.append({
                    "busName": name,
                    "status": "DRIVING" if is_moving else "STOPPED",
                    "location": direction_label,                 # rename for clarity
                    "reported": b.get("createdTime") or "n/a"     # time from feed, if present
                })


                last_pos[dev] = (lat, lon)

            buses_out.sort(key=lambda x: x["busName"])

            state = {
                "ok": True,
                "updated": datetime.now().strftime("%H:%M:%S"),
                "buses": buses_out
            }

        except Exception as e:
            state = {"ok": False, "error": str(e)}

        time.sleep(POLL_S)

@app.get("/api/state")
def api_state():
    return jsonify(state)

@app.get("/")
def index():
    base = os.path.dirname(os.path.abspath(__file__))
    return send_from_directory(base, "index.html")

if __name__ == "__main__":
    t = threading.Thread(target=poll_loop, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=5000)
