# AGENTS.md - Terrain Generator

Guidelines for agentic coding agents working in this repository.

## Project Overview

Terrain generator for Source Engine (Valve games). Generates compile-safe displacement terrain VMF files from noise-based heightmaps using fractal Brownian motion (fBm) and hydraulic erosion. Python 3.14+ with numpy, Pillow, and vmflib.

## Directory Structure

```
src/
  vmf_gen.py          # VMF generation (DisplacementVMF, PipelineSpec)
  noise.py            # Seeded Perlin noise generator
  terrain_spec.py     # Data models (TerrainSpec, HeightGrid, TerrainCell)
  terrain_pipeline.py # 10-step terrain pipeline (fBm + erosion + VMF prep)
  config_model.py     # GUIConfigModel (GUI config dataclass)
  ValveVMF.py        # VMF writing with alpha blend support
  vmf_writer.py      # ValveVMFWriter with slope-to-alpha conversion
tools/
  generate_vmf.py           # CLI from heightmap PNG → VMF
  generate_organic_vmf.py   # CLI with full pipeline (fBm + erosion)
  compile_vmf.py           # Compile VMF to BSP using wine
  terrain_gen.py            # Heightmap generator using WorldEngine
  terrain_generator.py      # GUI application (PySide6)
  vmflib/                  # VMF library (third-party, patched)
map_dataset/                # Reference VMF files for analysis
config/
  requirements.txt    # Python dependencies
  presets.json        # Terrain presets with tile sizes
  textures.json       # Texture references
output/              # Generated VMF, BSP, and resource files
docs/                # Reference VMFs
legacy/              # Old/outdated code
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

### Run Pipeline Validation
```bash
venv/bin/python -c "from src.terrain_spec import create_default_spec; from src.terrain_pipeline import run_pipeline; print(run_pipeline(create_default_spec()))"
```

### Generate Organic Terrain (fBm + erosion + VMF)
```bash
venv/bin/python tools/generate_organic_vmf.py  # defaults: ~32x32 tiles, 512 size, seed=12345
venv/bin/python tools/generate_organic_vmf.py --seed 42 --tiles-x 14 --tiles-y 14
venv/bin/python tools/generate_organic_vmf.py --tiles-x 20 --tiles-y 20 --seed 99  # Large map (max practical)
venv/bin/python tools/generate_organic_vmf.py --skip-erosion  # fast, no erosion
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
- Interactive PySide6 GUI with preset selection (Flat, Hills, Rugged, Competitive)
- Real-time configuration (seed, tiles, height scale, roughness, erosion)
- Generate VMF files saved to `output/` directory
- Compile button to run VBSP and deploy to Empires directories

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

### Base Placement
Bases are placed in opposite quadrants relative to (0,0):
```python
imp_base_x = int(origin_x + (map_width * 0.25))  # SW quadrant
imp_base_y = int(origin_y + (map_height * 0.25))
nf_base_x = int(origin_x + (map_width * 0.75))   # NE quadrant
nf_base_y = int(origin_y + (map_height * 0.75))
```

## Code Style

### Terrain Textures (CRITICAL)
Empires Mod requires specific texture paths. **Never use Source Engine default textures** like `nature/grass_hires` - they don't exist in Empires.

**Correct texture paths (from extracted materials):**
```
common/nature/blend_grass_mountainwall_000
common/nature/blend_grass_mud_003
common/terrain/blend_grass01a_dirt01a
nature/terrain/blend_grass1_dirt1
```

Available blend textures from `config/textures.json` include:
- `common/nature/blend_grass_mountainwall_000` - Grass/mountain blend
- `common/nature/blend_grass_mud_003` - Grass/mud blend
- `common/terrain/blend_grass01a_dirt01a` - Grass/dirt blend
- `common/terrain/blend_grass01a_dirt01a_nodetail` - Grass/dirt (no detail)
- `nature/terrain/blend_grass1_dirt1` - Grass/dirt terrain
- `nature/terrain/blend_grass1_rock1` - Grass/rock terrain

Using non-existent textures will cause the map to crash on load.

**Skyboxes (safe Empires whitelist):**
- `empsky_day1`, `empsky_day2`, `empsky_day3`
- `empsky_overcast1`, `empsky_overcast2`, `empsky_overcast3yellow`
- `empsky_sunset1`, `empsky_sunset2`

