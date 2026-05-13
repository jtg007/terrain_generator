# AGENTS.md - Terrain Generator

Guidelines for agentic coding agents working in this repository.

## Project Overview

Terrain generator for Source Engine (Valve games). Generates compile-safe displacement terrain VMF files from noise-based heightmaps using fractal Brownian motion (fBm), hydraulic erosion, and strategic lane generation. Python 3.14+ with numpy, Pillow, vmflib, PySide6, pyqtgraph, and PyOpenGL.

## Directory Structure

```
src/
  terrain_spec.py         # Data models (TerrainSpec, HeightGrid, TerrainCell, LayoutNode)
  terrain_pipeline.py     # Terrain pipeline (fBm + erosion + lanes + VMF prep)
  noise.py                # Seeded Perlin noise generator
  vmf_gen.py              # VMF generation (DisplacementVMF, PipelineSpec)
  ValveVMF.py             # Legacy VMF writing (manual serialization, mostly unused)
  config_model.py         # GUIConfigModel (GUI config dataclass with slider mapping)
  compat_utils.py         # scipy_zoom_equivalent (pure numpy bilinear upsampling)
  canyon_generator.py     # Gameplay-first canyon terrain (morphological ops, distance fields)
  detail_manager.py       # Smart detail density, auto_detail.vbsp generation
  displacement_builder.py # Displacement quantize, nodraw, terrain height sampling
  entity_placer.py        # Empires entity spawning (bases, resources, spawns, commanders)
  export_utils.py         # HeightGrid → PNG/VMF export, resource .txt generation
  layout_validator.py     # Entity placement validation (distances, bounds)
  material_manager.py     # Theme-based blend material selection (6 themes)
  project_utils.py        # Project file save/load (.terrain format, base64+zlib)
  qt_widgets.py           # WidePopupComboBox custom widget
  skybox_manager.py       # Skybox creation, safe skybox filtering, lighting entities
  steam_paths.py          # Cross-platform Steam/Empires path detection
tools/
  generate_vmf.py         # CLI from heightmap PNG → VMF
  generate_organic_vmf.py # CLI with full pipeline (fBm + erosion + lanes)
  compile_vmf.py          # Compile VMF to BSP using wine/VBSP
  terrain_generator.py    # GUI application (PySide6, 3391 lines)
  preview_widget.py       # 2D/3D heightmap preview with sculpting tools (3066 lines)
  editor_widget.py        # Layout/map editor widget (node/edge placement)
  verify_heightmap.py     # Heightmap verification utility
config/
  requirements.txt        # Python dependencies
  textures.json           # Theme-based texture definitions (6 themes, 1111 lines)
  skyboxes.json           # Skybox definitions
  config.json             # Default configuration
  config.py               # Config management module
  __init__.py             # Config package init
output/                   # Generated VMF, BSP, and resource files
docs/
  screenshots/            # GUI screenshots
materials/
  vmf_generator_assets/   # auto_detail.vbsp, blend .vmt files
map_rules.json            # Statistical rules from 28 Empires maps analyzed (104k lines)
```

## Commands

**CRITICAL:** Always use the project virtual environment at `venv/`. Never install packages system-wide.

### Activate Virtual Environment
```bash
source venv/bin/activate
```

Or prefix commands with `venv/bin/`:
```bash
venv/bin/ruff check src/ tools/
venv/bin/python tools/generate_vmf.py --test
```

### Install Dependencies
```bash
venv/bin/pip install -r config/requirements.txt
```

### Lint (ruff)
```bash
venv/bin/ruff check src/ tools/
```

### Type Check (mypy)
```bash
venv/bin/python -m mypy src/ tools/
```

### Run Pipeline Validation (default spec)
```bash
venv/bin/python -c "from src.terrain_spec import create_default_spec; from src.terrain_pipeline import run_pipeline; print(run_pipeline(create_default_spec()))"
```

### Verify Heightmaps (all presets)
```bash
venv/bin/python tools/verify_heightmap.py
```

