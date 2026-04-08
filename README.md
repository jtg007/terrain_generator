# Terrain Generator for Empires Mod

> **100% AI Generated** - This entire project was written by an AI assistant.

A GUI application for generating compile-safe displacement terrain VMF files for Source Engine maps, specifically designed for the Empires Mod.

## Features

- Procedural terrain generation using fractal Brownian motion (fBm)
- Hydraulic erosion simulation
- Automatic entity spawning (spawns, commanders, resource nodes, capture points)
- Cross-platform support (Windows and Linux)
- Automatic Empires installation detection
- GUI with preset configurations

## Requirements

- Python 3.10+
- Empires Mod installed via Steam (for map compilation)

## Installation

### Using the Executable (Recommended for Windows)

1. Download `TerrainGenerator.exe` from the latest release or build artifacts
2. Run the executable
3. Select your Empires installation folder if not auto-detected
4. Generate and compile maps!

### Manual Installation (Python)

```bash
# Clone the repository
git clone <repository-url>
cd terrain_generator

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On Linux:
source venv/bin/activate

# Install dependencies
pip install -r config/requirements.txt

# Run the GUI
python tools/terrain_generator.py
```

## Building the Windows Executable

### Option 1: GitHub Actions (Recommended)

The repository includes a GitHub Actions workflow that automatically builds the executable on every push to main/master. The artifact will be available in the Actions tab.

### Option 2: Manual Build

```bash
# Install dependencies
pip install -r config/requirements.txt
pip install pyinstaller

# Build the executable
pyinstaller terrain_generator.spec --onefile --windowed
```

The executable will be created in the `dist/` folder.

## Usage

1. **Select Preset** - Choose from Flat, Hills, Rugged, or Competitive terrain types
2. **Configure** - Adjust seed, tiles, height scale, roughness, and erosion
3. **Empires Path** - Select your Empires installation folder (auto-detected if possible)
4. **Generate** - Create the VMF terrain file
5. **Compile** - Compile to BSP and deploy to Empires

## Configuration Files

- `config/presets.json` - Terrain presets
- `config/textures.json` - Available terrain textures
- `config/skyboxes.json` - Available skyboxes

## Cross-Platform Notes

- **Windows**: VBSP runs directly
- **Linux**: VBSP runs via Wine
- Empires path is auto-detected on both platforms

## Tech Stack

This project was developed entirely with AI assistance:

- **Language**: Python 3.10+
- **GUI Framework**: PySide6 (Qt for Python)
- **Scientific Computing**: NumPy, SciPy
- **Image Processing**: Pillow
- **Build System**: PyInstaller

## License

MIT License
