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
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict, Any

from src.terrain_pipeline import slope_to_alpha

sys.path.insert(0, str(Path(__file__).parent.parent / "tools" / "vmflib"))
from vmflib import vmf
from vmflib.types import Vertex, Output
from vmflib.brush import DispInfo
from vmflib.tools import Block
from vmflib import vmf as vmf_lib

THEME_MATERIALS: dict[str, dict[str, tuple[str, bool]]] = {
    # Format: band → (material_path, uses_blend_alpha)
    # uses_blend_alpha = True only for materials with blend shader support

    "Temperate": {
        "cliff":      ("common/nature/mountain_wall_000",              True),
        "peak":       ("common/nature/blend_grass_mountainwall_000",   True),
        "high":       ("common/nature/blend_grassfloor08_rockwall02",  True),
        "transition": ("common/nature/blend_grass_mud_003",            True),
        "mid":        ("common/nature/blend_grass_mud_003",            True),
        "low":        ("common/nature/blend_grass_mud_003",            True),
        "valley":     ("common/nature/mud_003",                        False),
    },
    "Desert": {
        "cliff":      ("nature/cliff/stone_cliff_colorado",            True),
        "peak":       ("nature/blendrocksand008d",                     True),
        "high":       ("common/nature/blend_grass_sandfloor009a_000",  True),
        "transition": ("common/terrain/blend_grass01c_sand01a",        True),
        "mid":        ("common/nature/blend_grass_sandfloor009a_000",  True),
        "low":        ("maps/emp_arid/blenddirtdirt_silk",             True),
        "valley":     ("common/nature/sandfloor009a",                  False),
    },
    "Snow": {
        "cliff":      ("common/nature/mountain_wall_000",              False),
        "peak":       ("common/terrain/blend_snow01_rock01a",          True),
        "high":       ("common/terrain/blend_snow01_rock01a",          True),
        "transition": ("common/emp_snow/blend_snowsnow01a",            True),
        "mid":        ("common/emp_snow/blend_snowsnow01a",            True),
        "low":        ("common/emp_snow/snowfloor001b",                False),
        "valley":     ("common/emp_snow/snowfloor002b",                False),
    },
    "Industrial": {
        "cliff":      ("common/nature/mountain_wall_000",              False),
        "peak":       ("nature/cliffface001b",                         False),
        "high":       ("common/stene/dirtyconcrete",                   False),
        "transition": ("nature/terrain/tarmac_01",                     False),
        "mid":        ("common/stene/dirtyconcrete",                   False),
        "low":        ("common/concrete/pavingground01",               False),
        "valley":     ("common/concrete/pavingground02a",              False),
    },
    "Wasteland": {
        "cliff":      ("nature/cliff/stone_cliff_colorado",            True),
        "peak":       ("common/terrain/blend_red2_red4",               True),
        "high":       ("common/terrain/blend_red2_red3",               True),
        "transition": ("common/terrain/blend_red2_red3",               True),
        "mid":        ("common/terrain/redground2",                    False),
        "low":        ("common/terrain/redground3",                    False),
        "valley":     ("common/terrain/redground4",                    False),
    },
    "Generic": {
        "cliff":      ("common/nature/mountain_wall_000",              False),
        "peak":       ("nature/cliffface001b",                         False),
        "high":       ("common/nature/blend_grass_mud_003",            True),
        "transition": ("common/nature/blend_grass_mud_003",            True),
        "mid":        ("common/nature/blend_grass_mud_003",            True),
        "low":        ("common/nature/grass_001",                      False),
        "valley":     ("common/nature/grassfloor01",                   False),
    },
}

DEFAULT_MATERIALS = THEME_MATERIALS["Generic"]

