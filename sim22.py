import sys
import numpy as np
sys.path.append('.')
from src.terrain_spec import TerrainSpec
from src.terrain_pipeline import generate_strategic_layout, generate_playability_mask

spec = TerrainSpec()
spec.topology = "canyon"
spec.lane_numbers = 5
spec.maze_size = 90
spec.lane_width_scale = 1.9
spec.origin_x = -4096
spec.origin_y = -4096
spec.size_x = 8192
spec.size_y = 8192

nodes, conns = generate_strategic_layout(spec)
df = generate_playability_mask(spec, 512, 512, nodes, conns)
print(f"Max node radius: {max([n.radius for n in nodes])}")
print(f"Min df: {np.min(df)}")
