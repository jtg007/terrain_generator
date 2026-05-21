from dataclasses import dataclass
from src.terrain_spec import TerrainSpec

@dataclass
class WarzoneSpec(TerrainSpec):

    # Crater field
    crater_count_min: int   = 18
    crater_count_max: int   = 35
    crater_radius_min: float = 180.0   # world units
    crater_radius_max: float = 420.0   # world units
    crater_depth_min: float  = 50.0    # world units below local ground
    crater_depth_max: float  = 130.0   # world units below local ground
    center_crater_bias: float = 0.75
    # 0.0 = craters distributed evenly
    # 1.0 = craters concentrated heavily at map center

    # Berms (raised earth rings around craters)
    berm_enabled: bool        = True
    berm_height_scale: float  = 0.55
    # Berm height = crater_depth * berm_height_scale
    # Physical: displaced earth piles up around the crater rim
    berm_width_scale: float   = 0.40
    # Berm width = crater_radius * berm_width_scale

    # Base terrain
    base_roughness: float     = 1.0
    # Multiplier on fBm amplitude. 1.0 = standard battlefield churn.
    # 0.5 = flatter, more vehicle-friendly
    # 1.5 = heavily churned, more infantry-focused

    # Vehicle lane appearance
    lane_wear_depth: float    = 30.0
    # How much vehicle lanes are worn below surrounding terrain.
    # Gives the impression of tracks ground into the earth.
    lane_edge_softness: float = 0.6
    # 0.0 = sharp lane edges, 1.0 = very gradual transition

    # Alpha painting
    scorch_radius_scale: float = 1.3
    # Scorch alpha extends this multiple of crater_radius around
    # each crater center. 1.0 = exactly crater edge. 1.3 = 30% wider.
    edge_grass_width: float   = 0.25
    # Fraction of map width where edge grass appears.
    # Gives the impression of untouched terrain at map borders.

    # Props
    prop_density_scale: float = 1.0
    # Global prop density multiplier
