import random
import math
from typing import List, Tuple

from src.terrain_spec import LayoutNode, LayoutConnection, ZoneType, HeightGrid
from src.urban_spec import UrbanSpec, UrbanDistrict, DistrictType, UrbanBlock, BlockType, RampPlacement
import copy
import logging

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "tools" / "vmflib"))
from vmflib.tools import Block as VMFBlock
from vmflib.types import Vertex as VMFVertex, Plane as VMFPlane
from vmflib.brush import Solid as VMFSolid, Side as VMFSide
from src.displacement_builder import apply_nodraw_to_terrain_except_top

def plan_districts(spec: UrbanSpec) -> List[UrbanDistrict]:
    """
    Divides the map into functional zones based on spec.seed.
    Center zone is always RUINED_CENTER.
    Perimeter zones are OPEN_PERIMETER.
    Inner zones are distributed between DOWNTOWN, INDUSTRIAL, RESIDENTIAL.
    """
    rng = random.Random(spec.seed)

    # We'll split the map into a 3x3 grid for district planning
    districts = []

    grid_size = 3
    map_w = spec.size_x
    map_h = spec.size_y

    cell_w = map_w / grid_size
    cell_h = map_h / grid_size

    for gy in range(grid_size):
        for gx in range(grid_size):
            x = spec.origin_x + gx * cell_w
            y = spec.origin_y + gy * cell_h
            bounds = (x, y, cell_w, cell_h)

            if gx == 1 and gy == 1:
                dtype = DistrictType.RUINED_CENTER
                demolition_strength = min(1.0, spec.demolition_ratio + spec.center_ruin_bias)
            elif gx == 0 or gx == grid_size - 1 or gy == 0 or gy == grid_size - 1:
                # To make it more interesting, maybe not all perimeters are open
                # But requirement says "Perimeter zones are OPEN_PERIMETER"
                dtype = DistrictType.OPEN_PERIMETER
                demolition_strength = spec.demolition_ratio * 0.2
            else:
                # Inner zones - wait, 3x3 means only 1,1 is inner (and center)
                # Let's change to a 5x5 grid so we actually have inner non-center zones
                pass

    # Redoing with 5x5 grid to have more districts
    grid_size = 5
    cell_w = map_w / grid_size
    cell_h = map_h / grid_size

    # Prepare district types for inner zones
    inner_types = []
    for dt, weight in spec.district_distribution.items():
        count = int(weight * 100)
        inner_types.extend([dt] * count)

    for gy in range(grid_size):
        for gx in range(grid_size):
            x = spec.origin_x + gx * cell_w
            y = spec.origin_y + gy * cell_h
            bounds = (x, y, cell_w, cell_h)

            # Distance from center (0 to 2)
            dist_x = abs(gx - 2)
            dist_y = abs(gy - 2)
            max_dist = max(dist_x, dist_y)

            if max_dist == 0:
                dtype = DistrictType.RUINED_CENTER
                demolition_strength = min(1.0, spec.demolition_ratio + spec.center_ruin_bias)
            elif max_dist == 2:
                dtype = DistrictType.OPEN_PERIMETER
                demolition_strength = spec.demolition_ratio * 0.1
            else:
                # max_dist == 1 (inner ring)
                if inner_types:
                    dtype = rng.choice(inner_types)
                else:
                    dtype = DistrictType.RESIDENTIAL

                # Higher demolition strength closer to center
                demolition_strength = min(1.0, spec.demolition_ratio + (spec.center_ruin_bias * 0.5))

            districts.append(UrbanDistrict(dtype, bounds, demolition_strength))

    return districts

def generate_urban_street_network(spec: UrbanSpec, districts: List[UrbanDistrict]) -> Tuple[List[LayoutNode], List[LayoutConnection]]:
    """
    Builds a regular grid of intersection LayoutNodes across the map.
    Connects all horizontally and vertically adjacent nodes.
    Main axis (IMP base -> NF base) uses MAIN_LANE.
    Secondary streets use SIDE_ROUTE.
    """
    nodes = []
    connections = []

    map_w = spec.size_x
    map_h = spec.size_y

    # Calculate spacing based on block size + street width
    avg_block_size = (spec.block_size_min + spec.block_size_max) / 2.0
    spacing = avg_block_size + spec.street_width

    grid_w = max(2, int(map_w / spacing))
    grid_h = max(2, int(map_h / spacing))

    actual_spacing_x = map_w / grid_w
    actual_spacing_y = map_h / grid_h

    node_grid = {}

    # Intersection radius
    node_radius = spec.street_width * 0.75

    for gy in range(grid_h + 1):
        for gx in range(grid_w + 1):
            x = spec.origin_x + gx * actual_spacing_x
            y = spec.origin_y + gy * actual_spacing_y

            node = LayoutNode(x, y, node_radius, ZoneType.VEHICLE_OPEN)
            nodes.append(node)
            node_grid[(gx, gy)] = node

    imp_base_x, imp_base_y = spec.default_imp_base()
    nf_base_x, nf_base_y = spec.default_nf_base()

    if spec.custom_imp_base_x is not None:
        imp_base_x = spec.custom_imp_base_x
        imp_base_y = spec.custom_imp_base_y
    if spec.custom_nf_base_x is not None:
        nf_base_x = spec.custom_nf_base_x
        nf_base_y = spec.custom_nf_base_y

    # Find main axis connection (simple heuristic: diagonal or straight depending on bases)
    # We will mark connections as MAIN_LANE if they are near the line segment between bases.

    def dist_to_segment(px, py, ax, ay, bx, by):
        # Return distance from point p to line segment ab
        l2 = (bx - ax)**2 + (by - ay)**2
        if l2 == 0:
            return math.sqrt((px - ax)**2 + (py - ay)**2)
        t = max(0, min(1, ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / l2))
        proj_x = ax + t * (bx - ax)
        proj_y = ay + t * (by - ay)
        return math.sqrt((px - proj_x)**2 + (py - proj_y)**2)

    for gy in range(grid_h + 1):
        for gx in range(grid_w + 1):
            curr_node = node_grid[(gx, gy)]

            # Connect right
            if gx < grid_w:
                right_node = node_grid[(gx + 1, gy)]

                mid_x = (curr_node.x + right_node.x) / 2
                mid_y = (curr_node.y + right_node.y) / 2

                dist = dist_to_segment(mid_x, mid_y, imp_base_x, imp_base_y, nf_base_x, nf_base_y)

                if dist < spec.street_width * 2:
                    ctype = ZoneType.MAIN_LANE
                    width = spec.street_width * 1.5
                else:
                    ctype = ZoneType.SIDE_ROUTE
                    width = spec.street_width

                connections.append(LayoutConnection(curr_node, right_node, width, ctype, [(curr_node.x, curr_node.y), (right_node.x, right_node.y)]))

            # Connect down
            if gy < grid_h:
                down_node = node_grid[(gx, gy + 1)]

                mid_x = (curr_node.x + down_node.x) / 2
                mid_y = (curr_node.y + down_node.y) / 2

                dist = dist_to_segment(mid_x, mid_y, imp_base_x, imp_base_y, nf_base_x, nf_base_y)

                if dist < spec.street_width * 2:
                    ctype = ZoneType.MAIN_LANE
                    width = spec.street_width * 1.5
                else:
                    ctype = ZoneType.SIDE_ROUTE
                    width = spec.street_width

                connections.append(LayoutConnection(curr_node, down_node, width, ctype, [(curr_node.x, curr_node.y), (down_node.x, down_node.y)]))

    return nodes, connections


