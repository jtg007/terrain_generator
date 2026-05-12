import math
import random
import numpy as np
from typing import Optional, Dict, Any, List, Tuple
import sys
from pathlib import Path

# TODO: verify import
from src.displacement_builder import quantize_coord, get_terrain_height_at, calculate_yaw_to_center
sys.path.insert(0, str(Path(__file__).parent.parent / "tools" / "vmflib"))
from vmflib import vmf
from vmflib.types import Output
from vmflib import vmf as vmf_lib


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
        commander_entity.properties["TeamNum"] = str(team_num)
        commander_entity.properties["angles"] = f"0 {(commander_yaw + 90) % 360} 0"
        valve_map.world.children.append(commander_entity)

    if not skip_buildings:
        barracks_entity = vmf_lib.Entity(barracks_class)
        barracks_entity.origin = f"{quantize_coord(origin_x):.1f} {quantize_coord(origin_y):.1f} {barracks_z:.1f}"
        barracks_entity.properties["angles"] = f"0 {barracks_yaw:.1f} 0"
        barracks_entity.properties["TeamNum"] = str(team_num)
        barracks_entity.properties["startBuilt"] = "1"
        valve_map.world.children.append(barracks_entity)

        spawn_base_buildings(
            valve_map, faction, origin_x, origin_y, terrain_height, rules
        )


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
            building_entity.properties["TeamNum"] = str(team_num)
            if building_type in building_models:
                building_entity.properties["model"] = building_models[building_type]
            building_entity.properties["startBuilt"] = "1"
            if building_type in ("mgturret", "mlturret"):
                building_entity.properties["level"] = "2"
            valve_map.world.children.append(building_entity)


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
        resource_logic.properties["TeamNum"] = str(team_num)
        resource_logic.properties["StartDisabled"] = "0"
        resource_logic.properties["Enabled"] = "1"
        resource_logic.properties["ResourcesSecond"] = "3"
        resource_logic.properties["MaxResources"] = "-1"

        resource_prop = vmf_lib.Entity("emp_resource_point_prop")
        resource_prop.origin = f"{prop_x:.1f} {prop_y:.1f} {prop_z:.1f}"
        resource_prop.properties["targetname"] = model_targetname
        resource_prop.properties["TeamNum"] = str(team_num)
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

        valve_map.world.children.append(resource_logic)
        valve_map.world.children.append(resource_prop)
        valve_map.world.children.append(smoke)


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

        valve_map.world.children.append(resource_logic)
        valve_map.world.children.append(resource_prop)
        valve_map.world.children.append(smoke)


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
            valve_map.world.children.append(node)
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
        valve_map.world.children.append(node)
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

    # Important: append the required entities to the map
    valve_map.children.append(info_params)
    valve_map.children.append(info_overview)


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
            valve_map.world.children.append(spawn)

    if nf_base_x is not None and nf_base_y is not None:
        for i in range(nf_count):
            angle = (i / nf_count) * 360
            angle_rad = math.radians(angle)
            spawn_x = nf_base_x + math.cos(angle_rad) * spawn_offset
            spawn_y = nf_base_y + math.sin(angle_rad) * spawn_offset

            spawn = vmf_lib.Entity("emp_info_player_NF")
            spawn.origin = f"{quantize_coord(spawn_x)} {quantize_coord(spawn_y)} {quantize_coord(terrain_height + 16)}"
            spawn.properties["angles"] = f"0 {angle} 0"
            valve_map.world.children.append(spawn)


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
        valve_map.world.children.append(cap)

        cap_model = vmf_lib.Entity("emp_cap_model")
        cap_model.origin = f"{quantize_coord(cap_x)} {quantize_coord(cap_y)} {quantize_coord(terrain_height + 8)}"
        cap_model.properties["model"] = "models/common/emp_snow/flag_capmodel1a.mdl"
        cap_model.properties["angles"] = "0 0 0"
        valve_map.world.children.append(cap_model)
