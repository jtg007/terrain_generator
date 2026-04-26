import numpy as np
import sys
import os

from src.terrain_spec import TerrainSpec
from src.terrain_pipeline import run_pipeline
from PIL import Image

def generate_preview():
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
        topology="canyon",
        seed=42,
        generate_lanes=True,
        feature_scale=50.0 # Make sure to set high feature scale
    )

    print(f"\n--- Running with feature scale 50.0 and lanes ---")
    result = run_pipeline(spec)
    grid = result['grid']

    arr = grid.heights

    # Normalize to 0-255 for image viewing
    arr_min = np.min(arr)
    arr_max = np.max(arr)
    if arr_max > arr_min:
        norm = ((arr - arr_min) / (arr_max - arr_min)) * 255.0
    else:
        norm = np.zeros_like(arr)

    img = Image.fromarray(norm.astype(np.uint8))
    img.save('mask_test_high.png')

if __name__ == '__main__':
    sys.path.insert(0, os.path.abspath('.'))
    generate_preview()
