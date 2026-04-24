#!/usr/bin/env python3
"""
Terrain Generation Pipeline

8-step pipeline for compile-safe displacement terrain:
1. Generate vertex grid
2. Generate heights from multi-layered fBm
3. Simulate hydraulic erosion
4. Calculate slopes
5. Smooth heights
6. Clamp slope
7. Quantize heights
8. Build cells from shared vertices
9. Validate seams
10. Build underlay

All coordinate calculations use integer grid positions to prevent T-junctions.
"""

import math
import random
import sys
from typing import List, Tuple, Optional

import numpy as np

if getattr(sys, "frozen", False):
    from terrain_spec import (
        TerrainSpec,
        HeightGrid,
        TerrainCell,
        UnderlayBrush,
        ZoneType,
        LayoutNode,
        LayoutConnection,
    )
else:
    from src.terrain_spec import (
        TerrainSpec,
        HeightGrid,
        TerrainCell,
        UnderlayBrush,
        ZoneType,
        LayoutNode,
        LayoutConnection,
    )

from PIL import Image, ImageOps


def generate_vertex_grid(spec: TerrainSpec) -> HeightGrid:
    """
    Step 1: Generate empty vertex grid.

    Creates a grid of vertices with integer positions.
    Grid dimensions: (vertex_rows x vertex_cols)
    """
    rows = spec.vertex_rows
    cols = spec.vertex_cols

    heights = np.zeros((rows, cols), dtype=np.float32)

    return HeightGrid(
        heights=heights,
        origin_x=spec.origin_x,
        origin_y=spec.origin_y,
        cell_size=spec.cell_size,
    )


def create_connection_path(
    start_node: LayoutNode,
    end_node: LayoutNode,
    width: float,
    conn_type: str,
    spec: TerrainSpec,
) -> LayoutConnection:
    import math
    from src.noise import NoiseGenerator

    noise = NoiseGenerator(spec.seed)

    dx = end_node.x - start_node.x
    dy = end_node.y - start_node.y
    length = math.sqrt(dx * dx + dy * dy)

    if length == 0:
        return LayoutConnection(
            start_node, end_node, width, conn_type, [(start_node.x, start_node.y)]
        )

    nx = -dy / length
    ny = dx / length

    # Subdivide line: roughly one point every 30 units for dense polyline
    num_segments = max(1, int(length / 30.0))
    path_points = []

    # Max offset is 20% of the total connection length
    max_offset = length * 0.20
    freq = 3.0  # Frequency of the winding

    for i in range(num_segments + 1):
        t = i / num_segments
        base_x = start_node.x + t * dx
        base_y = start_node.y + t * dy

        if i == 0 or i == num_segments:
            # Anchor perfectly to the start and end nodes
            path_points.append((base_x, base_y))
            continue

        # Sine envelope forces noise to 0 at the start and end
        envelope = math.sin(t * math.pi)

        # 1D noise sampled along t
        noise_val = noise.fbm(t * freq, spec.seed * 0.1, octaves=2)
        offset = noise_val * envelope * max_offset

        px = base_x + nx * offset
        py = base_y + ny * offset
        path_points.append((px, py))

    return LayoutConnection(start_node, end_node, width, conn_type, path_points)


