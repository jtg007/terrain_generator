#!/usr/bin/env python3
"""
Terrain Specification Data Models

Core data structures for compile-safe displacement terrain generation.
"""

from dataclasses import dataclass
from typing import List, Tuple, Dict, Any, Optional
import numpy as np


class ZoneType:
    BASE = "base_zone"
    MAIN_LANE = "main_lane_zone"
    SIDE_ROUTE = "side_route_zone"
    VEHICLE_OPEN = "vehicle_open_zone"
    CHOKEPOINT = "chokepoint_zone"
    WILDERNESS = "wilderness_zone"
    RESOURCE = "resource_zone"


@dataclass
class LayoutNode:
    x: float
    y: float
    radius: float
    type: str  # ZoneType


@dataclass
class LayoutConnection:
    start_node: LayoutNode
    end_node: LayoutNode
    width: float
    type: str  # 'main_lane', 'side_lane', 'chokepoint_lane'
    path_points: Optional[List[Tuple[float, float]]] = None


@dataclass
class TerrainSpec:
    """
    Specification for terrain generation.

    All measurements are in Source engine world units.
    """

    origin_x: int = -4096
    origin_y: int = -4096
    size_x: int = 8192
    size_y: int = 8192
    cell_size: int = 512
    displacement_power: int = 3
    seed: int = 12345
    max_slope_step: int = 1024
    height_quantization: int = 1
    noise_octaves: int = 4
    erosion_iterations: int = 50000
    erosion_droplet_lifetime: int = 30
    terrain_max_height: int = 2048
    skybox_ceiling: int = 4096
    vpk_index: Optional[List[str]] = None
    roughness: float = 0.5
    topology: str = "random"
    lane_width_scale: float = 0.5
    mountain_height_scale: float = 1.0
    lane_elevation: float = 0.15

    # Canyon Generator Parameters
    feature_scale: float = 1.8
    warp_strength: float = 1.0
    canyon_roughness: float = 0.50
    plateau_noise: float = 0.12
    maze_size: int = 90
    lane_numbers: int = 6
    wall_slope: float = 0.06
    lane_depth: float = 0.72
    blur_radius: float = 0.0

    material: str = "nature/terrain/blend_dirt_grass_dmz_sscale"
    skybox: Optional[str] = None
    underlay_material: str = "TOOLS/TOOLSSKIP"
    underlay_height: int = 128
    custom_image_path: Optional[str] = None

    custom_imp_base_x: Optional[float] = None
    custom_imp_base_y: Optional[float] = None
    custom_nf_base_x: Optional[float] = None
    custom_nf_base_y: Optional[float] = None
    custom_resources: Optional[List[Tuple[float, float]]] = None

    custom_layout_nodes: Optional[List[LayoutNode]] = None
    custom_layout_connections: Optional[List[LayoutConnection]] = None
    custom_tile_materials: Optional[Dict[Tuple[int, int], str]] = None
    
    # Theme & Optimization
    current_theme: str = "Temperate"
    corridor_detail_width: int = 2048
    transition_width: int = 1536
    scenery_variation_noise: float = 0.4
    hero_prop_density: float = 0.5

    base_clear_radius: int = 0
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

    manual_terrain: bool = False
    invert_lanes: bool = False

    # Flag for natural un-carved canyon height generation
    canyon_natural: bool = False

    def default_imp_base(self) -> Tuple[float, float]:
        """
        Get the default imperial base spawn position (25% of map size).
        Note: The flatten area applied later is large enough to cover this spawn.
        """
        return (
            self.origin_x + self.size_x * 0.25,
            self.origin_y + self.size_y * 0.25,
        )

    def default_nf_base(self) -> Tuple[float, float]:
        """
        Get the default northern faction base spawn position (75% of map size).
        Note: The flatten area applied later is large enough to cover this spawn.
        """
        return (
            self.origin_x + self.size_x * 0.75,
            self.origin_y + self.size_y * 0.75,
        )

    def validate_layout(self) -> Any:
        """Validate the placement of bases and resources."""
        from src.layout_validator import LayoutValidator

        imp_base = (
            (self.custom_imp_base_x, self.custom_imp_base_y)
            if self.custom_imp_base_x is not None and self.custom_imp_base_y is not None
            else self.default_imp_base()
        )
        nf_base = (
            (self.custom_nf_base_x, self.custom_nf_base_y)
            if self.custom_nf_base_x is not None and self.custom_nf_base_y is not None
            else self.default_nf_base()
        )
        resources = self.custom_resources if self.custom_resources is not None else []
        return LayoutValidator().validate(self, imp_base, nf_base, resources)

    def __post_init__(self):
        if self.displacement_power not in (2, 3):
            raise ValueError(
                f"displacement_power must be 2 or 3, got {self.displacement_power}"
            )
        if self.cell_size <= 0:
            raise ValueError("cell_size must be positive")
        if self.size_x <= 0 or self.size_y <= 0:
            raise ValueError("size_x and size_y must be positive")
        if self.terrain_max_height <= 0:
            raise ValueError("terrain_max_height must be positive")

    @property
    def tiles_x(self) -> int:
        """Number of displacement tiles along X axis."""
        return self.size_x // self.cell_size

    @property
    def tiles_y(self) -> int:
        """Number of displacement tiles along Y axis."""
        return self.size_y // self.cell_size

    @property
    def grid_size(self) -> int:
        """Number of vertices along one edge of a displacement (power^2 + 1)."""
        return (2**self.displacement_power) + 1

    @property
    def vertex_cols(self) -> int:
        """Total number of vertex columns in the height grid."""
        return self.tiles_x * (self.grid_size - 1) + 1

    @property
    def vertex_rows(self) -> int:
        """Total number of vertex rows in the height grid."""
        return self.tiles_y * (self.grid_size - 1) + 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "origin_x": self.origin_x,
            "origin_y": self.origin_y,
            "size_x": self.size_x,
            "size_y": self.size_y,
            "cell_size": self.cell_size,
            "displacement_power": self.displacement_power,
            "seed": self.seed,
            "max_slope_step": self.max_slope_step,
            "height_quantization": self.height_quantization,
            "noise_octaves": self.noise_octaves,
            "erosion_iterations": self.erosion_iterations,
            "erosion_droplet_lifetime": self.erosion_droplet_lifetime,
            "topology": self.topology,
            "lane_width_scale": self.lane_width_scale,
            "mountain_height_scale": self.mountain_height_scale,
            "lane_elevation": self.lane_elevation,
            "material": self.material,
            "underlay_material": self.underlay_material,
            "underlay_height": self.underlay_height,
            "custom_image_path": self.custom_image_path,
            "current_theme": self.current_theme,
            "corridor_detail_width": self.corridor_detail_width,
            "transition_width": self.transition_width,
            "scenery_variation_noise": self.scenery_variation_noise,
            "hero_prop_density": self.hero_prop_density,
            # Note: custom_tile_materials intentionally omitted from to_dict as it's meant to be transient/project-level.
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TerrainSpec":
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class HeightGrid:
    """
    2D grid of height values.

    heights[r, c] gives the height at row r, column c.
    Coordinate system: row 0 = origin_y (min Y), col 0 = origin_x (min X)
    slopes[r][c] gives the gradient magnitude at vertex (r, c), or None if not calculated.
    """

    heights: np.ndarray
    origin_x: int
    origin_y: int
    cell_size: int
    slopes: Optional[List[List[float]]] = None
    global_selection_mask: Optional[np.ndarray] = None

    def __post_init__(self):
        if isinstance(self.heights, list):
            self.heights = np.array(self.heights, dtype=np.float32)

        self._rows = self.heights.shape[0]
        self._cols = self.heights.shape[1] if self._rows > 0 else 0
        if self.slopes is None:
            self.slopes = [[0.0 for _ in range(self._cols)] for _ in range(self._rows)]
        if self.global_selection_mask is None:
            self.global_selection_mask = np.ones((self._rows, self._cols), dtype=bool)

    @property
    def rows(self) -> int:
        """Number of rows (Y dimension)."""
        return self._rows

    @property
    def cols(self) -> int:
        """Number of columns (X dimension)."""
        return self._cols

    def get_height(self, row: int, col: int) -> float:
        """Get height at vertex (row, col)."""
        return self.heights[row][col]

    def set_height(self, row: int, col: int, height: float):
        """Set height at vertex (row, col)."""
        self.heights[row][col] = height

    def world_position(self, row: int, col: int) -> Tuple[int, int, float]:
        """Get world position (x, y, z) for vertex at (row, col)."""
        x = self.origin_x + col * self.cell_size
        y = self.origin_y + row * self.cell_size
        z = self.heights[row][col]
        return (x, y, z)

    def world_x(self, col: int) -> int:
        """Get world X for column."""
        return self.origin_x + col * self.cell_size

    def world_y(self, row: int) -> int:
        """Get world Y for row."""
        return self.origin_y + row * self.cell_size

    def neighbor_heights(self, row: int, col: int) -> List[float]:
        """Get heights of 4-connected neighbors. Returns [N, S, E, W] or fewer at edges."""
        neighbors = []
        if row > 0:
            neighbors.append(float(self.heights[row - 1, col]))  # North
        if row < self.rows - 1:
            neighbors.append(float(self.heights[row + 1, col]))  # South
        if col < self.cols - 1:
            neighbors.append(float(self.heights[row, col + 1]))  # East
        if col > 0:
            neighbors.append(float(self.heights[row, col - 1]))  # West
        return neighbors

    def max_height(self) -> float:
        """Get maximum height in grid."""
        return float(np.max(self.heights))

    def min_height(self) -> float:
        """Get minimum height in grid."""
        return float(np.min(self.heights))

    def average_height(self) -> float:
        """Get average height in grid."""
        return float(np.mean(self.heights))

    def copy(self) -> "HeightGrid":
        """Create a deep copy of the height grid."""
        return HeightGrid(
            heights=self.heights.copy(),
            origin_x=self.origin_x,
            origin_y=self.origin_y,
            cell_size=self.cell_size,
        )