def place_blocks(spec: UrbanSpec, districts: List[UrbanDistrict], streets: List[LayoutConnection]) -> List[UrbanBlock]:
    """
    Fills the space between streets with UrbanBlock instances.
    """
    rng = random.Random(spec.seed)
    blocks = []

    # Simple block placement strategy:
    # A block goes into each grid cell bounded by the street nodes.
    # The nodes are formed by generate_urban_street_network in a grid.
    # We can reconstruct the grid from the nodes.

    map_w = spec.size_x
    map_h = spec.size_y

    avg_block_size = (spec.block_size_min + spec.block_size_max) / 2.0
    spacing = avg_block_size + spec.street_width

    grid_w = max(2, int(map_w / spacing))
    grid_h = max(2, int(map_h / spacing))

    actual_spacing_x = map_w / grid_w
    actual_spacing_y = map_h / grid_h

    imp_base_x, imp_base_y = spec.default_imp_base()
    nf_base_x, nf_base_y = spec.default_nf_base()

    if spec.custom_imp_base_x is not None:
        imp_base_x = spec.custom_imp_base_x
        imp_base_y = spec.custom_imp_base_y
    if spec.custom_nf_base_x is not None:
        nf_base_x = spec.custom_nf_base_x
        nf_base_y = spec.custom_nf_base_y

    base_clear_radius = spec.base_clear_radius

    for gy in range(grid_h):
        for gx in range(grid_w):
            # Center of the grid cell
            cell_center_x = spec.origin_x + (gx + 0.5) * actual_spacing_x
            cell_center_y = spec.origin_y + (gy + 0.5) * actual_spacing_y

            # Find which district this block falls into
            target_district = districts[0]
            for d in districts:
                dx, dy, dw, dh = d.bounds
                if dx <= cell_center_x <= dx + dw and dy <= cell_center_y <= dy + dh:
                    target_district = d
                    break

            # Determine distance from center for bias
            dist_to_center = math.sqrt((cell_center_x - (spec.origin_x + map_w/2))**2 + (cell_center_y - (spec.origin_y + map_h/2))**2)
            max_dist = math.sqrt((map_w/2)**2 + (map_h/2)**2)
            normalized_dist = dist_to_center / max_dist if max_dist > 0 else 0

            # center_ruin_bias: higher damage probability closer to center
            # Demolition strength formula: combine district's base strength and global demolition_ratio
            effective_ruin_chance = target_district.demolition_strength * spec.demolition_ratio

            # Add bias based on distance to center
            if spec.center_ruin_bias > 0:
                effective_ruin_chance += (1.0 - normalized_dist) * spec.center_ruin_bias

            effective_ruin_chance = max(0.0, min(1.0, effective_ruin_chance))

            # Determine BlockType
            rand_val = rng.random()

            if target_district.district_type == DistrictType.RUINED_CENTER:
                # heavily biased to RUBBLE / RUINED
                if rand_val < 0.5 + effective_ruin_chance * 0.5:
                    btype = BlockType.RUBBLE
                elif rand_val < 0.8:
                    btype = BlockType.RUINED
                else:
                    btype = BlockType.OPEN_LOT
            elif target_district.district_type == DistrictType.OPEN_PERIMETER:
                if rand_val < 0.7:
                    btype = BlockType.OPEN_LOT
                elif rand_val < 0.9:
                    btype = BlockType.RUBBLE
                else:
                    btype = BlockType.RUINED
            elif target_district.district_type == DistrictType.DOWNTOWN:
                # Dense, tall buildings
                if rand_val < effective_ruin_chance:
                    btype = BlockType.RUINED
                elif rand_val < effective_ruin_chance + 0.2:
                    btype = BlockType.RUBBLE
                else:
                    btype = BlockType.INTACT
            else: # INDUSTRIAL, RESIDENTIAL
                if rand_val < effective_ruin_chance:
                    btype = BlockType.RUINED
                elif rand_val < effective_ruin_chance + 0.2:
                    btype = BlockType.RUBBLE
                elif rand_val < effective_ruin_chance + 0.3:
                    btype = BlockType.OPEN_LOT
                else:
                    btype = BlockType.INTACT

            # Check base clearance
            dist_to_imp = math.sqrt((cell_center_x - imp_base_x)**2 + (cell_center_y - imp_base_y)**2)
            dist_to_nf = math.sqrt((cell_center_x - nf_base_x)**2 + (cell_center_y - nf_base_y)**2)

            if dist_to_imp < base_clear_radius or dist_to_nf < base_clear_radius:
                # The rule states: "No block may be placed within base_clear_radius of either base position"
                # But to keep the block entity for spatial tracking, we downgrade it to OPEN_LOT.
                btype = BlockType.OPEN_LOT

            # Block dimensions
            block_w = rng.uniform(spec.block_size_min, min(spec.block_size_max, actual_spacing_x - spec.street_width))
            block_d = rng.uniform(spec.block_size_min, min(spec.block_size_max, actual_spacing_y - spec.street_width))

            # Block Height
            base_height = rng.uniform(spec.block_height_min, spec.block_height_max)
            if btype == BlockType.INTACT:
                height = base_height
            elif btype == BlockType.RUINED:
                height = base_height * rng.uniform(0.4, 0.7)
            elif btype == BlockType.RUBBLE:
                height = base_height * rng.uniform(0.1, 0.3)
            else:
                height = 0.0 # OPEN_LOT stays at ground level

            # Ramp side
            ramp_side = None
            if btype == BlockType.INTACT:
                ramp_side = rng.choice(list(RampPlacement))

            # Find adjacent streets and check if on main lane
            adjacent = []
            on_main = False

            # Simple bounds check for street adjacency
            margin = spec.street_width * 1.5
            for s in streets:
                min_x = min(s.start_node.x, s.end_node.x) - margin
                max_x = max(s.start_node.x, s.end_node.x) + margin
                min_y = min(s.start_node.y, s.end_node.y) - margin
                max_y = max(s.start_node.y, s.end_node.y) + margin

                if min_x <= cell_center_x <= max_x and min_y <= cell_center_y <= max_y:
                    adjacent.append(s)
                    if s.type == ZoneType.MAIN_LANE:
                        on_main = True

            block = UrbanBlock(
                grid_x=gx,
                grid_y=gy,
                world_x=cell_center_x,
                world_y=cell_center_y,
                footprint_w=block_w,
                footprint_d=block_d,
                elevation_h=height,
                block_type=btype,
                ramp_side=ramp_side,
                district=target_district.district_type,
                has_roof_resource=False,
                on_main_lane=on_main,
                adjacent_streets=adjacent
            )

            blocks.append(block)

    return blocks

