import re

with open('src/terrain_pipeline.py', 'r') as f:
    content = f.read()

playability_mask_function = """
def generate_playability_mask(
    spec: TerrainSpec,
    rows: int,
    cols: int,
    nodes: List[LayoutNode],
    connections: List[LayoutConnection]
) -> Tuple[np.ndarray, np.ndarray]:
    \"\"\"
    Calculates the playability mask and chokepoint block mask using numpy for speed.
    Returns two 2D float64 arrays (playable_mask, choke_block_mask).
    \"\"\"
    import numpy as np

    # Create coordinate grids
    x_coords = np.linspace(spec.origin_x, spec.origin_x + spec.size_x, cols)
    y_coords = np.linspace(spec.origin_y, spec.origin_y + spec.size_y, rows)
    WX, WY = np.meshgrid(x_coords, y_coords)

    playable_mask = np.zeros((rows, cols), dtype=np.float64)
    choke_block_mask = np.zeros((rows, cols), dtype=np.float64)

    # Helper to calculate smooth edge falloff (get_sharp_mask logic)
    def apply_mask_weight(current_mask, dist_grid, radius, flat_core_ratio=0.75):
        normalized_dist = dist_grid / max(1e-5, radius)
        # Core is 1.0, outside is 0.0
        weight = np.where(normalized_dist <= flat_core_ratio, 1.0, 0.0)
        # Smooth drop-off margin
        margin_mask = (normalized_dist > flat_core_ratio) & (normalized_dist < 1.0)
        t = 1.0 - (normalized_dist[margin_mask] - flat_core_ratio) / (1.0 - flat_core_ratio)
        weight[margin_mask] = t**2 * (3 - 2 * t)
        return np.maximum(current_mask, weight)

    # 1. Evaluate Nodes (Bases, Vehicle Areas)
    for node in nodes:
        dist_grid = np.sqrt((WX - node.x)**2 + (WY - node.y)**2)
        if node.type in (ZoneType.BASE, ZoneType.VEHICLE_OPEN):
            playable_mask = apply_mask_weight(playable_mask, dist_grid, node.radius)

    # 2. Evaluate Polyline Connections
    for conn in connections:
        # We need the minimum distance to ANY segment of the polyline
        min_dist_grid = np.full((rows, cols), np.inf)

        pts = conn.path_points
        for i in range(len(pts) - 1):
            ax, ay = pts[i]
            bx, by = pts[i+1]

            # Vectorized point-to-line-segment distance
            dx, dy = bx - ax, by - ay
            l2 = dx*dx + dy*dy

            if l2 == 0:
                dist = np.sqrt((WX - ax)**2 + (WY - ay)**2)
            else:
                # t = dot(P-A, B-A) / |B-A|^2
                t = ((WX - ax) * dx + (WY - ay) * dy) / l2
                t_clamped = np.clip(t, 0.0, 1.0)
                px = ax + t_clamped * dx
                py = ay + t_clamped * dy
                dist = np.sqrt((WX - px)**2 + (WY - py)**2)

            min_dist_grid = np.minimum(min_dist_grid, dist)

        # Apply weights based on zone type
        if conn.type in (ZoneType.MAIN_LANE, ZoneType.SIDE_ROUTE):
            playable_mask = apply_mask_weight(playable_mask, min_dist_grid, conn.width)

        elif conn.type == ZoneType.CHOKEPOINT:
            choke_playable_width = conn.width * 0.5
            playable_mask = apply_mask_weight(playable_mask, min_dist_grid, choke_playable_width)

            # Apply blockade if outside the narrow lane
            out_of_lane = min_dist_grid > choke_playable_width
            block_val = np.minimum(1.0, (min_dist_grid - choke_playable_width) / max(1e-5, choke_playable_width * 2))
            block_grid = np.zeros_like(choke_block_mask)
            block_grid[out_of_lane] = block_val[out_of_lane]
            choke_block_mask = np.maximum(choke_block_mask, block_grid)

    # Combine masks as previously done in generate_heights
    playable_mask = np.maximum(0.0, playable_mask - choke_block_mask)

    return playable_mask, choke_block_mask

def generate_heights(spec: TerrainSpec, grid: HeightGrid) -> HeightGrid:
"""

# replace `def generate_heights(spec: TerrainSpec, grid: HeightGrid) -> HeightGrid:` with the function + original function sig
content = content.replace("def generate_heights(spec: TerrainSpec, grid: HeightGrid) -> HeightGrid:", playability_mask_function)

# Also ensure numpy is imported at top level if not present, but it's imported locally inside the function.
# Wait, np is used in the signature Tuple[np.ndarray, np.ndarray].
# Let's check if numpy is imported at top level, or I can just import numpy as np at top level or change signature to Any.
# Let's change the signature to Tuple[Any, Any] or import np at top level. I will just import numpy at the top.

if "import numpy as np" not in content:
    content = "import numpy as np\n" + content

with open('src/terrain_pipeline.py', 'w') as f:
    f.write(content)
