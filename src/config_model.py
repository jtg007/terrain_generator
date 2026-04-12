from dataclasses import dataclass
from pathlib import Path
from typing import Tuple, Optional

from src.terrain_spec import TerrainSpec

@dataclass
class GUIConfigModel:
    seed: int = 12345
    tiles_x: int = 16
    tiles_y: int = 16
    cell_size: int = 512
    displacement_power: int = 3
    roughness: float = 0.5
    erosion_strength: float = 0.5
    height_scale: int = 2048