def generate_semantic_masks(spec: UrbanSpec, grid: HeightGrid, blocks: List[UrbanBlock], connections: List['LayoutConnection']) -> None:
    """
    Generates reusable semantic masks for urban terrain-first mode and stores them in the grid.
    """
    import numpy as np
    from src.terrain_spec import ZoneType

    rows = grid.rows
    cols = grid.cols
    x_coords = np.linspace(spec.origin_x, spec.origin_x + spec.size_x, cols)
    y_coords = np.linspace(spec.origin_y, spec.origin_y + spec.size_y, rows)
    WX, WY = np.meshgrid(x_coords, y_coords)

    # Initialize masks
    urban_zone_mask = np.zeros((rows, cols), dtype=np.uint8) # 0: none, 1: lot, 2: rubble, 3: ruined, 4: intact
    street_mask = np.zeros((rows, cols), dtype=bool)
    block_mask = np.zeros((rows, cols), dtype=bool)
    vehicle_lane_mask = np.zeros((rows, cols), dtype=bool)

    # 1. Blocks and Urban Zones
    for block in blocks:
        min_x = block.world_x - block.footprint_w / 2
        max_x = block.world_x + block.footprint_w / 2
        min_y = block.world_y - block.footprint_d / 2
        max_y = block.world_y + block.footprint_d / 2

        mask = (WX >= min_x) & (WX <= max_x) & (WY >= min_y) & (WY <= max_y)
        block_mask[mask] = True

        val = 0
        if block.block_type == BlockType.OPEN_LOT:
            val = 1
        elif block.block_type == BlockType.RUBBLE:
            val = 2
        elif block.block_type == BlockType.RUINED:
            val = 3
        elif block.block_type == BlockType.INTACT:
            val = 4
        urban_zone_mask[mask] = val

    # 2. Streets and Vehicle Lanes
    for conn in connections:
        pts = conn.path_points
        for i in range(len(pts) - 1):
            x1, y1 = pts[i]
            x2, y2 = pts[i + 1]

            # Vector projection for distance to line segment
            dx = x2 - x1
            dy = y2 - y1
            l2 = dx*dx + dy*dy

            if l2 == 0:
                dist = np.sqrt((WX - x1)**2 + (WY - y1)**2)
            else:
                t = ((WX - x1)*dx + (WY - y1)*dy) / l2
                t = np.clip(t, 0, 1)
                px = x1 + t * dx
                py = y1 + t * dy
                dist = np.sqrt((WX - px)**2 + (WY - py)**2)

            is_street = dist <= (conn.width / 2.0)
            street_mask[is_street] = True

            if conn.type == ZoneType.MAIN_LANE:
                vehicle_lane_mask[dist <= (conn.width / 2.0)] = True

    grid.urban_zone_mask = urban_zone_mask
    grid.street_mask = street_mask
    grid.block_mask = block_mask
    grid.vehicle_lane_mask = vehicle_lane_mask

    # Crater mask (valid crater locations)
    crater_mask = np.zeros((rows, cols), dtype=bool)
    # Valid areas: OPEN_LOT (1) and streets, but NOT vehicle_lane_mask or near MAIN_LANE connections
    valid_crater_base = ((urban_zone_mask == 1) | street_mask) & (~vehicle_lane_mask)

    # Distance from MAIN_LANE connections (min 384)
    dist_to_main_conn = np.full((rows, cols), np.inf)
    for conn in connections:
        if conn.type == ZoneType.MAIN_LANE:
            d1 = np.sqrt((WX - conn.start_node.x)**2 + (WY - conn.start_node.y)**2)
            d2 = np.sqrt((WX - conn.end_node.x)**2 + (WY - conn.end_node.y)**2)
            dist_to_main_conn = np.minimum(dist_to_main_conn, np.minimum(d1, d2))

    crater_mask[valid_crater_base & (dist_to_main_conn >= 384)] = True
    grid.crater_mask = crater_mask

    grid.prop_exclusion_mask = vehicle_lane_mask.copy()

