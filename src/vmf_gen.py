#!/usr/bin/env python3
"""
Enhanced VMF Generation with full rules support.
Uses all available data from map_rules.json.
"""

import os
import sys
import math
import json
import random
import numpy as np
from PIL import Image
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Tuple, Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent / "tools" / "vmflib"))
from vmflib import vmf
from vmflib.types import Vertex, Output
from vmflib.brush import DispInfo
from vmflib.tools import Block
from vmflib import vmf as vmf_lib

SAFE_EMPIRES_SKYBOXES = [
    "empsky_day1",
    "empsky_day2",
    "empsky_day3",
    "empsky_overcast1",
    "empsky_overcast2",
    "empsky_overcast3yellow",
    "empsky_sunset1",
    "empsky_sunset2",
]
SAFE_EMPIRES_SKYBOX_SET = set(SAFE_EMPIRES_SKYBOXES)
DEFAULT_SAFE_SKYBOX = "empsky_overcast2"
MAX_MAP_DISPINFO = 2048
WORLD_MIN_COORD = -16384
WORLD_MAX_COORD = 16384
WORLD_SAFE_MARGIN = 64


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


def choose_safe_skybox(
    requested_skybox: Optional[str], rules: Optional[Dict[str, Any]] = None
) -> str:
    """Return a deterministic, known-safe Empires skybox."""
    if requested_skybox:
        normalized = str(requested_skybox).strip().lower()
        if normalized in SAFE_EMPIRES_SKYBOX_SET:
            return normalized

    if rules:
        rule_skyboxes = rules.get("lighting_environment", {}).get(
            "typical_skyboxes", []
        )
        for sky in rule_skyboxes:
            normalized = str(sky).strip().lower()
            if normalized in SAFE_EMPIRES_SKYBOX_SET:
                return normalized

    return DEFAULT_SAFE_SKYBOX


def generate_skybox(
    valve_map: vmf.ValveMap,
    origin_x: int,
    origin_y: int,
    map_width: int,
    map_height: int,
    max_terrain_height: int,
    skyname: str = "empsky_overcast2",
) -> None:
    """Generate airtight skybox with exact flush coordinates, split into smaller sections."""
    wall_thickness = 64
    terrain_base_z = -512
    ceiling_z = max_terrain_height + 7072
    
    wall_height = ceiling_z - terrain_base_z
    wall_center_z = (ceiling_z + terrain_base_z) / 2.0
    max_brush_size = 2048

    map_end_x = origin_x + map_width
    map_end_y = origin_y + map_height

    # Expand outward where possible. If already at world bounds, place skybox walls inward.
    pad_west = wall_thickness if origin_x - wall_thickness >= WORLD_MIN_COORD else 0
    pad_east = wall_thickness if map_end_x + wall_thickness <= WORLD_MAX_COORD else 0
    pad_south = wall_thickness if origin_y - wall_thickness >= WORLD_MIN_COORD else 0
    pad_north = wall_thickness if map_end_y + wall_thickness <= WORLD_MAX_COORD else 0

    floor_min_x = max(WORLD_MIN_COORD, origin_x - pad_west)
    floor_max_x = min(WORLD_MAX_COORD, map_end_x + pad_east)
    floor_min_y = max(WORLD_MIN_COORD, origin_y - pad_south)
    floor_max_y = min(WORLD_MAX_COORD, map_end_y + pad_north)

    def split_range(start: int, end: int, max_size: int) -> List[Tuple[int, int]]:
        sections = []
        pos = start
        while pos < end:
            section_end = min(pos + max_size, end)
            sections.append((pos, section_end))
            pos = section_end
        if sections and sections[-1][1] != end:
            sections[-1] = (sections[-1][0], end)
        return sections

    x_sections = split_range(floor_min_x, floor_max_x, max_brush_size)
    y_sections = split_range(floor_min_y, floor_max_y, max_brush_size)
    x_wall_sections = split_range(floor_min_x, floor_max_x, max_brush_size)
    y_wall_sections = split_range(floor_min_y, floor_max_y, max_brush_size)

    for x_start, x_end in x_sections:
        for y_start, y_end in y_sections:
            cx = (x_start + x_end) // 2
            cy = (y_start + y_end) // 2
            w = x_end - x_start
            h = y_end - y_start

            floor = Block(
                Vertex(cx, cy, int(terrain_base_z - wall_thickness / 2)),
                (w, h, wall_thickness),
                "tools/toolsskybox",
            )
            floor.set_material("tools/toolsskybox")
            valve_map.world.children.append(floor)

            ceiling = Block(
                Vertex(cx, cy, int(ceiling_z + wall_thickness / 2)),
                (w, h, wall_thickness),
                "tools/toolsskybox",
            )
            ceiling.set_material("tools/toolsskybox")
            valve_map.world.children.append(ceiling)

    for x_start, x_end in x_wall_sections:
        cx = (x_start + x_end) // 2
        w = x_end - x_start
        if pad_north > 0:
            north_min_y = map_end_y
            north_max_y = map_end_y + wall_thickness
        else:
            north_min_y = map_end_y - wall_thickness
            north_max_y = map_end_y
        if pad_south > 0:
            south_min_y = origin_y - wall_thickness
            south_max_y = origin_y
        else:
            south_min_y = origin_y
            south_max_y = origin_y + wall_thickness
        north_y = (north_min_y + north_max_y) // 2
        south_y = (south_min_y + south_max_y) // 2

        north = Block(
            Vertex(
                cx,
                north_y,
                wall_center_z,
            ),
            (w, north_max_y - north_min_y, wall_height),
            "tools/toolsskybox",
        )
        north.set_material("tools/toolsskybox")
        valve_map.world.children.append(north)

        south = Block(
            Vertex(
                cx,
                south_y,
                wall_center_z,
            ),
            (w, south_max_y - south_min_y, wall_height),
            "tools/toolsskybox",
        )
        south.set_material("tools/toolsskybox")
        valve_map.world.children.append(south)

    for y_start, y_end in y_wall_sections:
        cy = (y_start + y_end) // 2
        h = y_end - y_start
        if pad_east > 0:
            east_min_x = map_end_x
            east_max_x = map_end_x + wall_thickness
        else:
            east_min_x = map_end_x - wall_thickness
            east_max_x = map_end_x
        if pad_west > 0:
            west_min_x = origin_x - wall_thickness
            west_max_x = origin_x
        else:
            west_min_x = origin_x
            west_max_x = origin_x + wall_thickness
        east_x = (east_min_x + east_max_x) // 2
        west_x = (west_min_x + west_max_x) // 2

        east = Block(
            Vertex(
                east_x,
                cy,
                wall_center_z,
            ),
            (east_max_x - east_min_x, h, wall_height),
            "tools/toolsskybox",
        )
        east.set_material("tools/toolsskybox")
        valve_map.world.children.append(east)

        west = Block(
            Vertex(
                west_x,
                cy,
                wall_center_z,
            ),
            (west_max_x - west_min_x, h, wall_height),
            "tools/toolsskybox",
        )
        west.set_material("tools/toolsskybox")
        valve_map.world.children.append(west)

    valve_map.world.skyname = skyname


