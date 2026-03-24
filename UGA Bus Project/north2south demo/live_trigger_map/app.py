import json
import math
import os
import threading
import time
from datetime import datetime

import requests
from flask import Flask, jsonify, send_from_directory

URL = "https://passiogo.com/mapGetData.php?getBuses=1&deviceId=124212705&speed=1"
HEADERS = {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
DATA = {"json": '{"s0":"3994","sA":1}'}
TARGET_LIVE_ROUTE_ID = "64201"
POLL_S = 5

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)

app = Flask(__name__)

TRIGGER_FILES = {
    "full": os.path.join(BASE_DIR, "trigger_points.full.json"),
    "segmented": os.path.join(BASE_DIR, "trigger_points.segmented.json"),
}


def load_trigger_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


MAP_CONFIGS = {name: load_trigger_config(path) for name, path in TRIGGER_FILES.items()}

state = {}
for name, config in MAP_CONFIGS.items():
    state[name] = {
        "ok": False,
        "updated": None,
        "mapName": config["map_name"],
        "mapImage": config["map_image"],
        "imageWidth": config["image_width"],
        "imageHeight": config["image_height"],
        "points": config["points"],
        "buses": [],
    }


def haversine_m(lat1, lon1, lat2, lon2):
    radius_m = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius_m * math.asin(math.sqrt(a))


def nearest_trigger_point(lat, lon, points):
    best = None
    best_distance = None
    for point in points:
        distance = haversine_m(lat, lon, point["lat"], point["lon"])
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best = point
    return best, best_distance


def fetch_route_buses():
    response = requests.post(URL, data=DATA, headers=HEADERS, timeout=10)
    response.raise_for_status()
    payload = response.json()

    buses = []
    for _, arr in payload.get("buses", {}).items():
        if not arr:
            continue
        bus = arr[0]
        if str(bus.get("routeId")) != TARGET_LIVE_ROUTE_ID:
            continue
        if bus.get("outOfService") == 1 or bus.get("outdated") == 1:
            continue
        buses.append(bus)
    return buses


def build_bus_state(points):
    buses_out = []
    for bus in fetch_route_buses():
        lat = float(bus["latitude"])
        lon = float(bus["longitude"])
        point, distance_m = nearest_trigger_point(lat, lon, points)

        buses_out.append(
            {
                "busName": bus.get("busName", str(bus["deviceId"])),
                "deviceId": str(bus["deviceId"]),
                "reported": bus.get("createdTime") or "n/a",
                "latitude": lat,
                "longitude": lon,
                "pointId": point["id"],
                "pointLabel": point["label"],
                "pointType": point["type"],
                "distanceToPointM": round(distance_m, 1),
                "x": point["x"],
                "y": point["y"],
            }
        )

    buses_out.sort(key=lambda item: item["busName"])
    return buses_out


def poll_loop():
    global state
    while True:
        for name, config in MAP_CONFIGS.items():
            try:
                state[name] = {
                    "ok": True,
                    "updated": datetime.now().strftime("%H:%M:%S"),
                    "mapName": config["map_name"],
                    "mapImage": config["map_image"],
                    "imageWidth": config["image_width"],
                    "imageHeight": config["image_height"],
                    "points": config["points"],
                    "buses": build_bus_state(config["points"]),
                }
            except Exception as exc:
                state[name] = {
                    "ok": False,
                    "updated": datetime.now().strftime("%H:%M:%S"),
                    "error": str(exc),
                    "mapName": config["map_name"],
                    "mapImage": config["map_image"],
                    "imageWidth": config["image_width"],
                    "imageHeight": config["image_height"],
                    "points": config["points"],
                    "buses": [],
                }
        time.sleep(POLL_S)


@app.get("/api/state/<map_name>")
def api_state(map_name):
    if map_name not in state:
        return jsonify({"ok": False, "error": f"unknown map '{map_name}'"}), 404
    return jsonify(state[map_name])


@app.get("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/maps/full")
@app.get("/maps/segmented")
def map_view():
    return send_from_directory(BASE_DIR, "map_view.html")


@app.get("/map_references/<path:filename>")
def map_image(filename):
    return send_from_directory(os.path.join(PROJECT_DIR, "map_references"), filename)


if __name__ == "__main__":
    thread = threading.Thread(target=poll_loop, daemon=True)
    thread.start()
    app.run(host="0.0.0.0", port=5001)