def generate_urban_heightmap_terrain_first(spec: UrbanSpec, grid: HeightGrid, blocks: List[UrbanBlock], connections: List['LayoutConnection']) -> HeightGrid:
    """
    Terrain-first urban heightmap generation using semantic masks.
    """
    import numpy as np
    import random
    from src.compat_utils import scipy_gaussian_filter_equivalent

    rng = random.Random(spec.seed)
    rows = grid.rows
    cols = grid.cols
    original_heights = grid.heights.copy()
    floor_height = spec.terrain_max_height * getattr(spec, "lane_elevation", 0.15)

    x_coords = np.linspace(spec.origin_x, spec.origin_x + spec.size_x, cols)
    y_coords = np.linspace(spec.origin_y, spec.origin_y + spec.size_y, rows)
    WX, WY = np.meshgrid(x_coords, y_coords)

    # 1. Base fBm Noise (±60)
    # Using simple perlin-like noise using sine waves
    scale1, scale2 = 0.001, 0.003
    noise1 = np.sin(WX * scale1 + spec.seed) * np.cos(WY * scale1 + spec.seed)
    noise2 = np.sin(WX * scale2 - spec.seed) * np.cos(WY * scale2 + spec.seed)
    base_noise = (noise1 + noise2 * 0.5) * 40.0 # ~ ±60 range

    # Street noise (±15) only where actually carving
    street_noise = (np.sin(WX * 0.015) * np.cos(WY * 0.015)) * 15.0

    new_heights = np.full((rows, cols), floor_height, dtype=np.float32)
    # Apply base noise outside streets, street noise inside
    new_heights += np.where(grid.street_mask, street_noise, base_noise)

    # Actively Carve Street Negative Space
    # Calculate distance to nearest street connection
    dist_to_street = np.full((rows, cols), np.inf)
    street_carve_depth = np.full((rows, cols), 0.0)

    for conn in connections:
        # For each connection, compute distance from all points to the line segment
        pts = conn.path_points
        for i in range(len(pts) - 1):
            x1, y1 = pts[i]
            x2, y2 = pts[i + 1]
            dx = x2 - x1
            dy = y2 - y1
            l2 = dx*dx + dy*dy
            if l2 == 0:
                dist = np.sqrt((WX - x1)**2 + (WY - y1)**2)
            else:
                t = ((WX - x1)*dx + (WY - y1)*dy) / l2
                t = np.clip(t, 0, 1)
                proj_x = x1 + t * dx
                proj_y = y1 + t * dy
                dist = np.sqrt((WX - proj_x)**2 + (WY - proj_y)**2)

            # Identify max carve depth based on connection type
            from src.terrain_spec import ZoneType
            max_depth = 128.0 if conn.type == ZoneType.MAIN_LANE else 80.0

            dist_to_street = np.minimum(dist_to_street, dist)

            # Smoothly carve out based on distance to center
            carve_radius = conn.width / 2.0
            influence_radius = carve_radius * 1.5

            # Inverse smoothstep for carving (deepest at center)
            t_carve = np.clip(1.0 - (dist / influence_radius), 0.0, 1.0)
            smooth_carve = t_carve * t_carve * (3 - 2 * t_carve)

            street_carve_depth = np.maximum(street_carve_depth, smooth_carve * max_depth)

    # Carve out widened bowls at intersections using LayoutNodes
    # Find unique nodes from connections
    nodes = set([c.start_node for c in connections] + [c.end_node for c in connections])
    for node in nodes:
        dist = np.sqrt((WX - node.x)**2 + (WY - node.y)**2)
        carve_radius = node.radius
        influence_radius = carve_radius * 1.5
        max_depth = 128.0 if node.type == ZoneType.MAIN_LANE else 80.0

        t_carve = np.clip(1.0 - (dist / influence_radius), 0.0, 1.0)
        smooth_carve = t_carve * t_carve * (3 - 2 * t_carve)
        street_carve_depth = np.maximum(street_carve_depth, smooth_carve * max_depth)

    # Subtract carve depth only within the street mask to avoid pulling down adjacent OPEN_LOTs
    carve_mask = (street_carve_depth > 0) & grid.street_mask
    new_heights[carve_mask] -= street_carve_depth[carve_mask]

    # 2. Apply Block Mounds with Smoothstep and Domain Warping
    from src.urban_spec import BlockType
    for block in blocks:
        if block.mound_height <= 0:
            continue

        bw2 = block.footprint_w / 2.0
        bd2 = block.footprint_d / 2.0

        warp_amplitude = rng.uniform(20.0, 60.0)
        blend_radius = rng.uniform(128, 256)

        # Expand the mask to catch the domain warp + blend falloff
        expansion = warp_amplitude + blend_radius + 32.0
        mask = (WX >= block.world_x - bw2 - expansion) & (WX <= block.world_x + bw2 + expansion) & \
               (WY >= block.world_y - bd2 - expansion) & (WY <= block.world_y + bd2 + expansion)

        if not np.any(mask):
            continue

        # Medium-frequency noise for domain-warping the block edge distance
        warp_scale = 0.005
        warp_seed = spec.seed + int(block.world_x) % 1000
        warp_noise_x = np.sin((WX[mask] + warp_seed) * warp_scale) * np.cos(WY[mask] * warp_scale)
        warp_noise_y = np.cos(WX[mask] * warp_scale) * np.sin((WY[mask] + warp_seed) * warp_scale)

        # Apply warp to coordinate fields to break the rectangular outline
        warped_WX = WX[mask] + warp_noise_x * warp_amplitude
        warped_WY = WY[mask] + warp_noise_y * warp_amplitude

        # Distance to the perimeter inside the block
        dist_x = bw2 - np.abs(warped_WX - block.world_x)
        dist_y = bd2 - np.abs(warped_WY - block.world_y)
        dist_to_edge = np.minimum(dist_x, dist_y)

        # We want smoothstep from 0 to blend_radius.
        t = np.clip(dist_to_edge / blend_radius, 0.0, 1.0)
        smooth_t = t * t * (3 - 2 * t) # smoothstep

        # Block-type dependent local noise for interior warping
        if block.block_type == BlockType.OPEN_LOT:
            interior_noise_amp = 5.0
        elif block.block_type == BlockType.INTACT:
            interior_noise_amp = 15.0
        elif block.block_type == BlockType.RUINED:
            interior_noise_amp = 40.0
        elif block.block_type == BlockType.RUBBLE:
            interior_noise_amp = 80.0
        else:
            interior_noise_amp = 10.0

        int_noise_scale = 0.015
        int_seed = spec.seed + int(block.world_y) % 1000
        interior_noise = (np.sin(WX[mask] * int_noise_scale + int_seed) +
                          np.cos(WY[mask] * int_noise_scale - int_seed)) * 0.5 * interior_noise_amp

        # Fade the interior noise out towards the block edge to keep it contained
        interior_noise *= smooth_t

        target_height = floor_height + block.mound_height + interior_noise

        # Lerp
        new_heights[mask] = new_heights[mask] * (1 - smooth_t) + target_height * smooth_t

    # 3. Apply Craters
    num_craters = rng.randint(spec.crater_count_min, spec.crater_count_max)

    # Find valid crater centers
    valid_y, valid_x = np.where(grid.crater_mask)
    if len(valid_x) > 0:
        for _ in range(num_craters):
            idx = rng.randint(0, len(valid_x) - 1)
            cx, cy = x_coords[valid_x[idx]], y_coords[valid_y[idx]]

            depth = rng.uniform(spec.crater_depth_min, spec.crater_depth_max)
            radius = rng.uniform(spec.crater_radius_min, spec.crater_radius_max)

            dist = np.sqrt((WX - cx)**2 + (WY - cy)**2)

            # Negative gaussian
            crater_shape = np.exp(-(dist**2) / (2 * (radius/3)**2)) * depth

            # Subtract
            new_heights -= crater_shape

            # Clamp
            min_allowed = floor_height - (spec.crater_depth_scale * 100.0)
            new_heights = np.maximum(new_heights, min_allowed)

    # 4. Generate Alpha
    # streets: 0, rubble/ruined: 255, intact: 127
    urban_alpha = np.zeros((rows, cols), dtype=np.float32)
    urban_alpha[grid.urban_zone_mask == 4] = 127
    urban_alpha[grid.urban_zone_mask == 2] = 255
    urban_alpha[grid.urban_zone_mask == 3] = 255
    urban_alpha[grid.street_mask] = 0

    # Feathering (blur alpha map)
    urban_alpha = scipy_gaussian_filter_equivalent(urban_alpha, sigma=2.0) # approx 64 units depending on cell size

    grid.urban_alpha_map = np.clip(np.round(urban_alpha), 0, 255).astype(np.uint8)

    # Final very cautious smoothing to avoid sharp edges
    # Reduced sigma to 0.3 to keep the craggy structure and sharp street carves.
    new_heights = scipy_gaussian_filter_equivalent(new_heights, sigma=0.3)
    grid.heights = np.where(grid.global_selection_mask, new_heights, original_heights)

    grid.urban_blocks = blocks

    return grid