def generate_strategic_layout(
    spec: TerrainSpec,
) -> Tuple[List[LayoutNode], List[LayoutConnection]]:
    """Generates an explicit layout of nodes and connections based on the terrain spec."""
    import random

    rng = random.Random(spec.seed)
    archetypes = [
        "central_gorge",
        "valley",
        "two_lane",
        "island",
        "classic_cross",
        "peninsula",
        "archipelago",
        "delta",
    ]
    if spec.topology in archetypes:
        topology = spec.topology
    else:
        topology = rng.choice(archetypes)

    center_x = spec.origin_x + spec.size_x / 2
    center_y = spec.origin_y + spec.size_y / 2

    # Keep strategic lane routing stable when users drag bases in the editor.
    # Custom base positions still apply to base flattening and final entity placement.
    imp_x, imp_y = spec.default_imp_base()
    nf_x, nf_y = spec.default_nf_base()

    # Use lane_node_radius for strategic layout nodes (separate from terrain flatten radius)
    base_radius = spec.lane_node_radius
    map_min_dim = min(spec.size_x, spec.size_y)

    imp_base = LayoutNode(imp_x, imp_y, base_radius, ZoneType.BASE)
    nf_base = LayoutNode(nf_x, nf_y, base_radius, ZoneType.BASE)

    lane_dx = nf_x - imp_x
    lane_dy = nf_y - imp_y
    lane_len = math.sqrt(lane_dx * lane_dx + lane_dy * lane_dy)
    if lane_len > 0:
        lane_dx /= lane_len
        lane_dy /= lane_len
    else:
        lane_dx, lane_dy = 1.0, 0.0

    perp_dx = -lane_dy
    perp_dy = lane_dx

    lane_width = rng.uniform(0.08, 0.15) * map_min_dim
    veh_radius = rng.uniform(0.15, 0.25) * map_min_dim
    choke_length = rng.uniform(0.10, 0.20) * map_min_dim

    lane_width *= spec.lane_width_scale
    veh_radius *= spec.lane_width_scale

    nodes = [imp_base, nf_base]
    connections = []

    if topology == "central_gorge":
        center_node = LayoutNode(
            center_x, center_y, choke_length / 2, ZoneType.CHOKEPOINT
        )
        nodes.append(center_node)
        connections.append(
            create_connection_path(
                imp_base, center_node, lane_width, ZoneType.MAIN_LANE, spec
            )
        )
        connections.append(
            create_connection_path(
                center_node, nf_base, lane_width, ZoneType.MAIN_LANE, spec
            )
        )

        offset = map_min_dim * rng.uniform(0.2, 0.4)
        side1 = LayoutNode(
            center_x + perp_dx * offset,
            center_y + perp_dy * offset,
            veh_radius,
            ZoneType.VEHICLE_OPEN,
        )
        side2 = LayoutNode(
            center_x - perp_dx * offset,
            center_y - perp_dy * offset,
            veh_radius,
            ZoneType.VEHICLE_OPEN,
        )
        nodes.extend([side1, side2])

        connections.append(
            create_connection_path(
                imp_base, side1, lane_width * 0.8, ZoneType.SIDE_ROUTE, spec
            )
        )
        connections.append(
            create_connection_path(
                side1, nf_base, lane_width * 0.8, ZoneType.SIDE_ROUTE, spec
            )
        )
        connections.append(
            create_connection_path(
                imp_base, side2, lane_width * 0.8, ZoneType.SIDE_ROUTE, spec
            )
        )
        connections.append(
            create_connection_path(
                side2, nf_base, lane_width * 0.8, ZoneType.SIDE_ROUTE, spec
            )
        )

    elif topology == "valley":
        valley_node = LayoutNode(
            center_x,
            center_y,
            map_min_dim * rng.uniform(0.3, 0.4),
            ZoneType.VEHICLE_OPEN,
        )
        nodes.append(valley_node)
        connections.append(
            create_connection_path(
                imp_base, valley_node, lane_width * 2, ZoneType.MAIN_LANE, spec
            )
        )
        connections.append(
            create_connection_path(
                valley_node, nf_base, lane_width * 2, ZoneType.MAIN_LANE, spec
            )
        )

    elif topology == "two_lane":
        offset = map_min_dim * rng.uniform(0.15, 0.3)
        choke1 = LayoutNode(
            center_x + perp_dx * offset,
            center_y + perp_dy * offset,
            choke_length,
            ZoneType.CHOKEPOINT,
        )
        choke2 = LayoutNode(
            center_x - perp_dx * offset,
            center_y - perp_dy * offset,
            choke_length,
            ZoneType.CHOKEPOINT,
        )
        nodes.extend([choke1, choke2])

        v_imp1 = LayoutNode(
            imp_x + lane_dx * lane_len * 0.25 + perp_dx * offset * 0.5,
            imp_y + lane_dy * lane_len * 0.25 + perp_dy * offset * 0.5,
            veh_radius * 0.8,
            ZoneType.VEHICLE_OPEN,
        )
        v_nf1 = LayoutNode(
            nf_x - lane_dx * lane_len * 0.25 + perp_dx * offset * 0.5,
            nf_y - lane_dy * lane_len * 0.25 + perp_dy * offset * 0.5,
            veh_radius * 0.8,
            ZoneType.VEHICLE_OPEN,
        )
        v_imp2 = LayoutNode(
            imp_x + lane_dx * lane_len * 0.25 - perp_dx * offset * 0.5,
            imp_y + lane_dy * lane_len * 0.25 - perp_dy * offset * 0.5,
            veh_radius * 0.8,
            ZoneType.VEHICLE_OPEN,
        )
        v_nf2 = LayoutNode(
            nf_x - lane_dx * lane_len * 0.25 - perp_dx * offset * 0.5,
            nf_y - lane_dy * lane_len * 0.25 - perp_dy * offset * 0.5,
            veh_radius * 0.8,
            ZoneType.VEHICLE_OPEN,
        )
        nodes.extend([v_imp1, v_nf1, v_imp2, v_nf2])

        connections.append(
            create_connection_path(
                imp_base, v_imp1, lane_width, ZoneType.MAIN_LANE, spec
            )
        )
        connections.append(
            create_connection_path(
                v_imp1, choke1, lane_width, ZoneType.CHOKEPOINT, spec
            )
        )
        connections.append(
            create_connection_path(choke1, v_nf1, lane_width, ZoneType.CHOKEPOINT, spec)
        )
        connections.append(
            create_connection_path(v_nf1, nf_base, lane_width, ZoneType.MAIN_LANE, spec)
        )

        connections.append(
            create_connection_path(
                imp_base, v_imp2, lane_width, ZoneType.MAIN_LANE, spec
            )
        )
        connections.append(
            create_connection_path(
                v_imp2, choke2, lane_width, ZoneType.CHOKEPOINT, spec
            )
        )
        connections.append(
            create_connection_path(choke2, v_nf2, lane_width, ZoneType.CHOKEPOINT, spec)
        )
        connections.append(
            create_connection_path(v_nf2, nf_base, lane_width, ZoneType.MAIN_LANE, spec)
        )

    elif topology == "island":
        center_island = LayoutNode(
            center_x, center_y, veh_radius * 1.5, ZoneType.VEHICLE_OPEN
        )
        nodes.append(center_island)

        choke_imp = LayoutNode(
            imp_x + lane_dx * lane_len * 0.3,
            imp_y + lane_dy * lane_len * 0.3,
            choke_length,
            ZoneType.CHOKEPOINT,
        )
        choke_nf = LayoutNode(
            nf_x - lane_dx * lane_len * 0.3,
            nf_y - lane_dy * lane_len * 0.3,
            choke_length,
            ZoneType.CHOKEPOINT,
        )
        nodes.extend([choke_imp, choke_nf])

        connections.append(
            create_connection_path(
                imp_base, choke_imp, lane_width, ZoneType.CHOKEPOINT, spec
            )
        )
        connections.append(
            create_connection_path(
                choke_imp, center_island, lane_width, ZoneType.MAIN_LANE, spec
            )
        )
        connections.append(
            create_connection_path(
                center_island, choke_nf, lane_width, ZoneType.MAIN_LANE, spec
            )
        )
        connections.append(
            create_connection_path(
                choke_nf, nf_base, lane_width, ZoneType.CHOKEPOINT, spec
            )
        )

    elif topology == "classic_cross":
        center_choke = LayoutNode(
            center_x, center_y, choke_length / 2, ZoneType.CHOKEPOINT
        )
        nodes.append(center_choke)

        veh1 = LayoutNode(
            imp_x + lane_dx * lane_len * 0.25,
            imp_y + lane_dy * lane_len * 0.25,
            veh_radius,
            ZoneType.VEHICLE_OPEN,
        )
        veh2 = LayoutNode(
            imp_x + lane_dx * lane_len * 0.75,
            imp_y + lane_dy * lane_len * 0.75,
            veh_radius,
            ZoneType.VEHICLE_OPEN,
        )
        nodes.extend([veh1, veh2])

        connections.append(
            create_connection_path(imp_base, veh1, lane_width, ZoneType.MAIN_LANE, spec)
        )
        connections.append(
            create_connection_path(
                veh1, center_choke, lane_width, ZoneType.CHOKEPOINT, spec
            )
        )
        connections.append(
            create_connection_path(
                center_choke, veh2, lane_width, ZoneType.CHOKEPOINT, spec
            )
        )
        connections.append(
            create_connection_path(veh2, nf_base, lane_width, ZoneType.MAIN_LANE, spec)
        )

        side_offset = map_min_dim * rng.uniform(0.25, 0.4)
        side_veh = LayoutNode(
            center_x + perp_dx * side_offset,
            center_y + perp_dy * side_offset,
            veh_radius * 0.7,
            ZoneType.VEHICLE_OPEN,
        )
        nodes.append(side_veh)

        connections.append(
            create_connection_path(
                veh1, side_veh, lane_width * 0.7, ZoneType.SIDE_ROUTE, spec
            )
        )
        connections.append(
            create_connection_path(
                side_veh, veh2, lane_width * 0.7, ZoneType.SIDE_ROUTE, spec
            )
        )

    elif topology == "peninsula":
        # Peninsula: landmass extending from one base with winding path
        mid_x = (imp_x + nf_x) / 2 + perp_dx * map_min_dim * rng.uniform(-0.1, 0.1)
        mid_y = (imp_y + nf_y) / 2 + perp_dy * map_min_dim * rng.uniform(-0.1, 0.1)
        choke1 = LayoutNode(
            imp_x
            + lane_dx * lane_len * 0.3
            + perp_dx * map_min_dim * rng.uniform(-0.15, 0.15),
            imp_y
            + lane_dy * lane_len * 0.3
            + perp_dy * map_min_dim * rng.uniform(-0.15, 0.15),
            choke_length,
            ZoneType.CHOKEPOINT,
        )
        choke2 = LayoutNode(
            mid_x + perp_dx * map_min_dim * rng.uniform(-0.2, 0.2),
            mid_y + perp_dy * map_min_dim * rng.uniform(-0.2, 0.2),
            choke_length,
            ZoneType.CHOKEPOINT,
        )
        choke3 = LayoutNode(
            nf_x
            - lane_dx * lane_len * 0.3
            + perp_dx * map_min_dim * rng.uniform(-0.15, 0.15),
            nf_y
            - lane_dy * lane_len * 0.3
            + perp_dy * map_min_dim * rng.uniform(-0.15, 0.15),
            choke_length,
            ZoneType.CHOKEPOINT,
        )
        nodes.extend([choke1, choke2, choke3])

        connections.append(
            create_connection_path(
                imp_base, choke1, lane_width, ZoneType.MAIN_LANE, spec
            )
        )
        connections.append(
            create_connection_path(
                choke1, choke2, lane_width, ZoneType.CHOKEPOINT, spec
            )
        )
        connections.append(
            create_connection_path(
                choke2, choke3, lane_width, ZoneType.CHOKEPOINT, spec
            )
        )
        connections.append(
            create_connection_path(
                choke3, nf_base, lane_width, ZoneType.MAIN_LANE, spec
            )
        )

        # Add side vehicle areas
        side_offset = map_min_dim * rng.uniform(0.2, 0.35)
        veh1 = LayoutNode(
            choke1.x + perp_dx * side_offset,
            choke1.y + perp_dy * side_offset,
            veh_radius * 0.8,
            ZoneType.VEHICLE_OPEN,
        )
        veh2 = LayoutNode(
            choke3.x - perp_dx * side_offset,
            choke3.y - perp_dy * side_offset,
            veh_radius * 0.8,
            ZoneType.VEHICLE_OPEN,
        )
        nodes.extend([veh1, veh2])

        connections.append(
            create_connection_path(
                choke1, veh1, lane_width * 0.6, ZoneType.SIDE_ROUTE, spec
            )
        )
        connections.append(
            create_connection_path(
                choke3, veh2, lane_width * 0.6, ZoneType.SIDE_ROUTE, spec
            )
        )

    elif topology == "archipelago":
        # Archipelago: multiple small islands with connections
        island1 = LayoutNode(
            imp_x
            + lane_dx * lane_len * 0.25
            + perp_dx * map_min_dim * rng.uniform(-0.1, 0.1),
            imp_y
            + lane_dy * lane_len * 0.25
            + perp_dy * map_min_dim * rng.uniform(-0.1, 0.1),
            veh_radius * 0.6,
            ZoneType.VEHICLE_OPEN,
        )
        island2 = LayoutNode(
            center_x + perp_dx * map_min_dim * rng.uniform(-0.15, 0.15),
            center_y + perp_dy * map_min_dim * rng.uniform(-0.15, 0.15),
            veh_radius * 0.7,
            ZoneType.VEHICLE_OPEN,
        )
        island3 = LayoutNode(
            nf_x
            - lane_dx * lane_len * 0.25
            + perp_dx * map_min_dim * rng.uniform(-0.1, 0.1),
            nf_y
            - lane_dy * lane_len * 0.25
            + perp_dy * map_min_dim * rng.uniform(-0.1, 0.1),
            veh_radius * 0.6,
            ZoneType.VEHICLE_OPEN,
        )
        island4 = LayoutNode(
            center_x - perp_dx * map_min_dim * rng.uniform(-0.15, 0.15),
            center_y - perp_dy * map_min_dim * rng.uniform(-0.15, 0.15),
            veh_radius * 0.7,
            ZoneType.VEHICLE_OPEN,
        )
        nodes.extend([island1, island2, island3, island4])

        # Create a network of connections
        connections.append(
            create_connection_path(
                imp_base, island1, lane_width * 0.8, ZoneType.MAIN_LANE, spec
            )
        )
        connections.append(
            create_connection_path(
                island1, island2, lane_width * 0.7, ZoneType.MAIN_LANE, spec
            )
        )
        connections.append(
            create_connection_path(
                island2, island3, lane_width * 0.7, ZoneType.MAIN_LANE, spec
            )
        )
        connections.append(
            create_connection_path(
                island3, nf_base, lane_width * 0.8, ZoneType.MAIN_LANE, spec
            )
        )
        connections.append(
            create_connection_path(
                island2, island4, lane_width * 0.6, ZoneType.SIDE_ROUTE, spec
            )
        )

    elif topology == "delta":
        # Delta: branching paths from center like a river delta
        center_node = LayoutNode(
            center_x, center_y, veh_radius * 1.2, ZoneType.VEHICLE_OPEN
        )
        nodes.append(center_node)

        # Three main branches
        branch_angle = rng.uniform(0, 2 * math.pi)
        for i in range(3):
            angle = branch_angle + i * (2 * math.pi / 3)
            branch_x = center_x + math.cos(angle) * map_min_dim * 0.3
            branch_y = center_y + math.sin(angle) * map_min_dim * 0.3
            branch_choke = LayoutNode(
                branch_x, branch_y, choke_length * 0.8, ZoneType.CHOKEPOINT
            )
            nodes.append(branch_choke)
            connections.append(
                create_connection_path(
                    center_node,
                    branch_choke,
                    lane_width * 0.8,
                    ZoneType.MAIN_LANE,
                    spec,
                )
            )

        # Connect bases to nearest branches
        if (center_x - imp_x) ** 2 + (center_y - imp_y) ** 2 < (
            center_x - nf_x
        ) ** 2 + (center_y - nf_y) ** 2:
            connections.append(
                create_connection_path(
                    imp_base, center_node, lane_width, ZoneType.MAIN_LANE, spec
                )
            )
            connections.append(
                create_connection_path(
                    center_node, nf_base, lane_width, ZoneType.MAIN_LANE, spec
                )
            )
        else:
            connections.append(
                create_connection_path(
                    nf_base, center_node, lane_width, ZoneType.MAIN_LANE, spec
                )
            )
            connections.append(
                create_connection_path(
                    center_node, imp_base, lane_width, ZoneType.MAIN_LANE, spec
                )
            )

        # Add side vehicle areas on branches
        for i in range(3):
            angle = branch_angle + i * (2 * math.pi / 3) + math.pi / 6
            side_x = center_x + math.cos(angle) * map_min_dim * 0.25
            side_y = center_y + math.sin(angle) * map_min_dim * 0.25
            side_veh = LayoutNode(
                side_x, side_y, veh_radius * 0.6, ZoneType.VEHICLE_OPEN
            )
            nodes.append(side_veh)

    else:
        # Default fallback (same as classic_cross)
        center_choke = LayoutNode(
            center_x, center_y, choke_length / 2, ZoneType.CHOKEPOINT
        )
        nodes.append(center_choke)

        veh1 = LayoutNode(
            imp_x + lane_dx * lane_len * 0.25,
            imp_y + lane_dy * lane_len * 0.25,
            veh_radius,
            ZoneType.VEHICLE_OPEN,
        )
        veh2 = LayoutNode(
            imp_x + lane_dx * lane_len * 0.75,
            imp_y + lane_dy * lane_len * 0.75,
            veh_radius,
            ZoneType.VEHICLE_OPEN,
        )
        nodes.extend([veh1, veh2])

        connections.append(
            create_connection_path(imp_base, veh1, lane_width, ZoneType.MAIN_LANE, spec)
        )
        connections.append(
            create_connection_path(
                veh1, center_choke, lane_width, ZoneType.CHOKEPOINT, spec
            )
        )
        connections.append(
            create_connection_path(
                center_choke, veh2, lane_width, ZoneType.CHOKEPOINT, spec
            )
        )
        connections.append(
            create_connection_path(veh2, nf_base, lane_width, ZoneType.MAIN_LANE, spec)
        )

        side_offset = map_min_dim * rng.uniform(0.25, 0.4)
        side_veh = LayoutNode(
            center_x + perp_dx * side_offset,
            center_y + perp_dy * side_offset,
            veh_radius * 0.7,
            ZoneType.VEHICLE_OPEN,
        )
        nodes.append(side_veh)

        connections.append(
            create_connection_path(
                veh1, side_veh, lane_width * 0.7, ZoneType.SIDE_ROUTE, spec
            )
        )
        connections.append(
            create_connection_path(
                side_veh, veh2, lane_width * 0.7, ZoneType.SIDE_ROUTE, spec
            )
        )

    return nodes, connections