### Generate Organic Terrain (fBm + erosion + lanes + VMF)
```bash
venv/bin/python tools/generate_organic_vmf.py  # defaults: ~32x32 tiles, 512 size, seed=12345
venv/bin/python tools/generate_organic_vmf.py --seed 42 --tiles-x 14 --tiles-y 14
venv/bin/python tools/generate_organic_vmf.py --tiles-x 20 --tiles-y 20 --seed 99
venv/bin/python tools/generate_organic_vmf.py --skip-erosion  # fast, no erosion
venv/bin/python tools/generate_organic_vmf.py --theme Desert --skybox empsky_sunset1
```

### Generate VMF from Heightmap PNG
```bash
venv/bin/python tools/generate_vmf.py path/to/heightmap.png
venv/bin/python tools/generate_vmf.py --test  # generates test heightmap
```

### Compile VMF to BSP
```bash
venv/bin/python tools/compile_vmf.py output/terrain.vmf
# BSP and VMF are copied to Empires directories automatically
```

### GUI Application
```bash
venv/bin/python tools/terrain_generator.py
```
Features:
- Interactive PySide6 GUI with 3-tab config (Main, Shape, Gameplay)
- Real-time 2D/3D heightmap preview with pyqtgraph
- Terrain sculpting (raise/lower/flatten/mask/texture paint/tile paint)
- Entity placement (bases, resource nodes, lane connections)
- Full pipeline generation (fBm + erosion + strategic lanes)
- Project save/load (.terrain format)
- Compile button to run VBSP and deploy to Empires directories

### Linux/macOS Launcher (terrain.sh)
For end users, use the smart launcher script instead of venv/bin/python directly:

```bash
./terrain.sh                    # Interactive menu (default)
./terrain.sh --gui              # Launch GUI mode
./terrain.sh --cli              # Interactive CLI preset selection
./terrain.sh --cli hills        # CLI with preset
./terrain.sh --cli custom --tiles-x 24  # Custom CLI options
./terrain.sh --compile          # Compile VMF to BSP
./terrain.sh --compile output/terrain.vmf  # Compile specific file
./terrain.sh --setup            # Force reinstall dependencies
./terrain.sh --help             # Show help
```

Features:
- Auto-creates `venv/` if missing (never writes to system Python)
- Auto-detects existing venv and reuses it
- Probes system for Python3, display, and Proton installations
- Interactive Proton selector for VBSP compilation
- Styled terminal UI with box drawing characters

**CLI Presets:** `flat`, `hills`, `rugged`, `competitive`, `mountain_pass`, `open_valley`, `island_hopping`

**Default map sizes:**
- Flat/Competitive: 16x16 tiles (8192x8192 units, 129x129 vertices with power=3)
- Hills/Rugged: 20x20 tiles (10240x10240 units, 161x161 vertices with power=3)

## Map Centering (CRITICAL)

**All maps MUST be centered around origin (0,0)**, not starting at X=0, Y=0.

### Why?
- Hammer coordinate limits: -16384 to +16384
- Starting at (0,0) causes East/North walls to exceed limits on large maps
- All real Empires Mod maps use negative coordinates (e.g., emp_arid_d: -15360 to 15360)

### Implementation
```python
map_width = tiles_x * tile_size
map_height = tiles_y * tile_size

origin_x = int(-map_width / 2)  # e.g., -8192 for 32x32 map
origin_y = int(-map_height / 2)  # e.g., -8192
map_center_x = 0.0
map_center_y = 0.0
```

This centering is applied in `config_model.py:make_spec()` and `export_utils.py:export_vmf()`.

### Base Placement
Bases are placed in opposite quadrants relative to (0,0):
```python
imp_base_x = int(origin_x + (map_width * 0.25))  # SW quadrant
imp_base_y = int(origin_y + (map_height * 0.25))
nf_base_x = int(origin_x + (map_width * 0.75))   # NE quadrant
nf_base_y = int(origin_y + (map_height * 0.75))
```

## Code Style

### General
- Python 3.14+ compatible
- No comments unless explaining complex logic
- 100 character line limit
- 4 space indentation (no tabs)
- Use `typing` module: `List`, `Tuple`, `Dict`, `Any`, `Optional` (not builtins)