def _select_material(band: str, theme_name: str) -> tuple[str, bool]:
    table = THEME_MATERIALS.get(theme_name, DEFAULT_MATERIALS)
    return table.get(band, DEFAULT_MATERIALS["mid"])


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
    skybox_ceiling: int,
    max_terrain_height: int,
    skyname: str = "empsky_overcast2",
) -> None:
    """Generate airtight skybox with exact flush coordinates, split into smaller sections."""
    wall_thickness = 64
    terrain_base_z = -512
    ceiling_z = skybox_ceiling
    
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
            ceiling_clip = Block(
                Vertex(cx, cy, int(ceiling_z - wall_thickness / 2)),
                (w, h, wall_thickness),
                "tools/toolsclip",
            )
            ceiling_clip.set_material("tools/toolsclip")
            valve_map.world.children.append(ceiling_clip)


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
            (w, wall_thickness, wall_height),
            "tools/toolsskybox",
        )
        north.set_material("tools/toolsskybox")
        valve_map.world.children.append(north)
        north_clip = Block(
            Vertex(cx, north_y - wall_thickness, wall_center_z),
            (w, wall_thickness, wall_height),
            "tools/toolsclip",
        )
        north_clip.set_material("tools/toolsclip")
        valve_map.world.children.append(north_clip)


        south = Block(
            Vertex(
                cx,
                south_y,
                wall_center_z,
            ),
            (w, wall_thickness, wall_height),
            "tools/toolsskybox",
        )
        south.set_material("tools/toolsskybox")
        valve_map.world.children.append(south)
        south_clip = Block(
            Vertex(cx, south_y + wall_thickness, wall_center_z),
            (w, wall_thickness, wall_height),
            "tools/toolsclip",
        )
        south_clip.set_material("tools/toolsclip")
        valve_map.world.children.append(south_clip)


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
            (wall_thickness, h, wall_height),
            "tools/toolsskybox",
        )
        east.set_material("tools/toolsskybox")
        valve_map.world.children.append(east)
        east_clip = Block(
            Vertex(east_x - wall_thickness, cy, wall_center_z),
            (wall_thickness, h, wall_height),
            "tools/toolsclip",
        )
        east_clip.set_material("tools/toolsclip")
        valve_map.world.children.append(east_clip)


        west = Block(
            Vertex(
                west_x,
                cy,
                wall_center_z,
            ),
            (wall_thickness, h, wall_height),
            "tools/toolsskybox",
        )
        west.set_material("tools/toolsskybox")
        valve_map.world.children.append(west)
        west_clip = Block(
            Vertex(west_x + wall_thickness, cy, wall_center_z),
            (wall_thickness, h, wall_height),
            "tools/toolsclip",
        )
        west_clip.set_material("tools/toolsclip")
        valve_map.world.children.append(west_clip)


    valve_map.world.skyname = skyname


