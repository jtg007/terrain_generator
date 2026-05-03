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
    d_norm = df / 512.0

    # Calculate effective_wall_slope logic
    min_clearance_px = 192.0 / (8192.0 / 512.0)
    ref_px = 512.0
    lane_norm = (min_clearance_px * 2.0) / ref_px
    wall_slope = 0.06
    effective_wall_slope = min(wall_slope, lane_norm * 0.4)

    print(f"Scale {width_scale}, attempt {attempt}")
    print(f"  effective_wall_slope: {effective_wall_slope:.4f}")

    from src.canyon_generator import enforce_minimum_width
    df_clean = enforce_minimum_width(df, min_clearance_px)
    d_norm_clean = df_clean / 512.0

    safe_margin = min_clearance_px / ref_px * 0.5

    print(f"  Safe margin: {safe_margin:.4f}")

    from src.canyon_generator import validate_connectivity
    playable_mask = df_clean <= 0
    conn_info = validate_connectivity(playable_mask)

    # Calculate base height breakdown
    floor_mask = d_norm_clean < -safe_margin
    ramp_mask = (d_norm_clean >= -safe_margin) & (d_norm_clean < 0.0)
    wall_mask = d_norm_clean >= 0.0

    print(f"  Floor px: {np.sum(floor_mask)}, Ramp px: {np.sum(ramp_mask)}, Wall px: {np.sum(wall_mask)}")

run_attempt(0.26, 0)
run_attempt(1.26, 0)
run_attempt(1.29, 0)
run_attempt(1.50, 0)