**CRITICAL skybox rule:**
- Do **not** select random skyboxes from `map_rules.json` (`lighting_environment.typical_skyboxes` contains non-Empires entries).
- Use only the safe whitelist above; fallback should be deterministic (`empsky_overcast2`).
- GUI and CLI generation must pass an explicit skybox into `PipelineSpec`.

### General
- Python 3.14+ compatible
- No comments unless explaining complex logic
- 100 character line limit
- 4 space indentation (no tabs)

### Imports (standard library → third-party → local)
```python
import math
import random
from typing import List, Tuple

import numpy as np
from PIL import Image

from terrain_spec import TerrainSpec, HeightGrid
from terrain_pipeline import run_pipeline
```

### Type Hints
- Use `List`, `Tuple`, `Dict`, `Any`, `Optional` from `typing` (not builtins)
- Use `np.float32`/`np.float64` for numpy arrays — prefer `np.float64` for erosion math to avoid overflow
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
- Quantization step as parameter, not hardcoded

### Grid Coordinate Convention
- `heights[r][c]` — row 0 = origin_y (min Y), col 0 = origin_x (min X)
- Grid iteration: `for r in range(rows): for c in range(cols):`

## Displacement Generation Rules

**vmflib has bugs with negative coordinates and displacement data:** When creating Blocks with origins in negative world coordinates, vmflib guesses the displacement startposition incorrectly, causing the heightmap to rotate and tear seams. Additionally, the Normals class outputs integers instead of floats.

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

5. **Float normals (CRITICAL - was causing "Cannot convert" errors):**
   - vmflib's Normals class uses `%d` format (integers) but Source Engine requires floats
   - Working reference VMs have normals like `"0.0 0.0 -0.99999994"`
   - Fix in `vmflib/brush.py`: Change `%d %d %d` to `%s %s %s` in Normals.__init__
   - Current code uses vertical normals `(0.0, 0.0, 1.0)` for all vertices (no sideways pulling):
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
   - This combination fixed broken/rotated displacement tiles and checkerboard seam artifacts.

## Pipeline Steps

Pipeline steps return modified objects (functional style):
1. Generate vertex grid → `HeightGrid`
2. Generate heights (fBm with base, ridge, detail layers + falloff)
3. Simulate hydraulic erosion (droplet-based)
4. Calculate slopes (central differences, stored in `grid.slopes`)
5. Smooth heights (3x3 averaging kernel)
6. Clamp slope (adjacent vertex max difference)
7. Quantize heights (round to step multiples — required for VBSP)
8. Build cells (shared vertex grid)
9. Validate seams
10. Build underlay

## Key Constraints

- **displacement_power**: Must be 2, 3, or 4 (5×5, 9×9, 17×17 vertices per tile)
- **cell_size**: Must divide `size_x`/`size_y` evenly
- **height quantization**: 1 = finest; higher = coarser steps
- **max_slope_step**: Max height difference between adjacent vertices (recommended: 64)
- **Map centering**: Always center around (0,0), not origin (0,0)

## GUI Configuration

### GUIConfigModel (src/config_model.py)
The `GUIConfigModel` dataclass bridges GUI inputs to `TerrainSpec`:

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `seed` | int | 12345 | Random seed for noise generation |
| `tiles_x` | int | 16 | Number of displacement tiles in X |
| `tiles_y` | int | 16 | Number of displacement tiles in Y |
| `cell_size` | int | 512 | World units per tile |
| `displacement_power` | int | 3 | Vertices per tile edge (9x9 for power 3) |
| `roughness` | float | 0.5 | Maps to noise octaves (1-8) |
| `erosion_strength` | float | 0.5 | Maps to erosion iterations (0-100000) |
| `height_scale` | int | 2048 | Maximum terrain height in world units |

### Presets (config/presets.json)
Each preset defines terrain characteristics and map size:

```json
{
  "presets": {
    "flat": {
      "tiles_x": 16, "tiles_y": 16,
      "roughness": 0.1, "erosion_strength": 0.05,
      "height_scale": 512
    },
    "hills": {
      "tiles_x": 20, "tiles_y": 20,
      "roughness": 0.4, "erosion_strength": 0.3,
      "height_scale": 1536
    },
    "rugged": {
      "tiles_x": 20, "tiles_y": 20,
      "roughness": 0.7, "erosion_strength": 0.6,
      "height_scale": 2560
    },
    "competitive": {
      "tiles_x": 16, "tiles_y": 16,
      "roughness": 0.3, "erosion_strength": 0.2,
      "height_scale": 1024
    }
  }
}
```