### Imports (standard library → third-party → local)
```python
import math
import random
from typing import List, Tuple, Optional

import numpy as np
from PIL import Image

from src.terrain_spec import TerrainSpec, HeightGrid, ZoneType
from src.terrain_pipeline import run_pipeline
```

### Type Hints
- Use `List`, `Tuple`, `Dict`, `Any`, `Optional` from `typing`
- Use `str | Path` union syntax (Python 3.10+) for simple unions
- Use `np.float32`/`np.float64` for numpy arrays — prefer `np.float64` for erosion math
- Annotate all function parameters and return types
- dataclasses automatically provide types

### Naming Conventions
- **Variables/functions**: `snake_case` (e.g., `grid_row`, `generate_heights`)
- **Classes**: `PascalCase` (e.g., `TerrainSpec`, `HeightGrid`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `MAX_HEIGHT`, `DEFAULT_SEED`)
- **Private methods**: prefix with `_` (e.g., `_generate_permutation`)
- **Files**: `snake_case.py`

### Dataclasses
Use `@dataclass` for data models. Validate in `__post_init__`:
```python
from dataclasses import dataclass

@dataclass
class TerrainSpec:
    origin_x: int = 0
    size_x: int = 2048

    def __post_init__(self):
        if self.size_x <= 0:
            raise ValueError("size_x must be positive")
```

### Error Handling
- Use exceptions for invalid input (ValueError, TypeError)
- Raise early, validate in `__post_init__`
- Print warnings for non-fatal issues
- Return error lists from validation functions

### Numeric Precision
- Use `np.float64` for hydraulic erosion calculations (prevents overflow)
- **STRICT INTEGER MATH** for all displacement coordinates to prevent vmflib rotation bugs
- Quantization step as parameter, not hardcoded (default: 4)

### Grid Coordinate Convention
- `heights[r][c]` — row 0 = origin_y (min Y), col 0 = origin_x (min X)
- Grid iteration: `for r in range(rows): for c in range(cols):`

## terrian Textures (CRITICAL)

Empires Mod requires specific texture paths. **Never use Source Engine default textures** like `nature/grass_hires` - they don't exist in Empires.

The game uses a **theme-based material system** with 6 themes in `material_manager.py`:

| Theme | Primary Blend | Primary Cliff |
|---|---|---|
| Temperate | `common/nature/blend_grass_mountainwall_000` | `common/nature/mountain_wall_000` |
| Desert | `nature/desert/blend_sand_rock_002` | `nature/desert/desert_rock_001` |
| Snow | `nature/snow/blend_snow_rock_001` | `nature/snow/snow_mountain_wall_001` |
| Industrial | `common/nature/blend_grass_mud_003` | `common/nature/mountain_wall_000` |
| Wasteland | `nature/wasteland/blend_dirt_rock_001` | `nature/wasteland/wasteland_rock_001` |
| Generic | `common/terrain/blend_grass01a_dirt01a` | `common/nature/mountain_wall_000` |

**Skyboxes (safe Empires whitelist):**
- `empsky_day1`, `empsky_day2`
- `empsky_overcast1`, `empsky_overcast2`, `empsky_overcast3yellow`
- `empsky_sunset1`, `empsky_sunset2`

**CRITICAL skybox rule:**
- Use only the safe whitelist above; fallback should be deterministic (`empsky_overcast2`).
- GUI and CLI generation must pass an explicit skybox into `PipelineSpec`.

## Strategic Lane Generation (CRITICAL ARCHITECTURE)

The terrain generator uses a **gameplay-first lane system** rather than purely organic terrain. This ensures generated maps are playable for Empires Mod's RTS/FPS hybrid gameplay.

### Topologies (defined in `terrain_pipeline.py`)
- `central_gorge` — single lane through center canyon
- `valley` — two lanes flanking a central valley
- `two_lane` — classic two-lane with base at each end
- `island` — bases on separate landmasses with water between
- `classic_cross` — 4-way cross with base in each quadrant
- `peninsula` — one base on peninsula, one on mainland
- `archipelago` — multiple small landmasses
- `delta` — branching river delta layout
- `canyon` — deep canyon with sheer walls (bypasses erosion/smoothing)
- fallback — random if no topology matches

