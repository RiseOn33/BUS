# BUS

This repo contains experiments for UGA bus tracking, with current focus on a live North South route display that maps Passio bus positions onto a custom trigger-point image.

## Current Goal

Build two live display versions for the North South route:
- a `full map` version using the fully outlined reference image
- a `segmented map` version using the reduced reference image

Both versions should:
- poll live bus data from Passio
- match each active bus to the nearest valid trigger point
- show the bus as an orange square on the custom map
- preserve named stops and intermediate route positions

## Current Structure

- `UGA Bus Project/north2south demo/legacy_prototypes`
  - older terminal and Flask prototypes
- `UGA Bus Project/north2south demo/live_trigger_map`
  - current image-based map work
- `UGA Bus Project/north2south demo/map_references`
  - source reference images

## Work Needed

### 1. Trigger-Point Characterization

For each map version:
- define the route points in exact travel order
- include both named stops and intermediate trigger dots
- identify dense areas that need more points
- identify ambiguous areas where nearest-point matching can fail

High-priority ambiguous areas:
- ACC loop
- Tate / MLC / Memorial / Instructional Plaza cluster
- Coliseum eastbound vs westbound area
- Driftmier and Coverdell northbound vs southbound pairs
- Lot E23 turnaround

### 2. Trigger Dataset Refinement

For each point in the trigger JSON files:
- verify `label`
- verify `type` (`stop` or `intermediate`)
- verify `lat` and `lon`
- verify image `x` and `y`

Files:
- `UGA Bus Project/north2south demo/live_trigger_map/trigger_points.full.json`
- `UGA Bus Project/north2south demo/live_trigger_map/trigger_points.segmented.json`

### 3. Matching Logic Improvements

Current matching is nearest-point based. It still needs:
- route-sequence awareness
- previous-position memory per bus
- reduced snapping across nearby parallel path sections
- better handling of loops and turnarounds
- optional smoothing or interpolation between updates

### 4. Display Accuracy Improvements

To get closer to PassioGo accuracy:
- add more intermediate trigger points
- use denser route characterization on curves and clusters
- calibrate visual point placement against the reference image
- compare live display output against PassioGo screenshots

### 5. UI Work

The live trigger map UI should support:
- full map view
- segmented map view
- clear bus-to-point highlighting
- readable labels for active buses
- easy visual debugging of incorrect trigger placement

## Parallel Work Split

User can help by:
- listing trigger dots in route order
- marking ambiguous map sections
- deciding where dense vs sparse trigger coverage is needed
- giving visual correction notes for stop and dot placement
- comparing our display to PassioGo and reporting mismatches

Codex can help by:
- structuring JSON trigger datasets
- improving bus matching logic
- refining the live map UI
- building calibration helpers
- updating project organization and documentation

## Immediate Next Steps

1. Choose whether `full` or `segmented` is the priority calibration target.
2. Finish route-order characterization for that map.
3. Densify trigger points in ambiguous sections.
4. Improve matching logic to follow route sequence instead of raw nearest-point only.
5. Calibrate `x,y` positions until the orange squares land correctly on the image.