@dataclass
class TerrainCell:
    """
    A terrain cell referencing 4 corner vertices in the shared height grid.
    The full (2^power + 1)^2 vertex grid is accessed through grid_row/grid_col/grid_span.
    """

    cell_id: int
    grid_row: int
    grid_col: int
    grid_span: int
    vertex_tl: Tuple[int, int]
    vertex_tr: Tuple[int, int]
    vertex_br: Tuple[int, int]
    vertex_bl: Tuple[int, int]

    @property
    def vertices(self) -> List[Tuple[int, int]]:
        """All 4 vertices as list [(r,c), (r,c), (r,c), (r,c)]."""
        return [self.vertex_tl, self.vertex_tr, self.vertex_br, self.vertex_bl]

    @property
    def vertex_indices(
        self,
    ) -> Tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int], Tuple[int, int]]:
        """All 4 vertices as tuple."""
        return (self.vertex_tl, self.vertex_tr, self.vertex_br, self.vertex_bl)

    def get_vertex_height(self, grid: HeightGrid, which: str) -> float:
        """Get height of specified vertex. which: 'tl', 'tr', 'br', 'bl'."""
        vertex_map = {
            "tl": self.vertex_tl,
            "tr": self.vertex_tr,
            "br": self.vertex_br,
            "bl": self.vertex_bl,
        }
        r, c = vertex_map[which]
        return grid.get_height(r, c)

    def get_edge_heights(self, grid: HeightGrid, edge: str) -> List[float]:
        """Get heights along an edge. edge: 'top', 'bottom', 'left', 'right'."""
        if edge == "top":
            return [
                grid.get_height(self.grid_row, c)
                for c in range(self.grid_col, self.grid_col + 2)
            ]
        elif edge == "bottom":
            return [
                grid.get_height(self.grid_row + 1, c)
                for c in range(self.grid_col, self.grid_col + 2)
            ]
        elif edge == "left":
            return [
                grid.get_height(r, self.grid_col)
                for r in range(self.grid_row, self.grid_row + 2)
            ]
        elif edge == "right":
            return [
                grid.get_height(r, self.grid_col + 1)
                for r in range(self.grid_row, self.grid_row + 2)
            ]
        return []


