#!/usr/bin/env python3
"""
Enhanced VMF Generation with full rules support.
Uses all available data from map_rules.json.
"""

import os
import sys
import math
import json
import numpy as np
from PIL import Image
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Tuple, Dict, Any

from src.terrain_pipeline import slope_to_alpha
from src.material_manager import THEME_BLEND_MATERIAL

sys.path.insert(0, str(Path(__file__).parent.parent / "tools" / "vmflib"))
from vmflib import vmf
from vmflib.types import Vertex
from vmflib.brush import DispInfo
from vmflib.tools import Block
from vmflib import vmf as vmf_lib

from src.displacement_builder import (
    quantize_coord,
    apply_nodraw_to_terrain_except_top,
    point_to_segment_dist,
    flatten_terrain_at_location,
    get_terrain_height_at
)

from src.entity_placer import (
    spawn_base_entities_enhanced,
    spawn_resource_nodes_enhanced,
    spawn_custom_resources,
    spawn_info_nodes,
    spawn_required_entities_enhanced,
    spawn_player_spawn_points,
    spawn_capture_points
)

from src.skybox_manager import (
    WORLD_MIN_COORD,
    WORLD_MAX_COORD,
    choose_safe_skybox,
    generate_skybox,
    spawn_lighting
)

MAX_MAP_DISPINFO = 2048
WORLD_SAFE_MARGIN = 64


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
    use_smart_details: bool = True
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
    custom_tile_paint_target: str = "floor"
    
    topology: str = "canyon"
    urban_blocks: Optional[List[Any]] = None
    street_cover_points: Optional[List[Any]] = None
    compile_budget: Optional[Any] = None
    resource_elevation: Optional[Any] = None

    current_theme: str = "Temperate"
    terrain_texture_scale: Optional[float] = None  # None = Auto (theme-based)
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

    def _spawn_urban_entities(self, spec, heightmap: np.ndarray, vmf_map, blocks):
        rules: Dict[str, Any] = {}
        rules_path = Path(spec.rules_file)
        if rules_path.exists():
            import json
            with open(rules_path, "r") as f:
                rules = json.load(f)
        rules["base_clear_radius"] = spec.base_clear_radius

        skip_commander = spec.disable_commander or spec.minimal_map or spec.terrain_only
        skip_buildings = spec.disable_buildings or spec.minimal_map or spec.terrain_only
        skip_resources = spec.disable_resource_nodes or spec.minimal_map or spec.terrain_only
        skip_misc = spec.disable_capture_points or spec.minimal_map or spec.terrain_only
        skip_player_spawns = spec.terrain_only

        tiles_x = spec.terrain_tiles_x
        tiles_y = spec.terrain_tiles_y
        power = spec.terrain_power
        tile_size = spec.terrain_tile_size
        height_scale = spec.terrain_max_height

        map_width = tiles_x * tile_size
        map_height = tiles_y * tile_size

        origin_x = int(-map_width / 2)
        origin_y = int(-map_height / 2)
        map_center_x = 0.0
        map_center_y = 0.0

        imp_base_x = int(spec.custom_imp_base_x) if spec.custom_imp_base_x is not None else spec.default_imp_base()[0]
        imp_base_y = int(spec.custom_imp_base_y) if spec.custom_imp_base_y is not None else spec.default_imp_base()[1]
        nf_base_x = int(spec.custom_nf_base_x) if spec.custom_nf_base_x is not None else spec.default_nf_base()[0]
        nf_base_y = int(spec.custom_nf_base_y) if spec.custom_nf_base_y is not None else spec.default_nf_base()[1]

        int(spec.terrain_actual_max) if spec.terrain_actual_max else int(np.max(heightmap) * height_scale)

        from src.entity_placer import spawn_urban_entities_phase7
        spawn_urban_entities_phase7(
            vmf_map, spec, blocks, heightmap, origin_x, origin_y,
            map_width, map_height, max_height=height_scale,
            tiles_x=tiles_x, tiles_y=tiles_y, power=power, rules=rules,
            imp_base_x=imp_base_x, imp_base_y=imp_base_y,
            nf_base_x=nf_base_x, nf_base_y=nf_base_y, map_center_x=map_center_x, map_center_y=map_center_y,
            skip_commander=skip_commander, skip_buildings=skip_buildings, skip_resources=skip_resources,
            skip_misc=skip_misc, skip_player_spawns=skip_player_spawns
        )

    def _spawn_entities(self, spec, heightmap: np.ndarray, vmf_map, enhanced: bool):
        rules: Dict[str, Any] = {}
        rules_path = Path(spec.rules_file)
        if rules_path.exists():
            import json
            with open(rules_path, "r") as f:
                rules = json.load(f)
        rules["base_clear_radius"] = spec.base_clear_radius

        skip_commander = spec.disable_commander or spec.minimal_map or spec.terrain_only
        skip_buildings = spec.disable_buildings or spec.minimal_map or spec.terrain_only
        skip_resources = spec.disable_resource_nodes or spec.minimal_map or spec.terrain_only
        skip_misc = spec.disable_capture_points or spec.minimal_map or spec.terrain_only
        skip_player_spawns = spec.terrain_only

        tiles_x = spec.terrain_tiles_x
        tiles_y = spec.terrain_tiles_y
        power = spec.terrain_power
        tile_size = spec.terrain_tile_size
        height_scale = spec.terrain_max_height

        map_width = tiles_x * tile_size
        map_height = tiles_y * tile_size

        origin_x = int(-map_width / 2)
        origin_y = int(-map_height / 2)
        map_center_x = 0.0
        map_center_y = 0.0

        imp_base_x = int(spec.custom_imp_base_x) if spec.custom_imp_base_x is not None else None
        imp_base_y = int(spec.custom_imp_base_y) if spec.custom_imp_base_y is not None else None
        nf_base_x = int(spec.custom_nf_base_x) if spec.custom_nf_base_x is not None else None
        nf_base_y = int(spec.custom_nf_base_y) if spec.custom_nf_base_y is not None else None

        max_terrain_height = int(spec.terrain_actual_max) if spec.terrain_actual_max else int(np.max(heightmap) * height_scale)

        if enhanced:
            if not skip_commander or not skip_buildings:
                spawn_base_entities_enhanced(
                    vmf_map, "imp", imp_base_x, imp_base_y, 0, map_center_x, map_center_y, rules,
                    heightmap=heightmap, origin_x_world=origin_x, origin_y_world=origin_y,
                    map_width=map_width, map_height=map_height, max_height=height_scale,
                    tiles_x=tiles_x, tiles_y=tiles_y, power=power,
                    skip_commander=skip_commander, skip_buildings=skip_buildings,
                )
            if not skip_commander or not skip_buildings:
                spawn_base_entities_enhanced(
                    vmf_map, "nf", nf_base_x, nf_base_y, 0, map_center_x, map_center_y, rules,
                    heightmap=heightmap, origin_x_world=origin_x, origin_y_world=origin_y,
                    map_width=map_width, map_height=map_height, max_height=height_scale,
                    tiles_x=tiles_x, tiles_y=tiles_y, power=power,
                    skip_commander=skip_commander, skip_buildings=skip_buildings,
                )

            if spec.custom_resources is not None:
                spawn_custom_resources(
                    vmf_map, spec.custom_resources, heightmap=heightmap,
                    origin_x=origin_x, origin_y=origin_y, map_width=map_width, map_height=map_height,
                    max_height=height_scale, tiles_x=tiles_x, tiles_y=tiles_y, power=power,
                )
            elif not skip_resources:
                spawn_resource_nodes_enhanced(
                    vmf_map, "imp", imp_base_x, imp_base_y, int(max_terrain_height),
                    map_center_x, map_center_y, rules, heightmap=heightmap, origin_x=origin_x, origin_y=origin_y,
                    map_width=map_width, map_height=map_height, max_height=height_scale,
                    tiles_x=tiles_x, tiles_y=tiles_y, power=power,
                )
                spawn_resource_nodes_enhanced(
                    vmf_map, "nf", nf_base_x, nf_base_y, int(max_terrain_height),
                    map_center_x, map_center_y, rules, heightmap=heightmap, origin_x=origin_x, origin_y=origin_y,
                    map_width=map_width, map_height=map_height, max_height=height_scale,
                    tiles_x=tiles_x, tiles_y=tiles_y, power=power,
                )

            if not skip_player_spawns:
                spawn_player_spawn_points(
                    vmf_map, imp_base_x, imp_base_y, nf_base_x, nf_base_y, int(max_terrain_height), rules,
                )

            if not skip_misc:
                spawn_capture_points(
                    vmf_map, imp_base_x, imp_base_y, nf_base_x, nf_base_y,
                    map_center_x, map_center_y, int(max_terrain_height), rules,
                )
        else:
            if not skip_commander or not skip_buildings:
                spawn_base_entities_enhanced(
                    vmf_map, "imp", imp_base_x, imp_base_y, 0, map_center_x, map_center_y, rules,
                    heightmap=heightmap, origin_x_world=origin_x, origin_y_world=origin_y,
                    map_width=map_width, map_height=map_height, max_height=height_scale,
                    tiles_x=tiles_x, tiles_y=tiles_y, power=power,
                    skip_commander=skip_commander, skip_buildings=skip_buildings,
                )
            if not skip_commander or not skip_buildings:
                spawn_base_entities_enhanced(
                    vmf_map, "nf", nf_base_x, nf_base_y, 0, map_center_x, map_center_y, rules,
                    heightmap=heightmap, origin_x_world=origin_x, origin_y_world=origin_y,
                    map_width=map_width, map_height=map_height, max_height=height_scale,
                    tiles_x=tiles_x, tiles_y=tiles_y, power=power,
                    skip_commander=skip_commander, skip_buildings=skip_buildings,
                )
            if spec.custom_resources is not None:
                spawn_custom_resources(
                    vmf_map, spec.custom_resources, heightmap=heightmap,
                    origin_x=origin_x, origin_y=origin_y, map_width=map_width, map_height=map_height,
                    max_height=height_scale, tiles_x=tiles_x, tiles_y=tiles_y, power=power,
                )
            elif not skip_resources:
                spawn_resource_nodes_enhanced(
                    vmf_map, "imp", imp_base_x, imp_base_y, int(max_terrain_height),
                    map_center_x, map_center_y, rules, heightmap=heightmap, origin_x=origin_x, origin_y=origin_y,
                    map_width=map_width, map_height=map_height, max_height=height_scale,
                    tiles_x=tiles_x, tiles_y=tiles_y, power=power,
                )
                spawn_resource_nodes_enhanced(
                    vmf_map, "nf", nf_base_x, nf_base_y, int(max_terrain_height),
                    map_center_x, map_center_y, rules, heightmap=heightmap, origin_x=origin_x, origin_y=origin_y,
                    map_width=map_width, map_height=map_height, max_height=height_scale,
                    tiles_x=tiles_x, tiles_y=tiles_y, power=power,
                )

        if not skip_misc:
            spawn_info_nodes(
                vmf_map, imp_base_x, imp_base_y, nf_base_x, nf_base_y,
                map_width, map_height, int(max_terrain_height), rules,
                origin_x=origin_x, origin_y=origin_y,
            )

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

        map_width = tiles_x * tile_size
        map_height = tiles_y * tile_size

        # Apply Smart Details if enabled
        terrain_material = self.spec.terrain_material
        patched_material = None
        if getattr(self.spec, "use_smart_details", False):
            from src.detail_manager import (
                calculate_smart_density,
                generate_auto_detail_vbsp,
                generate_smart_vmt_patch,
            )

            # 1. Calculate density
            density = calculate_smart_density(map_width, map_height)

            # 2. Generate auto_detail.vbsp and set worldspawn keys
            project_root = Path(self.spec.output_dir).parent
            detail_script = generate_auto_detail_vbsp(project_root, density)

            valve_map.world.properties["detailmaterial"] = "detail/detailsprites"
            valve_map.world.properties["detailvbsp"] = detail_script
            valve_map.world.properties["detailfile"] = detail_script

            # 3. Generate VMT patch and use it for the terrain faces
            patched_material = generate_smart_vmt_patch(project_root, terrain_material)
        else:
            valve_map.world.properties.pop("detailmaterial", None)
            valve_map.world.properties.pop("detailvbsp", None)

        valve_map.world.properties["generator_version"] = "2.0-themed-optimized"
        valve_map.world.properties["current_theme"] = getattr(self.spec, "current_theme", "Temperate")

        # Scenery Hero Prop Budget
        self.prop_count = 0
        self.placed_prop_origins = []
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
        tile_alpha_store = {}

        map_z_min = float(working_heightmap.min()) * height_scale
        map_z_max = float(working_heightmap.max()) * height_scale
        band_list = []
        custom_paint_centers: List[Tuple[float, float]] = []
        custom_tile_material_map: Dict[Tuple[int, int], str] = {}
        if self.spec.custom_tile_materials:
            for (custom_col, custom_row), custom_mat in self.spec.custom_tile_materials.items():
                custom_paint_centers.append(
                    (
                        origin_x + (custom_col + 0.5) * tile_size,
                        origin_y + (custom_row + 0.5) * tile_size,
                    )
                )
                custom_tile_material_map[(custom_col, custom_row)] = custom_mat
        paint_inner_radius = tile_size / 2.0
        paint_transition_radius = tile_size * 1.5
        theme_name = getattr(self.spec, "current_theme", "Temperate")
        theme_blend_mat, _ = THEME_BLEND_MATERIAL.get(
            theme_name,
            THEME_BLEND_MATERIAL["Generic"],
        )
        global_blend_material = patched_material if patched_material else theme_blend_mat

        if getattr(self.spec, "vpk_index", None) is not None:
            vpk_idx = self.spec.vpk_index

            if vpk_idx:
                vmt = f"materials/{global_blend_material.lower()}.vmt"
                if vmt not in vpk_idx:
                    for theme_candidate, _ in THEME_BLEND_MATERIAL.values():
                        candidate_vmt = f"materials/{theme_candidate.lower()}.vmt"
                        if candidate_vmt in vpk_idx:
                            global_blend_material = theme_candidate
                            break

        uses_blend_material = "blend" in global_blend_material.lower()
        if custom_paint_centers and not uses_blend_material:
            print(
                f"[Terrain Paint] '{global_blend_material}' is not a blend material; "
                "custom tile alpha paint will not be visible."
            )
        paint_target = getattr(self.spec, "custom_tile_paint_target", "floor").lower()
        if paint_target not in {"floor", "walls", "all"}:
            paint_target = "floor"

        from src.material_manager import get_theme_texture_scale

        theme_tex_scale = (
            self.spec.terrain_texture_scale
            if self.spec.terrain_texture_scale is not None
            else get_theme_texture_scale(self.spec.current_theme)
        )

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

                # Theme texturing uses one blend material; variation comes from alpha.
                zone_score = self.calculate_tile_zone_score(col_idx, row_idx)
                
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
                is_cliff = slope > 2.5

                # Edge tiles: never classify as cliff regardless of slope
                is_edge = (col_idx == 0 or col_idx == tiles_x - 1 or
                           row_idx == 0 or row_idx == tiles_y - 1)
                if is_edge:
                    is_cliff = False

                # Compute mean tile height in world units
                corners = []
                for dy in (0, grid_size - 1):
                    for dx in (0, grid_size - 1):
                        cpx = min(col_idx * (grid_size - 1) + dx, img_width - 1)
                        cpy = min(row_idx * (grid_size - 1) + dy, img_height - 1)
                        corners.append(working_heightmap[cpy, cpx] * height_scale)
                tile_z = sum(corners) / 4.0

                z_range = map_z_max - map_z_min
                ratio = (tile_z - map_z_min) / z_range if z_range > 200 else 0.5

                # Deterministic per-tile noise to prevent hard rings
                noise = ((col_idx * 2654435761 ^ row_idx * 2246822519) & 0xFFFFFF)
                noise = (noise / 0xFFFFFF - 0.5) * 0.12
                ratio = max(0.0, min(1.0, ratio + noise))

                if is_cliff:
                    band = "cliff"
                elif ratio > 0.78:
                    band = "peak"
                elif ratio > 0.55:
                    band = "high"
                elif ratio > 0.35:
                    band = "mid"
                elif ratio > 0.15:
                    band = "low"
                elif ratio > 0.05:
                    band = "transition"
                else:
                    band = "valley"

                band_list.append(band)

                if col_idx == 0 and row_idx == 0:
                    print(f"[Terrain] map_z range: {map_z_min:.0f} to {map_z_max:.0f}")
                    print(f"[Terrain] tile(0,0): z={tile_z:.0f} ratio={ratio:.2f} "
                          f"slope={slope:.3f} band={band}")

                tile_material = global_blend_material
                uses_blend = uses_blend_material
                if (col_idx, row_idx) in custom_tile_material_map:
                    tile_material = custom_tile_material_map[(col_idx, row_idx)]
                    uses_blend = "blend" in tile_material.lower()

                # Selective alpha blending for playable/painted blend materials.
                tile_alphas = np.zeros((sample_size, sample_size), dtype=int)

                # Calculate if this tile is deep scenery, under bases, or beneath water
                tile_cx = offset_x + tile_size / 2
                tile_cy = offset_y + tile_size / 2
                base_radius = self.spec.base_clear_radius

                if imp_base_x is not None and imp_base_y is not None:
                    if math.sqrt((tile_cx - imp_base_x)**2 + (tile_cy - imp_base_y)**2) <= base_radius:
                        pass
                if nf_base_x is not None and nf_base_y is not None:
                    if math.sqrt((tile_cx - nf_base_x)**2 + (tile_cy - nf_base_y)**2) <= base_radius:
                        pass

                # Check if tile is completely underwater
                if "water_level" in rules:
                    water_level = float(rules["water_level"])
                    # Check if the highest point of the tile is below water level
                    max_tile_z = -16000
                    for c_r in range(grid_size):
                        for c_c in range(grid_size):
                            w_y = min(img_height - 1, row_idx * (grid_size - 1) + c_r)
                            w_x = min(img_width - 1, col_idx * (grid_size - 1) + c_c)
                            hz = working_heightmap[w_y, w_x] * height_scale
                            if hz > max_tile_z:
                                max_tile_z = hz
                    if max_tile_z < water_level:
                        pass

                # Detail props are now handled by the Smart Detail system
                # which globally scales density based on map size.

                if uses_blend:
                    for iy in range(sample_size):
                        for ix in range(sample_size):
                            px = col_idx * (grid_size - 1) + ix
                            py = row_idx * (grid_size - 1) + iy
                            px = max(0, min(px, img_width - 1))
                            py = max(0, min(py, img_height - 1))

                            vx_world_x = origin_x + (px / (img_width - 1)) * map_width
                            vx_world_y = origin_y + (py / (img_height - 1)) * map_height

                            # Vertex slope via central difference
                            px_m = max(0, px - 1)
                            px_p = min(img_width - 1, px + 1)
                            py_m = max(0, py - 1)
                            py_p = min(img_height - 1, py + 1)

                            h_xm = working_heightmap[py, px_m] * height_scale
                            h_xp = working_heightmap[py, px_p] * height_scale
                            h_ym = working_heightmap[py_m, px] * height_scale
                            h_yp = working_heightmap[py_p, px] * height_scale

                            dz_dx = (h_xp - h_xm) / (2.0 * vertex_spacing)
                            dz_dy = (h_yp - h_ym) / (2.0 * vertex_spacing)
                            v_slope = math.sqrt(dz_dx**2 + dz_dy**2)

                            slope_alpha = slope_to_alpha(v_slope)
                            paint_alpha = 0
                            if custom_paint_centers:
                                nearest_paint_dist = min(
                                    math.sqrt(
                                        (vx_world_x - center_x) ** 2
                                        + (vx_world_y - center_y) ** 2
                                    )
                                    for center_x, center_y in custom_paint_centers
                                )
                                if nearest_paint_dist < paint_inner_radius:
                                    paint_alpha = 255
                                elif nearest_paint_dist < paint_transition_radius:
                                    blend_t = (
                                        (nearest_paint_dist - paint_inner_radius)
                                        / (paint_transition_radius - paint_inner_radius)
                                    )
                                    paint_alpha = int(255 * (1.0 - blend_t))

                                if paint_alpha > 0 and paint_target != "all":
                                    floor_t = (
                                        (0.55 - v_slope) / 0.35
                                        if paint_target == "floor"
                                        else (v_slope - 0.2) / 0.35
                                    )
                                    floor_t = max(0.0, min(1.0, floor_t))
                                    floor_t = floor_t * floor_t * (3.0 - 2.0 * floor_t)
                                    paint_alpha = int(paint_alpha * floor_t)

                            # Height bias only on genuinely HIGH tiles (ratio > 0.65)
                            # and only when the tile itself is high — not edge bleed.
                            # Use tile ratio (per-tile, not per-vertex) so flat low tiles
                            # with steep neighbors never get bias.
                            if ratio > 0.65:
                                # Plateau: flat+high → rock. Scale 0 at 0.65 to 200 at 1.0
                                height_bias = int((ratio - 0.65) / 0.35 * 200)
                            else:
                                height_bias = 0

                            slope_alpha = min(255, slope_alpha + height_bias)
                            final_alpha = max(slope_alpha, paint_alpha)

                            # Vertex Alpha Culling Optimization:
                            # 255 = Rock/No-detail. 0 = Grass.
                            if v_slope > 0.5:
                                final_alpha = 255

                            vx_under_base = False
                            if imp_base_x is not None and imp_base_y is not None:
                                if math.sqrt((vx_world_x - imp_base_x)**2 + (vx_world_y - imp_base_y)**2) <= base_radius:
                                    vx_under_base = True
                            if nf_base_x is not None and nf_base_y is not None:
                                if math.sqrt((vx_world_x - nf_base_x)**2 + (vx_world_y - nf_base_y)**2) <= base_radius:
                                    vx_under_base = True

                            if vx_under_base:
                                final_alpha = 255

                            tile_alphas[iy, ix] = final_alpha
                
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

                # Use a uniform texture scale to prevent mismatched grass resolutions
                # between adjacent tiles. We intentionally do not use a stretching_factor
                # because the Source Engine restricts texture scale per-tile, and dynamic
                # scaling based on slope causes flat grass on mixed tiles to scale down,
                # creating visible seams.
                tex_scale = theme_tex_scale

                top_face.uaxis = f"[1 0 0 0] {tex_scale:.4f}"
                top_face.vaxis = f"[0 -1 0 0] {tex_scale:.4f}"

                disp_infos[(col_idx, row_idx)] = disp_info
                floor_blocks[(col_idx, row_idx)] = floor_block
                zone_scores[(col_idx, row_idx)] = zone_score
                is_cliff_dict[(col_idx, row_idx)] = is_cliff
                tile_alpha_store[(col_idx, row_idx)] = tile_alphas.copy()

        from collections import Counter

        print(f"[Terrain] Band distribution: {dict(Counter(band_list))}")

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

                                # Proximity check
                                too_close = False
                                for old_px, old_py in self.placed_prop_origins:
                                    if math.sqrt((px - old_px)**2 + (py - old_py)**2) < 256:
                                        too_close = True
                                        break
                                if too_close:
                                    continue

                                # Slope check
                                hm_x = (px - origin_x) / map_width * (img_width - 1)
                                hm_y = (py - origin_y) / map_height * (img_height - 1)
                                ix, iy = int(round(hm_x)), int(round(hm_y))
                                ix_m, ix_p = max(0, ix - 1), min(img_width - 1, ix + 1)
                                iy_m, iy_p = max(0, iy - 1), min(img_height - 1, iy + 1)
                                h_xm = working_heightmap[iy, ix_m] * height_scale
                                h_xp = working_heightmap[iy, ix_p] * height_scale
                                h_ym = working_heightmap[iy_m, ix] * height_scale
                                h_yp = working_heightmap[iy_p, ix] * height_scale
                                vertex_spacing_hm = map_width / (img_width - 1)
                                dz_dx = (h_xp - h_xm) / (2.0 * vertex_spacing_hm)
                                dz_dy = (h_yp - h_ym) / (2.0 * vertex_spacing_hm)
                                point_slope = math.sqrt(dz_dx**2 + dz_dy**2)

                                is_tree = "tree" in prop_model.lower()
                                is_rock = "rock" in prop_model.lower() or "stone" in prop_model.lower()

                                if is_tree and point_slope > 0.35:
                                    continue
                                if is_rock and point_slope > 0.6:
                                    continue
                                if not is_tree and not is_rock and point_slope > 0.5:
                                    continue

                                # Skip unavailable models
                                if getattr(self.spec, "vpk_index", None) is not None:
                                    if self.spec.vpk_index and prop_model.lower() not in self.spec.vpk_index:
                                        print(f"[Props] Skipping unavailable: {prop_model}")
                                        continue

                                prop = vmf_lib.Entity("prop_static")
                                prop.origin = f"{px:.1f} {py:.1f} {pz:.1f}"
                                prop.properties["model"] = prop_model
                                prop.properties["angles"] = f"0 {sub_hash % 360} 0"
                                prop.properties["fademindist"] = "2048"
                                prop.properties["fademaxdist"] = "4096"
                                prop.properties["solid"] = "0" # Non-solid background props for performance
                                valve_map.world.children.append(prop)
                                self.prop_count += 1
                                self.placed_prop_origins.append((px, py))

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

        if getattr(self.spec, "topology", "").lower() == "urban" and getattr(self.spec, "urban_blocks", None):
            # Phase 7: Use urban blocks for spawning bases/resources if needed
            self._spawn_urban_entities(self.spec, height_array, valve_map, self.spec.urban_blocks)
        else:
            self._spawn_entities(self.spec, height_array, valve_map, enhanced=self.spec.use_enhanced_spawning)

        # Spawn func_detail_blocker for bases
        if getattr(self.spec, "use_smart_details", False):
            base_radius = self.spec.base_clear_radius

            def spawn_func_detail_blocker(bx: float, by: float):
                bz = get_terrain_height_at(
                    bx, by, height_array, origin_x, origin_y,
                    map_width, map_height, height_scale, tiles_x, tiles_y, power
                )
                bz = quantize_coord(bz, 1.0)

                # Bounding box coordinates — minimum 1024 to avoid degenerate brushes
                blocker_size = max(base_radius * 2, 1024)
                w = blocker_size
                h = blocker_size
                thickness = 128

                vmf_lib.Entity("func_detail_blocker")
                # Add brush using block
                blocker_brush = Block(
                    Vertex(bx, by, bz + 32), # centered at z + 32
                    (w, h, thickness),
                    "tools/toolsnodraw"
                )

                # func_detail_blocker doesn't actually need material per face, but it's a brush entity
                # so we must append the brush (which vmflib represents via the "solid" format).
                # vmflib doesn't easily let us add brushes to entities without using the class system.
                # The correct way to create brush entities in vmflib is slightly different. Let's build a raw Entity and add solid manually if needed.
                # Actually, vmflib allows `Entity` to have children. We can append the Block's solid structure.

                # Wait, vmflib might not have func_detail_blocker as a native type. It's a standard brush entity.

                # Add it as a top-level entity, since func_detail_blocker is an entity with brushes
                ent = vmf_lib.Entity("func_detail_blocker")
                ent.children.append(blocker_brush.brush)
                valve_map.children.append(ent)

            if imp_base_x is not None and imp_base_y is not None:
                spawn_func_detail_blocker(imp_base_x, imp_base_y)

            if nf_base_x is not None and nf_base_y is not None:
                spawn_func_detail_blocker(nf_base_x, nf_base_y)


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

        # Phase 4, 6 & 8: Urban Vertical Layers, Props, and Budget
        if getattr(self.spec, "topology", "").lower() == "urban" and getattr(self.spec, "urban_blocks", None):
            from src.urban_generator import generate_vertical_layers
            from src.entity_placer import spawn_urban_props
            from src.urban_budget import enforce_budget

            valve_map._urban_initial_world_len = len(valve_map.world.children)
            valve_map._urban_initial_children_len = len(valve_map.children)

            generate_vertical_layers(self.spec, self.spec.urban_blocks, valve_map)
            spawn_urban_props(valve_map, self.spec, self.spec.urban_blocks)

            blocks, report = enforce_budget(self.spec, self.spec.urban_blocks, valve_map, self.spec.compile_budget)
            self.spec.urban_blocks = blocks
            self.spec._urban_budget_report = report

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

        # Check alpha continuity at shared tile edges
        seam_violations = 0
        for row_idx in range(tiles_y - 1):
            for col_idx in range(tiles_x - 1):
                # Bottom edge of tile vs top edge of tile below
                if (col_idx, row_idx) in tile_alpha_store and (col_idx, row_idx + 1) in tile_alpha_store:
                    bottom = tile_alpha_store[(col_idx, row_idx)][-1, :]
                    top    = tile_alpha_store[(col_idx, row_idx + 1)][0, :]
                    diff   = np.abs(bottom.astype(int) - top.astype(int))
                    if diff.max() > 80:
                        seam_violations += 1

        print(f"[Alpha] Seam violations (>80 alpha jump): {seam_violations}")

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
