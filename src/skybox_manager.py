import math
from typing import Optional, Dict, Any, List, Tuple
import sys
from pathlib import Path

# TODO: verify import
sys.path.insert(0, str(Path(__file__).parent.parent / "tools" / "vmflib"))
from vmflib import vmf
from vmflib.types import Vertex
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
WORLD_MIN_COORD = -16384
WORLD_MAX_COORD = 16384


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
