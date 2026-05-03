import sys
import numpy as np
sys.path.append('.')
from src.terrain_spec import TerrainSpec
from src.terrain_pipeline import generate_strategic_layout, generate_playability_mask
from src.canyon_generator import generate_canyon_base, enforce_minimum_width, validate_connectivity

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

    nodes, conns = generate_strategic_layout(spec)
    df = generate_playability_mask(spec, 512, 512, nodes, conns)

    # Try the exact same loop as generate_canyon_base
    from src.canyon_generator import gaussian_blur
    smoothed_df = gaussian_blur(df, passes=3.0)
    df_clean = enforce_minimum_width(smoothed_df, 12.0) # 192.0 / 16.0
    playable_mask = df_clean <= 0
    conn_info = validate_connectivity(playable_mask)
    print(f"Scale {width_scale}, connected: {conn_info['connected']}")

run_test(1.26)
run_test(1.29)
