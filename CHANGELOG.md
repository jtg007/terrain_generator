# Changelog

All notable changes to this project will be documented in this file.

## [0.9.12] - 2026-05-13
### Pipeline & Stability
- **Non-Fatal Validation:** Heightmap playability checks (connectivity and minimum width) are now non-fatal, allowing users to compile maps even if the generator detects potential lane issues.
- **Single-Attempt Generation:** Disabled the 5-attempt retry loop for procedural canyon generation to speed up the workflow and ensure user-selected seeds are strictly followed.

## [0.9.11] - 2026-05-12
### Pipeline & Refactoring
- **Smart Detail System (WIP):** Implemented an intelligent detail system for automatic texture-based grass emissions. Prop-based safe placement is still under development.
- **Modular Pipeline Architecture:** Completely refactored the VMF generation core. Extracted responsibilities into dedicated modules (`displacement_builder.py`, `entity_placer.py`, `skybox_manager.py`), entirely removing the `worldengine` dependency and obsolete legacy tools for a much cleaner, streamlined pipeline.

### Terrain & Rendering
- **Texture Rendering Fixes:** Resolved texture stretching on sheer cliff walls and fixed mismatched grass texture resolutions between adjacent tiles for a cohesive, seamless landscape.
- **Lighting & Entities:** Corrected an issue where global lighting (`light_environment`) and game info entities were improperly nested inside the map's `worldspawn`, ensuring lighting compiles correctly in-game.
- **Scenery Placement:** Fixed scenery prop spawning rules to respect strict slope and proximity thresholds.

### Editor Features
- **Tile Painting System (WIP):** Introduced a new tile paint mode, allowing precise material assignments to individual 16x16 displacement tiles on the grid. Replaced the old "Texture" brush mode with this more powerful tool.
- **UI Improvements:** Improved the sidebar layout so the shape config sliders now dynamically expand to fill the available vertical space, eliminating unnecessary scrolling.

## [0.9.10] - 2026-04-25
### Terrain & Pipeline
- Integrated entirely new Canyon Heightmap Generator replacing old FBM ridge noise.
- Canyons generate with domain-warped FBM and a 3-zone transfer function for natural plateaus, vertical walls, and flat canyon floors.
- Bypassed hydraulic erosion and 3x3 secondary smoothing passes during generation to preserve hard drop-offs on canyon walls.
- Mapped previous procedural parameters into new Canyon parameters: "Roughness" is now "Canyon Warping", "Erosion" is now "Edge Smoothing" (Gaussian box blur proxy).
- Repurposed "Canyon Steepness" to scale the transfer function threshold, creating steeper or smoother cliffs.
- Cleaned up Topology preset list down to just "Canyon" as the base foundation for future updates.

## [0.9.9] - 2026-04-24
### Terrain & Generation
- Fixed terrain generation so mountains can scale to the absolute maximum map height.
- Implemented canyon wall steepness slider to make steep terrain block vehicles.
- Decoupled skybox ceiling height from terrain max height to improve compiler optimization (VVIS).
- Automatically generate bounding `toolsclip` brushes against skybox walls to seal map when terrain is outside bounds.
- Added a Lane Elevation slider to control the base height of paths and lanes.

## [0.9.8] - 2026-04-24
### Highlights
- Universal Masking (Stencil): New global selection mask system to protect/specific areas
- Lane-Aware Terrain Shaping: Terrain near lanes now flatter and smoother
- Toolbar Redesign: Modern, context-aware two-level layout with tabs
- Invert Terrain: New button to flip topology
- Save/Open Projects: Full project persistence with compressed sculpting data
---
### Editor UX
- Redesigned toolbar into modern, context-aware layout with tabs (Terrain, Entities, Layout)
- Added "Open Project" and "Save Project" buttons to the sidebar
- Implemented "Dirty State" tracking with unsaved changes prompts
- Flat dark theme with minimalist icons and blue accent highlights
- Global actions (Undo, Redo, 3D View, Clear Map) permanently visible
- Contextual tools appear dynamically based on selected tab
- Mask actions contextual: Reset and Clear only in Mask mode

### Project Persistence
- New `.terrain` file format for full project serialization
- Preserves all config settings, custom nodes, lanes, and manual sculpting
- Optimized storage: Sculpting overlays are compressed using zlib/base64
- Robust loading: Implemented signal blocking and versioning for stability

### Preview & Sculpting Fixes
- Mask brush and flatten brush now work correctly
- Sculpt edits are highlighted, mask tint only shown when actively using
- Fixed toolbar layout on small windows
- Mask overlay no longer disappears when switching tools

### Terrain Masking, Sculpting & Shaping
- Universal Masking: Left-click to draw mask, right-click to remove mask
- Lane-Aware Terrain: Flatter terrain near lanes, increased variation in distant areas
- Ridged Multifractal: New algorithm for sharp ridges and roughness

## [0.9.5] - 2026-04-23
### Editor Features & Fixes
- Added a new "Flatten ▬" sculpt tool for easier base building
- Fixed an issue where digging holes wouldn't show up on the 2D heightmap (they are now visible as contours)
- Fixed the 3D view showing bases and resources flipped on the wrong side of the map

### Windows & Cross-Platform
- Fixed VBSP path resolution for non-default Steam libraries
- Fixed map output to use Documents folder in frozen builds

### 3D Preview
- Added interactive 3D terrain preview using pyqtgraph
- Added 3D markers for bases and resources
- Improved preview alignment with 3D world
- Added building model rendering (Imperial/NF barracks)

## [0.9.4] - 2026-04-21
### UI & Experience
- Fixed in-game minimap orientation to correctly show North at the top
- Synchronized the strategy editor with the 3D world for perfect 1:1 alignment
- Corrected the visual orientation of base and resource icons in the editor
- Added 'No Flags' option to settings and disabled capture points by default
- Improved GUI stability by preventing overlapping background tasks
- Added proactive layout validation for misplaced entities
- Standardized project output folder structure
- Increased height input limit to 999999 for taller terrain

### Terrain & Pipeline
- Fixed critical alignment bug: bases/resources spawn on flattened valleys
- Resolved displacement "diamond" distortion and visual seams
- Improved terrain sculpting logic and fixed mirroring issues
- Refined displacement normal calculations for smoother lighting
- Fixed coordinate mapping for editor/BSP alignment
- Fixed duplicate commanders and barracks appearing in maps
- Adjusted entity height offsets for better ground placement
- Raised map_overview camera height to minimum 1087 for better zoom
- Skybox wall height now calculated from terrain height for better fit
- Removed world coordinate limits for flexible skybox placement


## [0.9.3] - 2026-04-20
### UI & Pipeline
- Decoupled `Lane Node Radius` from `Base Clear Radius`
- Added `Lane Node Radius` slider to control strategic node size independently from terrain flattening
- Removed "Generate strategic lanes" checkbox (lanes are now controlled via node radius)
- Updated `MapPreviewWidget` to visually render the `Lane Node Radius` as a separate indicator for bases
- Updated terrain pipeline to correctly use `lane_node_radius` for playability mask calculations

## [0.9.2] - 2026-04-20
### UI & Sizing
- Added separate sliders for `Clear Radius` (base areas) and `Resource Clear` (resource nodes)
- `Clear Radius` now only controls base area flattening
- Added `Resource Clear` slider (default: 256) to independently control resource node clearing radius

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

### Strategic Layer
- Fixed base placement no longer re-routing or re-drawing strategic lanes
- `generate_strategic_layout()` now always uses default map anchors for lane generation
- Custom base positions still apply to base flattening and entity placement
- Removed unused imports in terrain_pipeline.py

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
