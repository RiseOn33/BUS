import time, math, requests
from datetime import datetime

URL = "https://passiogo.com/mapGetData.php?getBuses=1&deviceId=124212705&speed=1"

DATA = {
    "json": '{"s0":"3994","sA":1}'
}

HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
}


TARGET_ROUTE_ID = "64201"   # North South (from your JSON)
POLL_S = 5

# Heuristics (tweak as you like)
SPEED_MOVING_MPS = 1.0      # ~2.2 mph
MOVE_MOVING_M = 12.0        # moved >= 12 meters between polls => moving
STOP_STREAK_FOR_STOPPED = 3 # how many polls in a row before we call it "at stop"

def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def fetch_route_buses():
    r = requests.post(URL, data=DATA, headers=HEADERS, timeout=10)

    print("HTTP status:", r.status_code)

    if r.status_code != 200:
        print("Bad response:", r.text[:200])
        return []

    try:
        j = r.json()
    except Exception:
        print("Response is not JSON:")
        print(r.text[:500])
        return []

    out = []
    for _, arr in j.get("buses", {}).items():
        if not arr:
            continue
        b = arr[0]
        if str(b.get("routeId")) != TARGET_ROUTE_ID:
            continue
        if b.get("outOfService") == 1 or b.get("outdated") == 1:
            continue
        out.append(b)

    return out


# state per deviceId
last_pos = {}        # deviceId -> (lat, lon)
still_streak = {}    # deviceId -> count of consecutive "not moving"

print(f"Tracking routeId={TARGET_ROUTE_ID} (North South) every {POLL_S}s...\nCtrl+C to stop.\n")

while True:
    try:
        buses = fetch_route_buses()
        now = datetime.now().strftime("%H:%M:%S")

        if not buses:
            print(f"[{now}] No active buses found on route {TARGET_ROUTE_ID}")
            time.sleep(POLL_S)
            continue

        for b in buses:
            dev = int(b["deviceId"])
            name = b.get("busName", str(dev))

            lat = float(b["latitude"])
            lon = float(b["longitude"])

            # Speed field is sometimes missing; treat missing as None
            sp = b.get("speed", None)
            speed = float(sp) if sp not in (None, "") else None

            moved_m = None
            if dev in last_pos:
                moved_m = haversine_m(last_pos[dev][0], last_pos[dev][1], lat, lon)

            # Decide moving/stopped
            moving_by_speed = (speed is not None and speed >= SPEED_MOVING_MPS)
            moving_by_move = (moved_m is not None and moved_m >= MOVE_MOVING_M)

            is_moving = moving_by_speed or moving_by_move

            if is_moving:
                still_streak[dev] = 0
                status = "DRIVING"
            else:
                still_streak[dev] = still_streak.get(dev, 0) + 1
                status = "AT/NEAR STOP" if still_streak[dev] >= STOP_STREAK_FOR_STOPPED else "PAUSING"

            last_pos[dev] = (lat, lon)

            speed_str = f"{speed:.2f} m/s" if speed is not None else "n/a"
            moved_str = f"{moved_m:.1f} m" if moved_m is not None else "n/a"

            print(f"[{now}] Bus {name:>6} | {status:<11} | speed={speed_str:<9} | moved={moved_str:<8} | streak={still_streak[dev]}")

        print("-" * 80)
        time.sleep(POLL_S)

    except KeyboardInterrupt:
        print("\nStopping.")
        break
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(POLL_S)
