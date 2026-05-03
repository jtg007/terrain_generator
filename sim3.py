import sys
import numpy as np
sys.path.append('.')
from src.terrain_spec import TerrainSpec
from src.terrain_pipeline import generate_strategic_layout, generate_playability_mask
from src.canyon_generator import generate_canyon_base

spec = TerrainSpec()
spec.topology = "canyon"
spec.lane_numbers = 5
spec.maze_size = 90
spec.lane_width_scale = 1.0

nodes, conns = generate_strategic_layout(spec)
df = generate_playability_mask(spec, 512, 512, nodes, conns)
print("lane_width_scale 1.0 -> df min:", np.min(df), "max:", np.max(df))
base, info = generate_canyon_base(512, 512, df, spec.size_x, spec.size_y, 4096.0)
print("Base type:", type(base), base.shape if base is not None else None)

spec.lane_width_scale = 1.26
nodes, conns = generate_strategic_layout(spec)
df = generate_playability_mask(spec, 512, 512, nodes, conns)
print("\nlane_width_scale 1.26 -> df min:", np.min(df), "max:", np.max(df))
base, info = generate_canyon_base(512, 512, df, spec.size_x, spec.size_y, 4096.0)
print("Base type:", type(base), base.shape if base is not None else None)

spec.lane_width_scale = 1.29
nodes, conns = generate_strategic_layout(spec)
df = generate_playability_mask(spec, 512, 512, nodes, conns)
print("\nlane_width_scale 1.29 -> df min:", np.min(df), "max:", np.max(df))
base, info = generate_canyon_base(512, 512, df, spec.size_x, spec.size_y, 4096.0)
print("Base type:", type(base), base.shape if base is not None else None)
