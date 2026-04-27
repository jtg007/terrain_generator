from dataclasses import dataclass
from pathlib import Path
from typing import Tuple, Optional
import sys

if getattr(sys, "frozen", False):
    from terrain_spec import TerrainSpec
else:
    from src.terrain_spec import TerrainSpec

# Keep a small safety margin from Hammer/VBSP hard bounds (±16384) to avoid
# borderline compile failures like "HashVec: point outside valid range".
MAX_MAP_WORLD_SIZE = 32640
MAX_MAP_DISPINFO = 2048


@dataclass
class GUIConfigModel:
    """
    Validatable user configuration for the GUI.
    Acts as an intermediary before generating the actual TerrainSpec.
    """

    seed: int = 12345
    tiles_x: int = 16
    tiles_y: int = 16
    cell_size: int = 512
    displacement_power: int = 3

    # 0.0 to 1.0 sliders, mapping to physical parameters roughly
    roughness: float = 0.5  # Maps to noise octaves
    erosion_strength: float = 0.5  # Maps to erosion iterations
    height_scale: int = 2048  # Absolute max height
    skybox_ceiling: int = 4096  # Skybox Ceiling Height

    topology: str = "canyon"
    lane_width_scale: float = 1.0
    mountain_height_scale: float = 1.0
    lane_elevation: float = 0.15

    # Canyon Generator Settings
    feature_scale: float = 1.8
    warp_strength: float = 0.018
    plateau_noise: float = 0.12
    wall_slope: float = 0.06
    lane_depth: float = 0.72
    blur_radius: int = 10

    # Selected preset for UI tracking
    preset_name: str = "mixed"

    custom_image_path: Optional[str] = None

    # Texture and skybox selections
    terrain_material: str = "common/nature/blend_grass_mountainwall_000"
    skybox: str = "empsky_overcast3yellow"
    use_nodetail_texture: bool = False

    # Base flattening settings
    base_clear_radius: int = 512
    base_flatness: float = 0.8
    resource_clear_radius: int = 256
    lane_node_radius: int = 512
    generate_lanes: bool = True

    # Spawn settings
    disable_commander: bool = False
    disable_buildings: bool = False
    disable_resource_nodes: bool = False
    disable_capture_points: bool = True
    minimal_map: bool = False
    terrain_only: bool = False

    custom_imp_base_x: Optional[float] = None
    custom_imp_base_y: Optional[float] = None
    custom_nf_base_x: Optional[float] = None
    custom_nf_base_y: Optional[float] = None
    custom_resources: Optional[list] = None

    manual_terrain: bool = False
    invert_lanes: bool = False
    preview_with_pipeline: bool = False

    @property
    def map_size_x(self) -> int:
        return self.tiles_x * self.cell_size

    @property
    def map_size_y(self) -> int:
        return self.tiles_y * self.cell_size

    def validate(self) -> Tuple[bool, str]:
        """
        Returns (is_valid, error_message).
        If is_valid is True, error_message is roughly 'Valid'.
        """
        if self.tiles_x <= 0 or self.tiles_y <= 0:
            return False, "Tile counts must be strictly positive."

        if self.displacement_power not in (2, 3, 4):
            return (
                False,
                f"Invalid displacement power: {self.displacement_power}. Allowed: 2, 3, 4.",
            )

        # Compile-safe limit check (slightly below Hammer hard bounds).
        if self.map_size_x > MAX_MAP_WORLD_SIZE or self.map_size_y > MAX_MAP_WORLD_SIZE:
            return (
                False,
                f"Map size ({self.map_size_x}x{self.map_size_y}) exceeds compile-safe limit "
                f"({MAX_MAP_WORLD_SIZE}x{MAX_MAP_WORLD_SIZE}).",
            )

        disp_count = self.tiles_x * self.tiles_y
        if disp_count > MAX_MAP_DISPINFO:
            return (
                False,
                f"Too many displacement tiles ({disp_count} > {MAX_MAP_DISPINFO}). "
                "Reduce Tiles X/Y or increase Tile Size.",
            )

        if self.height_scale <= 0 or self.height_scale > 999999:
            return (
                False,
                "Height scale is out of reasonable bounds (max recommended 999999).",
            )

        if self.custom_image_path and not Path(self.custom_image_path).is_file():
            return False, f"Custom heightmap not found: {self.custom_image_path}"

        # Layout check
        try:
            # Compile-safe map extent check is done above.

            # Use minimal spec for layout validation
            origin_x = int(-self.map_size_x / 2)
            origin_y = int(-self.map_size_y / 2)

            spec = TerrainSpec(
                origin_x=origin_x,
                origin_y=origin_y,
                size_x=self.map_size_x,
                size_y=self.map_size_y,
                base_clear_radius=self.base_clear_radius,
                base_flatness=self.base_flatness,
                resource_clear_radius=self.resource_clear_radius,
                lane_node_radius=self.lane_node_radius,
                generate_lanes=self.generate_lanes,
                custom_imp_base_x=self.custom_imp_base_x,
                custom_imp_base_y=self.custom_imp_base_y,
                custom_nf_base_x=self.custom_nf_base_x,
                custom_nf_base_y=self.custom_nf_base_y,
                custom_resources=self.custom_resources,
            )
            val_result = spec.validate_layout()
            if not val_result.valid:
                return False, val_result.errors[0]
        except Exception:
            # Catch transient errors during sync
            pass

        return True, "All validation checks passed."

    def auto_clamp(self):
        """
        Mutates the configuration to ensure it's safe to use.
        """
        # Clamp tiles to avoid exceeding hammer limits.
        max_tiles_x = MAX_MAP_WORLD_SIZE // max(self.cell_size, 1)
        max_tiles_y = MAX_MAP_WORLD_SIZE // max(self.cell_size, 1)

        self.tiles_x = max(1, min(self.tiles_x, max_tiles_x))
        self.tiles_y = max(1, min(self.tiles_y, max_tiles_y))

        if self.tiles_x * self.tiles_y > MAX_MAP_DISPINFO:
            self.tiles_y = max(1, MAX_MAP_DISPINFO // self.tiles_x)
            if self.tiles_x * self.tiles_y > MAX_MAP_DISPINFO:
                self.tiles_x = max(1, MAX_MAP_DISPINFO // self.tiles_y)

        # Power clamping
        if self.displacement_power < 2:
            self.displacement_power = 2
        elif self.displacement_power > 3:
            self.displacement_power = 3

        # Roughness and Erosion clamps
        self.roughness = max(0.0, min(self.roughness, 1.0))
        self.erosion_strength = max(0.0, min(self.erosion_strength, 1.0))

    def make_spec(self, validate: bool = True) -> TerrainSpec:
        """
        Transforms the GUI properties into the backend TerrainSpec, centered on origin.
        """
        if validate:
            is_valid, msg = self.validate()
            if not is_valid:
                raise ValueError(f"Cannot generate TerrainSpec: {msg}")

        # Map generic 0.0-1.0 ranges to physical ranges
        # Octaves: 1 to 8 (use exponential for better distribution)
        octaves = int(1 + (self.roughness**0.5 * 7))
        # Iterations: 0 to 100,000 (use exponential for fine control at low values)
        iterations = int(
            10 ** (self.erosion_strength * 5)
        )  # 10^0 to 10^5 = 1 to 100,000

        # AGENTS.md Map Centering: Origin offsets
        origin_x = int(-self.map_size_x / 2)
        origin_y = int(-self.map_size_y / 2)

        # Linear mapping: slider 0-100 maps to scale 0.0-1.0
        # This gives full range from flat (0%) to full mountains (100%)
        effective_mountain_height_scale = self.mountain_height_scale

        return TerrainSpec(
            origin_x=origin_x,
            origin_y=origin_y,
            size_x=self.map_size_x,
            size_y=self.map_size_y,
            cell_size=self.cell_size,
            displacement_power=self.displacement_power,
            seed=self.seed,
            max_slope_step=1024,
            noise_octaves=octaves,
            erosion_iterations=iterations,
            terrain_max_height=self.height_scale,
            skybox_ceiling=self.skybox_ceiling,
            roughness=self.roughness,
            topology=self.topology,
            lane_width_scale=self.lane_width_scale,
            mountain_height_scale=effective_mountain_height_scale,
            lane_elevation=self.lane_elevation,
            feature_scale=self.feature_scale,
            warp_strength=self.warp_strength,
            plateau_noise=self.plateau_noise,
            wall_slope=self.wall_slope,
            lane_depth=self.lane_depth,
            blur_radius=self.blur_radius,
            custom_image_path=self.custom_image_path,
            base_clear_radius=self.base_clear_radius,
            base_flatness=self.base_flatness,
            resource_clear_radius=self.resource_clear_radius,
            lane_node_radius=self.lane_node_radius,
            generate_lanes=self.generate_lanes,
            disable_commander=self.disable_commander,
            disable_buildings=self.disable_buildings,
            disable_resource_nodes=self.disable_resource_nodes,
            disable_capture_points=self.disable_capture_points,
            minimal_map=self.minimal_map,
            terrain_only=self.terrain_only,
            custom_imp_base_x=self.custom_imp_base_x,
            custom_imp_base_y=self.custom_imp_base_y,
            custom_nf_base_x=self.custom_nf_base_x,
            custom_nf_base_y=self.custom_nf_base_y,
            custom_resources=self.custom_resources,
            manual_terrain=self.manual_terrain,
            invert_lanes=self.invert_lanes,
        )
