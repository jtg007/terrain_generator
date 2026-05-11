import math
import numpy as np
from typing import Optional
import sys
from pathlib import Path

# TODO: verify import
sys.path.insert(0, str(Path(__file__).parent.parent / "tools" / "vmflib"))
from vmflib.tools import Block


def quantize_coord(val: float, precision: float = 1.0) -> float:
    """Deterministically quantize coordinate to prevent VBSP errors."""
    return math.floor(val / precision) * precision


def apply_nodraw_to_terrain_except_top(block: Block, top_material: str) -> None:
    """Apply toolsnodraw to bottom and side faces, keep top_material on top face."""
    for i, side in enumerate(block.brush.children):
        if i == 0:
            side.material = top_material
        else:
            side.material = "tools/toolsnodraw"


def point_to_segment_dist(p, a, b):
    """Calculate the shortest distance from point p to line segment ab."""
    px, py = p
    ax, ay = a
    bx, by = b

    dx = bx - ax
    dy = by - ay
    if dx == 0 and dy == 0:
        return math.sqrt((px - ax)**2 + (py - ay)**2)

    t = ((px - ax) * dx + (py - ay) * dy) / (dx*dx + dy*dy)
    t = max(0, min(1, t))

    closest_x = ax + t * dx
    closest_y = ay + t * dy
    return math.sqrt((px - closest_x)**2 + (py - closest_y)**2)


def flatten_terrain_at_location(
    heightmap: np.ndarray,
    center_x: float,
    center_y: float,
    radius: float,
    img_width: int,
    img_height: int,
    map_width: int,
    map_height: int,
    origin_x: float,
    origin_y: float,
    blend_to_avg: bool = True,
    flatness: float = 1.0,
) -> np.ndarray:
    """Gently clear terrain at base location with smooth falloff.

    Args:
        heightmap: Normalized heightmap (0-1)
        center_x, center_y: World coordinates of base center
        radius: Radius to apply clearing (world units)
        blend_to_avg: If True, blend toward average height; if False, just soften slopes
    """
    flat_heightmap = heightmap.copy()

    center_px = int((center_x - origin_x) / map_width * (img_width - 1))
    center_py = int((center_y - origin_y) / map_height * (img_height - 1))
    center_px = max(0, min(center_px, img_width - 1))
    center_py = max(0, min(center_py, img_height - 1))

    # Determine local average height in the base area
    local_heights = []
    for py in range(img_height):
        for px in range(img_width):
            world_x = origin_x + (px / (img_width - 1)) * map_width
            world_y = origin_y + (py / (img_height - 1)) * map_height
            if (
                math.sqrt((world_x - center_x) ** 2 + (world_y - center_y) ** 2)
                <= radius
            ):
                local_heights.append(float(heightmap[py, px]))

    if local_heights:
        local_avg = sum(local_heights) / len(local_heights)
    else:
        local_avg = float(heightmap[center_py, center_px])

    plateau_radius = radius * 0.8
    falloff_dist = radius - plateau_radius

    for py in range(img_height):
        for px in range(img_width):
            world_x = origin_x + (px / (img_width - 1)) * map_width
            world_y = origin_y + (py / (img_height - 1)) * map_height

            dist = math.sqrt((world_x - center_x) ** 2 + (world_y - center_y) ** 2)

            if dist < radius:
                if dist <= plateau_radius:
                    t = 1.0
                else:
                    # Smooth step falloff
                    t = 1.0 - ((dist - plateau_radius) / falloff_dist)
                    t = t * t * (3 - 2 * t)

                t = t * flatness

                if blend_to_avg:
                    target_height = local_avg
                else:
                    target_height = float(heightmap[center_py, center_px])

                flat_heightmap[py, px] = (
                    flat_heightmap[py, px] * (1 - t) + target_height * t
                )

    return flat_heightmap


def calculate_yaw_to_center(
    origin_x: float, origin_y: float, target_x: float, target_y: float
) -> float:
    """Calculate yaw angle in degrees pointing from origin to target."""
    dx = target_x - origin_x
    dy = target_y - origin_y
    angle = math.degrees(math.atan2(dy, dx))
    return angle


def get_terrain_height_at(
    world_x: float,
    world_y: float,
    heightmap: np.ndarray,
    origin_x: int,
    origin_y: int,
    map_width: int,
    map_height: int,
    max_height: int,
    tiles_x: int = 8,
    tiles_y: int = 8,
    power: int = 3,
) -> float:
    """Sample terrain height at world coordinates from heightmap.

    Uses strided sampling to match displacement vertex positions.
    """
    if heightmap is None:
        return float(max_height)

    img_height, img_width = heightmap.shape
    grid_size = (2**power) + 1
    cell_size = map_width / (tiles_x * (grid_size - 1))

    nearest_vx = round((world_x - origin_x) / cell_size)
    nearest_vy = round((world_y - origin_y) / cell_size)
    nearest_vx = max(0, min(nearest_vx, img_width - 1))
    nearest_vy = max(0, min(nearest_vy, img_height - 1))

    normalized_height = float(heightmap[nearest_vy, nearest_vx])
    return (normalized_height / 255.0) * max_height