def spawn_lighting(
    valve_map: vmf.ValveMap,
    rules: Dict[str, Any],
) -> None:
    """Spawn light_environment and env_sun entities based on rules."""
    lighting = rules.get("lighting_environment", {})
    light_env = lighting.get("light_environment", {})
    env_sun = lighting.get("env_sun", {})

    pitch_avg = light_env.get("pitch_stats", {}).get("avg", -20)
    sun_yaw_avg = env_sun.get("yaw_stats", {}).get("avg", 0)

    light_ent = vmf_lib.Entity("light_environment")
    light_ent.origin = "0.0 0.0 0.0"
    light_ent.properties["pitch"] = str(int(pitch_avg))
    light_ent.properties["angles"] = f"0 {sun_yaw_avg} 0"
    light_ent.properties["brightnessHDR"] = light_env.get(
        "brightnessHDR", "255 193 141 300"
    )
    light_ent.properties["ambientHDR"] = light_env.get("ambientHDR", "107 113 55 85")
    light_ent.properties["SunSpreadAngle"] = "2"

    sun_ent = vmf_lib.Entity("env_sun")
    sun_ent.origin = "0.0 0.0 0.0"
    sun_ent.properties["pitch"] = str(int(-pitch_avg))
    sun_ent.properties["angles"] = f"0 {sun_yaw_avg} 0"
    sun_ent.properties["sun_color"] = env_sun.get("sun_color", "249 216 147")


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


def spawn_base_entities_enhanced(
    valve_map: vmf.ValveMap,
    faction: str,
    origin_x: float,
    origin_y: float,
    terrain_z: float,
    map_center_x: float,
    map_center_y: float,
    rules: Optional[Dict[str, Any]] = None,
    heightmap: Optional[np.ndarray] = None,
    origin_x_world: int = 0,
    origin_y_world: int = 0,
    map_width: int = 4096,
    map_height: int = 4096,
    max_height: int = 512,
    tiles_x: int = 8,
    tiles_y: int = 8,
    power: int = 3,
    skip_commander: bool = False,
    skip_buildings: bool = False,
) -> None:
    """Spawn base entities for IMP or NF faction using data-driven placement."""
    if origin_x is None or origin_y is None:
        return
    if rules is None:
        rules = {}

    origin_x = quantize_coord(origin_x, 1.0)
    origin_y = quantize_coord(origin_y, 1.0)

    terrain_height = (
        get_terrain_height_at(
            origin_x,
            origin_y,
            heightmap,
            origin_x_world,
            origin_y_world,
            map_width,
            map_height,
            max_height,
            tiles_x,
            tiles_y,
            power,
        )
        if heightmap is not None
        else terrain_z
    )

    entity_orientations = rules.get("entity_orientations", {})
    faction_key = "nf" if faction == "nf" else "imp"
    commander_yaw = entity_orientations.get(f"{faction_key}_commander", {}).get(
        "circular_mean"
    )
    barracks_yaw = entity_orientations.get(f"{faction_key}_barracks", {}).get(
        "circular_mean"
    )

    if commander_yaw is None:
        commander_yaw = 0.0
    if barracks_yaw is None:
        barracks_yaw = 0.0

    commander_yaw = commander_yaw % 360
    barracks_yaw = barracks_yaw % 360

    base_layout = rules.get("base_layout", {})
    base_dist_avg = base_layout.get("separation", {}).get("avg")
    if base_dist_avg is None:
        base_dist_avg = 900.0
    base_dist_avg = min(base_dist_avg, 512.0)

    right_yaw_rad = math.radians(commander_yaw - 90)
    commander_x = origin_x + (math.cos(right_yaw_rad) * base_dist_avg)
    commander_y = origin_y + (math.sin(right_yaw_rad) * base_dist_avg)

    commander_terrain_h = (
        get_terrain_height_at(
            commander_x,
            commander_y,
            heightmap,
            origin_x_world,
            origin_y_world,
            map_width,
            map_height,
            max_height,
            tiles_x,
            tiles_y,
            power,
        )
        if heightmap is not None
        else terrain_height
    )

    if faction == "imp":
        commander_class = "emp_imp_commander"
        barracks_class = "emp_building_imp_barracks"
        team_num = 2
        commander_z = quantize_coord(commander_terrain_h + 64, 1.0)
        barracks_z = quantize_coord(terrain_height + 16, 1.0)
    elif faction == "nf":
        commander_class = "emp_nf_commander"
        barracks_class = "emp_building_nf_barracks"
        team_num = 3
        commander_z = quantize_coord(commander_terrain_h + 96, 1.0)
        barracks_z = quantize_coord(terrain_height + 16, 1.0)
    else:
        raise ValueError(f"Unknown faction: {faction}")

    if not skip_commander:
        commander_entity = vmf_lib.Entity(commander_class)
        commander_entity.origin = (
            f"{quantize_coord(commander_x)} {quantize_coord(commander_y)} {commander_z}"
        )
        commander_entity.properties["team"] = str(team_num)
        commander_entity.properties["angles"] = f"0 {(commander_yaw + 90) % 360} 0"

    if not skip_buildings:
        barracks_entity = vmf_lib.Entity(barracks_class)
        barracks_entity.origin = f"{quantize_coord(origin_x):.1f} {quantize_coord(origin_y):.1f} {barracks_z:.1f}"
        barracks_entity.properties["angles"] = f"0 {barracks_yaw:.1f} 0"
        barracks_entity.properties["team"] = str(team_num)
        barracks_entity.properties["startBuilt"] = "1"

        spawn_base_buildings(
            valve_map, faction, origin_x, origin_y, terrain_height, rules
        )

    if not skip_commander:
        pass
    if not skip_buildings:
        pass


def spawn_base_buildings(
    valve_map: vmf.ValveMap,
    faction: str,
    base_x: float,
    base_y: float,
    terrain_z: float,
    rules: Dict[str, Any],
) -> None:
    """Spawn additional buildings based on learned composition rules."""
    base_composition = rules.get("base_composition", {})
    faction_key = f"{faction}_buildings"
    buildings = base_composition.get(faction_key, {})

    building_offsets = {
        "refinery": (96, 0),
        "armory": (-96, 0),
        "vehiclefactory": (0, 96),
        "mgturret": (0, -96),
        "mlturret": (96, 96),
        "radar": (-96, 96),
        "repairstation": (96, -96),
    }

    building_classes = {
        "refinery": f"emp_building_{faction}_refinery",
        "armory": f"emp_building_{faction}_armory",
        "vehiclefactory": f"emp_building_{faction}_vehiclefactory",
        "mgturret": f"emp_building_{faction}_mgturret",
        "mlturret": f"emp_building_{faction}_mlturret",
        "radar": f"emp_building_{faction}_radar",
        "repairstation": f"emp_building_{faction}_repairstation",
    }

    faction_prefix = "NF" if faction == "nf" else "BE"
    faction_lower = faction_prefix.lower()

    building_models = {
        "refinery": f"models/{faction_prefix}/Buildings/Refinery/{faction_lower}_refinery.mdl",
        "armory": f"models/{faction_prefix}/Buildings/Armory/{faction_lower}_armory.mdl",
        "vehiclefactory": f"models/{faction_prefix}/Buildings/VehicleFactory/{faction_lower}_vehicle_factory.mdl",
        "mgturret": f"models/{faction_prefix}/turrets/mg_lvl2/{faction_lower}_turret_mg_lvl2.mdl",
        "mlturret": f"models/{faction_prefix}/turrets/ml_lvl2/{faction_lower}_turret_ml_lvl2.mdl",
        "radar": f"models/{faction_prefix}/Buildings/Radar/{faction_lower}_radar.mdl",
        "repairstation": f"models/{faction_prefix}/Buildings/RepairStation/{faction_lower}_repair_station.mdl",
    }

    team_num = 2 if faction == "imp" else 3

    for building_type, presence_data in buildings.items():
        if building_type == "barracks":
            continue

        presence_pct = presence_data.get("presence_frequency_pct", 0)
        should_spawn = random.random() * 100 < presence_pct

        if should_spawn and building_type in building_classes:
            offset = building_offsets.get(building_type, (0, 0))
            building_x = base_x + offset[0]
            building_y = base_y + offset[1]
            building_z = quantize_coord(terrain_z + 32, 1.0)

            building_entity = vmf_lib.Entity(building_classes[building_type])
            building_entity.origin = f"{quantize_coord(building_x)} {quantize_coord(building_y)} {building_z}"
            building_entity.properties["team"] = str(team_num)
            if building_type in building_models:
                building_entity.properties["model"] = building_models[building_type]
            building_entity.properties["startBuilt"] = "1"
            if building_type in ("mgturret", "mlturret"):
                building_entity.properties["level"] = "2"


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