### Pipeline Flow (when `generate_lanes=True`)
1. `generate_strategic_layout()` creates `LayoutNode`s and `LayoutConnection`s based on topology
2. `generate_playability_mask()` creates a smoothstep distance field from lane paths
3. Heights are generated with fBm, then blended with the playability mask
4. Canyon topology uses `canyon_generator.generate_canyon_base()` instead

### Canyon Generator (`canyon_generator.py`)
- Gameplay-first: enforces minimum lane width via morphological closing
- Uses domain-warped noise + distance fields for organic canyon walls
- Validates lane connectivity via BFS
- Falls back to pure-noise canyons when morphological pass fails

## Displacement Generation Rules

**vmflib has bugs with negative coordinates and displacement data:** When creating Blocks with origins in negative world coordinates, vmflib guesses the displacement startposition incorrectly, causing the heightmap to rotate and tear seams. Additionally, the Normals class outputs integers instead of floats.

vmflib is installed via pip (`venv/lib/python*/site-packages/vmflib/`). The code still attempts `sys.path.insert(0, "tools/vmflib")` for backward compatibility but falls back to the installed package.

### Required Fixes

1. **Force strict integers for Block origins:**
   ```python
   floor_block = Block(
       Vertex(int(offset_x + tile_size / 2), int(offset_y + tile_size / 2), 0),
       (tile_size, tile_size, 16),
       material,
   )
   ```

2. **Override startposition (CRITICAL):**
   ```python
   disp_info = DispInfo(power, vertex_normals, height_distances)
   disp_info.startposition = f"[{offset_x} {offset_y} 0]"
   ```

3. **Add flags property (required):**
   ```python
   disp_info.flags = 0
   ```

4. **allowed_verts must all be "-1":**
   ```python
   disp_info.allowed_verts.properties.clear()
   for i in range(2**power + 1):
       disp_info.allowed_verts.properties[f"row{i}"] = "-1"
   ```

5. **Float normals (CRITICAL):**
   - vmflib's Normals class uses `%d` format (integers) but Source Engine requires floats
   - Fix in installed `vmflib/brush.py`: Change `%d %d %d` to `%s %s %s` in Normals.__init__
   - Current code uses vertical normals `(0.0, 0.0, 1.0)` for all vertices:
   ```python
   vertex_normals = []
   for iy in range(sample_size):
       row_normals = []
       for ix in range(sample_size):
           row_normals.append(Vertex(0.0, 0.0, 1.0))
       vertex_normals.append(row_normals)
   ```

6. **Working displacement orientation contract (validated in Hammer + in-game):**
   - Use `startposition = f"[{offset_x} {offset_y} 0]"` (tile min X/min Y corner).
   - Fill `distances` rows in increasing Y order (`iy = 0..N-1` maps to min→max world Y).
   - Do **not** force a custom `top().vaxis`; keep vmflib/Hammer default face axes.

## Coordinate System & Mapping (CRITICAL)

**The terrain generator uses a perfect, native Cartesian mapping system.**
All Python array indices map 1:1 to the 3D world coordinates. There is NO "Hammer flip" or mirroring in X or Y if the displacement rules above are followed.

### The Truth of Coordinates
- **Row 0, Col 0** (`Data_SW`) -> Maps to **South-West** in the 3D World `(-X, -Y)`
- **Row N-1, Col N-1** (`Data_NE`) -> Maps to **North-East** in the 3D World `(+X, +Y)`
- **Row N-1, Col 0** (`Data_NW`) -> Maps to **North-West** in the 3D World `(-X, +Y)`
- **Row 0, Col N-1** (`Data_SE`) -> Maps to **South-East** in the 3D World `(+X, -Y)`

**CRITICAL RULE: DO NOT INVERT COORDINATES**
Never invert `X` or `Y` when placing entities (e.g. `imp_base_x = -custom_x`).
Because the procedural terrain (fBm noise + erosion) matches the Cartesian world exactly, inverting coordinates will cause entities to spawn on mountains instead of their flattened valley patches.

