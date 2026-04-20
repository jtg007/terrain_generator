# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

## [0.9.2] - 2026-04-20
### UI & Sizing
- Added `Tile Size` control in `MAP DIMENSIONS` and wired it through generation and preview
- Added `Target Size` + `Auto Tile Size` calculator with safe clamping and 64-unit snapping
- Added `Size Help` button with map-size and displacement-limit guidance
- Added live map info line with world size and displacement usage
- Updated preview grid spacing to follow current tile size

### Compile Safety
- Added compile-safe map size validation to block borderline world-bound maps before compile
- Added displacement-count validation (`Tiles X * Tiles Y <= 2048`) with clear GUI errors
- Added compile-safe coordinate guard in VMF generation to avoid `HashVec`/bounds edge cases
- Fixed skybox generation at world edges to avoid out-of-range brush coordinates
- Improved compile failure tips for bounds and `HashVec` errors
- Added automatic nodetail retry when compile hits `Too many detail props emitted`
- Added nodetail material override during retry to reduce detail-prop overflow risk

### Terrain & Topology
- Updated `Clear Radius` behavior: at `0`, base flattening is disabled; above `0`, flattening works as expected
- Preserved topology shaping (chokepoints, vehicle areas, lanes) when `Clear Radius = 0`
- Added topology option: `Archipelago` (multiple small islands with connections)
- Added topology option: `Delta` (branching paths from center)
- Added topology option: `Peninsula` (winding path with chokepoints)

## [0.9.1] - 2026-04-20
### UI
- Added custom output folder picker with toggle for auto-copy
- Added manual `Use nodetail texture` toggle in Settings
- Renamed `SPAWN SETTINGS` to `SETTINGS` in GUI

### Compile
- Added nodetail setting persistence to config
- Changed compile failure output to show a nodetail tip
- Fixed VBSP compile error by using `NODRAW` for non-displacement faces
- Removed automatic nodetail switching for large maps

### Terrain
- Fixed island topology height inversion
- Removed unused center flatten sliders from UI and models