def generate_playability_mask(
    spec: TerrainSpec,
    rows: int,
    cols: int,
    nodes: List[LayoutNode],
    connections: List[LayoutConnection],
):
    """
    Calculates the playability mask using numpy.

    Returns a 2D float64 array with values bounded between 0.0 and 1.0.
    Uses Smoothstep to calculate a smooth ramp directly from the distance grids.
    """
    import numpy as np

    x_coords = np.linspace(spec.origin_x, spec.origin_x + spec.size_x, cols)
    y_coords = np.linspace(spec.origin_y, spec.origin_y + spec.size_y, rows)
    WX, WY = np.meshgrid(x_coords, y_coords)

    # Compute signed distance to the playability boundary
    distance_field = np.full((rows, cols), np.inf, dtype=np.float64)

    # 1. Evaluate Nodes (BASE, VEHICLE_OPEN)
    for node in nodes:
        if spec.lane_node_radius <= 0 and node.type == ZoneType.BASE:
            continue
        dist_grid = np.sqrt((WX - node.x) ** 2 + (WY - node.y) ** 2)
        if node.type in (ZoneType.BASE, ZoneType.VEHICLE_OPEN):
            distance_field = np.minimum(distance_field, dist_grid - node.radius)

    # 2. Evaluate Polyline Connections
    for conn in connections:
        # Skip connections from/to base nodes when lane_node_radius is 0
        if spec.lane_node_radius <= 0 and conn.start_node.type == ZoneType.BASE:
            continue
        if spec.lane_node_radius <= 0 and conn.end_node.type == ZoneType.BASE:
            continue
        min_dist_grid = np.full((rows, cols), np.inf)

        pts = conn.path_points
        if not pts:
            pts = [
                (conn.start_node.x, conn.start_node.y),
                (conn.end_node.x, conn.end_node.y),
            ]

        for i in range(len(pts) - 1):
            ax, ay = pts[i]
            bx, by = pts[i + 1]

            dx, dy = bx - ax, by - ay
            l2 = dx * dx + dy * dy

            if l2 == 0:
                dist = np.sqrt((WX - ax) ** 2 + (WY - ay) ** 2)
            else:
                t = ((WX - ax) * dx + (WY - ay) * dy) / l2
                t_clamped = np.clip(t, 0.0, 1.0)
                px = ax + t_clamped * dx
                py = ay + t_clamped * dy
                dist = np.sqrt((WX - px) ** 2 + (WY - py) ** 2)

            min_dist_grid = np.minimum(min_dist_grid, dist)

        if conn.type in (ZoneType.MAIN_LANE, ZoneType.SIDE_ROUTE):
            playable_width = conn.width
        elif conn.type == ZoneType.CHOKEPOINT:
            playable_width = conn.width * 0.5
        else:
            continue

        distance_field = np.minimum(distance_field, min_dist_grid - playable_width)

    # distance_field is now the continuous distance from the playable boundary.
    # negative means inside the lane, positive means outside in the wilderness.
    return distance_field


def generate_heights(spec: TerrainSpec, grid: HeightGrid) -> HeightGrid:
    rows = grid.rows
    cols = grid.cols
    from src.noise import NoiseGenerator
    original_heights = grid.heights.copy()

    noise = NoiseGenerator(spec.seed)
    roughness = getattr(spec, "roughness", 0.5)
    max_height = spec.terrain_max_height

    hard_mask = getattr(grid, "playability_mask", None)
    if hard_mask is None:
        nodes, connections = generate_strategic_layout(spec)
        hard_mask = generate_playability_mask(spec, rows, cols, nodes, connections)

    floor_height = max_height * getattr(spec, 'lane_elevation', 0.15)
    base_mountain_height = max_height * 1.0
    scaled_mountain_height = spec.mountain_height_scale
    mountain_height = (
        floor_height + (base_mountain_height - floor_height) * scaled_mountain_height
    )

    warp_scale = 0.005
    warp_strength = 150.0 * roughness
    macro_scale = 0.0015
    ridge_scale = 0.0025

    new_heights = np.zeros((rows, cols), dtype=np.float32)

    for r in range(rows):
        wy = spec.origin_y + r * spec.size_y / max(1, rows - 1)
        for c in range(cols):
            wx = spec.origin_x + c * spec.size_x / max(1, cols - 1)

            wx_warp = (
                wx
                + noise.fbm(wx * warp_scale, wy * warp_scale, octaves=2) * warp_strength
            )
            wy_warp = (
                wy
                + noise.fbm(wx * warp_scale + 100, wy * warp_scale + 100, octaves=2)
                * warp_strength
            )

            dist_field_val = float(hard_mask[r, c])
            # mask_val replaces the old playable_mask concept for height interpolation.
            # dist_field_val is negative inside the lane, positive outside.
            # We want mask_val = 1.0 on the lane (dist_field_val <= 0),
            # and smoothly transitioning to 0.0 at ramp_width.
            ramp_width = max(10.0, spec.transition_blur_sigma * 30.0)
            fade = np.clip(dist_field_val / ramp_width, 0.0, 1.0)
            mask_val = 1.0 - (fade * fade * (3.0 - 2.0 * fade))

            if spec.manual_terrain:
                base_noise = 0.0
                ridge_val = 0.0
                detail_val = 0.0
                noise_combined = 1.0
            else:
                # Use a broader ramp for distance shaping of noise, so the terrain
                # gets progressively rougher over a larger distance from the lane.
                shaping_ramp_width = max(400.0, ramp_width * 4.0)
                dist_factor = np.clip(dist_field_val / shaping_ramp_width, 0.0, 1.0)
                # Smooth the factor
                dist_factor = dist_factor * dist_factor * (3.0 - 2.0 * dist_factor)

                effective_roughness = roughness * dist_factor

                base_noise = noise.fbm(
                    wx_warp * macro_scale, wy_warp * macro_scale, octaves=spec.noise_octaves
                )
                # True ridged multifractal noise (fold each octave)
                t_ridge = 0.0
                f_ridge = 1.0
                a_ridge = 1.0
                m_ridge = 0.0
                rx = wx_warp * ridge_scale + 50
                ry = wy_warp * ridge_scale + 50
                for _ in range(spec.noise_octaves):
                    v = noise.noise2d(rx * f_ridge, ry * f_ridge) * 2.0 - 1.0
                    v = 1.0 - abs(v)
                    v = v * v
                    t_ridge += v * a_ridge
                    m_ridge += a_ridge
                    a_ridge *= 0.5
                    f_ridge *= 2.0
                ridge_val = t_ridge / m_ridge if m_ridge > 0 else 0.0
                ridge_val = ridge_val * dist_factor

                detail_val = noise.fbm(wx_warp * 0.008, wy_warp * 0.008, octaves=3)
                detail_val = detail_val * dist_factor

                noise_combined = (
                    (0.5 - 0.2 * effective_roughness) * base_noise
                    + (0.3 + 0.4 * effective_roughness) * ridge_val
                    + 0.05 * detail_val
                )

            playable_height = floor_height + (max_height * 0.01 * base_noise)
            wilderness_target = (
                floor_height + (mountain_height - floor_height) * noise_combined
            )

            if spec.invert_lanes:
                # User selected invert lanes: lane is raised, wilderness is low
                final_height = wilderness_target * mask_val + playable_height * (
                    1.0 - mask_val
                )
            elif spec.topology == "island":
                # For islands, the playable area should be the elevated mountain,
                # and the wilderness should be the low floor (water level)
                final_height = wilderness_target * mask_val + playable_height * (
                    1.0 - mask_val
                )
            else:
                final_height = playable_height * mask_val + wilderness_target * (
                    1.0 - mask_val
                )

            new_heights[r, c] = final_height

    grid.heights = np.where(grid.global_selection_mask, new_heights, original_heights)

    return grid