### Minimap Orientation
The Source Engine `emp_info_map_overview` entity reads `min_bounds_y` as the **TOP** of the image, not the bottom.
To ensure the minimap is oriented correctly (North = Up), the bounds must be swapped in the resource `.txt` script:
```text
"min_bounds_y"  "{origin_y + map_height}"  // Top of image = North (+max)
"max_bounds_y"  "{origin_y}"               // Bottom of image = South (-max)
```
Do NOT use `np.flipud` when generating the heightmap PNG, but DO use `Image.FLIP_TOP_BOTTOM` when exporting the VTF.

## Pipeline Steps

Pipeline steps return modified objects (functional style). The actual steps vary by topology:

1. **Generate vertex grid** → `HeightGrid`
2a. **Generate strategic layout** (if `generate_lanes=True`): nodes + connections per topology
2b. **Generate playability mask**: smoothstep distance field from lane paths
2c. **Generate heights**: fBm (base + ridge + detail layers) blended with playability mask, or flat for manual mode. Canyon topology uses `canyon_generator.generate_canyon_base()`.
2d. **Pre-stamp base areas**: flatten base zones with soft blending
3. **Simulate hydraulic erosion** (BYPASSED for Canyon topology; optional skip with `--skip-erosion`)
4. **Calculate slopes** (central differences, stored in `grid.slopes`)
5. **Smooth heights** (BYPASSED for Canyon topology; 3x3 averaging kernel for others)
6. **Clamp slope** (adjacent vertex max difference; canyon uses `max_slope_step=99999`)
7. **Quantize heights** (round to step multiples — required for VBSP)
7.5. **Feather mask edges** (if `global_selection_mask` present)
7.6. **Final global slope clamp** (without mask, for seam safety)
8. **Build cells** (shared vertex grid from tiles)
9. **Validate seams** (check adjacency match)
10. **Build underlay** (single brush below terrain)
11. **Export minimap** (if `map_name` and `output_dir` provided)

## Key Constraints

- **displacement_power**: Must be **2 or 3** (power 4 crashes server physics)
- **cell_size**: Must divide `size_x`/`size_y` evenly
- **height quantization**: 1 = finest; higher = coarser steps (default: 4)
- **max_slope_step**: Max height difference between adjacent vertices (recommended: 64; canyon: 99999)
- **Map centering**: Always center around (0,0), not origin at (0,0)
- **Topology-specific**: Canyon bypasses erosion and smoothing; other topologies use full pipeline

## VBSP Compiler Rules

**Failure to follow these causes catastrophic compile errors ("17 solids not loaded", map leaks, VBSP crashes).**

### Compiling with wine
VBSP requires specific argument ordering and directory structure:
```python
cmd = ["wine", "vbsp.exe", "-game", "../empires", vmf_name]
```

### Geometry & Format
- KeyValue text format with nested `{}`. No unescaped quotes in values.
- Every brush MUST be 100% mathematically convex.
- **Floats**: Format to exactly 6 decimal places (`0.000000`).
- **Booleans**: Use `"0"` or `"1"`.
- **Vertices**: Space-separated `"X Y Z"`.

### Displacements (dispinfo)
- Vertex count: $(2^p + 1)^2$. Power must be 2 or 3.
- `allowed_verts` must always be `"-1"` for all rows.
- Seam edges must be vertex-snapped exactly (prevents black lightmaps).
- **startposition**: Must be explicitly set to `[X Y 0]` to override vmflib bugs.
- **flags**: Must be set to `0`.
- **normals**: Must be float format, not integers.

### VBSP Tolerances
- **DIST_EPSILON**: 0.03125 (1/32) engine units. Deviations destroy brushes.
- **Rounding**: Use `math.floor()` / `math.ceil()` — not Python's default `round()` which causes micro-gaps on large grids.

