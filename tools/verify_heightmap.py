#!/usr/bin/env python3
"""
Heightmap verification script for testing presets and terrain pipeline changes.
Usage: python tools/verify_heightmap.py
"""

import sys
import json
from pathlib import Path
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.terrain_spec import create_default_spec, TerrainSpec
from src.terrain_pipeline import run_pipeline
from src.export_utils import heightgrid_to_heightmap
from src.config_model import GUIConfigModel

def verify_preset(preset_name, preset_data):
    print(f"\nVerifying preset: {preset_name}")
    config = GUIConfigModel()
    # Apply preset data
    for k, v in preset_data.items():
        if hasattr(config, k):
            setattr(config, k, v)

    spec = config.make_spec()

    result = run_pipeline(spec)
    grid = result["grid"]

    grid_size = (2**spec.displacement_power) + 1
    tiles_x = spec.size_x // spec.cell_size
    tiles_y = spec.size_y // spec.cell_size

    vertex_cols = tiles_x * (grid_size - 1) + 1
    vertex_rows = tiles_y * (grid_size - 1) + 1

    heightmap = heightgrid_to_heightmap(grid, vertex_rows, vertex_cols)
    hm_array = (heightmap * 255).astype(np.uint8)

    output_dir = Path("output_verify")
    output_dir.mkdir(exist_ok=True)
    img_path = output_dir / f"heightmap_{preset_name}.png"
    Image.fromarray(hm_array).save(img_path)
    print(f"Saved heightmap to {img_path}")

def main():
    presets_file = Path("config/presets.json")
    if not presets_file.exists():
        print("Error: config/presets.json not found")
        sys.exit(1)

    with open(presets_file, "r") as f:
        presets_data = json.load(f).get("presets", {})

    # Verify the specific presets mentioned by the user or the interesting ones
    targets = ["flat", "mountain_pass", "competitive"]
    for target in targets:
        if target in presets_data:
            verify_preset(target, presets_data[target])
        else:
            print(f"Warning: preset {target} not found")

if __name__ == "__main__":
    main()