def load_custom_heights(spec: TerrainSpec, grid: HeightGrid) -> HeightGrid:
    """
    Step 2 (Alternative): Load heights from a custom PNG image.
    Uses PIL ImageOps.fit to perfectly scale and crop the image to the grid.
    """
    if not spec.custom_image_path:
        return grid

    original_heights = grid.heights.copy()

    img = Image.open(spec.custom_image_path).convert("L")

    # Fit and crop the image to the required vertex grid dimensions
    # ImageOps.fit maintains aspect ratio while filling the target size exactly.
    img_fitted = ImageOps.fit(
        img, (grid.cols, grid.rows), method=Image.Resampling.LANCZOS
    )

    # Extract pixel data mapped proportionally to maximum physical height
    pixels = list(img_fitted.getdata())
    max_height = spec.terrain_max_height

    new_heights = np.zeros((grid.rows, grid.cols), dtype=np.float32)
    idx = 0
    for r in range(grid.rows):
        for c in range(grid.cols):
            val = pixels[idx] / 255.0
            new_heights[r, c] = val * max_height
            idx += 1

    grid.heights = np.where(grid.global_selection_mask, new_heights, original_heights)
    return grid


def smooth_heights(grid: HeightGrid, iterations: int = 1) -> HeightGrid:
    """
    Step 3: Smooth heights using 3x3 averaging kernel.

    Each vertex becomes the average of itself and 8 neighbors.
    Border vertices remain unchanged (no neighbors outside grid).
    """
    rows = grid.rows
    cols = grid.cols
    original_heights = grid.heights.copy()

    current_heights = grid.heights.copy()

    for _ in range(iterations):
        new_heights = np.zeros_like(current_heights)
        for r in range(rows):
            for c in range(cols):
                if r == 0 or r == rows - 1 or c == 0 or c == cols - 1:
                    new_heights[r, c] = current_heights[r, c]
                else:
                    total = 0.0
                    count = 0
                    for dr in (-1, 0, 1):
                        for dc in (-1, 0, 1):
                            total += current_heights[r + dr, c + dc]
                            count += 1
                    new_heights[r, c] = total / count
        current_heights = new_heights

    grid.heights = np.where(grid.global_selection_mask, current_heights, original_heights)

    return grid


def flatten_base_areas(
    grid: HeightGrid,
    spec: "TerrainSpec",
) -> HeightGrid:
    """
    Flatten areas where bases will be placed for competitive gameplay.
    """
    if spec.base_clear_radius <= 0:
        return grid

    rows = grid.rows
    cols = grid.cols

    original_heights = grid.heights.copy()
    new_heights = grid.heights.copy()

    vertex_spacing = spec.size_x / (cols - 1)

    base_radius = spec.base_clear_radius
    flatness = spec.base_flatness

    # In manual mode, only use custom positions. In procedural mode, use defaults if not set.
    if spec.manual_terrain:
        imp_base_x = spec.custom_imp_base_x
        imp_base_y = spec.custom_imp_base_y
        nf_base_x = spec.custom_nf_base_x
        nf_base_y = spec.custom_nf_base_y
    else:
        imp_base_x, imp_base_y = (
            (spec.custom_imp_base_x, spec.custom_imp_base_y)
            if spec.custom_imp_base_x is not None and spec.custom_imp_base_y is not None
            else spec.default_imp_base()
        )
        nf_base_x, nf_base_y = (
            (spec.custom_nf_base_x, spec.custom_nf_base_y)
            if spec.custom_nf_base_x is not None and spec.custom_nf_base_y is not None
            else spec.default_nf_base()
        )

    # Determine local average heights for the bases instead of global floor height
    def get_local_avg(bx: float, by: float, r_area: float) -> float:
        if bx is None or by is None:
            return 0.0
        heights = []
        for r_ in range(rows):
            wy = spec.origin_y + r_ * vertex_spacing
            if abs(wy - by) > r_area:
                continue
            for c_ in range(cols):
                wx = spec.origin_x + c_ * vertex_spacing
                if abs(wx - bx) > r_area:
                    continue
                if math.sqrt((wx - bx) ** 2 + (wy - by) ** 2) <= r_area:
                    heights.append(new_heights[r_, c_])
        return (
            sum(heights) / len(heights) if heights else spec.terrain_max_height * 0.15
        )

    imp_avg_height = get_local_avg(imp_base_x, imp_base_y, base_radius)
    nf_avg_height = get_local_avg(nf_base_x, nf_base_y, base_radius)

    imp_target_height = imp_avg_height
    nf_target_height = nf_avg_height

    # We want the plateau to be perfectly flat for the inner 60% of the radius.
    plateau_radius = base_radius * 0.6
    falloff_dist = base_radius - plateau_radius

    # Flatten bases
    for r in range(rows):
        world_y = spec.origin_y + r * vertex_spacing
        for c in range(cols):
            world_x = spec.origin_x + c * vertex_spacing

            dist_to_imp = 999999.0
            if imp_base_x is not None and imp_base_y is not None:
                dist_to_imp = math.sqrt(
                    (world_x - imp_base_x) ** 2 + (world_y - imp_base_y) ** 2
                )
            
            dist_to_nf = 999999.0
            if nf_base_x is not None and nf_base_y is not None:
                dist_to_nf = math.sqrt(
                    (world_x - nf_base_x) ** 2 + (world_y - nf_base_y) ** 2
                )

            if dist_to_imp < base_radius:
                dist = dist_to_imp
                target_height = imp_target_height
            elif dist_to_nf < base_radius:
                dist = dist_to_nf
                target_height = nf_target_height
            else:
                continue

            if dist <= plateau_radius:
                t = 1.0
            else:
                t = 1.0 - ((dist - plateau_radius) / falloff_dist)
                t = t * t * (3 - 2 * t)

            t = t * flatness

            current = new_heights[r, c]
            new_heights[r, c] = float(current * (1.0 - t) + target_height * t)

    avg_height = spec.terrain_max_height * 0.15  # Fallback for resource nodes
    # Flatten resource nodes
    if spec.resource_clear_radius > 0 and spec.custom_resources:
        res_radius = spec.resource_clear_radius
        res_flatness = spec.base_flatness * 0.6
        for res_x, res_y in spec.custom_resources:
            # First, calculate local average height for this resource
            local_heights = []
            for r in range(rows):
                world_y = spec.origin_y + r * vertex_spacing
                for c in range(cols):
                    world_x = spec.origin_x + c * vertex_spacing
                    dist_to_res = math.sqrt(
                        (world_x - res_x) ** 2 + (world_y - res_y) ** 2
                    )
                    if dist_to_res <= res_radius:
                        local_heights.append(new_heights[r, c])

            local_avg_height = (
                sum(local_heights) / len(local_heights) if local_heights else avg_height
            )

            # Now apply flattening using the local average height
            for r in range(rows):
                world_y = spec.origin_y + r * vertex_spacing
                for c in range(cols):
                    world_x = spec.origin_x + c * vertex_spacing
                    dist_to_res = math.sqrt(
                        (world_x - res_x) ** 2 + (world_y - res_y) ** 2
                    )
                    if dist_to_res < res_radius:
                        t = 1.0 - (dist_to_res / res_radius)
                        t = t * t * (3 - 2 * t)
                        t = t * res_flatness

                        current = new_heights[r, c]
                        new_heights[r, c] = current * (1.0 - t) + local_avg_height * t

    grid.heights = np.where(grid.global_selection_mask, new_heights, original_heights)

    return grid


