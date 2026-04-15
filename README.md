# Empires Mod Terrain Generator

An advanced **procedural terrain generator and graphical interface** designed specifically for creating compile-ready displacement maps for the Source Engine modification, **Empires Mod**.

![Terrain Generator UI Screenshot](docs/screenshots/gui_preview.png)

## Overview

The Terrain Generator bridges the gap between procedural noise generation and the strict mapping requirements of the Source Engine. It creates organic, playable maps using multi-layered Fractal Brownian Motion (fBm) and hydraulic erosion, handling all the complex VMF (Valve Map Format) intricacies behind the scenes.

## Features

*   **Interactive Live Map Preview:** Visualize the generated heightmap instantly as you tweak parameters. Changes to the noise seed, size, or ruggedness reflect in real-time.
*   **Procedural Landscape Engine:** Combines rolling hills, sharp mountain ridges, and hydraulic erosion to create natural-looking, continuous terrain grids.
*   **Intelligent Auto-Balancing:** Built-in algorithms flatten the terrain gently at base locations to ensure builders have a level playing field, while avoiding unnatural sudden drops.
*   **Drag-and-Drop Entity Placement:** Directly click and drag on the live preview to custom place the Imperial Commander Base, Northern Faction Base, and Resource Nodes exactly where you want them.
*   **Custom Heightmaps:** You can also choose to import your own custom `.png` image heightmaps to manually author the fundamental terrain shapes, skipping the procedural noise entirely.
*   **Source Engine Compliance:** Generates 100% mathematically convex, correctly aligned, airtight displacement geometry designed specifically to avoid VBSP compilation errors or engine crashes.
*   **Automatic VBSP Compilation:** Automatically locates your Empires Mod installation and directly compiles the generated VMF into a playable BSP format with one click.
*   **Ready-to-Play Presets:** Select from pre-configured terrain styles like *Flat*, *Hills*, *Rugged*, or *Competitive* to get a fast start.

## Quick Start

### Windows

1. Download the latest release `.exe` from the [Releases page](https://github.com/jtg007/terrain_generator/releases).
2. Extract the ZIP file and double-click `TerrainGenerator.exe` to launch the GUI.
3. *Note: If you have Python installed, you can also run it from source via `python tools/terrain_generator.py` after installing dependencies (`pip install -r config/requirements.txt`).*

### Linux / macOS

1. Clone or download the repository:
   ```bash
   git clone https://github.com/jtg007/terrain_generator.git
   cd terrain_generator
   ```
2. Run the launcher script (it will automatically create a local virtual environment and install dependencies on first run):
   ```bash
   ./terrain.sh
   ```
   *Alternative commands:*
   ```bash
   ./terrain.sh --gui                    # GUI mode (default)
   ./terrain.sh --cli hills --seed 123  # CLI with preset
   ./terrain.sh --compile               # Compile last VMF
   ./terrain.sh --help                  # Show all options
   ```

## Step-by-Step Guide

1. **Configure Your Map:** Choose a baseline style under the **PRESETS** section on the left sidebar. Adjust basic parameters such as **Tiles X** / **Tiles Y** (map size), **Roughness**, **Erosion**, and **Height**. Optionally, choose a custom heightmap image.
2. **Setup Base Layout:** In the **MAP PREVIEW** section at the bottom, select a tool (e.g., *BE Base*, *NF Base*, or *Resource*). Click or drag within the preview image to accurately position entity spawns.
3. **Generate VMF:** Ensure you have selected a valid **COMPILE PATH** pointing to your Empires Mod folder. Click the **Generate VMF** button to bake the map and layout.
4. **Compile Map:** Once the VMF is successfully generated, click **Compile (VBSP)**. The tool will process your map and place it into the game directories.
5. **Play:** Launch Empires Mod, open the developer console, and load your new map using `map gui_terrain` (or the custom map name you provided).