### Skybox (CRITICAL)
- Inner faces MUST perfectly touch terrain bounds. No gaps, no overlap.
- **Must use origin-centered coordinates** so walls stay within ±16384 Hammer limits.
- Side wall sections must span the same XY extent as floor/ceiling (`origin - thickness` to `end + thickness`) to avoid corner leaks.
- Use integer-aligned wall Z bounds/centers (no `.5` offsets) to avoid micro seams.
- Floor at z=-16 to -80. Ceiling at least 1087 units above max terrain (default: 4096).
- Skybox walls/floor/ceiling are split into max 2048-unit sections to avoid giant brushes (see `skybox_manager.py`).

## Compiling & Deployment

### Compile Script (tools/compile_vmf.py)
The compile script handles:
1. Copying VMF to Empires bin directory
2. Running VBSP with correct arguments
3. Copying BSP/VMF to Empires directories:
   - **BSP (primary)**: `.../Empires/empires/maps/<mapname>.bsp`
   - **BSP (download mirror)**: `.../Empires/empires/download/maps/<mapname>.bsp`
   - **VMF**: `.../Empires/empires/maps/prefabs/<mapname>.vmf`
   - **Resource .txt**: `.../Empires/empires/resource/maps/<mapname>.txt`
   - **Minimap VMT/VTF**: `.../Empires/empires/materials/maps/`

**CRITICAL deployment rule:**
- Always update BSP in both `empires/maps/` and `empires/download/maps/`.

### Empires File Paths
```
SteamLibrary/steamapps/common/Empires/
├── bin/                    # VBSP and other compile tools
│   └── vbsp.exe
└── empires/
    ├── maps/               # Runtime map loads + prefabs subdir
    │   ├── <mapname>.bsp   # Primary BSP location
    │   └── prefabs/        # VMF source files go here
    ├── download/maps/      # Compiled BSP files go here
    ├── resource/maps/      # Overview .txt scripts
    └── materials/          # Game materials
```

## Architecture: Key Modules

### `terrain_spec.py` — Data Models
- `ZoneType`: Enum-like constants (`BASE`, `MAIN_LANE`, `SIDE_ROUTE`, etc.)
- `LayoutNode`: Position, radius, type for strategic lane generation
- `LayoutConnection`: Edge between nodes with width and path_points
- `TerrainSpec`: Full generation spec (40+ fields including topology, canyon params, theme, custom resources/layout)
- `HeightGrid`: Grid with heights, slopes, normals, playability_mask, global_selection_mask
- `TerrainCell`: Individual displacement tile with position, size, power, distances
- `UnderlayBrush`: Single brush below all terrain
- `create_default_spec()` factory function

### `terrain_pipeline.py` — Pipeline Orchestrator (2357 lines)
Main orchestrator with topology-aware branching. Key functions:
- `generate_vertex_grid()` / `generate_heights()` / `load_custom_heights()`
- `generate_strategic_layout()` (10+ topology generators)
- `generate_playability_mask()` (smoothstep distance field)
- `simulate_hydraulic_erosion()` (droplet-based, optionally uses `Numba` JIT compilation via `_erosion_kernel`)
- `calculate_slopes()` / `smooth_heights()` / `clamp_slope()` / `quantize_heights()`
- `flatten_base_areas()` / `feather_mask_edges()`
- `build_cells()` / `validate_seams()` / `build_underlay()`
- `export_minimap()` / `slope_to_alpha()` / `get_cell_alphas()`
- `apply_pipeline_for_preview()` (lightweight version for GUI preview)
- `run_pipeline()` (full orchestrator with all 11+ steps)

### `vmf_gen.py` — VMF Output (1390 lines)
- `PipelineSpec` dataclass (35+ fields: map_name, theme, entity flags, custom positions, etc.)
- `DisplacementVMF` class: loads heightmap PNG, generates tile-based VMF with alpha blending, per-tile zone scoring, hero prop spawning, smart details
- Uses vmflib for VMF construction with all displacement fixes applied
- Imports from `entity_placer`, `skybox_manager`, `material_manager`, `displacement_builder`

