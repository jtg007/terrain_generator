from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple, Dict

from src.terrain_spec import TerrainSpec

class BlockType(Enum):
    INTACT = "intact"
    RUINED = "ruined"
    RUBBLE = "rubble"
    OPEN_LOT = "open_lot"

class RampPlacement(Enum):
    NORTH = "north"
    SOUTH = "south"
    EAST = "east"
    WEST = "west"

class ResourceElevation(Enum):
    GROUND = "ground"
    ROOF = "roof"

class DistrictType(Enum):
    DOWNTOWN = "downtown"
    INDUSTRIAL = "industrial"
    RESIDENTIAL = "residential"
    RUINED_CENTER = "ruined_center"
    OPEN_PERIMETER = "open_perimeter"

@dataclass
class UrbanBlock:
    grid_x: int
    grid_y: int
    world_x: float
    world_y: float
    footprint_w: float
    footprint_d: float
    elevation_h: float
    block_type: BlockType
    ramp_side: Optional[RampPlacement]
    district: DistrictType
    has_roof_resource: bool
    on_main_lane: bool
    adjacent_streets: list
    needs_rooftop_cover: bool = False
    downgraded_flat_walls: bool = False
    mound_height: float = 0.0

@dataclass
class UrbanDistrict:
    district_type: DistrictType
    bounds: Tuple[float, float, float, float]  # x, y, w, h in world units
    demolition_strength: float                 # 0.0–1.0

from src.urban_budget import CompileBudget

@dataclass
class UrbanSpec(TerrainSpec):
    block_size_min: float = 1024.0
    block_size_max: float = 2048.0
    street_width: float = 512.0
    block_height_min: float = 256.0
    block_height_max: float = 1024.0
    demolition_ratio: float = 0.5
    center_ruin_bias: float = 0.8
    district_distribution: Dict[DistrictType, float] = field(default_factory=lambda: {
        DistrictType.DOWNTOWN: 0.2,
        DistrictType.INDUSTRIAL: 0.3,
        DistrictType.RESIDENTIAL: 0.5
    })
    resource_elevation: ResourceElevation = ResourceElevation.GROUND
    compile_budget: CompileBudget = field(default_factory=CompileBudget)
    max_los_length: float = 3072.0
    street_cover_points: List[Tuple[float, float]] = field(default_factory=list)

    # Terrain-first generation mode
    urban_generation_mode: str = "terrain_first" # "legacy" or "terrain_first"

    # Tuning parameters for terrain-first mode
    crater_depth_min: float = 40.0
    crater_depth_max: float = 100.0
    crater_radius_min: float = 200.0
    crater_radius_max: float = 400.0
    crater_count_min: int = 3
    crater_count_max: int = 8
    crater_depth_scale: float = 1.0 # max relative crater depth multiplier

    mound_height_rubble_min: float = 40.0
    mound_height_rubble_max: float = 120.0
    mound_height_ruined_min: float = 120.0
    mound_height_ruined_max: float = 280.0
    mound_height_intact_min: float = 280.0
    mound_height_intact_max: float = 480.0

    def __post_init__(self):
        super().__post_init__()
