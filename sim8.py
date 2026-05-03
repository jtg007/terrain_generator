import sys
import numpy as np
sys.path.append('.')
from src.terrain_spec import TerrainSpec
from src.terrain_pipeline import generate_strategic_layout, generate_playability_mask

def run_attempt(width_scale, attempt):
    spec = TerrainSpec(seed=42+attempt)
    spec.topology = "canyon"
    spec.lane_numbers = 5
    spec.maze_size = 90
    spec.lane_width_scale = width_scale
    spec.origin_x = -4096
    spec.origin_y = -4096
    spec.size_x = 8192
    spec.size_y = 8192

    nodes, conns = generate_strategic_layout(spec)
    df = generate_playability_mask(spec, 512, 512, nodes, conns)

    # Calculate d_norm_clean logic from canyon_generator
    # df_clean / ref_px
    d_norm_clean = df / 512.0

    # Check what effective mask looks like
    print(f"Scale {width_scale}, attempt {attempt}")
    print(f"  d_norm_clean min: {np.min(d_norm_clean):.4f}, max: {np.max(d_norm_clean):.4f}")

run_attempt(1.26, 0)
run_attempt(1.29, 0)
