import sys
import numpy as np
sys.path.append('.')
from src.terrain_spec import TerrainSpec
from src.terrain_pipeline import generate_strategic_layout, generate_playability_mask

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
df_clean = df.copy()

print("Distance Field Mean:", np.mean(df))
print("Distance Field Min:", np.min(df))
print("Distance Field Max:", np.max(df))

for n in nodes:
    if n.type == 3: # BASE
        print("Base node:", n.x, n.y, "radius:", n.radius)
    else:
        print("Node radius:", n.radius)
        break