**Important**: All presets MUST include `tiles_x` and `tiles_y` to produce properly-sized maps.

## VBSP Compiler Rules

**Failure to follow these causes catastrophic compile errors ("17 solids not loaded", map leaks, VBSP crashes).**

### Compiling with wine
VBSP requires specific argument ordering and directory structure:
```python
# Run from Empires bin directory
cmd = ["wine", "vbsp.exe", "-game", "../empires", vmf_name]
# Note: -game must come BEFORE the VMF filename
```

### Geometry & Format
- KeyValue text format with nested `{}`. No unescaped quotes in values.
- Every brush MUST be 100% mathematically convex.
- **Floats**: Format to exactly 6 decimal places (`0.000000`).
- **Booleans**: Use `"0"` or `"1"`.
- **Vertices**: Space-separated `"X Y Z"`.

### Displacements (dispinfo)
- Vertex count: $(2^p + 1)^2$. Power must be 2, 3, or 4.
- `allowed_verts` must always be `"−1"` for all rows.
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
- Floor at z=-16 to -80. Ceiling at least 1087 units above max terrain.
- Example centered 16384×16384 map:
  - Floor: X: -8224 to 8192, Y: -8224 to 8192, Z: -80 to -16
  - West Wall: X: -8224 to -8160, Y: -8192 to 8192, Z: -16 to 1300
  - East Wall: X: 8160 to 8224, Y: -8192 to 8192, Z: -16 to 1300

## Compiling & Deployment

### Compile Script (tools/compile_vmf.py)
The compile script handles:
1. Copying VMF to Empires bin directory
2. Running VBSP with correct arguments
3. Copying BSP/VMF to Empires directories:
   - **BSP (primary)**: `.../Empires/empires/maps/<mapname>.bsp`
   - **BSP (download mirror)**: `.../Empires/empires/download/maps/<mapname>.bsp`
   - **VMF**: `.../Empires/empires/maps/prefabs/<mapname>.vmf`

**CRITICAL deployment rule:**
- Always update BSP in both `empires/maps/` and `empires/download/maps/`.
- If only `download/maps` is updated, the game may still load an older BSP from `empires/maps` and appear to "still crash".

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

## map_rules.json Structure

Learned rules from analyzing Empires Mod maps (28 maps analyzed):

```json
{
  "meta": { "maps_analyzed": 28 },
  "map_dimensions": {
    "map_bbox": { ... },        // Full technical VMF extent
    "playfield_bbox": { ... }   // Gameplay-anchored area with padding
  },
  "base_layout": {
    "separation": { "avg": 24195.47 },  // Base-to-base distance
    "nf_offset_from_center": { "dist_2d": { "avg": 12476 } },
    "imp_offset_from_center": { "dist_2d": { "avg": 12444 } }
  },
  "entity_orientations": {
    "nf_commander": { "circular_mean": 1.8 },
    "imp_commander": { "circular_mean": 359.8 }
  },
  "spawn_system": {
    "spawn_point_frequency_by_type": {
      "emp_info_player_Imp": 97,
      "emp_info_player_NF": 98
    },
    "capture_point_frequency_by_type": {
      "emp_cap_point": 53
    }
  },
  "lighting_environment": {
    "typical_skyboxes": ["empsky_overcast2", "sky_day01_01", ...]
  }
}
```

## Empires Mod Specific

- **Displacement power**: Max **3** (power 4 crashes server physics with multi-wheeled vehicles)
- **Commander camera ceiling**: At least 1087 units above max terrain height
- **Required entities**: `emp_info_params`, `emp_info_map_overview`, `info_node` (without this, players timeout)
- Required entities must be spawned even when `--no-enhanced` mode is used.
- **Playable spawn system**: For playable maps, use enhanced spawning (or manually place spawn/cap entities). `--no-enhanced` is primarily for compile/debug maps.
- **Player spawn classname (CRITICAL)**: Use `emp_info_player_Imp` and `emp_info_player_NF` (mixed case). Lowercase versions will cause players to join teams but not be able to spawn.
- **Capture model entity (CRITICAL)**: `emp_cap_model` must include a valid `model` key (for example `models/common/emp_snow/flag_capmodel1a.mdl`) and `angles`.
- **Restriction zones**: `emp_eng_restrict` / `emp_comm_restrict` are optional and currently disabled by default (`include_restriction_zones=False`) for stability.
- **Resource nodes**: Spawn as pairs (`emp_resource_point` + `emp_resource_point_prop`). Required keyvalues: `ResourcesSecond` (e.g., "3"), `MaxResources` (e.g., "-1" for infinite).
- **Resource script** (`<map_name>.txt`): Bounds use origin-centered coordinates (e.g., `"-8192"` to `"8192"`)
- **Weather**: Never one huge `func_precipitation` brush — split into small boxes or it crashes the engine
- **AI Blocker**: Place `func_nav_blocker` on steep terrain, otherwise AI hangs
- **VMF order**: `versioninfo` → `visgroups` → `viewsettings` → `world` → `entity` → `hidden` → `cameras` → `cordon`
- **Entity bounds**: All entities must be within map bounds (clamp positions with 64-unit margin)