def clamp_slope(grid: HeightGrid, max_step: int, use_mask: bool = True) -> HeightGrid:
    """
    Step 4: Clamp height differences between adjacent vertices.

    Ensures no adjacent vertices differ by more than max_step.
    Iterates until all differences are within limits.
    """
    rows = grid.rows
    cols = grid.cols

    original_heights = grid.heights.copy()
    new_heights = grid.heights.copy()

    changed = True
    passes = 0
    max_passes = 100

    while changed and passes < max_passes:
        changed = False
        passes += 1

        for r in range(rows):
            for c in range(cols):
                current = new_heights[r, c]

                if r > 0:
                    diff = new_heights[r - 1, c] - current
                    if abs(diff) > max_step:
                        new_adj = current + (max_step if diff > 0 else -max_step)
                        if new_adj != new_heights[r - 1, c]:
                            changed = True
                        new_heights[r - 1, c] = new_adj

                if r < rows - 1:
                    diff = new_heights[r + 1, c] - current
                    if abs(diff) > max_step:
                        new_adj = current + (max_step if diff > 0 else -max_step)
                        if new_adj != new_heights[r + 1, c]:
                            changed = True
                        new_heights[r + 1, c] = new_adj

                if c > 0:
                    diff = new_heights[r, c - 1] - current
                    if abs(diff) > max_step:
                        new_adj = current + (max_step if diff > 0 else -max_step)
                        if new_adj != new_heights[r, c - 1]:
                            changed = True
                        new_heights[r, c - 1] = new_adj

                if c < cols - 1:
                    diff = new_heights[r, c + 1] - current
                    if abs(diff) > max_step:
                        new_adj = current + (max_step if diff > 0 else -max_step)
                        if new_adj != new_heights[r, c + 1]:
                            changed = True
                        new_heights[r, c + 1] = new_adj

    if passes >= max_passes:
        print(f"Warning: slope clamping reached max passes ({max_passes})")

    if use_mask:
        grid.heights = np.where(grid.global_selection_mask, new_heights, original_heights)
    else:
        grid.heights = new_heights

    return grid


def quantize_heights(grid: HeightGrid, step: int, use_mask: bool = True) -> HeightGrid:
    """
    Step 7: Quantize heights to grid step.

    All heights snap to multiples of the quantization step.
    """
    if step <= 0:
        return grid

    original_heights = grid.heights.copy()
    new_heights = np.round(grid.heights / step) * step

    if use_mask:
        grid.heights = np.where(grid.global_selection_mask, new_heights, original_heights)
    else:
        grid.heights = new_heights

    return grid




def simulate_hydraulic_erosion(grid: HeightGrid, spec: TerrainSpec) -> HeightGrid:
    """
    Step 3: Simulate hydraulic erosion using droplet-based algorithm.

    Droplets spawn randomly on the terrain, move downhill following the gradient,
    erode terrain where moving fast, and deposit sediment where moving slow.
    Uses numpy for terrain storage with float64 precision to prevent overflow.

    Args:
        grid: HeightGrid to erode (modified in place)
        spec: TerrainSpec containing erosion parameters

    Returns:
        Modified HeightGrid with eroded terrain
    """
    import numpy as np

    rows = grid.rows
    cols = grid.cols
    iterations = spec.erosion_iterations
    lifetime = spec.erosion_droplet_lifetime

    original_heights = grid.heights.copy()

    terrain = np.array(grid.heights, dtype=np.float64)

    initial_min = float(np.min(terrain))
    initial_max = float(np.max(terrain))
    height_range = initial_max - initial_min

    sediment_capacity = 0.01
    erosion_rate = 0.005
    deposition_rate = 0.01
    evaporation_rate = 0.01
    max_erosion_per_step = height_range * 0.001
    max_deposition_per_step = height_range * 0.001

    rng = random.Random(spec.seed + 1000)

    # Fetch mask safely
    playability_mask = getattr(grid, "playability_mask", None)

    for _ in range(iterations):
        start_r = rng.randint(1, rows - 2)
        start_c = rng.randint(1, cols - 2)

        # Protect playable lanes: DO NOT spawn droplets on paths or bases
        # distance_field is negative inside the lane, positive outside.
        # We want to avoid spawning droplets near the lane (e.g. distance < 256.0).
        if playability_mask is not None and playability_mask[start_r, start_c] < 256.0:
            continue

        pos_r = float(start_r)
        pos_c = float(start_c)
        sediment = 0.0
        speed = 0.0

        for step in range(lifetime):
            ir = int(pos_r)
            ic = int(pos_c)

            if ir <= 0 or ir >= rows - 1 or ic <= 0 or ic >= cols - 1:
                break

            # Protect playable lanes: droplets instantly evaporate when hitting a lane
            if playability_mask is not None and playability_mask[ir, ic] < 256.0:
                break

            fx = pos_c - ic
            fy = pos_r - ir

            h00 = float(terrain[ir][ic])
            h01 = float(terrain[ir][ic + 1])
            h10 = float(terrain[ir + 1][ic])
            h11 = float(terrain[ir + 1][ic + 1])

            h_top = h00 * (1.0 - fx) + h01 * fx
            h_bot = h10 * (1.0 - fx) + h11 * fx
            height = h_top * (1.0 - fy) + h_bot * fy

            dx = (h00 * (1.0 - fy) + h10 * fy) - (h01 * (1.0 - fy) + h11 * fy)
            dy = (h00 * (1.0 - fx) + h01 * fx) - (h10 * (1.0 - fx) + h11 * fx)

            grad_len = math.sqrt(dx * dx + dy * dy)
            if grad_len < 1e-6:
                break

            nx = dx / grad_len
            ny = dy / grad_len

            pos_c += nx * 0.5
            pos_r += ny * 0.5

            new_ir = int(pos_r)
            new_ic = int(pos_c)

            if new_ir <= 0 or new_ir >= rows - 1 or new_ic <= 0 or new_ic >= cols - 1:
                break

            new_fx = pos_c - new_ic
            new_fy = pos_r - new_ir

            new_h00 = float(terrain[new_ir][new_ic])
            new_h01 = float(terrain[new_ir][new_ic + 1])
            new_h10 = float(terrain[new_ir + 1][new_ic])
            new_h11 = float(terrain[new_ir + 1][new_ic + 1])

            new_h_top = new_h00 * (1.0 - new_fx) + new_h01 * new_fx
            new_h_bot = new_h10 * (1.0 - new_fx) + new_h11 * new_fx
            new_height = new_h_top * (1.0 - new_fy) + new_h_bot * new_fy

            delta_h = new_height - height
            speed = max(speed * 0.3, abs(delta_h))

            if delta_h > 0:
                deposit_amount = min(sediment * deposition_rate, delta_h * 0.3)
                deposit_amount = min(deposit_amount, max_deposition_per_step)
                if deposit_amount > 0:
                    terrain[new_ir][new_ic] += (
                        deposit_amount * (1.0 - new_fx) * (1.0 - new_fy)
                    )
                    terrain[new_ir][new_ic + 1] += (
                        deposit_amount * new_fx * (1.0 - new_fy)
                    )
                    terrain[new_ir + 1][new_ic] += (
                        deposit_amount * (1.0 - new_fx) * new_fy
                    )
                    terrain[new_ir + 1][new_ic + 1] += deposit_amount * new_fx * new_fy
                    sediment -= deposit_amount
            else:
                max_sediment = sediment_capacity * speed * abs(delta_h)
                available_sediment = max_sediment - sediment
                if available_sediment > 0:
                    erode_amount = min(
                        erosion_rate * available_sediment, abs(delta_h) * 0.5
                    )
                    erode_amount = min(erode_amount, max_erosion_per_step)
                    if erode_amount > 0:
                        terrain[new_ir][new_ic] -= (
                            erode_amount * (1.0 - new_fx) * (1.0 - new_fy)
                        )
                        terrain[new_ir][new_ic + 1] -= (
                            erode_amount * new_fx * (1.0 - new_fy)
                        )
                        terrain[new_ir + 1][new_ic] -= (
                            erode_amount * (1.0 - new_fx) * new_fy
                        )
                        terrain[new_ir + 1][new_ic + 1] -= (
                            erode_amount * new_fx * new_fy
                        )
                        sediment += erode_amount

            sediment *= 1.0 - evaporation_rate

            if sediment < 1e-6 and speed < 1e-6:
                break

    new_heights = terrain.astype(np.float32)
    grid.heights = np.where(grid.global_selection_mask, new_heights, original_heights)

    return grid


def calculate_slopes(grid: HeightGrid) -> HeightGrid:
    """
    Step 4: Calculate the gradient (slope) magnitude at each vertex.

    Uses central differences for interior vertices and forward/backward
    differences at edges. Stores results in grid.slopes.

    The slope is the magnitude of the height gradient in world units,
    representing the steepness of terrain at each vertex.

    Args:
        grid: HeightGrid to calculate slopes for

    Returns:
        HeightGrid with slopes populated
    """
    rows = grid.rows
    cols = grid.cols
    cell_size = grid.cell_size

    slopes = [[0.0 for _ in range(cols)] for _ in range(rows)]

    for r in range(rows):
        for c in range(cols):
            if r == 0:
                dz_dr = grid.heights[r + 1, c] - grid.heights[r, c]
            elif r == rows - 1:
                dz_dr = grid.heights[r, c] - grid.heights[r - 1, c]
            else:
                dz_dr = (grid.heights[r + 1, c] - grid.heights[r - 1, c]) / 2.0

            if c == 0:
                dz_dc = grid.heights[r, c + 1] - grid.heights[r, c]
            elif c == cols - 1:
                dz_dc = grid.heights[r, c] - grid.heights[r, c - 1]
            else:
                dz_dc = (grid.heights[r, c + 1] - grid.heights[r, c - 1]) / 2.0

            slope_r = dz_dr / cell_size
            slope_c = dz_dc / cell_size
            slopes[r][c] = math.sqrt(slope_r * slope_r + slope_c * slope_c)

    grid.slopes = slopes
    return grid


