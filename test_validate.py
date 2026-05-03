import sys
import numpy as np
sys.path.append('.')
from src.terrain_spec import TerrainSpec
from src.terrain_pipeline import generate_strategic_layout, generate_playability_mask
from src.canyon_generator import enforce_minimum_width, validate_connectivity

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
    df_clean = enforce_minimum_width(df, 12.0)
    mask = df_clean <= 0

    info = validate_connectivity(mask)
    print(f"Scale {width_scale}, attempt {attempt}, connected: {info['connected']}")
    return info['connected']

for attempt in range(5):
    run_attempt(1.26, attempt)

for attempt in range(5):
    run_attempt(1.29, attempt)