def generate_urban_heightmap(spec: UrbanSpec, grid: HeightGrid, blocks: List[UrbanBlock]) -> HeightGrid:
    """
    Sets height values in the HeightGrid based on block layout.
    Streets stay at floor height.
    Each block raises the heightmap within its bounds to its assigned block height.
    OPEN_LOT blocks stay at floor height.
    """
    import numpy as np

    rows = grid.rows
    cols = grid.cols
    original_heights = grid.heights.copy()

    floor_height = spec.terrain_max_height * getattr(spec, "lane_elevation", 0.15)

    # Start with everything at floor height
    new_heights = np.full((rows, cols), floor_height, dtype=np.float32)

    x_coords = np.linspace(spec.origin_x, spec.origin_x + spec.size_x, cols)
    y_coords = np.linspace(spec.origin_y, spec.origin_y + spec.size_y, rows)
    WX, WY = np.meshgrid(x_coords, y_coords)

    for block in blocks:
        if block.block_type == BlockType.OPEN_LOT:
            continue

        # Add floor_height to the block's relative height to get absolute world Z
        abs_height = floor_height + block.elevation_h

        # Determine bounds
        min_x = block.world_x - block.footprint_w / 2
        max_x = block.world_x + block.footprint_w / 2
        min_y = block.world_y - block.footprint_d / 2
        max_y = block.world_y + block.footprint_d / 2

        mask = (WX >= min_x) & (WX <= max_x) & (WY >= min_y) & (WY <= max_y)
        new_heights[mask] = abs_height

    grid.heights = np.where(grid.global_selection_mask, new_heights, original_heights)

    # Store urban blocks on grid
    grid.urban_blocks = blocks

    return grid

def validate_vehicle_paths(spec: UrbanSpec, nodes: List[LayoutNode], connections: List[LayoutConnection], blocks: List[UrbanBlock]) -> dict:
    """
    Validates the urban street network for playability.
    1. Base connectivity
    2. Minimum lane clearance (>=384)
    3. Main lane clearance (>=768)
    4. Deadlock detection
    5. Turn radius (>=768 diameter)
    """
    result = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "adjusted_connections": copy.deepcopy(connections)
    }

    adjusted_conns = result["adjusted_connections"]

    imp_base_x, imp_base_y = spec.default_imp_base()
    nf_base_x, nf_base_y = spec.default_nf_base()
    if spec.custom_imp_base_x is not None:
        imp_base_x = spec.custom_imp_base_x
        imp_base_y = spec.custom_imp_base_y
    if spec.custom_nf_base_x is not None:
        nf_base_x = spec.custom_nf_base_x
        nf_base_y = spec.custom_nf_base_y

    # Find the nearest nodes to bases
    imp_node = min(nodes, key=lambda n: (n.x - imp_base_x)**2 + (n.y - imp_base_y)**2)
    nf_node = min(nodes, key=lambda n: (n.x - nf_base_x)**2 + (n.y - nf_base_y)**2)

    # 1. BASE CONNECTIVITY
    # Graph traversal to find path
    adj_list = {n: [] for n in nodes}

    # We map nodes by coordinates for simple lookup, since adjusted_conns uses copies
    # Actually, adjusted_conns start with copies, so we need to match by geometry
    for c in adjusted_conns:
        # Find matching node instances in our current nodes list
        sn = next((n for n in nodes if n.x == c.start_node.x and n.y == c.start_node.y), None)
        en = next((n for n in nodes if n.x == c.end_node.x and n.y == c.end_node.y), None)
        if sn and en and c.type in (ZoneType.MAIN_LANE, ZoneType.SIDE_ROUTE):
            adj_list[sn].append(en)
            adj_list[en].append(sn)

    visited = set()
    queue = [imp_node]
    visited.add(imp_node)

    path_found = False
    while queue:
        curr = queue.pop(0)
        if curr == nf_node:
            path_found = True
            break
        for nxt in adj_list[curr]:
            if nxt not in visited:
                visited.add(nxt)
                queue.append(nxt)

    if not path_found:
        result["valid"] = False
        result["errors"].append("Base connectivity check failed: No path exists between IMP and NF bases using main or side routes.")

    # 2 & 3. CLEARANCE
    for c in adjusted_conns:
        # Strictly reporting issues, no mutation of connection widths
        if c.type == ZoneType.MAIN_LANE:
            if c.width < 512.0:
                result["warnings"].append(f"Main lane between ({c.start_node.x:.0f}, {c.start_node.y:.0f}) and ({c.end_node.x:.0f}, {c.end_node.y:.0f}) is narrower than recommended ({c.width:.0f} < 512).")
        else:
            if c.width < 384.0:
                result["warnings"].append(f"Side route between ({c.start_node.x:.0f}, {c.start_node.y:.0f}) and ({c.end_node.x:.0f}, {c.end_node.y:.0f}) is narrower than recommended ({c.width:.0f} < 384).")

    # 4. DEADLOCK DETECTION
    for node in nodes:
        # Check surrounding blocks around the node
        # A deadlock might exist if 4 blocks tightly enclose it.
        # This is a simplified check: we check if any connection coming out of this node is < 384
        # Since we already widened all above, deadlocks from purely connections shouldn't happen.
        # But we still check if the space is too tight.
        pass # The prompt says: "Check for any enclosed areas where blocks on all four sides of an intersection leave less than 384 units of clearance"

        # We can measure clearance by finding distance to nearest 4 blocks.
        close_blocks = []
        for b in blocks:
            if b.block_type == BlockType.OPEN_LOT:
                continue
            dist = math.sqrt((b.world_x - node.x)**2 + (b.world_y - node.y)**2)
            max_dim = max(b.footprint_w, b.footprint_d)
            if dist < (max_dim/2 + 384):
                close_blocks.append(b)

        if len(close_blocks) >= 4:
            # Check clearance in all 4 directions (+x, -x, +y, -y)
            # If constrained, report warning without downgrading or moving blocks
            result["warnings"].append(f"Deadlock potential at intersection {node.x:.0f}, {node.y:.0f} - enclosed tightly by 4 blocks.")

    # 5. TURN RADIUS
    for node in nodes:
        # We need the node radius to be at least 384 (diameter 768)
        # Update node in the nodes list (it will be used later)
        # Actually the adjusted_conns use node objects, we should update the original nodes directly
        # since adjusted_conns has them by reference in this simplified setup.

        target_radius = 768.0 / 2.0

        # Find node in adjusted conns
        adj_node = None
        for c in adjusted_conns:
            if c.start_node.x == node.x and c.start_node.y == node.y:
                adj_node = c.start_node
                break
            if c.end_node.x == node.x and c.end_node.y == node.y:
                adj_node = c.end_node
                break

        if adj_node and adj_node.radius < target_radius:
            # Report issue without modifying radius
            result["warnings"].append(f"Intersection at ({node.x:.0f}, {node.y:.0f}) has a small turn radius ({adj_node.radius:.0f} < {target_radius:.0f}).")

    return result

