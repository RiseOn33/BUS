import time, math, json, os, requests, threading, queue

# ---- Passio request (your working format) ----
URL = "https://passiogo.com/mapGetData.php?getBuses=1&deviceId=124212705&speed=1"
HEADERS = {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
DATA = {"json": '{"s0":"3994","sA":1}'}

POLL_S = 5

# Driving/stopped heuristics
SPEED_MOVING_MPS = 1.0   # if speed exists and >= this => moving
MOVE_MOVING_M = 12.0     # if moved >= this since last poll => moving
STOP_RADIUS_M = 35.0     # for AT: stop label when stopped

def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))

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

def build_routes_index(buses):
    routes = {}  # routeId -> {name,color,count}
    for b in buses:
        rid = str(b.get("routeId"))
        routes.setdefault(rid, {
            "routeId": rid,
            "name": (b.get("route") or "").strip(),
            "color": b.get("color"),
            "count": 0
        })
        routes[rid]["count"] += 1
    # sort by name then routeId
    return sorted(routes.values(), key=lambda x: (x["name"], x["routeId"]))

def load_stop_map_for_live_route(route_name):
    rn = (route_name or "").strip().lower()
    if not rn:
        return None

    idx_path = os.path.join("stopmaps", "_index.json")
    if not os.path.exists(idx_path):
        return None

    with open(idx_path, "r", encoding="utf-8") as f:
        idx = json.load(f)

    fname = idx.get(rn)
    if not fname:
        return None

    path = os.path.join("stopmaps", fname)
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

def input_thread(cmd_q):
    while True:
        try:
            s = input().strip()
            cmd_q.put(s)
        except EOFError:
            break

def print_routes(routes):
    print("\nAvailable routes (routeId | buses | name):")
    for r in routes:
        print(f"  {r['routeId']:>6} | {r['count']:>2} | {r['name']}")
    print("\nCommands:")
    print("  set <routeId>     (switch route)")
    print("  list              (show routes)")
    print("  help              (show commands)")
    print("  quit              (exit)\n")

def main():
    cmd_q = queue.Queue()
    threading.Thread(target=input_thread, args=(cmd_q,), daemon=True).start()

    selected_route_id = None
    last_pos = {}

    # initial discovery
    buses = fetch_all_buses()
    routes = build_routes_index(buses)
    print_routes(routes)

    # default route: North South if present, else first route
    ns = next((r for r in routes if r["name"].strip().lower() == "north south"), None)
    if ns:
        selected_route_id = ns["routeId"]
    elif routes:
        selected_route_id = routes[0]["routeId"]

    print(f"Tracking routeId={selected_route_id}. Type 'list' to see routes, 'set <id>' to switch.\n")

    while True:
        # handle commands (non-blocking)
        while not cmd_q.empty():
            cmd = cmd_q.get()
            if cmd in ("quit", "exit"):
                print("Bye.")
                return
            if cmd == "help":
                print_routes(routes)
            elif cmd == "list":
                # refresh routes list from latest pull
                buses_tmp = fetch_all_buses()
                routes = build_routes_index(buses_tmp)
                print_routes(routes)
            elif cmd.startswith("set "):
                rid = cmd.split(" ", 1)[1].strip()
                selected_route_id = rid
                print(f"\nSwitched to routeId={selected_route_id}\n")

            elif cmd.startswith("setname "):
                name = cmd.split(" ", 1)[1].strip().lower()
                # make sure routes list is fresh
                buses_tmp = fetch_all_buses()
                routes = build_routes_index(buses_tmp)

                match = next((r for r in routes if name in r["name"].lower()), None)
                if not match:
                    print(f"No route name match for: {name}. Try 'list' to see names.")
                else:
                    selected_route_id = match["routeId"]
                    print(f"\nSwitched to {match['name']} (routeId={selected_route_id})\n")

            elif cmd:
                print("Unknown command. Try: list, set <routeId>, help, quit")

        # poll
        try:
            buses = fetch_all_buses()
        except Exception as e:
            print(f"[poll error] {e}")
            time.sleep(POLL_S)
            continue

        # build route info
        route_name = None
        route_color = None
        buses_on_route = []
        for b in buses:
            if str(b.get("routeId")) == str(selected_route_id):
                buses_on_route.append(b)
                route_name = (b.get("route") or "").strip()
                route_color = b.get("color")

        # load stop map based on route name (only if available)
        stops = load_stop_map_for_live_route(route_name)

        print("-" * 90)
        print(f"Route {route_name or ''} (routeId={selected_route_id}, color={route_color}) | buses={len(buses_on_route)}")

        if not buses_on_route:
            print("No active buses on this route right now.")
            time.sleep(POLL_S)
            continue

        for b in sorted(buses_on_route, key=lambda x: str(x.get("busName",""))):
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

            status = "DRIVING" if is_moving else "STOPPED"
            speed_str = f"{speed:.2f} m/s" if speed is not None else "n/a"
            moved_str = f"{moved_m:.1f} m" if moved_m is not None else "n/a"

            # If you don't want speed/moved, delete those fields from this print line.
            print(f"Bus {bus_name:>6} | {status:<7} | {loc} | speed={speed_str} | moved={moved_str}")

            last_pos[dev] = (lat, lon)

        time.sleep(POLL_S)

if __name__ == "__main__":
    main()
