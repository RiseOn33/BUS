import csv, json, os, re
from collections import defaultdict, Counter

# Configuration
GTFS_DIR = "."  # Directory containing the .txt files
OUT_DIR = "stopmaps"

def slug(s: str) -> str:
    """Sanitizes a string to be safe for filenames."""
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_") or "route"

def load_gtfs_data(gtfs_dir):
    """Loads necessary GTFS files into memory."""
    print("Loading GTFS data...")

    # Routes: route_id -> name
    routes = {}
    with open(os.path.join(gtfs_dir, "routes.txt"), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = (row.get("route_long_name") or row.get("route_short_name") or "").strip()
            routes[row["route_id"]] = name

    # Trips: route_id -> set(trip_ids)
    route_to_trips = defaultdict(set)
    with open(os.path.join(gtfs_dir, "trips.txt"), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            route_to_trips[row["route_id"]].add(row["trip_id"])

    # Stop Times: trip_id -> list[(seq, stop_id)]
    trip_stopseq = defaultdict(list)
    with open(os.path.join(gtfs_dir, "stop_times.txt"), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            trip_stopseq[row["trip_id"]].append((int(row["stop_sequence"]), row["stop_id"]))

    # Sort stop sequences for each trip
    for tid in trip_stopseq:
        trip_stopseq[tid].sort(key=lambda x: x[0])

    # Stops: stop_id -> {name, lat, lon}
    stops = {}
    with open(os.path.join(gtfs_dir, "stops.txt"), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            stops[row["stop_id"]] = {
                "stop_id": row["stop_id"],
                "name": row.get("stop_name", ""),
                "lat": float(row["stop_lat"]),
                "lon": float(row["stop_lon"]),
            }

    return routes, route_to_trips, trip_stopseq, stops

def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    try:
        routes, route_to_trips, trip_stopseq, stops = load_gtfs_data(GTFS_DIR)
    except FileNotFoundError as e:
        print(f"Error: Could not find GTFS files in '{GTFS_DIR}'. {e}")
        return

    index = {}  # route_name_lower -> filename
    written = 0
    skipped = 0

    print("Processing routes...")
    for route_id, name in routes.items():
        trip_ids = route_to_trips.get(route_id, set())

        # 1. Filter trips that actually have stop_times
        valid_trips = [t for t in trip_ids if t in trip_stopseq and trip_stopseq[t]]

        if not valid_trips:
            skipped += 1
            continue

        # 2. Find modal length (most common number of stops)
        lengths = [len(trip_stopseq[t]) for t in valid_trips]
        rep_len = Counter(lengths).most_common(1)[0][0]

        # 3. Pick the first trip that matches this length
        rep_trip = next((t for t in valid_trips if len(trip_stopseq[t]) == rep_len), None)

        if not rep_trip:
            skipped += 1
            continue

        # 4. Build the ordered stop list
        ordered_stop_ids = [sid for _, sid in trip_stopseq[rep_trip]]
        ordered = []
        seq = 1
        for sid in ordered_stop_ids:
            if sid not in stops:
                continue
            o = stops[sid].copy()
            o["seq"] = seq
            seq += 1
            ordered.append(o)

        if len(ordered) < 2:
            skipped += 1
            continue

        # 5. Write JSON
        fname = f"{slug(name)}__{route_id}.json"
        path = os.path.join(OUT_DIR, fname)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "gtfs_route_id": route_id,
                    "route_name": name,
                    "representative_trip_id": rep_trip,
                    "stops": ordered,
                },
                f,
                indent=2,
            )

        index[name.strip().lower()] = fname
        written += 1

    # Write index
    with open(os.path.join(OUT_DIR, "_index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)

    print(f"Done. Wrote {written} stopmaps to ./{OUT_DIR}/, skipped {skipped}.")
    print("Index written to stopmaps/_index.json")

if __name__ == "__main__":
    main()