def feather_mask_edges(grid: HeightGrid, feather_radius: int = 3) -> HeightGrid:
    """
    Apply feathering to mask edges to prevent sharp height discontinuities.

    Blends heights at mask boundaries over a specified radius to ensure
    smooth transitions and avoid seam validation errors.

    Args:
        grid: HeightGrid with global_selection_mask set
        feather_radius: Number of pixels to blend over at mask edges

    Returns:
        HeightGrid with feathered heights at mask boundaries
    """
    if grid.global_selection_mask is None or np.all(grid.global_selection_mask):
        return grid

    rows, cols = grid.rows, grid.cols
    mask = grid.global_selection_mask.astype(np.float32)
    heights = np.array(grid.heights, dtype=np.float32)

    # Compute distance transform: distance to nearest False pixel
    # Invert mask so True (selected) = 0 distance, False = positive distance
    inverted_mask = 1.0 - mask

    # Simple iterative distance computation (no scipy dependency)
    distance = np.zeros((rows, cols), dtype=np.float32)
    max_dist = rows + cols

    # Initialize: False pixels have distance 0, True pixels have max distance
    distance[inverted_mask > 0.5] = 0.0
    distance[mask > 0.5] = max_dist

    # Pass 1: top-left to bottom-right
    for r in range(rows):
        for c in range(cols):
            if distance[r, c] > 0:
                min_neighbor = distance[r, c]
                if r > 0:
                    min_neighbor = min(min_neighbor, distance[r - 1, c] + 1)
                if c > 0:
                    min_neighbor = min(min_neighbor, distance[r, c - 1] + 1)
                distance[r, c] = min_neighbor

    # Pass 2: bottom-right to top-left
    for r in range(rows - 1, -1, -1):
        for c in range(cols - 1, -1, -1):
            if distance[r, c] > 0:
                min_neighbor = distance[r, c]
                if r < rows - 1:
                    min_neighbor = min(min_neighbor, distance[r + 1, c] + 1)
                if c < cols - 1:
                    min_neighbor = min(min_neighbor, distance[r, c + 1] + 1)
                distance[r, c] = min_neighbor

    # Create feathering weight: 1.0 inside mask, 0.0 outside, smooth transition at edges
    feather_weight = np.clip(distance / feather_radius, 0.0, 1.0)

    # Apply feathering: blend heights toward original at edges
    # We need the original heights before any mask operations
    # Since we can't easily get that here, we'll smooth the transition
    # by averaging with neighbors at the feather boundary

    # We'll use a temporary array to store smoothed values
    smoothed_heights = heights.copy()

    for r in range(1, rows - 1):
        for c in range(1, cols - 1):
            weight = feather_weight[r, c]
            if 0.0 < weight < 1.0:
                # At feather boundary, blend with neighbors
                neighbor_avg = (
                    heights[r - 1, c] + heights[r + 1, c] +
                    heights[r, c - 1] + heights[r, c + 1]
                ) / 4.0
                smoothed_heights[r, c] = heights[r, c] * weight + neighbor_avg * (1.0 - weight)

    grid.heights = smoothed_heights
    return grid


def build_cells(spec: TerrainSpec, grid: HeightGrid) -> List[TerrainCell]:
    """
    Step 6: Build terrain cells from shared vertex grid.

    Each cell spans the full tile size, referencing all (2^power + 1)^2 vertices
    through the shared grid. Corner vertices define the cell extent.
    """
    cells = []
    cell_id = 0

    tiles_x = spec.tiles_x
    tiles_y = spec.tiles_y
    grid_span = spec.grid_size - 1

    for tile_row in range(tiles_y):
        for tile_col in range(tiles_x):
            grid_row = tile_row * grid_span
            grid_col = tile_col * grid_span

            vertex_tl = (grid_row, grid_col)
            vertex_tr = (grid_row, grid_col + grid_span)
            vertex_br = (grid_row + grid_span, grid_col + grid_span)
            vertex_bl = (grid_row + grid_span, grid_col)

            cell = TerrainCell(
                cell_id=cell_id,
                grid_row=grid_row,
                grid_col=grid_col,
                grid_span=grid_span,
                vertex_tl=vertex_tl,
                vertex_tr=vertex_tr,
                vertex_br=vertex_br,
                vertex_bl=vertex_bl,
            )
            cells.append(cell)
            cell_id += 1

    return cells


def validate_seams(cells: List[TerrainCell], grid: HeightGrid, spec: TerrainSpec) -> List[str]:
    """
    Step 7: Validate seam topology.

    Checks:
    - All cells use shared vertex references
    - No edge is shared by more than 2 cells
    - No T-junctions (all vertices on integer grid)
    - Heights obey slope limits

    Returns list of error messages (empty if valid).
    """
    errors = []

    if not cells:
        errors.append("No cells to validate")
        return errors

    rows = grid.rows
    cols = grid.cols

    edge_to_cells = {}

    for cell in cells:
        for r, c in cell.vertices:
            if r < 0 or r >= rows or c < 0 or c >= cols:
                errors.append(
                    f"Cell {cell.cell_id}: vertex ({r},{c}) out of bounds ({rows}x{cols})"
                )

    for cell in cells:
        edges = [
            (("top", cell.grid_row, cell.grid_col, cell.grid_col + 1), cell.cell_id),
            (
                ("bottom", cell.grid_row + 1, cell.grid_col, cell.grid_col + 1),
                cell.cell_id,
            ),
            (("left", cell.grid_row, cell.grid_row + 1, cell.grid_col), cell.cell_id),
            (
                ("right", cell.grid_row, cell.grid_row + 1, cell.grid_col + 1),
                cell.cell_id,
            ),
        ]

        for edge_key, cell_id in edges:
            if edge_key in edge_to_cells:
                edge_to_cells[edge_key].append(cell_id)
            else:
                edge_to_cells[edge_key] = [cell_id]

    for edge_key, cell_ids in edge_to_cells.items():
        if len(cell_ids) > 2:
            edge_type = edge_key[0]
            errors.append(
                f"Edge {edge_type} shared by {len(cell_ids)} cells: {cell_ids}"
            )

    for cell in cells:
        for edge in ["top", "bottom", "left", "right"]:
            edge_heights = cell.get_edge_heights(grid, edge)
            if len(edge_heights) >= 2:
                diff = abs(edge_heights[0] - edge_heights[1])
                if diff > spec.max_slope_step:

                    errors.append(
                        f"Cell {cell.cell_id} {edge} edge has height diff {diff:.1f} "
                        f"(heights: {edge_heights})"
                    )

    return errors


def build_underlay(spec: TerrainSpec, grid: HeightGrid) -> UnderlayBrush:
    """
    Step 8 (part 1): Build underlay brush beneath terrain.

    The underlay seals the map beneath the displacement terrain.
    """
    min_height = grid.min_height()
    bottom_z = int(min_height - spec.underlay_height)

    return UnderlayBrush(
        origin_x=spec.origin_x,
        origin_y=spec.origin_y,
        size_x=spec.size_x,
        size_y=spec.size_y,
        bottom_z=bottom_z,
        top_z=int(min_height),
        material=spec.underlay_material,
    )


def get_cell_heightmap(
    cell: TerrainCell,
    grid: HeightGrid,
    power: int,
) -> List[List[float]]:
    """
    Extract heightmap for a single displacement cell.

    Returns a 2D list of heights for the cell's vertices.
    All cells sample from the shared grid to ensure seam consistency.
    """
    grid_size = (2**power) + 1
    span = cell.grid_span

    step = span / (grid_size - 1) if grid_size > 1 else 1.0

    heights = []
    for i in range(grid_size):
        row = []
        for j in range(grid_size):
            r = round(cell.grid_row + i * step)
            c = round(cell.grid_col + j * step)
            r = max(0, min(r, grid.rows - 1))
            c = max(0, min(c, grid.cols - 1))
            h = grid.get_height(int(r), int(c))
            row.append(round(h, 1))
        heights.append(row)

    return heights


def get_cell_normals(
    heights: List[List[float]], power: int
) -> List[List[Tuple[float, float, float]]]:
    """
    Calculate normals for displacement vertices based on height gradients.

    Float format required for Source Engine compatibility.
    Uses strict vertical normals (0.0, 0.0, 1.0) to prevent sideways pulling.
    """
    grid_size = (2**power) + 1
    normals = []

    for iy in range(grid_size):
        row_normals = []
        for ix in range(grid_size):
            row_normals.append((0.0, 0.0, 1.0))
        normals.append(row_normals)

    return normals


def get_cell_slopes(
    cell: TerrainCell,
    grid: HeightGrid,
    power: int,
) -> List[List[float]]:
    """
    Extract slope values for a single displacement cell.

    Returns a 2D list of slope magnitudes for the cell's vertices.
    The slope is the gradient magnitude in world units per cell unit.

    Args:
        cell: TerrainCell to extract slopes for
        grid: HeightGrid containing slope data
        power: Displacement power (2, 3, or 4)

    Returns:
        2D list of slope values (0 = flat, higher = steeper)
    """
    grid_size = (2**power) + 1
    span = cell.grid_span

    step = span / (grid_size - 1) if grid_size > 1 else 1.0

    slopes = []
    for i in range(grid_size):
        row_slopes = []
        for j in range(grid_size):
            r = round(cell.grid_row + i * step)
            c = round(cell.grid_col + j * step)
            r = max(0, min(r, grid.rows - 1))
            c = max(0, min(c, grid.cols - 1))
            s = grid.slopes[r][c]
            row_slopes.append(float(s))
        slopes.append(row_slopes)

    return slopes