def spawn_resource_nodes_enhanced(
    valve_map: vmf.ValveMap,
    faction: str,
    base_x: float,
    base_y: float,
    terrain_height: int,
    map_center_x: float,
    map_center_y: float,
    rules: Dict[str, Any],
    heightmap: Optional[np.ndarray] = None,
    origin_x: int = 0,
    origin_y: int = 0,
    map_width: int = 4096,
    map_height: int = 4096,
    max_height: int = 512,
    tiles_x: int = 8,
    tiles_y: int = 8,
    power: int = 3,
) -> None:
    """Spawn resource nodes around a base using learned placement patterns."""
    if base_x is None or base_y is None:
        return

    resource_strategy = rules.get("resource_strategy", {})

    node_count_avg = resource_strategy.get("node_count_per_map", {}).get("avg", 9)
    node_count = max(2, int(round(node_count_avg / 2)))

    scale_factor = map_width / 27000
    dist_to_base_avg = (
        resource_strategy.get(f"node_distance_to_{faction}_base", {}).get("avg", 1500)
        * scale_factor
    )
    dist_to_base_avg = min(dist_to_base_avg, map_width * 0.4)

    base_radius = rules.get("base_clear_radius", 512)
    # Ensure resource node spawns INSIDE the base flattened area if possible,
    # but strictly OUTSIDE the barracks center radius
    if base_radius > 512:
        dist_to_base_avg = min(dist_to_base_avg, base_radius * 0.8)

    dist_to_base_avg = max(dist_to_base_avg, 256.0)

    team_num = 2 if faction == "imp" else 3

    prefabs = rules.get("learned_prefabs", {}).get("resource_cluster", {})
    prop_offset = prefabs.get("prop_offset", {})

    yaw_to_center = calculate_yaw_to_center(base_x, base_y, map_center_x, map_center_y)
    angles = [yaw_to_center + i * (360 / node_count) for i in range(node_count)]

    for i in range(node_count):
        angle = angles[i]
        offset_dist = random.uniform(dist_to_base_avg * 0.8, dist_to_base_avg * 1.2)
        if base_radius > 512:
            offset_dist = min(offset_dist, base_radius * 0.95)
        offset_dist = max(offset_dist, 256.0)

        angle_rad = math.radians(angle)
        node_x = base_x + (math.cos(angle_rad) * offset_dist)
        node_y = base_y + (math.sin(angle_rad) * offset_dist)

        map_min_x = origin_x + 64
        map_max_x = origin_x + map_width - 64
        map_min_y = origin_y + 64
        map_max_y = origin_y + map_height - 64

        node_x = quantize_coord(max(map_min_x, min(map_max_x, node_x)), 1.0)
        node_y = quantize_coord(max(map_min_y, min(map_max_y, node_y)), 1.0)
        node_terrain_z = get_terrain_height_at(
            node_x,
            node_y,
            heightmap,
            origin_x,
            origin_y,
            map_width,
            map_height,
            max_height,
            tiles_x,
            tiles_y,
            power,
        )
        # Tutorial: Place it at the very bottom, touching the ground.
        node_z = node_terrain_z

        model_targetname = f"Res_Model_{faction.upper()}_{i}"
        point_targetname = f"Res_Point_{faction.upper()}_{i}"
        smoke_targetname = f"Res_Smoke_{faction.upper()}_{i}"

        prop_dx_raw = random.uniform(
            prop_offset.get("dx", {}).get("min", -40),
            prop_offset.get("dx", {}).get("max", 64),
        )
        prop_dy_raw = random.uniform(
            prop_offset.get("dy", {}).get("min", -88),
            prop_offset.get("dy", {}).get("max", 30),
        )

        prop_x = node_x + prop_dx_raw
        prop_y = node_y + prop_dy_raw
        prop_x = quantize_coord(max(map_min_x, min(map_max_x, prop_x)), 1.0)
        prop_y = quantize_coord(max(map_min_y, min(map_max_y, prop_y)), 1.0)

        prop_terrain_z = get_terrain_height_at(
            prop_x,
            prop_y,
            heightmap,
            origin_x,
            origin_y,
            map_width,
            map_height,
            max_height,
            tiles_x,
            tiles_y,
            power,
        )

        # Prevent negative Z offsets to ensure the model sticks out of the ground
        # but retain the variation
        prop_dz_raw = random.uniform(
            0,
            max(0, prop_offset.get("dz", {}).get("max", 49)),
        )

        prop_z = prop_terrain_z + prop_dz_raw

        prop_z = quantize_coord(prop_z, 1.0)
        node_x = quantize_coord(node_x, 1.0)
        node_y = quantize_coord(node_y, 1.0)
        node_z = quantize_coord(node_z, 1.0)

        resource_logic = vmf_lib.Entity("emp_resource_point")
        resource_logic.origin = f"{node_x:.1f} {node_y:.1f} {node_z:.1f}"
        resource_logic.properties["targetname"] = point_targetname
        resource_logic.properties["team"] = str(team_num)
        resource_logic.properties["StartDisabled"] = "0"
        resource_logic.properties["Enabled"] = "1"
        resource_logic.properties["ResourcesSecond"] = "3"
        resource_logic.properties["MaxResources"] = "-1"

        resource_prop = vmf_lib.Entity("emp_resource_point_prop")
        resource_prop.origin = f"{prop_x:.1f} {prop_y:.1f} {prop_z:.1f}"
        resource_prop.properties["targetname"] = model_targetname
        resource_prop.properties["team"] = str(team_num)
        resource_prop.properties["model"] = "models/props_wasteland/rockcliff01b.mdl"
        resource_prop.properties["Enabled"] = "1"
        resource_prop.properties["angles"] = f"0 {random.uniform(0, 360):.1f} 0"

        conn = vmf_lib.Connections()
        conn.children.append(
            Output("OnEnable", model_targetname, "InputEnable", "", 0, -1)
        )
        conn.children.append(
            Output("OnDisable", model_targetname, "InputDisable", "", 0, -1)
        )
        conn.children.append(
            Output("OnDisable", smoke_targetname, "TurnOff", "", 0, -1)
        )
        conn.children.append(Output("OnEnable", smoke_targetname, "TurnOn", "", 0, -1))
        resource_logic.children.append(conn)

        smoke = vmf_lib.Entity("env_smokestack")
        smoke.origin = f"{prop_x:.1f} {prop_y:.1f} {prop_z + 80:.1f}"
        smoke.properties["targetname"] = smoke_targetname
        smoke.properties["InitialState"] = "1"
        smoke.properties["BaseSpread"] = "20"
        smoke.properties["SpreadSpeed"] = "10"
        smoke.properties["Speed"] = "30"
        smoke.properties["StartSize"] = "20"
        smoke.properties["EndSize"] = "30"
        smoke.properties["Rate"] = "15"
        smoke.properties["JetLength"] = "200"
        smoke.properties["SmokeMaterial"] = "particle/particle_smokegrenade.vmt"
        smoke.properties["rendercolor"] = "100 100 100"