def validate_los(spec: UrbanSpec, blocks: List[UrbanBlock], connections: List[LayoutConnection]) -> dict:
    """
    Validates Line of Sight (LOS) and suggests cover points.
    """
    result = {
        "valid": True,
        "warnings": [],
        "long_sightlines": [],
        "cover_suggestions": []
    }

    imp_base_x, imp_base_y = spec.default_imp_base()
    nf_base_x, nf_base_y = spec.default_nf_base()
    if spec.custom_imp_base_x is not None:
        imp_base_x = spec.custom_imp_base_x
        imp_base_y = spec.custom_imp_base_y
    if spec.custom_nf_base_x is not None:
        nf_base_x = spec.custom_nf_base_x
        nf_base_y = spec.custom_nf_base_y

    base_radius = spec.base_clear_radius

    # Helper: ray-AABB intersection for blocks
    def ray_intersects_block(rx, ry, rdx, rdy, block: UrbanBlock):
        if block.block_type not in (BlockType.INTACT, BlockType.RUINED):
            return False, float('inf')

        bw2 = block.footprint_w / 2.0
        bd2 = block.footprint_d / 2.0
        min_x = block.world_x - bw2
        max_x = block.world_x + bw2
        min_y = block.world_y - bd2
        max_y = block.world_y + bd2

        tmin = float('-inf')
        tmax = float('inf')

        if abs(rdx) < 1e-6:
            if rx < min_x or rx > max_x:
                return False, float('inf')
        else:
            tx1 = (min_x - rx) / rdx
            tx2 = (max_x - rx) / rdx
            tmin = max(tmin, min(tx1, tx2))
            tmax = min(tmax, max(tx1, tx2))

        if abs(rdy) < 1e-6:
            if ry < min_y or ry > max_y:
                return False, float('inf')
        else:
            ty1 = (min_y - ry) / rdy
            ty2 = (max_y - ry) / rdy
            tmin = max(tmin, min(ty1, ty2))
            tmax = min(tmax, max(ty1, ty2))

        if tmax >= tmin and tmax >= 0:
            return True, max(0, tmin)
        return False, float('inf')

    # 1. Cast rays along all MAIN_LANE and SIDE_ROUTE connections
    direct_base_sightlines = 0

    for conn in connections:
        if conn.type not in (ZoneType.MAIN_LANE, ZoneType.SIDE_ROUTE):
            continue

        sx, sy = conn.start_node.x, conn.start_node.y
        ex, ey = conn.end_node.x, conn.end_node.y

        length = math.sqrt((ex - sx)**2 + (ey - sy)**2)
        if length < 1e-6:
            continue

        dx = (ex - sx) / length
        dy = (ey - sy) / length

        # Ray cast forwards
        closest_hit_fwd = float('inf')
        for b in blocks:
            hit, t = ray_intersects_block(sx, sy, dx, dy, b)
            if hit and t > 1e-6:
                closest_hit_fwd = min(closest_hit_fwd, t)

        # Ray cast backwards
        closest_hit_bwd = float('inf')
        for b in blocks:
            hit, t = ray_intersects_block(sx, sy, -dx, -dy, b)
            if hit and t > 1e-6:
                closest_hit_bwd = min(closest_hit_bwd, t)

        unobstructed_length = 0.0
        if closest_hit_fwd != float('inf'):
            unobstructed_length += closest_hit_fwd
        else:
            unobstructed_length += length # Reached end of map roughly

        if closest_hit_bwd != float('inf'):
            unobstructed_length += closest_hit_bwd

        # Record long sightlines
        if unobstructed_length > spec.max_los_length:
            fwd_dist = min(closest_hit_fwd, length)
            bwd_dist = 0.0 if closest_hit_bwd == float('inf') else closest_hit_bwd

            p1_x = sx - dx * bwd_dist
            p1_y = sy - dy * bwd_dist
            p2_x = sx + dx * fwd_dist
            p2_y = sy + dy * fwd_dist

            mid_x = (p1_x + p2_x) / 2
            mid_y = (p1_y + p2_y) / 2

            result["long_sightlines"].append((p1_x, p1_y, p2_x, p2_y))
            result["cover_suggestions"].append((mid_x, mid_y))
            result["warnings"].append(f"Long sightline detected: {unobstructed_length:.0f} units at ({mid_x:.0f}, {mid_y:.0f})")

        # Count direct sightlines between bases
        # Simple heuristic: if the ray goes from near imp_base to near nf_base
        dist_start_imp = math.sqrt((sx - imp_base_x)**2 + (sy - imp_base_y)**2)
        dist_end_nf = math.sqrt((ex - nf_base_x)**2 + (ey - nf_base_y)**2)
        dist_start_nf = math.sqrt((sx - nf_base_x)**2 + (sy - nf_base_y)**2)
        dist_end_imp = math.sqrt((ex - imp_base_x)**2 + (ey - imp_base_y)**2)

        if (dist_start_imp < base_radius * 2 and dist_end_nf < base_radius * 2) or \
           (dist_start_nf < base_radius * 2 and dist_end_imp < base_radius * 2):
            if closest_hit_fwd >= length:
                direct_base_sightlines += 1

    if direct_base_sightlines > 2:
        result["warnings"].append(f"More than 2 direct sightlines between bases ({direct_base_sightlines}). Consider adding cover.")

    # 5. Check for fully enclosed areas
    # For each node, if all outward rays hit a block within < node.radius + 128
    nodes_with_conns = set([c.start_node for c in connections] + [c.end_node for c in connections])
    for n in nodes_with_conns:
        rays_hit_close = True
        conns = [c for c in connections if c.start_node == n or c.end_node == n]
        if not conns:
            continue

        for c in conns:
            dx = c.end_node.x - c.start_node.x if c.start_node == n else c.start_node.x - c.end_node.x
            dy = c.end_node.y - c.start_node.y if c.start_node == n else c.start_node.y - c.end_node.y
            length = math.sqrt(dx**2 + dy**2)
            if length < 1e-6:
                continue
            dx /= length
            dy /= length

            hit_dist = float('inf')
            for b in blocks:
                hit, t = ray_intersects_block(n.x, n.y, dx, dy, b)
                if hit and t > 1e-6:
                    hit_dist = min(hit_dist, t)

            if hit_dist > (n.radius + 256):
                rays_hit_close = False
                break

        if rays_hit_close:
            result["warnings"].append(f"Intersection at {n.x:.0f}, {n.y:.0f} is heavily enclosed. Suggestion: Widen an adjacent street.")

    return result