def apply_pipeline_for_preview(grid: HeightGrid, spec: TerrainSpec) -> HeightGrid:
    """
    Apply pipeline post-processing steps for preview accuracy.

    Runs erosion, smoothing, clamping, and quantization to show
    what the final export will look like. Used for WYSIWYG preview.
    In manual_terrain mode, returns the grid as-is (no modifications).
    """
    if spec.manual_terrain:
        return grid

    rows = grid.rows
    cols = grid.cols

    heights = np.array(grid.heights, dtype=np.float64)

    terrain_copy = HeightGrid(
        heights=heights,
        origin_x=grid.origin_x,
        origin_y=grid.origin_y,
        cell_size=grid.cell_size,
    )
    if grid.global_selection_mask is not None:
        terrain_copy.global_selection_mask = grid.global_selection_mask.copy()

    if spec.erosion_iterations > 0:
        import random as rng_module

        rng = rng_module.Random(spec.seed + 1000)
        iterations = min(spec.erosion_iterations, 5000)
        lifetime = spec.erosion_droplet_lifetime

        initial_min = float(np.min(heights))
        initial_max = float(np.max(heights))
        height_range = initial_max - initial_min

        sediment_capacity = 0.01
        erosion_rate = 0.005
        deposition_rate = 0.01
        evaporation_rate = 0.01
        max_erosion_per_step = height_range * 0.001
        max_deposition_per_step = height_range * 0.001

        playability_mask = getattr(grid, "playability_mask", None)

        for _ in range(iterations):
            start_r = rng.randint(1, rows - 2)
            start_c = rng.randint(1, cols - 2)

            if playability_mask is not None and playability_mask[start_r, start_c] > 0.5:
                continue

            pos_r = float(start_r)
            pos_c = float(start_c)
            sediment = 0.0
            speed = 0.0

            for step_idx in range(lifetime):
                ir = int(pos_r)
                ic = int(pos_c)

                if ir <= 0 or ir >= rows - 1 or ic <= 0 or ic >= cols - 1:
                    break

                if playability_mask is not None and playability_mask[ir, ic] > 0.5:
                    break

                fx = pos_c - ic
                fy = pos_r - ir

                h00 = float(terrain_copy.heights[ir, ic])
                h01 = float(terrain_copy.heights[ir, ic + 1])
                h10 = float(terrain_copy.heights[ir + 1, ic])
                h11 = float(terrain_copy.heights[ir + 1, ic + 1])

                h_top = h00 * (1.0 - fx) + h01 * fx
                h_bot = h10 * (1.0 - fx) + h11 * fx
                height = h_top * (1.0 - fy) + h_bot * fy

                dx = (h00 * (1.0 - fy) + h10 * fy) - (h01 * (1.0 - fy) + h11 * fy)
                dy = (h00 * (1.0 - fx) + h01 * fx) - (h10 * (1.0 - fx) + h11 * fx)

                grad_len = math.sqrt(dx * dx + dy * dy)
                if grad_len < 1e-6:
                    break

                nx = dx / grad_len
                ny = dy / grad_len

                pos_c += nx * 0.5
                pos_r += ny * 0.5

                new_ir = int(pos_r)
                new_ic = int(pos_c)

                if new_ir <= 0 or new_ir >= rows - 1 or new_ic <= 0 or new_ic >= cols - 1:
                    break

                new_fx = pos_c - new_ic
                new_fy = pos_r - new_ir

                new_h00 = float(terrain_copy.heights[new_ir, new_ic])
                new_h01 = float(terrain_copy.heights[new_ir, new_ic + 1])
                new_h10 = float(terrain_copy.heights[new_ir + 1, new_ic])
                new_h11 = float(terrain_copy.heights[new_ir + 1, new_ic + 1])

                new_h_top = new_h00 * (1.0 - new_fx) + new_h01 * new_fx
                new_h_bot = new_h10 * (1.0 - new_fx) + new_h11 * new_fx
                new_height = new_h_top * (1.0 - new_fy) + new_h_bot * new_fy

                delta_h = new_height - height
                speed = max(speed * 0.3, abs(delta_h))

                if delta_h > 0:
                    deposit_amount = min(sediment * deposition_rate, delta_h * 0.3)
                    deposit_amount = min(deposit_amount, max_deposition_per_step)
                    if deposit_amount > 0:
                        # For preview we might not need to respect the mask completely
                        # inside the droplet loop as it's too slow, so we can apply the mask
                        # outside via np.where at the end. Actually, `apply_pipeline_for_preview`
                        # doesn't strictly need the mask if it's just a preview, but let's apply
                        # the numpy operations directly here.
                        terrain_copy.heights[new_ir, new_ic] += (
                            deposit_amount * (1.0 - new_fx) * (1.0 - new_fy)
                        )
                        terrain_copy.heights[new_ir, new_ic + 1] += (
                            deposit_amount * new_fx * (1.0 - new_fy)
                        )
                        terrain_copy.heights[new_ir + 1, new_ic] += (
                            deposit_amount * (1.0 - new_fx) * new_fy
                        )
                        terrain_copy.heights[new_ir + 1, new_ic + 1] += (
                            deposit_amount * new_fx * new_fy
                        )
                        sediment -= deposit_amount
                else:
                    max_sediment = sediment_capacity * speed * abs(delta_h)
                    available_sediment = max_sediment - sediment
                    if available_sediment > 0:
                        erode_amount = min(
                            erosion_rate * available_sediment, abs(delta_h) * 0.5
                        )
                        erode_amount = min(erode_amount, max_erosion_per_step)
                        if erode_amount > 0:
                            terrain_copy.heights[new_ir, new_ic] -= (
                                erode_amount * (1.0 - new_fx) * (1.0 - new_fy)
                            )
                            terrain_copy.heights[new_ir, new_ic + 1] -= (
                                erode_amount * new_fx * (1.0 - new_fy)
                            )
                            terrain_copy.heights[new_ir + 1, new_ic] -= (
                                erode_amount * (1.0 - new_fx) * new_fy
                            )
                            terrain_copy.heights[new_ir + 1, new_ic + 1] -= (
                                erode_amount * new_fx * new_fy
                            )
                            sediment += erode_amount

                sediment *= 1.0 - evaporation_rate

                if sediment < 1e-6 and speed < 1e-6:
                    break

    if terrain_copy.global_selection_mask is not None:
        if terrain_copy.global_selection_mask.shape != terrain_copy.heights.shape:
            from src.compat_utils import scipy_zoom_equivalent
            scale_y = terrain_copy.heights.shape[0] / terrain_copy.global_selection_mask.shape[0]
            scale_x = terrain_copy.heights.shape[1] / terrain_copy.global_selection_mask.shape[1]
            terrain_copy.global_selection_mask = scipy_zoom_equivalent(
                terrain_copy.global_selection_mask.astype(np.float32), (scale_y, scale_x)
            ) > 0.5
        terrain_copy.heights = np.where(terrain_copy.global_selection_mask, terrain_copy.heights, heights)

    terrain_copy = smooth_heights(terrain_copy, iterations=2)
    terrain_copy = clamp_slope(terrain_copy, spec.max_slope_step, use_mask=False)
    terrain_copy = quantize_heights(terrain_copy, spec.height_quantization, use_mask=False)

    return terrain_copy


def slope_to_alpha(
    slope: float,
    flat_threshold: float = 0.005,
    steep_threshold: float = 0.03,
) -> int:
    """
    Convert slope value to alpha value for blend materials.

    Args:
        slope: Slope magnitude (rise/run, e.g., 0 = flat, 0.5 = ~26 degrees)
        flat_threshold: Slope below which alpha is 0 (fully primary texture)
        steep_threshold: Slope above which alpha is 255 (fully secondary texture)

    Returns:
        Alpha value 0-255
    """
    if slope <= flat_threshold:
        return 0
    if slope >= steep_threshold:
        return 255

    t = (slope - flat_threshold) / (steep_threshold - flat_threshold)
    t = t * t * (3 - 2 * t)
    return int(round(t * 255))


def get_cell_alphas(
    cell: TerrainCell,
    grid: HeightGrid,
    power: int,
    flat_threshold: float = 0.005,
    steep_threshold: float = 0.03,
) -> List[List[int]]:
    """
    Extract alpha values for a displacement cell based on slope.

    Args:
        cell: TerrainCell to extract alphas for
        grid: HeightGrid containing slope data
        power: Displacement power (2, 3, or 4)
        flat_threshold: Slope below which alpha is 0
        steep_threshold: Slope above which alpha is 255

    Returns:
        2D list of alpha values (0-255)
    """
    slopes = get_cell_slopes(cell, grid, power)
    grid_size = len(slopes)

    alphas = []
    for i in range(grid_size):
        row_alphas = []
        for j in range(grid_size):
            alpha = slope_to_alpha(slopes[i][j], flat_threshold, steep_threshold)
            row_alphas.append(alpha)
        alphas.append(row_alphas)

    return alphas