### `entity_placer.py` — Empires Entity Spawning (731 lines)
Data-driven entity placement using map_rules.json statistics:
- `spawn_base_entities_enhanced()`: Bases, buildings, commander, vehicle spawns
- `spawn_resource_nodes_enhanced()`: Resource points + prop pairs with smoke stacks
- `spawn_player_spawn_points()`: 4 points around each base
- `spawn_capture_points()`: Capture points with cap_model entites
- `spawn_info_nodes()`: Navigation mesh nodes (required to prevent player timeout)
- `spawn_required_entities_enhanced()`: `emp_info_params`, `emp_info_map_overview`
- All entities clamped to map bounds with 64-unit margin

### `skybox_manager.py` — Skybox & Lighting (373 lines)
- `choose_safe_skybox()`: Filters against SAFE_EMPIRES_SKYBOXES whitelist
- `generate_skybox()`: Creates skybox walls/floor/ceiling split into max 2048-unit sections
- `spawn_lighting()`: light_environment, env_sun, env_tonemap_controller, logic_auto

### `canyon_generator.py` — Canyon Terrain (474 lines)
- `max_filter_2d()` / `min_filter_2d()`: Morphological operations via sliding_window_view
- `enforce_minimum_width()`: Ensures minimum lane width for gameplay
- `validate_connectivity()`: BFS-based lane connectivity check
- `generate_canyon_base()`: Main entry point with domain-warped noise

### `steam_paths.py` — Path Detection (246 lines)
Cross-platform Steam library detection:
- Windows: registry + VDF parsing
- Linux: common Steam library paths
- `find_empires_path()`, `find_empires_bin()`, `find_vbsp()`

### `material_manager.py` — Theme Materials (119 lines)
- `THEME_BLEND_MATERIAL` dict mapping 6 themes to their materials
- `choose_compile_safe_material()`: Filters unsafe materials (tree, water, wall, etc.)
- `is_displacement_floor_material()` / `is_blend_floor_material()`: Safety checks

### `project_utils.py` — Project Files (201 lines)
- Save/load `.terrain` files: JSON with zlib-compressed base64 numpy arrays
- Stores: nodes, connections, resources, base positions, sculpting data
- Current version: 1

### `config_model.py` — GUI Config (289 lines)
- `GUIConfigModel`: Bridges GUI slider values (0-1) to physical TerrainSpec ranges
- Constants: `MAX_MAP_WORLD_SIZE = 32640`, `MAX_MAP_DISPINFO = 2048`
- `validate()`: Checks tile counts, power, map size, dispinfo count
- `make_spec()`: Creates centered TerrainSpec from GUI settings

## Empires Mod Specific

- **Displacement power**: Max **3** (power 4 crashes server physics with multi-wheeled vehicles)
- **Skybox ceiling**: At least 1087 units above max terrain height (default: 4096)
- **Required entities**: `emp_info_params`, `emp_info_map_overview`, `info_node` (without this, players timeout)
- Required entities must be spawned even when `--no-enhanced` mode is used.
- **Playable spawn system**: For playable maps, use enhanced spawning. `--no-enhanced` is primarily for compile/debug maps.
- **Player spawn classname (CRITICAL)**: Use `emp_info_player_Imp` and `emp_info_player_NF` (mixed case). Lowercase versions cause players to join teams but not be able to spawn.
- **Capture model entity (CRITICAL)**: `emp_cap_model` must include a valid `model` key and `angles`.
- **Resource nodes**: Spawn as pairs (`emp_resource_point` + `emp_resource_point_prop`). Required keyvalues: `ResourcesSecond` (e.g., "3"), `MaxResources` (e.g., "-1" for infinite).
- **Resource script** (`<map_name>.txt`): Bounds use origin-centered coordinates with swapped Y bounds for correct minimap orientation.
- **Weather**: Never one huge `func_precipitation` brush — split into small boxes or it crashes the engine
- **AI Blocker**: Place `func_nav_blocker` on steep terrain, otherwise AI hangs
- **VMF order**: `versioninfo` → `visgroups` → `viewsettings` → `world` → `entity` → `hidden` → `cameras` → `cordon`
- **Entity bounds**: All entities must be within map bounds (clamp positions with 64-unit margin)

## Implementation Notes