def spawn_custom_resources(
    valve_map: vmf.ValveMap,
    custom_points: List[Tuple[float, float]],
    heightmap: Optional[np.ndarray] = None,
    origin_x: int = 0,
    origin_y: int = 0,
    map_width: int = 4096,
    map_height: int = 4096,
    max_height: int = 512,
    tiles_x: int = 8,
    tiles_y: int = 8,
    power: int = 3,
) -> None:
    """Spawn neutral custom resource nodes at user-specified positions."""
    prefabs = {
        "prop_offset": {
            "dx": {"min": -40, "max": 64},
            "dy": {"min": -88, "max": 30},
            "dz": {"max": 49},
        }
    }
    prop_offset = prefabs.get("prop_offset", {})

    map_min_x = origin_x + 64
    map_max_x = origin_x + map_width - 64
    map_min_y = origin_y + 64
    map_max_y = origin_y + map_height - 64

    for i, (node_x, node_y) in enumerate(custom_points):
        node_x = quantize_coord(max(map_min_x, min(map_max_x, node_x)), 1.0)
        node_y = quantize_coord(max(map_min_y, min(map_max_y, node_y)), 1.0)
        node_terrain_z = get_terrain_height_at(
            node_x,
            node_y,
            heightmap,
            origin_x,
            origin_y,
            map_width,
            map_height,
            max_height,
            tiles_x,
            tiles_y,
            power,
        )
        # Tutorial: Place it at the very bottom, touching the ground.
        node_z = node_terrain_z

        point_targetname = f"Res_Point_Neutral_{i}"
        model_targetname = f"Res_Model_Neutral_{i}"
        smoke_targetname = f"Res_Smoke_Neutral_{i}"

        prop_dx_raw = random.uniform(
            prop_offset.get("dx", {}).get("min", -40),
            prop_offset.get("dx", {}).get("max", 64),
        )
        prop_dy_raw = random.uniform(
            prop_offset.get("dy", {}).get("min", -88),
            prop_offset.get("dy", {}).get("max", 30),
        )

        prop_x = node_x + prop_dx_raw
        prop_y = node_y + prop_dy_raw

        prop_x = quantize_coord(max(map_min_x, min(map_max_x, prop_x)), 1.0)
        prop_y = quantize_coord(max(map_min_y, min(map_max_y, prop_y)), 1.0)

        prop_terrain_z = get_terrain_height_at(
            prop_x,
            prop_y,
            heightmap,
            origin_x,
            origin_y,
            map_width,
            map_height,
            max_height,
            tiles_x,
            tiles_y,
            power,
        )

        prop_dz_raw = random.uniform(
            0,
            max(0, prop_offset.get("dz", {}).get("max", 49)),
        )

        prop_z = prop_terrain_z + prop_dz_raw
        prop_z = quantize_coord(prop_z, 1.0)
        node_z = quantize_coord(node_z, 1.0)

        resource_logic = vmf_lib.Entity("emp_resource_point")
        resource_logic.origin = f"{node_x:.1f} {node_y:.1f} {node_z:.1f}"
        resource_logic.properties["targetname"] = point_targetname
        resource_logic.properties["StartDisabled"] = "0"
        resource_logic.properties["Enabled"] = "1"
        resource_logic.properties["ResourcesSecond"] = "3"
        resource_logic.properties["MaxResources"] = "-1"

        resource_prop = vmf_lib.Entity("emp_resource_point_prop")
        resource_prop.origin = f"{prop_x:.1f} {prop_y:.1f} {prop_z:.1f}"
        resource_prop.properties["targetname"] = model_targetname
        resource_prop.properties["model"] = "models/props_wasteland/rockcliff01b.mdl"
        resource_prop.properties["Enabled"] = "1"
        resource_prop.properties["angles"] = f"0 {random.uniform(0, 360):.1f} 0"

        conn = vmf_lib.Connections()
        conn.children.append(
            Output("OnEnable", model_targetname, "InputEnable", "", 0, -1)
        )
        conn.children.append(
            Output("OnDisable", model_targetname, "InputDisable", "", 0, -1)
        )
        conn.children.append(
            Output("OnDisable", smoke_targetname, "TurnOff", "", 0, -1)
        )
        conn.children.append(Output("OnEnable", smoke_targetname, "TurnOn", "", 0, -1))
        resource_logic.children.append(conn)

        smoke = vmf_lib.Entity("env_smokestack")
        smoke.origin = f"{prop_x:.1f} {prop_y:.1f} {prop_z + 80:.1f}"
        smoke.properties["targetname"] = smoke_targetname
        smoke.properties["InitialState"] = "1"
        smoke.properties["BaseSpread"] = "20"
        smoke.properties["SpreadSpeed"] = "10"
        smoke.properties["Speed"] = "30"
        smoke.properties["StartSize"] = "20"
        smoke.properties["EndSize"] = "30"
        smoke.properties["Rate"] = "15"
        smoke.properties["JetLength"] = "200"
        smoke.properties["SmokeMaterial"] = "particle/particle_smokegrenade.vmt"
        smoke.properties["rendercolor"] = "100 100 100"


