# Empires Mod Terrain Generator

An advanced **procedural terrain generator and graphical interface** designed specifically for creating compile-ready displacement maps for the Source Engine modification, **Empires Mod**.

<img width="2560" height="1388" alt="Bildschirmfoto_20260424_162523" src="https://github.com/user-attachments/assets/7dfd9bc0-6a64-487f-817d-20fc945d7eca" />

## Overview

The Terrain Generator bridges the gap between procedural noise generation and the strict mapping requirements of the Source Engine. It creates organic, playable maps using multi-layered Fractal Brownian Motion (fBm), customized domain warping, and custom Canyon topology, handling all the complex VMF (Valve Map Format) intricacies behind the scenes.

## Features

*   **Interactive Strategy Canvas:** A dedicated editor tab with a professional canvas for visually planning your map. Place bases, resource nodes, and connect them with lanes.
*   **Universal Masking (Stencil):** A global 2D selection mask allows you to freeze or unfreeze specific areas of the map. Painted areas (red) are fully editable, while unpainted areas are protected from all procedural generation sliders and manual sculpting tools.
*   **Procedural Landscape Engine (Canyon Topology):** Combines rolling hills, sharp ridges, and domain-warped Canyons with a 3-zone transfer function for natural plateaus, vertical walls, and flat floors.
*   **Lane-Aware Shaping:** Intelligently shapes terrain based on distance to paths, keeping vehicle lanes wide and smooth while generating steeper cliffs and rougher ridges farther away.
*   **Smart Detail System:** Automatically handles prop spawning with advanced collision and slope checks to prevent clipping, floating props, and compiler limits.
*   **Interactive Terrain Sculpting & Painting:**
    *   **Sculpt Tools:** Raise, Lower, and Flatten brushes with smooth falloff to manually sculpt tactical features.
    *   **Tile Painting System (WIP):** A precise grid-based painter allowing you to assign specific textures to 16x16 displacement grid tiles.
*   **Source Engine Compliance:** Generates 100% mathematically convex, correctly aligned, airtight displacement geometry designed for Empires Mod, complete with smart skybox generation.
*   **Automatic VBSP Compilation:** Detects your Empires Mod installation and compiles the generated VMF into a playable BSP format with one click.

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
   ./terrain.sh --gui                   # GUI mode (default)
   ./terrain.sh --cli --seed 123        # CLI with custom seed
   ./terrain.sh --compile               # Compile last VMF
   ./terrain.sh --help                  # Show all options
   ```

## Step-by-Step Guide

1. **Configure Your Map:** Adjust basic parameters such as **Tiles X** / **Tiles Y** (map size), **Topology**, and **Canyon Depth** in the sidebar. Optionally, choose a custom heightmap image.
2. **Setup Map Strategy:** Use the interactive canvas tabs (**Terrain**, **Entities**, **Layout**) to:
   * Select a tool (e.g., *Set BE*, *Add Res*) to set up spawns.
   * Draw structural paths or strategy lanes using the **Lane** tool with adjustable widths.
   * Manually sculpt terrain details using the **Raise**, **Lower**, and **Flatten** tools.
   * Assign specific ground textures using the **Tile Paint** tool.
3. **Generate VMF:** Ensure your **COMPILE PATH** is correct, then click **Generate VMF**.
   * *Note: If you do not specify a custom output folder, the generated files will be saved in your user `Documents/TerrainGenerator/output/` directory on Windows (or `./output/` when running from source).*
4. **Compile Map:** Click **Compile VMT/BSP** to process and deploy the map to your game directories.
