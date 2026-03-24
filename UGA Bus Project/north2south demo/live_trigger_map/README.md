# North South Live Trigger Map

This folder is the new workspace for the image-based North South bus map.

Goal:
- use one reference image as the visual map
- define named stop points and intermediate trigger points on top of that image
- poll the live Passio feed
- assign each active bus to the nearest trigger point
- render that trigger point as an orange square in the browser

Files:
- `app.py`: Flask backend and bus-to-trigger matching logic for both map versions
- `index.html`: version chooser page
- `map_view.html`: shared live map UI used by both routes
- `trigger_points.full.json`: starter trigger-point dataset for the full reference image
- `trigger_points.segmented.json`: starter trigger-point dataset for the segmented reference image

Current status:
- both full-map and segmented-map views are scaffolded
- both versions use the same live feed and separate trigger-point datasets
- trigger points are seeded from route stop coordinates
- image pixel positions still need manual calibration for exact visual placement on the reference image