def spawn_info_nodes(
    valve_map: vmf.ValveMap,
    imp_base_x: float,
    imp_base_y: float,
    nf_base_x: float,
    nf_base_y: float,
    map_width: int,
    map_height: int,
    terrain_height: int,
    rules: Dict[str, Any],
    origin_x: int = 0,
    origin_y: int = 0,
) -> None:
    """Spawn info_nodes based on pathing rules."""
    pathing = rules.get("pathing", {})
    info_nodes = pathing.get("info_nodes", {})
    node_count_avg = info_nodes.get("count_per_map", {}).get("avg", 20)
    clustering_threshold = info_nodes.get("clustering_threshold", 400)
    min_cluster_size = info_nodes.get("min_cluster_size", 3)

    node_count = max(4, int(node_count_avg / 2))

    map_end_x = origin_x + map_width
    map_end_y = origin_y + map_height
    margin = 256

    important_points = [
        (imp_base_x, imp_base_y),
        (nf_base_x, nf_base_y),
        (0.0, 0.0),
        (imp_base_x + 300, imp_base_y + 300),
        (nf_base_x - 300, nf_base_y - 300),
        (200, 0.0),
        (-200, 0.0),
        (0.0, 200),
        (0.0, -200),
    ]

    node_id = 100

    for point_x, point_y in important_points[:4]:
        for _ in range(min_cluster_size):
            offset_x = random.uniform(
                -clustering_threshold / 2, clustering_threshold / 2
            )
            offset_y = random.uniform(
                -clustering_threshold / 2, clustering_threshold / 2
            )

            node_x = point_x + offset_x
            node_y = point_y + offset_y
            node_x = max(origin_x + margin, min(node_x, map_end_x - margin))
            node_y = max(origin_y + margin, min(node_y, map_end_y - margin))
            node_x = quantize_coord(node_x, 1.0)
            node_y = quantize_coord(node_y, 1.0)
            node_z = quantize_coord(terrain_height + 16, 1.0)

            yaw = calculate_yaw_to_center(point_x, point_y, 0.0, 0.0)

            node = vmf_lib.Entity("info_node")
            node.origin = f"{node_x} {node_y} {node_z}"
            node.properties["angles"] = f"0 {yaw} 0"
            node.properties["nodetype"] = "0"
            node.properties["targetname"] = f"node_{node_id}"
            node_id += 1

    remaining_nodes = node_count - len(important_points[:4]) * min_cluster_size
    for _ in range(max(0, remaining_nodes)):
        node_x = random.uniform(origin_x + margin, map_end_x - margin)
        node_y = random.uniform(origin_y + margin, map_end_y - margin)
        node_z = quantize_coord(terrain_height + 16, 1.0)
        yaw = random.uniform(0, 360)

        node = vmf_lib.Entity("info_node")
        node.origin = f"{quantize_coord(node_x)} {quantize_coord(node_y)} {node_z}"
        node.properties["angles"] = f"0 {yaw} 0"
        node.properties["nodetype"] = "0"
        node.properties["targetname"] = f"node_{node_id}"
        node_id += 1


def spawn_required_entities_enhanced(
    valve_map: vmf.ValveMap,
    map_width: int,
    map_height: int,
    max_terrain_height: int,
    rules: Optional[Dict[str, Any]] = None,
    origin_x: int = 0,
    origin_y: int = 0,
) -> None:
    """Spawn required Empires Mod entities with enhanced rules."""
    if rules is None:
        rules = {}

    center_x = 0.0
    center_y = 0.0

    info_params = vmf_lib.Entity("emp_info_params")
    info_params.origin = f"{center_x:.1f} {center_y:.1f} 0.0"
    # Required gameplay params: without non-zero tickets/resources,
    # Empires can immediately declare a winner and lock team switching.
    info_params.properties["Skin"] = "1"
    info_params.properties["NFRes"] = "400"
    info_params.properties["NFReinf"] = "400"
    info_params.properties["ImpRes"] = "400"
    info_params.properties["ImpReinf"] = "400"
    info_params.properties["eng_restrict_NF"] = "0"
    info_params.properties["eng_restrict_Imp"] = "0"
    info_params.properties["AutoResearch"] = "0"

    empires_meta = rules.get("empires_mod_meta", {})
    minimap_camera = empires_meta.get("minimap_camera", {})
    minimap_z_avg = minimap_camera.get("z_height_stats", {}).get("avg")
    minimap_z_median = minimap_camera.get("z_height_stats", {}).get("median")

    if minimap_z_median is not None:
        overview_z = max(1087, minimap_z_median)
    elif minimap_z_avg is not None:
        overview_z = max(1087, minimap_z_avg)
    else:
        overview_z = max(1087, max_terrain_height + 512)

    info_overview = vmf_lib.Entity("emp_info_map_overview")
    info_overview.origin = f"{center_x:.1f} {center_y:.1f} {overview_z:.1f}"
    info_overview.properties["angles"] = "90 0 0"


def spawn_player_spawn_points(
    valve_map: vmf.ValveMap,
    imp_base_x: float,
    imp_base_y: float,
    nf_base_x: float,
    nf_base_y: float,
    terrain_height: int,
    rules: Dict[str, Any],
) -> None:
    """Spawn player spawn points based on learned frequency data."""
    spawn_system = rules.get("spawn_system", {})
    spawn_freq = spawn_system.get("spawn_point_frequency_by_type", {})

    imp_spawn_pct = spawn_freq.get("emp_info_player_Imp", 97)
    nf_spawn_pct = spawn_freq.get("emp_info_player_NF", 98)

    imp_count = 4 if imp_spawn_pct > 50 else 0
    nf_count = 4 if nf_spawn_pct > 50 else 0

    spawn_offset = 200
    if imp_base_x is not None and imp_base_y is not None:
        for i in range(imp_count):
            angle = (i / imp_count) * 360
            angle_rad = math.radians(angle)
            spawn_x = imp_base_x + math.cos(angle_rad) * spawn_offset
            spawn_y = imp_base_y + math.sin(angle_rad) * spawn_offset

            spawn = vmf_lib.Entity("emp_info_player_Imp")
            spawn.origin = f"{quantize_coord(spawn_x)} {quantize_coord(spawn_y)} {quantize_coord(terrain_height + 16)}"
            spawn.properties["angles"] = f"0 {angle} 0"

    if nf_base_x is not None and nf_base_y is not None:
        for i in range(nf_count):
            angle = (i / nf_count) * 360
            angle_rad = math.radians(angle)
            spawn_x = nf_base_x + math.cos(angle_rad) * spawn_offset
            spawn_y = nf_base_y + math.sin(angle_rad) * spawn_offset

            spawn = vmf_lib.Entity("emp_info_player_NF")
            spawn.origin = f"{quantize_coord(spawn_x)} {quantize_coord(spawn_y)} {quantize_coord(terrain_height + 16)}"
            spawn.properties["angles"] = f"0 {angle} 0"


def spawn_capture_points(
    valve_map: vmf.ValveMap,
    imp_base_x: float,
    imp_base_y: float,
    nf_base_x: float,
    nf_base_y: float,
    center_x: float,
    center_y: float,
    terrain_height: int,
    rules: Dict[str, Any],
) -> None:
    """Spawn capture points based on learned frequency data."""
    if imp_base_x is None or nf_base_x is None:
        return
    spawn_system = rules.get("spawn_system", {})
    cap_freq = spawn_system.get("capture_point_frequency_by_type", {})

    cap_pct = cap_freq.get("emp_cap_point", 53)
    cap_count = 3 if cap_pct > 50 else 1

    for i in range(cap_count):
        if cap_count == 1:
            t = 0.5
        else:
            t = (i + 1) / (cap_count + 1)

        cap_x = imp_base_x + (nf_base_x - imp_base_x) * t
        cap_y = imp_base_y + (nf_base_y - imp_base_y) * t

        cap = vmf_lib.Entity("emp_cap_point")
        cap.origin = f"{quantize_coord(cap_x)} {quantize_coord(cap_y)} {quantize_coord(terrain_height + 8)}"
        cap.properties["point_num"] = str(i)
        cap.properties["neutral_owner"] = "0"

        cap_model = vmf_lib.Entity("emp_cap_model")
        cap_model.origin = f"{quantize_coord(cap_x)} {quantize_coord(cap_y)} {quantize_coord(terrain_height + 8)}"
        cap_model.properties["model"] = "models/common/emp_snow/flag_capmodel1a.mdl"
        cap_model.properties["angles"] = "0 0 0"