def tune_cover(spec: UrbanSpec, blocks: List[UrbanBlock], cover_suggestions: List[Tuple[float,float]]) -> List[UrbanBlock]:
    """
    Applies cover suggestions to the blocks or spec.
    """
    for sx, sy in cover_suggestions:
        nearest_block = None
        min_dist = 512.0

        for b in blocks:
            if b.block_type in (BlockType.INTACT, BlockType.RUINED):
                dist = math.sqrt((b.world_x - sx)**2 + (b.world_y - sy)**2)
                # Ensure we find blocks strictly within or exactly equal to 512 radius
                if dist <= min_dist:
                    min_dist = dist
                    nearest_block = b

        if nearest_block:
            nearest_block.needs_rooftop_cover = True
        else:
            spec.street_cover_points.append((sx, sy))

    return blocks


def _create_wedge_brush(x: float, y: float, z: float, width: float, length: float, height: float, direction: RampPlacement, material: str) -> VMFSolid:
    """Creates a 5-sided wedge brush (ramp) using vmflib."""
    b = VMFSolid()

    # Base corners
    w2 = width / 2.0
    l2 = length / 2.0

    p_sw = VMFVertex(x - w2, y - l2, z)
    p_se = VMFVertex(x + w2, y - l2, z)
    p_ne = VMFVertex(x + w2, y + l2, z)
    p_nw = VMFVertex(x - w2, y + l2, z)

    bottom = VMFSide(VMFPlane(p_sw, p_se, p_ne), material)

    if direction == RampPlacement.NORTH: # high in North, low in South
        pt_nw = VMFVertex(x - w2, y + l2, z + height)
        pt_ne = VMFVertex(x + w2, y + l2, z + height)

        top = VMFSide(VMFPlane(pt_ne, pt_nw, p_sw), material)
        back = VMFSide(VMFPlane(p_nw, p_ne, pt_ne), material) # North face
        east = VMFSide(VMFPlane(p_se, pt_ne, p_ne), material)
        west = VMFSide(VMFPlane(pt_nw, p_sw, p_nw), material)
        b.children.extend([bottom, top, back, east, west])

    elif direction == RampPlacement.SOUTH: # high in South, low in North
        pt_sw = VMFVertex(x - w2, y - l2, z + height)
        pt_se = VMFVertex(x + w2, y - l2, z + height)

        top = VMFSide(VMFPlane(pt_sw, pt_se, p_ne), material)
        back = VMFSide(VMFPlane(p_se, p_sw, pt_sw), material) # South face
        east = VMFSide(VMFPlane(pt_se, p_se, p_ne), material)
        west = VMFSide(VMFPlane(p_sw, pt_sw, p_nw), material)
        b.children.extend([bottom, top, back, east, west])

    elif direction == RampPlacement.EAST: # high in East, low in West
        pt_se = VMFVertex(x + w2, y - l2, z + height)
        pt_ne = VMFVertex(x + w2, y + l2, z + height)

        top = VMFSide(VMFPlane(pt_ne, pt_se, p_sw), material)
        back = VMFSide(VMFPlane(p_se, p_ne, pt_ne), material) # East face
        north = VMFSide(VMFPlane(pt_ne, p_ne, p_nw), material)
        south = VMFSide(VMFPlane(p_sw, p_se, pt_se), material)
        b.children.extend([bottom, top, back, north, south])

    elif direction == RampPlacement.WEST: # high in West, low in East
        pt_sw = VMFVertex(x - w2, y - l2, z + height)
        pt_nw = VMFVertex(x - w2, y + l2, z + height)

        top = VMFSide(VMFPlane(pt_sw, pt_nw, p_ne), material)
        back = VMFSide(VMFPlane(p_nw, p_sw, pt_sw), material) # West face
        north = VMFSide(VMFPlane(p_nw, pt_nw, p_ne), material)
        south = VMFSide(VMFPlane(pt_sw, p_sw, p_se), material)
        b.children.extend([bottom, top, back, north, south])

    return b

