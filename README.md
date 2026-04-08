# Terrain Generator for Empires Mod

Generate compile-safe displacement terrain maps for Empires Mod. Creates VMF files with procedural terrain using fractal noise and hydraulic erosion.

## Quick Start (Windows)

1. Download `TerrainGenerator.exe` from [Actions](https://github.com/jtg007/terrain_generator/actions) → latest run → Artifacts
2. Run the executable
3. Select your Empires folder if not auto-detected
4. Click **Generate** to create the terrain
5. Click **Compile** to build and deploy to Empires

## Installation (Linux / Manual)

```bash
git clone https://github.com/jtg007/terrain_generator.git
cd terrain_generator

python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

pip install -r config/requirements.txt
python tools/terrain_generator.py
```

## Usage

1. **Preset** - Choose terrain style: Flat, Hills, Rugged, or Competitive
2. **Configure** - Adjust seed, map size, height, roughness, erosion
3. **Generate** - Creates the VMF file
4. **Compile** - Builds BSP and copies to Empires maps folder

The map will be available in Empires under "Play → Create Server → Map".

## Requirements

- Empires Mod installed via Steam (for VBSP compiler)
- Windows or Linux with Wine (for map compilation)

## Troubleshooting

**Empires not detected?** Click "Browse" and select your Empires folder manually (usually `C:\Program Files\Steam\steamapps\common\Empires`)

**Compilation fails?** Make sure your Empires installation is complete and VBSP.exe exists in the bin folder.

**Map crashes?** Try reducing map size (fewer tiles) or lowering height scale.
