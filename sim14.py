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
spec.lane_width_scale = 1.29
spec.origin_x = -4096
spec.origin_y = -4096
spec.size_x = 8192
spec.size_y = 8192

nodes, conns = generate_strategic_layout(spec)
df = generate_playability_mask(spec, 512, 512, nodes, conns)
print("DF min:", np.min(df), "max:", np.max(df))
base, info = generate_canyon_base(512, 512, df, spec.size_x, spec.size_y, 4096.0)

floor_pixels = np.sum(base < 0.20)
print(f"Floor pixels: {floor_pixels} out of {512*512}")