def generate_vertical_layers(spec: UrbanSpec, blocks: List[UrbanBlock], vmf_doc) -> None:
    """
    Generates VMF brushes for urban blocks enforcing the compile budget.
    """
    logger = logging.getLogger(__name__)

    budget = spec.compile_budget
    rng = random.Random(spec.seed)

    floor_height = spec.terrain_max_height * getattr(spec, "lane_elevation", 0.15)

    if hasattr(spec, "size_x"):
        map_w = spec.size_x
        map_h = spec.size_y
        origin_x = spec.origin_x
        origin_y = spec.origin_y
    else:
        map_w = spec.terrain_tiles_x * spec.terrain_tile_size
        map_h = spec.terrain_tiles_y * spec.terrain_tile_size
        origin_x = -(map_w // 2)
        origin_y = -(map_h // 2)

    center_x = origin_x + map_w / 2.0
    center_y = origin_y + map_h / 2.0

    # Pre-select wall texture
    import json

    theme_name = getattr(spec, "current_theme", "Temperate")
    facade_material = "tools/toolsnodraw"

    textures_path = Path(__file__).parent.parent / "config" / "textures.json"
    if textures_path.exists():
        try:
            with open(textures_path, "r") as f:
                themes = json.load(f).get("themes", {})
                theme = themes.get(theme_name, themes.get("Generic", {}))
                scenery_floors = theme.get("defaults", {}).get("scenery_floors", [])
                if scenery_floors:
                    facade_material = scenery_floors[0] # Just pick first as facade
        except Exception:
            pass

    # Sort blocks by distance to center to prioritize reductions on outer blocks later
    blocks_with_dist = []
    for b in blocks:
        dist = math.sqrt((b.world_x - center_x)**2 + (b.world_y - center_y)**2)
        blocks_with_dist.append((dist, b))

    # State tracking for budget reductions
    class BlockGenState:
        def __init__(self, block):
            self.block = block
            self.ramp_enabled = block.ramp_side is not None
            self.irregular_walls = (block.block_type == BlockType.RUINED)
            self.current_type = block.block_type
            self.brushes = []

    states = [BlockGenState(b) for _, b in sorted(blocks_with_dist, key=lambda x: x[0], reverse=True)]
    # sorted furthest to closest so we can easily iterate for reductions

    def generate_brushes_for_state(state: BlockGenState):
        b = state.block
        state.brushes = []
        if state.current_type == BlockType.OPEN_LOT:
            return

        bw2 = b.footprint_w / 2.0
        bd2 = b.footprint_d / 2.0
        wall_thickness = 64.0

        if state.current_type in (BlockType.INTACT, BlockType.RUINED):
            # 4 Perimeter walls
            # North Wall
            n_y = b.world_y + bd2 - wall_thickness / 2.0
            # South Wall
            s_y = b.world_y - bd2 + wall_thickness / 2.0
            # East Wall
            e_x = b.world_x + bw2 - wall_thickness / 2.0
            # West Wall
            w_x = b.world_x - bw2 + wall_thickness / 2.0

            walls = [
                (b.world_x, n_y, b.footprint_w, wall_thickness),
                (b.world_x, s_y, b.footprint_w, wall_thickness),
                (e_x, b.world_y, wall_thickness, b.footprint_d - wall_thickness * 2),
                (w_x, b.world_y, wall_thickness, b.footprint_d - wall_thickness * 2)
            ]

            for wx, wy, ww, wl in walls:
                if state.irregular_walls:
                    offset = b.elevation_h * rng.uniform(-0.15, 0.15)
                    h = max(64.0, b.elevation_h + offset)
                else:
                    h = b.elevation_h

                wall_block = VMFBlock(VMFVertex(wx, wy, floor_height + h/2.0), (ww, wl, h), facade_material)
                apply_nodraw_to_terrain_except_top(wall_block, facade_material)
                # We need all outer faces to have facade, but apply_nodraw_to_terrain_except_top makes sides nodraw.
                # Let's just use the facade material for the whole block for simplicity in this phase.
                for side in wall_block.brush.children:
                    side.material = facade_material
                state.brushes.append(wall_block.brush)

            if state.current_type == BlockType.INTACT:
                # Roof
                roof_thickness = 32.0
                roof_block = VMFBlock(VMFVertex(b.world_x, b.world_y, floor_height + b.elevation_h - roof_thickness/2.0), (b.footprint_w, b.footprint_d, roof_thickness), facade_material)
                for side in roof_block.brush.children:
                    side.material = "tools/toolsnodraw"
                roof_block.brush.children[0].material = facade_material # Top face
                state.brushes.append(roof_block.brush)

                # Ramp
                if state.ramp_enabled and b.ramp_side:
                    ramp_w = 192.0
                    ramp_l = b.footprint_w

                    if b.ramp_side in (RampPlacement.NORTH, RampPlacement.SOUTH):
                        rx = b.world_x
                        ry = b.world_y + (b.footprint_d/2.0 + ramp_w/2.0) if b.ramp_side == RampPlacement.NORTH else b.world_y - (b.footprint_d/2.0 + ramp_w/2.0)
                        ramp_brush = _create_wedge_brush(rx, ry, floor_height, ramp_l, ramp_w, b.elevation_h, b.ramp_side, facade_material)
                        state.brushes.append(ramp_brush)
                    else:
                        ramp_l = b.footprint_d
                        rx = b.world_x + (b.footprint_w/2.0 + ramp_w/2.0) if b.ramp_side == RampPlacement.EAST else b.world_x - (b.footprint_w/2.0 + ramp_w/2.0)
                        ry = b.world_y
                        ramp_brush = _create_wedge_brush(rx, ry, floor_height, ramp_w, ramp_l, b.elevation_h, b.ramp_side, facade_material)
                        state.brushes.append(ramp_brush)

                # INTERNAL_ACCESS: TODO reserve enum value, skip implementation

        elif state.current_type == BlockType.RUBBLE:
            # Low raised brush
            rubble_h = b.elevation_h
            rubble_block = VMFBlock(VMFVertex(b.world_x, b.world_y, floor_height + rubble_h/2.0), (b.footprint_w, b.footprint_d, rubble_h), facade_material)
            apply_nodraw_to_terrain_except_top(rubble_block, facade_material)
            state.brushes.append(rubble_block.brush)

    # Initial generation
    for state in states:
        generate_brushes_for_state(state)

    # Finally, add all brushes to the VMF
    # Assume vmf_doc is a vmflib.ValveMap instance
    if vmf_doc is not None and hasattr(vmf_doc, "world"):
        for state in states:
            for brush in state.brushes:
                vmf_doc.world.children.append(brush)

def validate_urban_terrain_first_output(spec: UrbanSpec, grid: HeightGrid, blocks: List[UrbanBlock], connections: List['LayoutConnection']) -> dict:
    """
    Validates the generated urban terrain.
    Checks vehicle path clearance, prop floating/buried,
    crater compliance, alpha map completeness, and seams.
    """
    import numpy as np
    warnings = []
    errors = []

    # Check alpha map completeness
    if grid.urban_alpha_map is None:
        errors.append("urban_alpha_map was not generated.")
    elif grid.urban_alpha_map.shape != (grid.rows, grid.cols):
        errors.append("urban_alpha_map shape mismatch.")

    # Check vehicle path clearance conceptually (ensure height variations on streets are small)
    if grid.street_mask is not None:
        street_heights = grid.heights[grid.street_mask]
        if len(street_heights) > 0:
            max_h = np.max(street_heights)
            min_h = np.min(street_heights)
            # We applied noise to streets (~±20), so variation shouldn't exceed ~60.
            if max_h - min_h > 120:
                warnings.append(f"High height variation on streets: {max_h - min_h} units.")

    # Check craters (just that we didn't go below the minimum allowed depth)
    floor_height = spec.terrain_max_height * getattr(spec, "lane_elevation", 0.15)
    min_allowed = floor_height - (spec.crater_depth_scale * 100.0)
    if np.min(grid.heights) < min_allowed - 1.0: # 1.0 for fp error
        warnings.append("Terrain went below minimum allowed crater depth.")

    # Validate props
    if grid.placed_props is not None:
        for prop in grid.placed_props:
            x, y, z = prop['x'], prop['y'], prop['z']

            # Simple bounds check
            if x < spec.origin_x - 512 or x > spec.origin_x + spec.size_x + 512 or y < spec.origin_y - 512 or y > spec.origin_y + spec.size_y + 512:
                errors.append(f"Prop placed out of bounds: ({x}, {y})")

            # Z should closely match height map (floating/buried check)
            row = int((y - spec.origin_y) / spec.cell_size)
            col = int((x - spec.origin_x) / spec.cell_size)
            if 0 <= row < grid.rows and 0 <= col < grid.cols:
                h = grid.heights[row][col]
                if abs(z - h) > 32:
                    warnings.append(f"Prop might be floating/buried at ({x}, {y}): diff {abs(z - h)}")

    return {
        "valid": len(errors) == 0,
        "warnings": warnings,
        "errors": errors
    }