@dataclass
class UnderlayBrush:
    """Solid brush underneath the displacement terrain."""

    origin_x: int
    origin_y: int
    size_x: int
    size_y: int
    bottom_z: int
    top_z: int
    material: str

    def world_bounds(self) -> Tuple[int, int, int, int, int, int]:
        """Return (min_x, min_y, min_z, max_x, max_y, max_z)."""
        return (
            self.origin_x,
            self.origin_y,
            self.bottom_z,
            self.origin_x + self.size_x,
            self.origin_y + self.size_y,
            self.top_z,
        )


def create_default_spec() -> TerrainSpec:
    return TerrainSpec(
        origin_x=-4096,
        origin_y=-4096,
        size_x=8192,
        size_y=8192,
        cell_size=512,
        displacement_power=3,
        seed=12345,
        max_slope_step=1024,
        height_quantization=1,
        noise_octaves=4,
        erosion_iterations=50000,
        erosion_droplet_lifetime=30,
        topology="random",
        lane_width_scale=0.5,
        mountain_height_scale=1.0,
        lane_elevation=0.15,
        feature_scale=1.8,
        warp_strength=1.0,
        canyon_roughness=0.50,
        wall_slope=0.06,
        plateau_noise=0.12,
        lane_depth=0.72,
        blur_radius=14,
        material="common/nature/blend_grass_mountainwall_000",
        underlay_material="TOOLS/TOOLSSKIP",
        underlay_height=128,
    )


if __name__ == "__main__":
    spec = create_default_spec()
    print("Default TerrainSpec:")
    print(f"  Tiles: {spec.tiles_x} x {spec.tiles_y}")
    print(f"  Grid size: {spec.grid_size} vertices per tile")
    print(f"  Total vertices: {spec.vertex_cols} x {spec.vertex_rows}")
    print(f"  Max slope step: {spec.max_slope_step}")
    print(f"  Quantization: {spec.height_quantization}")