### Heightmap Resolution
The terrain pipeline generates a grid at spec resolution, but entity spawning requires heightmap sampling at displacement resolution. Always upsample using `src.compat_utils.scipy_zoom_equivalent` before passing to VMF generation.

### Base Terrain Clearing
Bases should NOT be deeply flattened — real Empires maps have natural terrain variation near bases. Use a small gentle clearing radius (128-384 units) with soft blending toward average terrain height, not zero.

### Terrain Height Sampling for Entities
When placing entities that need terrain height (resource nodes, spawn points, commanders):
1. Pass `terrain_actual_max` from the pipeline (`grid.max_height()`) to `PipelineSpec`
2. Use `heightmap[py, px] / 255.0 * terrain_actual_max` to get world height
3. Do NOT multiply by `height_scale` twice — the max is already in world units
4. **Commander height**: Sample terrain at the actual commander position, not the barracks origin.

### Entity Position Clamping
Resource nodes and props can spawn outside map bounds. Always clamp positions:
```python
map_min_x = origin_x + 64
map_max_x = origin_x + map_width - 64
map_min_y = origin_y + 64
map_max_y = origin_y + map_height - 64

node_x = max(map_min_x, min(map_max_x, node_x))
node_y = max(map_min_y, min(map_max_y, node_y))
```

### `emp_info_params` Gameplay Defaults (CRITICAL)
Do not leave `emp_info_params` with only classname/origin. Missing team resources/reinforcements can cause instant round-end and lock team changes/spectator join.

Use safe defaults:
```text
Skin = 1
NFRes = 400
NFReinf = 400
ImpRes = 400
ImpReinf = 400
eng_restrict_NF = 0
eng_restrict_Imp = 0
AutoResearch = 0
```

**IMPORTANT**: The `NFRes`, `NFReinf`, `ImpRes`, `ImpReinf` keys are case-sensitive.

### "Cannot convert" Errors
This error occurs when displacement normals are in integer format instead of float. Ensure:
1. Normals are formatted as floats (even if using vertical normals `(0.0, 0.0, 1.0)`)
2. vmflib's Normals class uses `%s` format instead of `%d` (patch installed vmflib if needed)
3. Vertex objects contain float values

A small number of `make_triangles:calc_triangle_representation: Cannot convert` warnings can still appear even with correct float normals — treat as non-fatal if VBSP finishes and displacements look correct.

### Project Files (.terrain format)
Project files are JSON with base64+zlib-encoded numpy arrays:
- `height_overlay`: terrain sculpting overlay
- `global_selection_mask`: selected region mask
- `texture_overlay`: per-tile texture assignments
- `tile_overlay`: tile painting data
Save with `project_utils.save_project()`, load with `project_utils.load_project()`.

### GUI Output Files
The GUI generates the following in a versioned output subdirectory:
- `mapsrc/<name>.vmf` - VMF source file
- `mapsrc/<name>_temp.png` - Temporary heightmap (deleted after VMF generation)
- `resource/maps/<name>.txt` - Resource script with map bounds
- `materials/maps/<name>.vmt` / `<name>.vtf` - Minimap material
- `materials/vmf_generator_assets/` - Detail VMT/VBSP files

## Building Windows Executable

### Prerequisites
- Python 3.10+ installed
- Windows with Empires Mod installed via Steam

### Build Steps
```bash
pip install -r config/requirements.txt
python build_exe.py            # onefile mode (default)
python build_exe.py --onedir   # directory mode
```

The executable will be in `dist/TerrainGenerator.exe`.

### Manual PyInstaller Build
```bash
pip install pyinstaller
pyinstaller terrain_generator.spec --onefile --windowed
```

### Cross-Platform Notes
- The code automatically detects Windows vs Linux via `steam_paths.is_windows()`
- On Windows: VBSP runs directly
- On Linux: VBSP runs via Wine (with interactive Proton selector in terrain.sh)
- Steam Library paths are detected for both platforms via registry/VDF parsing

### Distribution
- `dist/TerrainGenerator.exe` - Main executable
- Include Empires VBSP.exe alongside if users need to compile
