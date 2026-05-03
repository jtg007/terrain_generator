import sys
import numpy as np
sys.path.append('.')
from src.terrain_spec import TerrainSpec
from src.terrain_pipeline import generate_strategic_layout, generate_playability_mask, generate_heights, generate_vertex_grid
from src.terrain_spec import HeightGrid

def run_test(width_scale):
    spec = TerrainSpec()
    spec.topology = "canyon"
    spec.lane_numbers = 5
    spec.maze_size = 90
    spec.lane_width_scale = width_scale
    spec.origin_x = -4096
    spec.origin_y = -4096
    spec.size_x = 8192
    spec.size_y = 8192
    spec.roughness = 0.5

    grid = generate_vertex_grid(spec)

    try:
        grid = generate_heights(spec, grid)
        print(f"Scale {width_scale}, min height: {np.min(grid.heights):.2f}, max height: {np.max(grid.heights):.2f}")

        # Check standard deviation to see if the canyon is completely flat (which means it fell back or washed out)
        print(f"Scale {width_scale}, std dev: {np.std(grid.heights):.2f}")
    except Exception as e:
        print(f"Scale {width_scale}, error: {e}")

run_test(0.26)
run_test(0.29)
run_test(1.26)
run_test(1.29)
