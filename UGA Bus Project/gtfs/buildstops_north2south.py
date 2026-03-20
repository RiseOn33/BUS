import csv, json
from collections import defaultdict, Counter

ROUTE_ID = "5749"  # North South (from your live feed)
OUTFILE = "north_south_stops.json"

# --- Load trips for this route ---
trip_ids = set()
with open("trips.txt", newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        if row.get("route_id") == ROUTE_ID:
            trip_ids.add(row["trip_id"])

if not trip_ids:
    raise SystemExit(f"No trips found for route_id={ROUTE_ID}. Check route_id in GTFS.")

# --- Load stop_times for those trips (keep one representative trip) ---
# Pick the most common stop_sequence pattern length as "representative"
trip_stopseq = defaultdict(list)  # trip_id -> list of (seq, stop_id)

with open("stop_times.txt", newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        tid = row["trip_id"]
        if tid not in trip_ids:
            continue
        seq = int(row["stop_sequence"])
        trip_stopseq[tid].append((seq, row["stop_id"]))

# Clean + sort
for tid in list(trip_stopseq.keys()):
    trip_stopseq[tid].sort(key=lambda x: x[0])

# Choose a representative trip: the modal number of stops (most common length)
lengths = Counter(len(v) for v in trip_stopseq.values() if v)
rep_len = lengths.most_common(1)[0][0]
rep_trip = next(t for t, v in trip_stopseq.items() if len(v) == rep_len)

ordered_stop_ids = [sid for _, sid in trip_stopseq[rep_trip]]

print(f"Found {len(trip_ids)} trips for route {ROUTE_ID}.")
print(f"Representative trip_id: {rep_trip} with {len(ordered_stop_ids)} stops.")

# --- Load stops.txt lookup ---
stops = {}
with open("stops.txt", newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        stops[row["stop_id"]] = {
            "stop_id": row["stop_id"],
            "name": row.get("stop_name", ""),
            "lat": float(row["stop_lat"]),
            "lon": float(row["stop_lon"]),
        }

# --- Build ordered stop list ---
ordered = []
for i, sid in enumerate(ordered_stop_ids, start=1):
    if sid not in stops:
        continue
    o = stops[sid].copy()
    o["seq"] = i
    ordered.append(o)

with open(OUTFILE, "w", encoding="utf-8") as f:
    json.dump(
        {
            "route_id": ROUTE_ID,
            "representative_trip_id": rep_trip,
            "stops": ordered,
        },
        f,
        indent=2,
    )

print(f"Wrote {len(ordered)} stops to {OUTFILE}.")