def spawn_lighting(
    valve_map: vmf.ValveMap,
    rules: Dict[str, Any],
    skyname: str = "",
) -> None:
    """Spawn light_environment and env_sun entities based on rules and skybox."""
    lighting = rules.get("lighting_environment", {})
    light_env = lighting.get("light_environment", {})
    env_sun = lighting.get("env_sun", {})

    # Try to find specific lighting for the chosen skybox
    specific_light = None
    specific_sun = None
    target_sky = skyname.strip().lower()
    if target_sky and "individual_maps" in rules:
        for m in rules["individual_maps"]:
            if m.get("skyname", "").strip().lower() == target_sky:
                if "light_environment" in m:
                    specific_light = m["light_environment"]
                    specific_sun = m.get("env_sun", {})
                    break

    if specific_light:
        light_env = specific_light
    if specific_sun is not None:
        env_sun = specific_sun or {}

    pitch_val = light_env.get("pitch", light_env.get("pitch_stats", {}).get("avg", -20))
    # 'angles' usually looks like "0 120 0" or "-45 180 0". If absent, use yaw avg.
    angles_val = light_env.get("angles")
    if not angles_val:
        sun_yaw_avg = env_sun.get("yaw_stats", {}).get("avg", 0) if isinstance(env_sun, dict) else 0
        angles_val = f"0 {sun_yaw_avg} 0"

    _light_val = light_env.get("_light", light_env.get("brightnessHDR", "255 193 141 300"))
    if not _light_val: # In case it's empty string
        _light_val = "255 193 141 300"

    _ambient_val = light_env.get("_ambient", light_env.get("ambientHDR", "107 113 55 85"))
    if not _ambient_val:
        _ambient_val = "107 113 55 85"

    _lightHDR_val = light_env.get("brightnessHDR", "-1 -1 -1 1")
    if not _lightHDR_val:
        _lightHDR_val = "-1 -1 -1 1"

    _ambientHDR_val = light_env.get("ambientHDR", "-1 -1 -1 1")
    if not _ambientHDR_val:
        _ambientHDR_val = "-1 -1 -1 1"

    light_ent = vmf_lib.Entity("light_environment")
    light_ent.origin = "0.0 0.0 0.0"
    light_ent.properties["pitch"] = str(int(float(pitch_val)))
    light_ent.properties["angles"] = angles_val
    light_ent.properties["_light"] = _light_val
    light_ent.properties["_ambient"] = _ambient_val
    light_ent.properties["_lightHDR"] = _lightHDR_val
    light_ent.properties["_ambientHDR"] = _ambientHDR_val
    light_ent.properties["SunSpreadAngle"] = "2"

    sun_ent = vmf_lib.Entity("env_sun")
    sun_ent.origin = "0.0 0.0 0.0"

    # env_sun pitch is often negative of light_environment's pitch or simply the same angles
    if specific_sun and isinstance(specific_sun, dict) and "pitch" in specific_sun:
        sun_pitch = specific_sun["pitch"]
    else:
        sun_pitch = str(int(-float(pitch_val)))

    sun_ent.properties["pitch"] = sun_pitch

    sun_angles = specific_sun.get("angles") if isinstance(specific_sun, dict) else None
    if not sun_angles:
        sun_angles = angles_val

    sun_ent.properties["angles"] = sun_angles
    sun_ent.properties["use_angles"] = "1"

    sun_color = env_sun.get("sun_color", "249 216 147") if isinstance(env_sun, dict) else "249 216 147"
    if not sun_color:
        sun_color = "249 216 147"
    sun_ent.properties["rendercolor"] = sun_color

    valve_map.world.children.append(light_ent)
    valve_map.world.children.append(sun_ent)


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

    important_points = []
    if imp_base_x is not None and imp_base_y is not None:
        important_points.extend(
            [(imp_base_x, imp_base_y), (imp_base_x + 300, imp_base_y + 300)]
        )
    if nf_base_x is not None and nf_base_y is not None:
        important_points.extend(
            [(nf_base_x, nf_base_y), (nf_base_x - 300, nf_base_y - 300)]
        )
    important_points.extend([(0.0, 0.0), (200.0, 0.0), (-200.0, 0.0), (0.0, 200.0)])

    node_id = 100

    clustered_points = important_points[:4]
    for point_x, point_y in clustered_points:
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

    remaining_nodes = node_count - len(clustered_points) * min_cluster_size
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
    skybox_ceiling: int,
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
    seed: int = 12345

    terrain_max_height: int = 512
    skybox_ceiling: int = 4096
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
    custom_layout_nodes: Optional[List[Any]] = None
    custom_layout_connections: Optional[List[Any]] = None
    manual_terrain: bool = False
    custom_tile_materials: Optional[Dict[Tuple[int, int], str]] = None
    
    current_theme: str = "Temperate"
    corridor_detail_width: int = 2048
    transition_width: int = 1536
    scenery_variation_noise: float = 0.4
    hero_prop_density: float = 0.5

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
        
        # Load thematic defaults
        self.themes = {}
        textures_path = Path(__file__).parent.parent / "config" / "textures.json"
        if textures_path.exists():
            try:
                with open(textures_path, "r") as f:
                    self.themes = json.load(f).get("themes", {})
            except Exception as e:
                print(f"Warning: Failed to load themes for VMF gen: {e}")

    def calculate_tile_zone_score(self, tx: int, ty: int) -> float:
        """
        Calculate a continuous zone score (0.0 to 1.0) for a tile.
        1.0 = deep action zone, 0.0 = deep scenery.
        """
        tile_size = self.spec.terrain_tile_size
        map_w = self.spec.terrain_tiles_x * tile_size
        map_h = self.spec.terrain_tiles_y * tile_size
        origin_x = int(-map_w / 2)
        origin_y = int(-map_h / 2)
        
        twx = origin_x + (tx + 0.5) * tile_size
        twy = origin_y + (ty + 0.5) * tile_size
        
        threshold = getattr(self.spec, "corridor_detail_width", 2048)
        transition = getattr(self.spec, "transition_width", 1536)

        min_dist = float('inf')
        
        # Check bases
        bases = []
        if self.spec.custom_imp_base_x is not None:
            bases.append((self.spec.custom_imp_base_x, self.spec.custom_imp_base_y))
        else:
            bases.append(self.spec.default_imp_base())

        if self.spec.custom_nf_base_x is not None:
            bases.append((self.spec.custom_nf_base_x, self.spec.custom_nf_base_y))
        else:
            bases.append(self.spec.default_nf_base())
            
        for bx, by in bases:
            min_dist = min(min_dist, math.sqrt((twx - bx)**2 + (twy - by)**2))
                
        # Check lanes
        if self.spec.custom_layout_connections and self.spec.custom_layout_nodes:
            # Pre-map nodes for faster lookups in serialized dict-like data
            nodes_map = None

            for conn in self.spec.custom_layout_connections:
                try:
                    if hasattr(conn, 'start_node'):
                        p1 = (conn.start_node.x, conn.start_node.y)
                        p2 = (conn.end_node.x, conn.end_node.y)
                    else:
                        # Fallback for dict-like connections from serialization
                        if nodes_map is None:
                            nodes_map = {n.id if hasattr(n, 'id') else n.get('id'): n for n in self.spec.custom_layout_nodes}
                        n1 = nodes_map.get(conn.from_id if hasattr(conn, 'from_id') else conn.get('from_id'))
                        n2 = nodes_map.get(conn.to_id if hasattr(conn, 'to_id') else conn.get('to_id'))
                        p1 = (n1.x, n1.y) if hasattr(n1, 'x') else (n1.get('x'), n1.get('y'))
                        p2 = (n2.x, n2.y) if hasattr(n2, 'x') else (n2.get('x'), n2.get('y'))

                    min_dist = min(min_dist, point_to_segment_dist((twx, twy), p1, p2))
                except Exception:
                    continue

        # Score calculation: 1.0 inside threshold, fades to 0.0 over transition_width
        if min_dist <= threshold:
            return 1.0

        score = 1.0 - (min_dist - threshold) / max(1.0, transition)
        return max(0.0, min(1.0, score))

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

        valve_map.world.properties["generator_version"] = "2.0-themed-optimized"
        valve_map.world.properties["current_theme"] = getattr(self.spec, "current_theme", "Temperate")

        # Scenery Hero Prop Budget
        self.prop_count = 0
        max_hero_props = 256
        hero_prop_density = getattr(self.spec, "hero_prop_density", 0.5)

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

        imp_base_x = (
            int(self.spec.custom_imp_base_x)
            if self.spec.custom_imp_base_x is not None
            else None
        )
        imp_base_y = (
            int(self.spec.custom_imp_base_y)
            if self.spec.custom_imp_base_y is not None
            else None
        )
        nf_base_x = (
            int(self.spec.custom_nf_base_x)
            if self.spec.custom_nf_base_x is not None
            else None
        )
        nf_base_y = (
            int(self.spec.custom_nf_base_y)
            if self.spec.custom_nf_base_y is not None
            else None
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

        edge_alphas: dict[tuple, np.ndarray] = {}

        # First Pass: Generate blocks, displacement infos, and base alphas
        disp_infos = {}
        floor_blocks = {}
        zone_scores = {}
        is_cliff_dict = {}

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

                # Selective Procedural Texturing based on Theme and Zone Scoring
                tile_material = self.spec.terrain_material
                zone_score = self.calculate_tile_zone_score(col_idx, row_idx)
                
                theme_name = getattr(self.spec, "current_theme", "Temperate")
                theme = self.themes.get(theme_name, self.themes.get("Generic", {}))
                defaults = theme.get("defaults", {})
                
                # Debug first tile
                if col_idx == 0 and row_idx == 0:
                    print(f"DEBUG: Using theme '{theme_name}', zone_score example: {zone_score:.2f}")
                
                # Determine "Standard" material for this tile if not painted
                band = "mid"
                is_cliff = False
                
                # Average tile height to determine if it's a cliff
                mid = (grid_size - 1) // 2
                
                # Calculate center slope for procedural choice
                px = col_idx * (grid_size - 1) + mid
                py = row_idx * (grid_size - 1) + mid
                px_m, px_p = max(0, px - 1), min(img_width - 1, px + 1)
                py_m, py_p = max(0, py - 1), min(img_height - 1, py + 1)
                
                h_xm = working_heightmap[py, px_m] * height_scale
                h_xp = working_heightmap[py, px_p] * height_scale
                h_ym = working_heightmap[py_m, px] * height_scale
                h_yp = working_heightmap[py_p, px] * height_scale
                
                # Scale factor for slope to match typical terrain_pipeline expectations
                # In terrain_pipeline: slope = dz / cell_size.
                # Here px_p - px_m is 2 pixel units. vertex_spacing = tile_size / (grid_size - 1)
                vertex_spacing = tile_size / (grid_size - 1)
                dz_dx = (h_xp - h_xm) / (2.0 * vertex_spacing)
                dz_dy = (h_yp - h_ym) / (2.0 * vertex_spacing)
                slope = math.sqrt(dz_dx**2 + dz_dy**2)
                # Scenery cliffs: use a threshold that matches Source terrain steepness
                is_cliff = slope > 0.2
                
                if is_cliff:
                    band = "cliff"
                elif zone_score > 0.7:
                    band = "low" # ACTION ZONE
                elif zone_score > 0.3:
                    band = "transition" # TRANSITION BELT
                else:
                    band = "valley" # SCENERY ZONE

                tile_material, uses_blend = _select_material(band, theme_name)

                # Manual Paint Override
                if hasattr(self.spec, "custom_tile_materials") and self.spec.custom_tile_materials:
                    if (col_idx, row_idx) in self.spec.custom_tile_materials:
                        tile_material = self.spec.custom_tile_materials[(col_idx, row_idx)]
                        # Determine uses_blend for custom material? We'll assume yes if "blend" is in the name
                        uses_blend = "blend" in tile_material.lower()

                # Selective Alpha Blending: Generate slope-based alphas ONLY for playable/painted blend materials
                tile_alphas = np.zeros((sample_size, sample_size), dtype=int)
                
                if uses_blend:
                    # Reference the original float heightmap for high-precision slope math
                    # working_heightmap is [img_height, img_width]
                    for iy in range(sample_size):
                        for ix in range(sample_size):
                            # Global coordinates in the heightmap
                            px = col_idx * (grid_size - 1) + ix
                            py = row_idx * (grid_size - 1) + iy
                            
                            # Central difference for slope (match terrain_pipeline.py logic)
                            # Spacing is effectively 1 vertex unit (dz_dr/cell_size in pipeline)
                            # but we need to normalize to match the expected thresholds.
                            
                            # Boundary-safe indices
                            px_m = max(0, px - 1)
                            px_p = min(img_width - 1, px + 1)
                            py_m = max(0, py - 1)
                            py_p = min(img_height - 1, py + 1)
                            
                            # Heights in world units
                            h_xm = working_heightmap[py, px_m] * height_scale
                            h_xp = working_heightmap[py, px_p] * height_scale
                            h_ym = working_heightmap[py_m, px] * height_scale
                            h_yp = working_heightmap[py_p, px] * height_scale
                            
                            # dz_dx and dz_dy over 2 vertex steps
                            dz_dx = (h_xp - h_xm) / 2.0
                            dz_dy = (h_yp - h_ym) / 2.0
                            
                            # Pipeline slope normalization: dz / tile_size
                            slope_x = dz_dx / tile_size
                            slope_y = dz_dy / tile_size
                            slope = math.sqrt(slope_x**2 + slope_y**2)
                            
                            # Apply standard thresholds from terrain_pipeline.py
                            if band == "cliff":
                                alpha = slope_to_alpha(slope, flat_threshold=0.3, steep_threshold=0.6)
                            else:
                                alpha = slope_to_alpha(slope)
                            tile_alphas[iy, ix] = alpha
                
                edge_alphas[(col_idx, row_idx)] = tile_alphas

                # Block centered at Z=-8 -> top face at Z=0, bottom at Z=-16
                floor_block = Block(
                    Vertex(
                        int(offset_x + tile_size / 2), int(offset_y + tile_size / 2), -8
                    ),
                    (tile_size, tile_size, 16),
                    tile_material,
                )

                apply_nodraw_to_terrain_except_top(
                    floor_block, tile_material
                )

                # Addressing steep-slope rendering artifacts
                top_face = floor_block.top()
                top_face.lightmapscale = 32

                uaxis_scale = 0.25
                vaxis_scale = 0.25

                top_face.uaxis = f"[1 0 0 0] {uaxis_scale}"
                top_face.vaxis = f"[0 -1 0 0] {vaxis_scale}"

                disp_infos[(col_idx, row_idx)] = disp_info
                floor_blocks[(col_idx, row_idx)] = floor_block
                zone_scores[(col_idx, row_idx)] = zone_score
                is_cliff_dict[(col_idx, row_idx)] = is_cliff

        # Second Pass: Average border alphas and attach disp_info
        for row_idx in range(tiles_y):
            for col_idx in range(tiles_x):
                disp_info = disp_infos[(col_idx, row_idx)]
                floor_block = floor_blocks[(col_idx, row_idx)]
                zone_score = zone_scores[(col_idx, row_idx)]
                is_cliff = is_cliff_dict[(col_idx, row_idx)]
                tile_alphas = edge_alphas[(col_idx, row_idx)].copy()

                # Blend edge rows with neighbor average to prevent hard seams
                
                # Top edge: average with tile above (row_idx - 1)
                if (col_idx, row_idx - 1) in edge_alphas:
                    neighbor_alphas = edge_alphas[(col_idx, row_idx - 1)]
                    tile_alphas[0, :] = (tile_alphas[0, :] + neighbor_alphas[-1, :]) // 2

                # Bottom edge: average with tile below (row_idx + 1)
                if (col_idx, row_idx + 1) in edge_alphas:
                    neighbor_alphas = edge_alphas[(col_idx, row_idx + 1)]
                    tile_alphas[-1, :] = (tile_alphas[-1, :] + neighbor_alphas[0, :]) // 2

                # Left edge: average with tile left (col_idx - 1)
                if (col_idx - 1, row_idx) in edge_alphas:
                    neighbor_alphas = edge_alphas[(col_idx - 1, row_idx)]
                    tile_alphas[:, 0] = (tile_alphas[:, 0] + neighbor_alphas[:, -1]) // 2

                # Right edge: average with tile right (col_idx + 1)
                if (col_idx + 1, row_idx) in edge_alphas:
                    neighbor_alphas = edge_alphas[(col_idx + 1, row_idx)]
                    tile_alphas[:, -1] = (tile_alphas[:, -1] + neighbor_alphas[:, 0]) // 2
                
                sample_size = grid_size
                for iy in range(sample_size):
                    disp_info.alphas.properties[f"row{iy}"] = " ".join(map(str, tile_alphas[iy]))

                top_face = floor_block.top()
                top_face.children.append(disp_info)
                valve_map.world.children.append(floor_block)

                offset_x = int(origin_x + (col_idx * tile_size))
                offset_y = int(origin_y + (row_idx * tile_size))

                # Deterministic Hero Prop Spawning in Scenery Zone
                if zone_score < 0.3 and self.prop_count < max_hero_props:
                    theme_name = getattr(self.spec, "current_theme", "Temperate")
                    theme = self.themes.get(theme_name, self.themes.get("Generic", {}))
                    defaults = theme.get("defaults", {})
                    theme_props = defaults.get("scenery_props", [])
                    if theme_props:
                        # Use deterministic hash of tile coordinates for cluster placement
                        tile_hash = (col_idx * 127 + row_idx * 511 + self.spec.seed) % 10000
                        # Density check - lower probability for cluster centers
                        if (tile_hash / 10000.0) < (0.02 * hero_prop_density):
                            num_in_cluster = 1 + (tile_hash % 3) # 1 to 3 props
                            cluster_base_x = offset_x + (tile_hash % 100) / 100.0 * tile_size
                            cluster_base_y = offset_y + ((tile_hash // 100) % 100) / 100.0 * tile_size

                            for i in range(num_in_cluster):
                                if self.prop_count >= max_hero_props: break
                                # Deterministic offset within cluster
                                sub_hash = (tile_hash + i * 31) % 10000
                                px = cluster_base_x + (sub_hash % 128 - 64)
                                py = cluster_base_y + ((sub_hash // 100) % 128 - 64)

                                # Sample height
                                pz = get_terrain_height_at(px, py, height_array, origin_x, origin_y, map_width, map_height, height_scale, tiles_x, tiles_y, power)

                                prop_model = theme_props[sub_hash % len(theme_props)]

                                prop = vmf_lib.Entity("prop_static")
                                prop.origin = f"{px:.1f} {py:.1f} {pz:.1f}"
                                prop.properties["model"] = prop_model
                                prop.properties["angles"] = f"0 {sub_hash % 360} 0"
                                prop.properties["fademindist"] = "2048"
                                prop.properties["fademaxdist"] = "4096"
                                prop.properties["solid"] = "0" # Non-solid background props for performance
                                valve_map.world.children.append(prop)
                                self.prop_count += 1

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
            self.spec.skybox_ceiling if hasattr(self.spec, "skybox_ceiling") and self.spec.skybox_ceiling is not None else 4096,
            max_terrain_height,
            skyname,
        )

        spawn_lighting(valve_map, rules, skyname)

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
                    int(max_terrain_height),
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
                    int(max_terrain_height),
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
                    int(max_terrain_height),
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
                    int(max_terrain_height),
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
                    int(max_terrain_height),
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
                    int(max_terrain_height),
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
                int(max_terrain_height),
                rules,
                origin_x=origin_x,
                origin_y=origin_y,
            )

        spawn_required_entities_enhanced(
            valve_map,
            map_width,
            map_height,
            self.spec.skybox_ceiling if hasattr(self.spec, "skybox_ceiling") and self.spec.skybox_ceiling is not None else 4096,
            max_terrain_height,
            rules,
            origin_x=origin_x,
            origin_y=origin_y,
        )

        valve_map.write_vmf(output_path)
        print(f"VMF saved: {output_path}")

        # Generation Diagnostics
        print("\n--- Map Generation Diagnostics ---")
        print(f"Scenery Hero Props: {self.prop_count} / {max_hero_props}")

        # Estimate detail prop density
        total_tiles = tiles_x * tiles_y
        action_tiles = 0
        transition_tiles = 0
        scenery_tiles = 0

        for r in range(tiles_y):
            for c in range(tiles_x):
                score = self.calculate_tile_zone_score(c, r)
                if score > 0.7: action_tiles += 1
                elif score > 0.3: transition_tiles += 1
                else: scenery_tiles += 1

        print(f"Action Zone Tiles: {action_tiles} ({action_tiles/total_tiles*100:.1f}%)")
        print(f"Transition Belt Tiles: {transition_tiles} ({transition_tiles/total_tiles*100:.1f}%)")
        print(f"Scenery Zone Tiles: {scenery_tiles} ({scenery_tiles/total_tiles*100:.1f}%)")

        # Detail Prop Warnings
        # Typical Empires/Source limit is ~4096-8192 props if using many small ones.
        # Detail props are harder to count exactly without VBSP, but we can estimate.
        if action_tiles > 1024:
            print("WARNING: Large Action Zone area. You may approach detail prop limits if primary material spawns dense grass.")
            print("Consider reducing corridor_detail_width or using a material with fewer detail props.")

        print("----------------------------------\n")

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
