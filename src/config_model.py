from dataclasses import dataclass
from pathlib import Path
from typing import Tuple, Optional
import sys

if getattr(sys, "frozen", False):
    from terrain_spec import TerrainSpec
else:
    from src.terrain_spec import TerrainSpec


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

    topology: str = "random"
    lane_width_scale: float = 1.0
    mountain_height_scale: float = 1.0

    # Selected preset for UI tracking
    preset_name: str = "mixed"

    custom_image_path: Optional[str] = None

    # Texture and skybox selections
    terrain_material: str = "common/nature/blend_grass_mountainwall_000"
    skybox: str = "empsky_overcast3yellow"

    # Base flattening settings
    base_clear_radius: int = 512
    base_flatness: float = 0.8

    # Spawn settings
    disable_commander: bool = False
    disable_buildings: bool = False
    disable_resource_nodes: bool = False
    minimal_map: bool = False
    terrain_only: bool = False

    custom_imp_base_x: Optional[float] = None
    custom_imp_base_y: Optional[float] = None
    custom_nf_base_x: Optional[float] = None
    custom_nf_base_y: Optional[float] = None
    custom_resources: Optional[list] = None

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

        # Hammer limit check: map centered at 0,0, limits are -16384 to +16384 -> max size = 32768
        if self.map_size_x > 32768 or self.map_size_y > 32768:
            return (
                False,
                f"Map size ({self.map_size_x}x{self.map_size_y}) exceeds Hammer limits (32768x32768).",
            )

        if self.height_scale <= 0 or self.height_scale > 4096:
            return (
                False,
                "Height scale is out of reasonable bounds (max recommended 4096).",
            )

        if self.custom_image_path and not Path(self.custom_image_path).is_file():
            return False, f"Custom heightmap not found: {self.custom_image_path}"

        # Layout check
        try:
            # Hammer limit check: map centered at 0,0, limits are -16384 to +16384 -> max size = 32768
            # (Done above)
            
            # Use minimal spec for layout validation
            origin_x = int(-self.map_size_x / 2)
            origin_y = int(-self.map_size_y / 2)
            
            spec = TerrainSpec(
                origin_x=origin_x,
                origin_y=origin_y,
                size_x=self.map_size_x,
                size_y=self.map_size_y,
                base_clear_radius=self.base_clear_radius,
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
        # Clamp tiles to avoid exceeding hammer limits
        max_tiles_x = 32768 // max(self.cell_size, 1)
        max_tiles_y = 32768 // max(self.cell_size, 1)

        self.tiles_x = max(1, min(self.tiles_x, max_tiles_x))
        self.tiles_y = max(1, min(self.tiles_y, max_tiles_y))

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
            max_slope_step=64,
            noise_octaves=octaves,
            erosion_iterations=iterations,
            terrain_max_height=self.height_scale,
            roughness=self.roughness,
            topology=self.topology,
            lane_width_scale=self.lane_width_scale,
            mountain_height_scale=effective_mountain_height_scale,
            custom_image_path=self.custom_image_path,
            base_clear_radius=self.base_clear_radius,
            base_flatness=self.base_flatness,
            disable_commander=self.disable_commander,
            disable_buildings=self.disable_buildings,
            disable_resource_nodes=self.disable_resource_nodes,
            minimal_map=self.minimal_map,
            terrain_only=self.terrain_only,
            custom_imp_base_x=self.custom_imp_base_x,
            custom_imp_base_y=self.custom_imp_base_y,
            custom_nf_base_x=self.custom_nf_base_x,
            custom_nf_base_y=self.custom_nf_base_y,
            custom_resources=self.custom_resources,
        )
