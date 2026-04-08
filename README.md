# Terrain Generator for Empires Mod

**Generate professional displacement terrain maps for Empires Mod in minutes.**

A powerful GUI tool that creates compile-safe VMF files using procedural terrain generation, hydraulic erosion simulation, and automatic entity placement.

[Download v1.0.0](https://github.com/jtg007/terrain_generator/releases/latest) • [Report Bug](https://github.com/jtg007/terrain_generator/issues)

---

## Features

### Terrain Generation
- **Procedural Heightmaps** - Generate terrain using fractal Brownian motion (fBm) noise
- **Hydraulic Erosion** - Simulate water erosion for realistic valleys and ridges
- **Height Quantization** - Ensures compile-safe displacement geometry
- **Slope Control** - Automatic smoothing to prevent VBSP failures

### Map Entities
- **Automatic Spawn Points** - Players can join and respawn correctly
- **Commander Placement** - Proper Z-height calculation prevents stuck commanders
- **Resource Nodes** - Fully configured with income settings
- **Capture Points** - Balanced point placement based on map analysis
- **info_node Entities** - Prevents player timeout issues

### User Experience
- **One-Click Generation** - Select preset → Generate → Compile
- **Real-Time Preview** - See terrain parameters before generating
- **Auto-Detection** - Finds Empires installation automatically
- **Cross-Platform** - Works on Windows and Linux (via Wine)

### Presets
| Preset | Tiles | Height | Roughness | Best For |
|--------|-------|--------|-----------|----------|
| Flat | 16×16 | 512 | 0.1 | Infantry combat |
| Hills | 20×20 | 1536 | 0.4 | Mixed warfare |
| Rugged | 20×20 | 2560 | 0.7 | Tactical battles |
| Competitive | 16×16 | 1024 | 0.3 | Balanced gameplay |

---

## Quick Start

### 1. Download
Get the latest release from [Releases](https://github.com/jtg007/terrain_generator/releases/latest):
```
TerrainGenerator-Windows.zip
```

### 2. Extract
Extract the zip to any folder.

### 3. Run
Double-click `TerrainGenerator.exe`

### 4. Generate
1. Select a **Preset** (Flat, Hills, Rugged, or Competitive)
2. Adjust settings if needed:
   - **Seed** - Change for different terrain
   - **Tiles** - Map size (more = larger)
   - **Height Scale** - Mountain height
   - **Roughness** - Terrain detail level
   - **Erosion** - Water erosion amount
3. Select your **Empires folder** (auto-detected)
4. Click **Generate**
5. Click **Compile** to build and deploy

### 5. Play
Launch Empires → Create Server → Select your map

---

## Requirements

- **Windows 10/11** (or Linux with Wine for compilation)
- **Empires Mod** installed via Steam
- ~300MB disk space

---

## Configuration

### Textures
Modify `config/textures.json` to use different terrain materials.

### Skyboxes
Modify `config/skyboxes.json` to change the sky. Safe options:
- `empsky_day1`, `empsky_day2`, `empsky_day3`
- `empsky_overcast1`, `empsky_overcast2`, `empsky_overcast3yellow`
- `empsky_sunset1`, `empsky_sunset2`

### Presets
Modify `config/presets.json` to create custom terrain profiles.

---

## Troubleshooting

**Empires not detected?**
Click "Browse" and select your Empires folder manually:
```
C:\Program Files\Steam\steamapps\common\Empires
```

**Compilation fails?**
- Try reducing map size (fewer tiles)
- Lower the height scale
- Ensure Empires installation is complete

**Map crashes on load?**
- Reduce erosion strength
- Use fewer tiles
- Check VBSP output for specific errors

---

## Technical Details

- **Displacement Power**: 3 (9×9 vertices per tile) - Maximum safe for Empires physics
- **Coordinate System**: Maps centered around origin (0,0)
- **Entity Bounds**: All entities clamped within map boundaries
- **Height Quantization**: Rounded to prevent micro-gaps

---

## License

MIT License - Free to use, modify, and distribute.

---

*100% AI Generated* - Built with OpenCode AI assistant.
