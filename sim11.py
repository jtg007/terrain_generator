import sys
import numpy as np
sys.path.append('.')
from src.terrain_spec import TerrainSpec
from src.terrain_pipeline import generate_strategic_layout, generate_playability_mask

def test(scale, maze_size):
    spec = TerrainSpec()
    spec.topology = "canyon"
    spec.lane_numbers = 5
    spec.maze_size = maze_size
    spec.lane_width_scale = scale
    spec.origin_x = -4096
    spec.origin_y = -4096
    spec.size_x = 8192
    spec.size_y = 8192

    nodes, conns = generate_strategic_layout(spec)

    # Calculate node_radius inside terrain_pipeline.py
    grid_size = 5
    maze_scale = maze_size / 100.0
    maze_dim_x = 8192 * maze_scale
    spacing_x = maze_dim_x / grid_size
    node_radius = spacing_x * 0.25
    lane_width = max(192.0, spacing_x * 0.30 * scale)

    print(f"Scale {scale}, Maze {maze_size}: spacing={spacing_x:.2f}, node_radius={node_radius:.2f}, lane_width={lane_width:.2f}")

test(0.26, 90)
test(0.29, 90)
test(1.26, 90)
test(1.29, 90)
