# Empires Mod Terrain Generator

An advanced **procedural terrain generator and graphical interface** designed specifically for creating compile-ready displacement maps for the Source Engine modification, **Empires Mod**.

<img width="2560" height="1388" alt="Bildschirmfoto_20260423_223928" src="https://github.com/user-attachments/assets/c077c334-0983-4e3e-b245-8fde475a8da9" />


## Overview

The Terrain Generator bridges the gap between procedural noise generation and the strict mapping requirements of the Source Engine. It creates organic, playable maps using multi-layered Fractal Brownian Motion (fBm) and hydraulic erosion, handling all the complex VMF (Valve Map Format) intricacies behind the scenes.

## Features

*   **Interactive Strategy Canvas:** A dedicated editor tab with a professional canvas for visually planning your map. Place bases, resource nodes, and connect them with lanes.
*   **Interactive Terrain Sculpting:** Real-time terrain manipulation tools. Use the **Raise** and **Lower** brushes with smooth Gaussian falloff to manually sculpt tactical features.
*   **Procedural Landscape Engine:** Combines rolling hills, sharp mountain ridges, and hydraulic erosion to create natural-looking, continuous terrain grids.
*   **Lane-Aware Shaping:** Intelligently shapes terrain based on distance to paths, keeping vehicle lanes wide and smooth while generating sharper, rougher mountain ridges farther away.
*   **Intelligent Auto-Balancing:** Built-in algorithms flatten the terrain gently at base locations to ensure builders have a level playing field.
*   **Real-time Layout Validation:** Immediate visual feedback on entity placement validity directly in the GUI status label.
*   **Source Engine Compliance:** Generates 100% mathematically convex, correctly aligned, airtight displacement geometry designed for Empires Mod.
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
   ./terrain.sh --gui                    # GUI mode (default)
   ./terrain.sh --cli --seed 123         # CLI with custom seed
   ./terrain.sh --compile               # Compile last VMF
   ./terrain.sh --help                  # Show all options
   ```

## Step-by-Step Guide

1. **Configure Your Map:** Adjust basic parameters such as **Tiles X** / **Tiles Y** (map size), **Roughness**, **Erosion**, and **Height** in the sidebar. Optionally, choose a custom heightmap image.
2. **Setup Map Strategy:** In the **STRATEGY PREVIEW** section, use the interactive canvas to:
   * Select a tool (e.g., *Add Base*, *Add Resource*) to set up spawns.
   * Draw structural paths or strategy lanes using the **Lane** tool with adjustable widths.
   * Manually sculpt terrain details using the **Raise** and **Lower** tools.
   * Review all elements mapped onto your heightmap with **Undo/Redo** support.
3. **Generate VMF:** Ensure your **COMPILE PATH** is correct, then click **Generate VMF**.
   * *Note: If you do not specify a custom output folder, the generated files will be saved in your user `Documents/TerrainGenerator/output/` directory on Windows (or `./output/` when running from source).*
4. **Compile Map:** Click **Compile (VBSP)** to process and deploy the map to your game directories.
