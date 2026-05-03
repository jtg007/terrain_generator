import sys
import numpy as np
sys.path.append('.')
from src.terrain_spec import TerrainSpec
from src.terrain_pipeline import generate_strategic_layout, generate_playability_mask
from src.canyon_generator import generate_canyon_base, enforce_minimum_width, validate_connectivity

spec = TerrainSpec()
spec.topology = "canyon"
spec.lane_numbers = 5
spec.maze_size = 90
spec.lane_width_scale = 1.26
spec.origin_x = -4096
spec.origin_y = -4096
spec.size_x = 8192
spec.size_y = 8192

nodes, conns = generate_strategic_layout(spec)
df = generate_playability_mask(spec, 512, 512, nodes, conns)
df_clean = enforce_minimum_width(df, 192.0 / (8192.0/512))
playable_mask = df_clean <= 0
conn_info = validate_connectivity(playable_mask)
print("1.26 width, connected:", conn_info["connected"])

spec.lane_width_scale = 1.29
nodes, conns = generate_strategic_layout(spec)
df = generate_playability_mask(spec, 512, 512, nodes, conns)
df_clean = enforce_minimum_width(df, 192.0 / (8192.0/512))
playable_mask = df_clean <= 0
conn_info = validate_connectivity(playable_mask)
print("1.29 width, connected:", conn_info["connected"])