@dataclass
class PipelineSpec:
    """Specification for VMF generation pipeline."""

    map_name: str
    heightmap_path: Optional[str] = None

    terrain_max_height: int = 512
    terrain_actual_max: Optional[float] = None
    terrain_tile_size: int = 512
    terrain_power: int = 3
    terrain_material: str = "common/nature/blend_grass_mountainwall_000"
    skybox: Optional[str] = None
    terrain_tiles_x: int = 8
    terrain_tiles_y: int = 8

    output_dir: str = "."
    rules_file: str = "map_rules.json"
    use_enhanced_spawning: bool = True
    include_detail_props: bool = False
    disable_commander: bool = False
    disable_buildings: bool = False
    disable_resource_nodes: bool = False
    disable_capture_points: bool = True
    minimal_map: bool = False
    terrain_only: bool = False
    base_clear_radius: int = 512
    base_flatness: float = 0.8

    custom_imp_base_x: Optional[float] = None
    custom_imp_base_y: Optional[float] = None
    custom_nf_base_x: Optional[float] = None
    custom_nf_base_y: Optional[float] = None
    custom_resources: Optional[List[Tuple[float, float]]] = None
    manual_terrain: bool = False

    def default_imp_base(self) -> Tuple[float, float]:
        """
        Get the default imperial base spawn position (25% of map size).
        """
        size_x = self.terrain_tiles_x * self.terrain_tile_size
        size_y = self.terrain_tiles_y * self.terrain_tile_size
        origin_x = -size_x / 2.0
        origin_y = -size_y / 2.0
        return (
            float(origin_x + size_x * 0.25),
            float(origin_y + size_y * 0.25),
        )

    def default_nf_base(self) -> Tuple[float, float]:
        """
        Get the default northern faction base spawn position (75% of map size).
        """
        size_x = self.terrain_tiles_x * self.terrain_tile_size
        size_y = self.terrain_tiles_y * self.terrain_tile_size
        origin_x = -size_x / 2.0
        origin_y = -size_y / 2.0
        return (
            float(origin_x + size_x * 0.75),
            float(origin_y + size_y * 0.75),
        )

    def get_required_heightmap_size(self) -> Tuple[int, int]:
        """Calculate required heightmap dimensions for displacement tiles."""
        grid_size = (2**self.terrain_power) + 1
        w = self.terrain_tiles_x * (grid_size - 1) + 1
        h = self.terrain_tiles_y * (grid_size - 1) + 1
        return w, h


