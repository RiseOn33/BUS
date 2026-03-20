import time, math, json, requests
from datetime import datetime

# --- Passio live feed (matches your working curl format) ---
URL = "https://passiogo.com/mapGetData.php?getBuses=1&deviceId=124212705&speed=1"
HEADERS = {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
DATA = {"json": '{"s0":"3994","sA":1}'}

# Live routeId for North South in the Passio feed (from your JSON)
TARGET_LIVE_ROUTE_ID = "64201"

POLL_S = 5

# Tuning knobs
STOP_RADIUS_M = 35.0          # within 35m counts as "at stop" (when stopped)
SPEED_STOPPED_MPS = 0.6       # <= ~1.3 mph treat as stopped
MOVE_STOPPED_M = 8.0          # moved less than 8m since last poll treat as stopped
STOP_STREAK = 2               # require 2 consecutive "stopped" polls for AT stop

def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))

# --- Load ordered stops from Step 2 output ---
with open("north_south_stops.json", "r", encoding="utf-8") as f:
    stop_data = json.load(f)

STOPS = stop_data["stops"]  # list of {"seq", "stop_id", "name", "lat", "lon"}
N = len(STOPS)
print(f"Loaded {N} North South stops from north_south_stops.json")

# state
last_pos = {}       # deviceId -> (lat, lon)
stop_streak = {}    # deviceId -> consecutive stopped polls

def fetch_route_buses():
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

def nearest_stop_index(lat, lon):
    dists = [haversine_m(lat, lon, s["lat"], s["lon"]) for s in STOPS]
    i = min(range(N), key=dists.__getitem__)
    return i, dists[i], dists

def label_position(lat, lon, is_stopped):
    i, d_i, dists = nearest_stop_index(lat, lon)

    # If stopped and close to a stop -> AT that stop
    if is_stopped and d_i <= STOP_RADIUS_M:
        return ("AT", STOPS[i]["name"], None, d_i)

    # Otherwise BETWEEN: pick the nearer neighbor (i-1 or i+1) as the other stop
    left = i - 1 if i - 1 >= 0 else None
    right = i + 1 if i + 1 < N else None

    # Edge cases: first/last stop
    if left is None and right is None:
        return ("BETWEEN", STOPS[i]["name"], STOPS[i]["name"], d_i)
    if left is None:
        return ("BETWEEN", STOPS[i]["name"], STOPS[right]["name"], d_i)
    if right is None:
        return ("BETWEEN", STOPS[left]["name"], STOPS[i]["name"], d_i)

    # Choose neighbor with smaller distance
    j = left if dists[left] <= dists[right] else right

    a, b = sorted([i, j])
    return ("BETWEEN", STOPS[a]["name"], STOPS[b]["name"], d_i)

print("\nTracking North South buses; printing AT stop or BETWEEN stops...\nCtrl+C to stop.\n")

while True:
    try:
        buses = fetch_route_buses()
        now = datetime.now().strftime("%H:%M:%S")

        if not buses:
            print(f"[{now}] No active North South buses found.")
            time.sleep(POLL_S)
            continue

        for b in buses:
            dev = int(b["deviceId"])
            bus_name = b.get("busName", str(dev))
            lat = float(b["latitude"])
            lon = float(b["longitude"])

            sp = b.get("speed", None)
            speed = float(sp) if sp not in (None, "") else None

            moved_m = None
            if dev in last_pos:
                moved_m = haversine_m(last_pos[dev][0], last_pos[dev][1], lat, lon)

            # stopped logic
            stopped_by_speed = (speed is not None and speed <= SPEED_STOPPED_MPS)
            stopped_by_move = (moved_m is not None and moved_m <= MOVE_STOPPED_M)
            is_stopped_now = stopped_by_speed or stopped_by_move

            if is_stopped_now:
                stop_streak[dev] = stop_streak.get(dev, 0) + 1
            else:
                stop_streak[dev] = 0

            is_stopped = stop_streak[dev] >= STOP_STREAK

            mode, x, y, d = label_position(lat, lon, is_stopped)

            speed_str = f"{speed:.2f} m/s" if speed is not None else "n/a"
            moved_str = f"{moved_m:.1f} m" if moved_m is not None else "n/a"

            if mode == "AT":
                print(f"[{now}] Bus {bus_name:>6} | AT: {x} | dist={d:.0f}m | speed={speed_str} | moved={moved_str}")
            else:
                print(f"[{now}] Bus {bus_name:>6} | BETWEEN: {x} → {y} | near={d:.0f}m | speed={speed_str} | moved={moved_str}")

            last_pos[dev] = (lat, lon)

        print("-" * 90)
        time.sleep(POLL_S)

    except KeyboardInterrupt:
        print("\nStopping.")
        break
