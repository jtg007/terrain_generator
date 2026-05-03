import sys
import numpy as np
sys.path.append('.')
from src.terrain_spec import TerrainSpec
from src.terrain_pipeline import generate_strategic_layout, generate_playability_mask

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

    nodes, conns = generate_strategic_layout(spec)
    df = generate_playability_mask(spec, 512, 512, nodes, conns)

    print(f"Scale {width_scale}, df range: {np.min(df):.2f} to {np.max(df):.2f}")

run_test(0.26)
run_test(1.26)
run_test(1.29)
run_test(1.50)