class DisplacementVMF:
    """Generates Source Engine VMF files with proper displacement terrain."""

    def __init__(self, spec: PipelineSpec):
        self.spec = spec
        self.heightmap: Optional[np.ndarray] = None
        self.heightmap_width: int = 0
        self.heightmap_height: int = 0

    def load_heightmap(self, path: str, auto_resize: bool = True) -> np.ndarray:
        """Load heightmap from file, optionally auto-resizing to required dimensions."""
        img = Image.open(path)
        img_w, img_h = img.size

        required_w, required_h = self.spec.get_required_heightmap_size()

        if auto_resize and (img_w != required_w or img_h != required_h):
            print(
                f"Resizing heightmap from {img_w}x{img_h} to {required_w}x{required_h}"
            )

            if img.mode == "I;16" or img.mode == "I":
                arr = np.array(img, dtype=np.float32)
                arr = arr / 65535.0
            elif img.mode == "L":
                arr = np.array(img.convert("L"), dtype=np.float32) / 255.0
            else:
                arr = np.array(img.convert("L"), dtype=np.float32) / 255.0

            arr_resized = np.array(
                Image.fromarray(arr).resize((required_w, required_h), Image.LANCZOS)
            )

            if img.mode == "I;16" or img.mode == "I":
                arr_resized = (arr_resized * 65535).astype(np.uint16)
                img = Image.fromarray(arr_resized, mode="I;16")
            else:
                arr_resized = (arr_resized * 255).astype(np.uint8)
                img = Image.fromarray(arr_resized, mode="L")

            output_path = str(Path(path).parent / f"{Path(path).stem}_resized.png")
            img.save(output_path)
            path = output_path
            print(f"Saved resized heightmap: {output_path}")
            img = Image.open(path)

        if img.mode == "I;16" or img.mode == "I":
            arr = np.array(img, dtype=np.float32)
            arr = arr / 65535.0
        elif img.mode == "L":
            arr = np.array(img.convert("L"), dtype=np.float32) / 255.0
        else:
            arr = np.array(img.convert("L"), dtype=np.float32) / 255.0

        self.heightmap = arr
        self.heightmap_height, self.heightmap_width = arr.shape
        return arr

    def generate_vmf(self, output_path: str) -> str:
        """Generate complete VMF file with displacement terrain using vmflib."""
        if self.heightmap is None:
            raise ValueError("Heightmap not loaded")

        rules: Dict[str, Any] = {}
        rules_path = Path(self.spec.rules_file)
        if rules_path.exists():
            with open(rules_path, "r") as f:
                rules = json.load(f)
            print(f"Loaded rules from {rules_path}")
        else:
            print(f"No rules file found at {rules_path}, using defaults")

        # Ensure our generated rules dictionary contains pipeline overrides
        rules["base_clear_radius"] = self.spec.base_clear_radius

        tiles_x = self.spec.terrain_tiles_x
        tiles_y = self.spec.terrain_tiles_y
        power = self.spec.terrain_power
        tile_size = self.spec.terrain_tile_size
        height_scale = self.spec.terrain_max_height
        disp_count = tiles_x * tiles_y
        if disp_count > MAX_MAP_DISPINFO:
            raise ValueError(
                f"Too many displacement tiles for VBSP: {disp_count} > {MAX_MAP_DISPINFO}. "
                "Reduce Tiles X/Y or increase tile size."
            )

        valve_map = vmf.ValveMap()
        valve_map.world.properties["maxpropscreenwidth"] = "-1"
        if self.spec.include_detail_props:
            valve_map.world.properties["detailmaterial"] = "detail/detailsprites"
            valve_map.world.properties["detailvbsp"] = "detail.vbsp"
        else:
            valve_map.world.properties.pop("detailmaterial", None)
            valve_map.world.properties.pop("detailvbsp", None)
        height_array = (self.heightmap * 255).astype(np.uint8)
        img_height, img_width = height_array.shape

        map_width = tiles_x * tile_size
        map_height = tiles_y * tile_size

        origin_x = int(-map_width / 2)
        origin_y = int(-map_height / 2)
        map_end_x = origin_x + map_width
        map_end_y = origin_y + map_height
        if (
            origin_x < WORLD_MIN_COORD + WORLD_SAFE_MARGIN
            or origin_y < WORLD_MIN_COORD + WORLD_SAFE_MARGIN
            or map_end_x > WORLD_MAX_COORD - WORLD_SAFE_MARGIN
            or map_end_y > WORLD_MAX_COORD - WORLD_SAFE_MARGIN
        ):
            raise ValueError(
                "Map extents exceed compile-safe coordinate limits: "
                f"X [{origin_x}, {map_end_x}], Y [{origin_y}, {map_end_y}] "
                "must stay within "
                f"[{WORLD_MIN_COORD + WORLD_SAFE_MARGIN}, {WORLD_MAX_COORD - WORLD_SAFE_MARGIN}]."
            )
        map_center_x = 0.0
        map_center_y = 0.0

        base_layout = rules.get("base_layout", {})

        original_avg_size = 27000
        scale_factor = map_width / original_avg_size

        nf_offset = int(
            base_layout.get("nf_offset_from_center", {})
            .get("dist_2d", {})
            .get("avg", 1200)
            * scale_factor
        )
        imp_offset = int(
            base_layout.get("imp_offset_from_center", {})
            .get("dist_2d", {})
            .get("avg", 1200)
            * scale_factor
        )

        max_offset = int(map_width / 3)
        nf_offset = min(nf_offset, max_offset)
        imp_offset = min(imp_offset, max_offset)

        # In manual mode, only use custom positions. In procedural mode, use defaults if not set.
        if self.spec.manual_terrain:
            imp_base_x = int(self.spec.custom_imp_base_x) if self.spec.custom_imp_base_x is not None else None
            imp_base_y = int(self.spec.custom_imp_base_y) if self.spec.custom_imp_base_y is not None else None
            nf_base_x = int(self.spec.custom_nf_base_x) if self.spec.custom_nf_base_x is not None else None
            nf_base_y = int(self.spec.custom_nf_base_y) if self.spec.custom_nf_base_y is not None else None
        else:
            imp_default_x, imp_default_y = self.spec.default_imp_base()
            imp_base_x = (
                int(self.spec.custom_imp_base_x)
                if self.spec.custom_imp_base_x is not None
                else int(imp_default_x)
            )
            imp_base_y = (
                int(self.spec.custom_imp_base_y)
                if self.spec.custom_imp_base_y is not None
                else int(imp_default_y)
            )
            nf_default_x, nf_default_y = self.spec.default_nf_base()
            nf_base_x = (
                int(self.spec.custom_nf_base_x)
                if self.spec.custom_nf_base_x is not None
                else int(nf_default_x)
            )
            nf_base_y = (
                int(self.spec.custom_nf_base_y)
                if self.spec.custom_nf_base_y is not None
                else int(nf_default_y)
            )

        flatten_radius = self.spec.base_clear_radius

        working_heightmap = self.heightmap.copy()

        if flatten_radius > 0:
            if imp_base_x is not None and imp_base_y is not None:
                working_heightmap = flatten_terrain_at_location(
                    working_heightmap,
                    imp_base_x,
                    imp_base_y,
                    flatten_radius,
                    img_width,
                    img_height,
                    map_width,
                    map_height,
                    origin_x,
                    origin_y,
                    True,
                    self.spec.base_flatness,
                )

            if nf_base_x is not None and nf_base_y is not None:
                working_heightmap = flatten_terrain_at_location(
                    working_heightmap,
                    nf_base_x,
                    nf_base_y,
                    flatten_radius,
                    img_width,
                    img_height,
                    map_width,
                    map_height,
                    origin_x,
                    origin_y,
                    True,
                    self.spec.base_flatness,
                )

        height_array = (working_heightmap * 255).astype(np.uint8)

        grid_size = (2**power) + 1

        for row_idx in range(tiles_y):
            for col_idx in range(tiles_x):
                offset_x = int(origin_x + (col_idx * tile_size))
                offset_y = int(origin_y + (row_idx * tile_size))

                sample_size = grid_size

                height_distances = []
                for iy in range(sample_size):
                    row_heights = []
                    for ix in range(sample_size):
                        px = col_idx * (grid_size - 1) + ix
                        py = row_idx * (grid_size - 1) + iy
                        px = max(0, min(px, img_width - 1))
                        py = max(0, min(py, img_height - 1))
                        h = height_array[py, px]
                        h = int(math.floor(h / 255.0 * height_scale))
                        # Clamp h to avoid exceeding world bounds
                        h = max(-16000, min(16000, h))
                        row_heights.append(h)
                    height_distances.append(row_heights)

                vertex_normals = []
                for iy in range(sample_size):
                    row_normals = []
                    for ix in range(sample_size):
                        # Force vertical normals to ensure vertical heightmap displacement.
                        # Using surface normals as displacement vectors causes sideways pulling/fins.
                        row_normals.append(Vertex(0.0, 0.0, 1.0))
                    vertex_normals.append(row_normals)

                disp_info = DispInfo(power, vertex_normals, height_distances)
                disp_info.properties["flags"] = "0"
                disp_info.startposition = f"[{int(offset_x)} {int(offset_y)} 0]"
                disp_info.allowed_verts.properties.clear()
                for i in range((2**power) + 1):
                    disp_info.allowed_verts.properties[f"row{i}"] = "-1"

                # Block centered at Z=-8 -> top face at Z=0, bottom at Z=-16
                floor_block = Block(
                    Vertex(
                        int(offset_x + tile_size / 2), int(offset_y + tile_size / 2), -8
                    ),
                    (tile_size, tile_size, 16),
                    self.spec.terrain_material,
                )

                apply_nodraw_to_terrain_except_top(
                    floor_block, self.spec.terrain_material
                )
                floor_block.top().lightmapscale = 32
                floor_block.top().children.append(disp_info)
                valve_map.world.children.append(floor_block)

        max_terrain_height = (
            int(self.spec.terrain_actual_max)
            if self.spec.terrain_actual_max
            else int(np.max(working_heightmap) * height_scale)
        )
        print(
            f"DEBUG: max_terrain_height={max_terrain_height}, terrain_actual_max={self.spec.terrain_actual_max}"
        )

        skyname = choose_safe_skybox(self.spec.skybox, rules)

        generate_skybox(
            valve_map,
            origin_x,
            origin_y,
            map_width,
            map_height,
            max_terrain_height,
            skyname,
        )

        spawn_lighting(valve_map, rules)

        skip_commander = (
            self.spec.disable_commander
            or self.spec.minimal_map
            or self.spec.terrain_only
        )
        skip_buildings = (
            self.spec.disable_buildings
            or self.spec.minimal_map
            or self.spec.terrain_only
        )
        skip_resources = (
            self.spec.disable_resource_nodes
            or self.spec.minimal_map
            or self.spec.terrain_only
        )
        skip_misc = (
            self.spec.disable_capture_points
            or self.spec.minimal_map
            or self.spec.terrain_only
        )
        skip_player_spawns = self.spec.terrain_only


        if self.spec.use_enhanced_spawning:
            if not skip_commander or not skip_buildings:
                spawn_base_entities_enhanced(
                    valve_map,
                    "imp",
                    imp_base_x,
                    imp_base_y,
                    0,
                    map_center_x,
                    map_center_y,
                    rules,
                    heightmap=height_array,
                    origin_x_world=origin_x,
                    origin_y_world=origin_y,
                    map_width=map_width,
                    map_height=map_height,
                    max_height=height_scale,
                    tiles_x=tiles_x,
                    tiles_y=tiles_y,
                    power=power,
                    skip_commander=skip_commander,
                    skip_buildings=skip_buildings,
                )

            if not skip_commander or not skip_buildings:
                spawn_base_entities_enhanced(
                    valve_map,
                    "nf",
                    nf_base_x,
                    nf_base_y,
                    0,
                    map_center_x,
                    map_center_y,
                    rules,
                    heightmap=height_array,
                    origin_x_world=origin_x,
                    origin_y_world=origin_y,
                    map_width=map_width,
                    map_height=map_height,
                    max_height=height_scale,
                    tiles_x=tiles_x,
                    tiles_y=tiles_y,
                    power=power,
                    skip_commander=skip_commander,
                    skip_buildings=skip_buildings,
                )

            if self.spec.custom_resources is not None:
                spawn_custom_resources(
                    valve_map,
                    self.spec.custom_resources,
                    heightmap=height_array,
                    origin_x=origin_x,
                    origin_y=origin_y,
                    map_width=map_width,
                    map_height=map_height,
                    max_height=height_scale,
                    tiles_x=tiles_x,
                    tiles_y=tiles_y,
                    power=power,
                )
            elif not skip_resources:
                spawn_resource_nodes_enhanced(
                    valve_map,
                    "imp",
                    imp_base_x,
                    imp_base_y,
                    max_terrain_height,
                    map_center_x,
                    map_center_y,
                    rules,
                    heightmap=height_array,
                    origin_x=origin_x,
                    origin_y=origin_y,
                    map_width=map_width,
                    map_height=map_height,
                    max_height=height_scale,
                    tiles_x=tiles_x,
                    tiles_y=tiles_y,
                    power=power,
                )
                spawn_resource_nodes_enhanced(
                    valve_map,
                    "nf",
                    nf_base_x,
                    nf_base_y,
                    max_terrain_height,
                    map_center_x,
                    map_center_y,
                    rules,
                    heightmap=height_array,
                    origin_x=origin_x,
                    origin_y=origin_y,
                    map_width=map_width,
                    map_height=map_height,
                    max_height=height_scale,
                    tiles_x=tiles_x,
                    tiles_y=tiles_y,
                    power=power,
                )

            if not skip_player_spawns:
                spawn_player_spawn_points(
                    valve_map,
                    imp_base_x,
                    imp_base_y,
                    nf_base_x,
                    nf_base_y,
                    max_terrain_height,
                    rules,
                )

            if not skip_misc:
                spawn_capture_points(
                    valve_map,
                    imp_base_x,
                    imp_base_y,
                    nf_base_x,
                    nf_base_y,
                    map_center_x,
                    map_center_y,
                    max_terrain_height,
                    rules,
                )
        else:
            if not skip_commander or not skip_buildings:
                spawn_base_entities_enhanced(
                    valve_map,
                    "imp",
                    imp_base_x,
                    imp_base_y,
                    0,
                    map_center_x,
                    map_center_y,
                    rules,
                    heightmap=height_array,
                    origin_x_world=origin_x,
                    origin_y_world=origin_y,
                    map_width=map_width,
                    map_height=map_height,
                    max_height=height_scale,
                    tiles_x=tiles_x,
                    tiles_y=tiles_y,
                    power=power,
                    skip_commander=skip_commander,
                    skip_buildings=skip_buildings,
                )
            if not skip_commander or not skip_buildings:
                spawn_base_entities_enhanced(
                    valve_map,
                    "nf",
                    nf_base_x,
                    nf_base_y,
                    0,
                    map_center_x,
                    map_center_y,
                    rules,
                    heightmap=height_array,
                    origin_x_world=origin_x,
                    origin_y_world=origin_y,
                    map_width=map_width,
                    map_height=map_height,
                    max_height=height_scale,
                    tiles_x=tiles_x,
                    tiles_y=tiles_y,
                    power=power,
                    skip_commander=skip_commander,
                    skip_buildings=skip_buildings,
                )
            if self.spec.custom_resources is not None:
                spawn_custom_resources(
                    valve_map,
                    self.spec.custom_resources,
                    heightmap=height_array,
                    origin_x=origin_x,
                    origin_y=origin_y,
                    map_width=map_width,
                    map_height=map_height,
                    max_height=height_scale,
                    tiles_x=tiles_x,
                    tiles_y=tiles_y,
                    power=power,
                )
            elif not skip_resources:
                spawn_resource_nodes_enhanced(
                    valve_map,
                    "imp",
                    imp_base_x,
                    imp_base_y,
                    max_terrain_height,
                    map_center_x,
                    map_center_y,
                    rules,
                    heightmap=height_array,
                    origin_x=origin_x,
                    origin_y=origin_y,
                    map_width=map_width,
                    map_height=map_height,
                    max_height=height_scale,
                    tiles_x=tiles_x,
                    tiles_y=tiles_y,
                    power=power,
                )
                spawn_resource_nodes_enhanced(
                    valve_map,
                    "nf",
                    nf_base_x,
                    nf_base_y,
                    max_terrain_height,
                    map_center_x,
                    map_center_y,
                    rules,
                    heightmap=height_array,
                    origin_x=origin_x,
                    origin_y=origin_y,
                    map_width=map_width,
                    map_height=map_height,
                    max_height=height_scale,
                    tiles_x=tiles_x,
                    tiles_y=tiles_y,
                    power=power,
                )

        if not skip_misc:
            spawn_info_nodes(
                valve_map,
                imp_base_x,
                imp_base_y,
                nf_base_x,
                nf_base_y,
                map_width,
                map_height,
                max_terrain_height,
                rules,
                origin_x=origin_x,
                origin_y=origin_y,
            )

        spawn_required_entities_enhanced(
            valve_map,
            map_width,
            map_height,
            max_terrain_height,
            rules,
            origin_x=origin_x,
            origin_y=origin_y,
        )

        valve_map.write_vmf(output_path)
        print(f"VMF saved: {output_path}")
        return output_path


