import numpy as np
import sys
import os

from src.terrain_spec import TerrainSpec
from src.terrain_pipeline import run_pipeline

def test_pipeline():
    spec = TerrainSpec(
        size_x=8192,
        size_y=8192,
        cell_size=512,
        displacement_power=3,
        canyon_threshold=0.42,
        plateau_threshold=0.6,
        blur_radius=0,
        max_slope_step=99999,
        mountain_height_scale=1.0,
        terrain_max_height=16384,
        topology="canyon", # Ensure canyon
        seed=42,
        generate_lanes=False # Disable lanes so we just see the raw canyon noise
    )

    print(f"\n--- Running pure canyon generation ---")
    result = run_pipeline(spec)
    grid = result['grid']

    # Analyze the generated heightmap
    arr = grid.heights
    print(f"Min: {np.min(arr)}")
    print(f"Max: {np.max(arr)}")
    print(f"Mean: {np.mean(arr)}")

    gy, gx = np.gradient(arr)
    gradient_mag = np.sqrt(gx**2 + gy**2)
    print(f"Max Slope (Gradient): {np.max(gradient_mag)}")
    print(f"Mean Slope: {np.mean(gradient_mag)}")

if __name__ == '__main__':
    sys.path.insert(0, os.path.abspath('.'))
    test_pipeline()