def export_minimap(
    spec: TerrainSpec, grid: HeightGrid, map_name: str, project_root: str
) -> None:
    """
    Exports a minimap texture combining heights (grayscale) and playability mask.
    Saves as 1024x1024 .vtf and creates corresponding .vmt file.
    """
    import struct
    import numpy as np
    from PIL import Image
    from pathlib import Path

    if grid.rows <= 0 or grid.cols <= 0:
        return

    min_h = grid.min_height()
    max_h = grid.max_height()
    h_range = max_h - min_h
    if h_range < 1e-6:
        h_range = 1.0

    heights_arr = np.array(grid.heights, dtype=np.float32)
    normalized = (heights_arr - min_h) / h_range
    base_img = (np.clip(normalized, 0.0, 1.0) * 255.0).astype(np.uint8)

    img_rgb = np.stack((base_img, base_img, base_img), axis=-1)

    mask = getattr(grid, "playability_mask", None)
    if mask is not None:
        shading = img_rgb.astype(np.float32)
        tint_color = np.array([200.0, 180.0, 140.0], dtype=np.float32)
        tinted_shading = shading * (tint_color / 255.0)

        # Tint slightly brighter where mask > 0.1
        mask_clip = np.clip(mask, 0.0, 1.0)
        alpha = mask_clip[:, :, np.newaxis] * 0.6

        final_rgb = shading * (1.0 - alpha) + tinted_shading * alpha
        img_rgb = np.clip(final_rgb, 0, 255).astype(np.uint8)

    out_folder = Path(project_root) / "materials" / "maps"
    out_folder.mkdir(parents=True, exist_ok=True)

    # Generate 1024x1024 image
    img = Image.fromarray(img_rgb, mode="RGB")
    img = img.resize((1024, 1024), Image.LANCZOS)

    img = img.transpose(Image.FLIP_TOP_BOTTOM)

    # Native VTF Export (v7.2, BGR888)
    bgr_data = np.array(img)[..., ::-1].copy()

    header = struct.pack(
        "<4s 2I I 2H I 2H 4s 3f 4s f I B i 2B H",
        b"VTF\0",
        7,
        2,
        80,
        1024,
        1024,
        0x0100 | 0x0200 | 0x2000,
        1,
        0,
        b"\0\0\0\0",
        0.0,
        0.0,
        0.0,
        b"\0\0\0\0",
        1.0,
        3,
        1,
        -1,
        0,
        0,
        1,
    )
    header += b"\0" * 15  # Padding to 80 bytes

    vtf_path = out_folder / f"{map_name}.vtf"
    with open(vtf_path, "wb") as f:
        f.write(header)
        f.write(bgr_data.tobytes())

    vmt_path = out_folder / f"{map_name}.vmt"
    vmt_content = f""""UnlitGeneric"
{{
    "$baseTexture" "maps/{map_name}"
    "$vertexcolor" 1
    "$vertexalpha" 1
    "$no_fullbright" 1
    "$ignorez" 1
    "%keywords" "empires"
}}"""
    vmt_path.write_text(vmt_content)

    print(
        "Minimap generated. For your Empires map script, use Top-Left: (0, 0) and Bottom-Right: (1024, 1024)."
    )


def run_pipeline(
    spec: TerrainSpec,
    map_name: Optional[str] = None,
    output_dir: Optional[str] = None,
    skip_layout_validation: bool = False,
    global_selection_mask: Optional[np.ndarray] = None,
    initial_heights: Optional[np.ndarray] = None,
) -> dict:
    """
    Run the complete terrain generation pipeline.

    Returns dict with:
    - spec: the input specification
    - grid: the height grid
    - cells: list of terrain cells
    - underlay: the underlay brush
    - errors: validation errors (empty if successful)
    """
    # Validate layout before starting
    layout_result = spec.validate_layout()
    if not layout_result.valid and not skip_layout_validation:
        raise ValueError(
            "Invalid layout configuration:\n" + "\n".join(layout_result.errors)
        )

    print("Running terrain pipeline...")
    print(
        f"  Spec: {spec.size_x}x{spec.size_y}, cell_size={spec.cell_size}, power={spec.displacement_power}"
    )

    print(f"  Step 1: Generate vertex grid ({spec.vertex_cols}x{spec.vertex_rows})")
    grid = generate_vertex_grid(spec)

    if initial_heights is not None:
        if initial_heights.shape != grid.heights.shape:
            from src.compat_utils import scipy_zoom_equivalent
            scale_y = grid.heights.shape[0] / initial_heights.shape[0]
            scale_x = grid.heights.shape[1] / initial_heights.shape[1]
            grid.heights = scipy_zoom_equivalent(
                initial_heights.astype(np.float32), (scale_y, scale_x)
            )
        else:
            grid.heights = initial_heights.astype(np.float32).copy()

    if global_selection_mask is not None:
        if global_selection_mask.shape != grid.heights.shape:
            from src.compat_utils import scipy_zoom_equivalent
            scale_y = grid.heights.shape[0] / global_selection_mask.shape[0]
            scale_x = grid.heights.shape[1] / global_selection_mask.shape[1]
            grid.global_selection_mask = scipy_zoom_equivalent(
                global_selection_mask.astype(np.float32), (scale_y, scale_x)
            ) > 0.5
        else:
            grid.global_selection_mask = global_selection_mask.copy()

    if spec.custom_image_path:
        print(f"  Step 2: Loading custom heightmap from {spec.custom_image_path}")
        grid = load_custom_heights(spec, grid)
    elif spec.manual_terrain:
        print("  Step 2: Manual terrain mode (flat base, user controls everything)")
        # Still use editor-drawn lane tool for playability if nodes exist
        if spec.custom_layout_nodes is not None:
            nodes = list(spec.custom_layout_nodes)
            connections = spec.custom_layout_connections or []
            print("  Step 2a: Using editor lane tool for playability mask")
            hard_mask = generate_playability_mask(
                spec, grid.rows, grid.cols, nodes, connections
            )
            grid.playability_mask = hard_mask
            print("  Step 2c: Generate heights with flat terrain (manual mode)")
            grid = generate_heights(spec, grid)
        else:
            grid.playability_mask = None
            print("  Step 2c: Generate heights with flat terrain (manual mode)")
            grid = generate_heights(spec, grid)
    else:
        if spec.generate_lanes:
            print("  Step 2a: Generate playability mask (Smoothstep distance field)")
            nodes, connections = generate_strategic_layout(spec)
            if spec.custom_layout_nodes is not None:
                nodes.extend(spec.custom_layout_nodes)
            if spec.custom_layout_connections is not None:
                connections.extend(spec.custom_layout_connections)
            hard_mask = generate_playability_mask(
                spec, grid.rows, grid.cols, nodes, connections
            )
            grid.playability_mask = hard_mask
        else:
            print(
                "  Step 2a: Skipping strategic lane generation (generate_lanes=False)"
            )
            grid.playability_mask = None

        print(
            f"  Step 2c: Generate heights with fBm (seed={spec.seed}, octaves={spec.noise_octaves})"
        )
        grid = generate_heights(spec, grid)

    print(f"    Height range: {grid.min_height():.1f} to {grid.max_height():.1f}")

    if spec.base_clear_radius > 0:
        print(
            f"  Step 2d: Pre-stamp base areas (radius={spec.base_clear_radius}, flatness={spec.base_flatness})"
        )
        grid = flatten_base_areas(grid, spec)

    if spec.manual_terrain:
        print("  Step 3-6: Manual terrain mode (no modifications)")
        grid = calculate_slopes(grid)
    else:
        print(
            f"  Step 3: Simulate hydraulic erosion ({spec.erosion_iterations} droplets, lifetime={spec.erosion_droplet_lifetime})"
        )
        grid = simulate_hydraulic_erosion(grid, spec)
        print(
            f"    Height range after erosion: {grid.min_height():.1f} to {grid.max_height():.1f}"
        )

        print("  Step 4: Calculate slopes")
        grid = calculate_slopes(grid)

        print("  Step 5: Smooth heights")
        grid = smooth_heights(grid, iterations=2)

        if spec.base_clear_radius > 0 and spec.base_flatness > 0.5:
            print("  Step 5b: Light touch-up for base areas after erosion")
            import copy

            spec_light = copy.copy(spec)
            spec_light.base_flatness = spec.base_flatness * 0.3
            grid = flatten_base_areas(grid, spec_light)
            print(
                f"    Height range after base flatten touch-up: {grid.min_height():.1f} to {grid.max_height():.1f}"
            )

    if not spec.manual_terrain:
        print(f"  Step 6: Clamp slope (max step={spec.max_slope_step})")
        grid = clamp_slope(grid, spec.max_slope_step)

        print(f"  Step 7: Quantize heights (step={spec.height_quantization})")
        grid = quantize_heights(grid, spec.height_quantization)

    # Apply feathering to mask edges if mask is present to prevent seam errors
    if grid.global_selection_mask is not None and not np.all(grid.global_selection_mask):
        print("  Step 7.5: Feather mask edges")
        grid = feather_mask_edges(grid, feather_radius=3)
        
        # FINAL STEP: Run a global slope clamp WITHOUT mask restriction to resolve
        # any remaining discontinuities introduced by the mask or feathering.
        # This ensures the map is 100% compile-safe (slope < 100).
        print("  Step 7.6: Final global slope clamp for seam safety")
        grid = clamp_slope(grid, spec.max_slope_step, use_mask=False)
        grid = quantize_heights(grid, spec.height_quantization, use_mask=False)

    print("  Step 8: Build cells")
    cells = build_cells(spec, grid)
    print(f"    Created {len(cells)} cells")

    print("  Step 9: Validate seams")
    errors = validate_seams(cells, grid, spec)
    if errors:
        print("    ERRORS FOUND:")
        for e in errors:
            print(f"      - {e}")
    else:
        print("    Validation passed!")

    print("  Step 10: Build underlay")
    underlay = build_underlay(spec, grid)
    print(f"    Underlay: z={underlay.bottom_z} to {underlay.top_z}")

    if map_name and output_dir:
        print("  Step 11: Export minimap")
        export_minimap(spec, grid, map_name, output_dir)

    return {
        "spec": spec,
        "grid": grid,
        "cells": cells,
        "underlay": underlay,
        "errors": errors,
    }


if __name__ == "__main__":
    if getattr(sys, "frozen", False):
        from terrain_spec import create_default_spec
    else:
        from src.terrain_spec import create_default_spec

    result = run_pipeline(create_default_spec())

    if result["errors"]:
        print("\nValidation FAILED:")
        for e in result["errors"]:
            print(f"  {e}")
    else:
        print("\nPipeline completed successfully!")
        print(f"  Grid: {result['grid'].rows}x{result['grid'].cols}")
        print(f"  Cells: {len(result['cells'])}")
        print(
            f"  Underlay: z={result['underlay'].bottom_z} to {result['underlay'].top_z}"
        )