def run_pipeline(spec: PipelineSpec) -> dict:
    """Run the terrain generation pipeline."""
    vmf = DisplacementVMF(spec)

    if spec.heightmap_path:
        if not os.path.exists(spec.heightmap_path):
            raise FileNotFoundError(f"Heightmap not found: {spec.heightmap_path}")
        vmf.load_heightmap(spec.heightmap_path)
    else:
        raise ValueError("heightmap_path is required for terrain generation")

    output_dir = Path(spec.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    vmf_path = output_dir / f"{spec.map_name}.vmf"
    vmf.generate_vmf(str(vmf_path))

    return {
        "vmf_path": str(vmf_path),
        "tiles_x": vmf.heightmap_width,
        "tiles_y": vmf.heightmap_height,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Enhanced Source Engine Terrain Pipeline"
    )
    parser.add_argument("heightmap", help="Path to heightmap PNG")
    parser.add_argument("-o", "--output", default="terrain.vmf", help="Output VMF path")
    parser.add_argument("-x", "--tiles-x", type=int, default=8, help="Tiles X")
    parser.add_argument("-y", "--tiles-y", type=int, default=8, help="Tiles Y")
    parser.add_argument("-s", "--tile-size", type=int, default=512, help="Tile size")
    parser.add_argument("-H", "--max-height", type=int, default=512, help="Max height")
    parser.add_argument(
        "-p", "--power", type=int, default=3, choices=[2, 3, 4], help="Disp power"
    )
    parser.add_argument(
        "-m",
        "--material",
        default="nature/terrain/blend_dirt_grass_dmz_sscale",
        help="Material",
    )
    parser.add_argument(
        "--no-enhanced", action="store_true", help="Disable enhanced entity spawning"
    )

    args = parser.parse_args()

    spec = PipelineSpec(
        map_name=Path(args.output).stem,
        heightmap_path=args.heightmap,
        terrain_tile_size=args.tile_size,
        terrain_max_height=args.max_height,
        terrain_power=args.power,
        terrain_material=args.material,
        terrain_tiles_x=args.tiles_x,
        terrain_tiles_y=args.tiles_y,
        output_dir=str(Path(args.output).parent),
        use_enhanced_spawning=not args.no_enhanced,
    )

    run_pipeline(spec)


if __name__ == "__main__":
    main()
