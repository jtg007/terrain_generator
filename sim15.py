import sys
import numpy as np
sys.path.append('.')
from src.terrain_spec import TerrainSpec
from src.terrain_pipeline import generate_strategic_layout, generate_playability_mask

spec = TerrainSpec()
spec.topology = "canyon"
spec.lane_numbers = 5
spec.maze_size = 90
spec.lane_width_scale = 1.0 # Standard width scale for tests

nodes, conns = generate_strategic_layout(spec)
df = generate_playability_mask(spec, 512, 512, nodes, conns)
df_clean = df.copy()

print("Nodes length:", len(nodes))
print("Conns length:", len(conns))
print("Base Node size:", [n.radius for n in nodes if n.type == 3][0])

spec.lane_width_scale = 1.29
nodes, conns = generate_strategic_layout(spec)
df = generate_playability_mask(spec, 512, 512, nodes, conns)
print("\nAfter node scale update, 1.29 width:")
print("Nodes length:", len(nodes))
print("Conns length:", len(conns))
print("Base Node size:", [n.radius for n in nodes if n.type == 3][0])