## Reference Files

- `empires_entity_index.md` — Empires Mod entity reference
- `empires_textures.md` — Empires Mod texture reference
- `mapping.md` — Empires Wiki mapping guide
- `map_rules.json` — Statistical rules from map analysis
- `map_dataset/` — Reference VMF files (emp_arid_d, emp_homeland_b12, etc.)

## Implementation Notes

### Heightmap Resolution
The terrain pipeline generates a grid (e.g., 257x257 for 32x32 tiles with power=3), but entity spawning (resource nodes) requires heightmap sampling. Always upsample the grid to displacement resolution using `scipy.ndimage.zoom` before passing to VMF generation.

### Base Terrain Clearing
Bases should NOT be deeply flattened — real Empires maps have natural terrain variation near bases. Use a small gentle clearing radius (128-384 units based on map scale) with soft blending toward average terrain height, not zero.

### Terrain Height Sampling for Entities
When placing entities that need terrain height (resource nodes, spawn points, commanders):
1. Pass `terrain_actual_max` from the pipeline (`grid.max_height()`) to `PipelineSpec`
2. Use `heightmap[py, px] / 255.0 * terrain_actual_max` to get world height
3. Do NOT multiply by `height_scale` twice — the max is already in world units
4. **Commander height**: Sample terrain at the actual commander position, not the barracks origin. Commanders placed at wrong height will spawn stuck in ground.

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

**IMPORTANT**: The `NFRes`, `NFReinf`, `ImpRes`, `ImpReinf` keys are case-sensitive and must use this exact casing.

Important:
- Avoid forcing `AllowedTeams` unless intentionally restricting team joining.

### "Cannot convert" Errors
This error occurs when displacement normals are in integer format instead of float. The Source Engine expects normals like `"0.0 0.0 1.0"` not `"0 0 1"`. Ensure:
1. Normals are formatted as floats (even if using vertical normals `(0.0, 0.0, 1.0)`)
2. vmflib's Normals class uses `%s` format instead of `%d`
3. Vertex objects contain float values

Additional note from current pipeline validation:
- A small number of `make_triangles:calc_triangle_representation: Cannot convert` warnings can still appear even with correct float normals.
- If VBSP finishes, BSP is produced, and displacements look correct in Hammer/in-game, treat these as non-fatal warnings.
- If warnings are widespread and visuals break, re-check the displacement orientation contract above (`startposition`, row order, no custom `vaxis` override).

### GUI Output Files
The GUI generates the following files in `output/`:
- `gui_terrain.vmf` - VMF source file
- `gui_terrain.txt` - Resource script with map bounds
- `gui_terrain_temp.png` - Temporary heightmap (deleted after VMF generation)

The compile button also copies:
- `.bsp` to both `Empires/empires/maps/` and `Empires/empires/download/maps/`
- `.vmf` to `Empires/empires/maps/prefabs/`
- `.txt` to `Empires/empires/resource/maps/`
- `.vmt` minimap material to `Empires/empires/materials/maps/`

## Building Windows Executable

### Prerequisites
- Python 3.10+ installed
- Windows with Empires Mod installed via Steam

### Build Steps
1. Install dependencies:
```bash
pip install -r config/requirements.txt
```

2. Run the build script:
```bash
python build_exe.py
```

3. The executable will be in `dist/TerrainGenerator.exe`

### Manual PyInstaller Build
```bash
pip install pyinstaller
pyinstaller terrain_generator.spec --onefile --windowed
```

### Cross-Platform Notes
- The code automatically detects Windows vs Linux
- On Windows: VBSP runs directly
- On Linux: VBSP runs via Wine
- Steam Library paths are detected for both platforms

### Files for Distribution
When distributing:
- `dist/TerrainGenerator.exe` - Main executable
- Include Empires VBSP.exe alongside if users need to compile
