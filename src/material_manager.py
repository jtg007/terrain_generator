from typing import Optional, Tuple
from pathlib import Path

THEME_BLEND_MATERIAL: dict[str, tuple[str, str]] = {
    "Temperate": (
        "common/nature/blend_grass_mountainwall_000",
        "common/nature/blend_grass_mountainwall_000",
    ),
    "Desert": (
        "common/nature/blend_grass_sandfloor009a_000",
        "common/nature/blend_grass_sandfloor009a_000",
    ),
    "Snow": (
        "common/terrain/blend_snow01_rock01a",
        "common/terrain/blend_snow01_rock01a",
    ),
    "Industrial": (
        "common/stene/dirtyconcrete",
        "common/stene/dirtyconcrete",
    ),
    "Wasteland": (
        "common/terrain/blend_red2_red3",
        "common/terrain/blend_red2_red3",
    ),
    "Generic": (
        "common/nature/blend_grass_mud_003",
        "common/nature/blend_grass_mud_003",
    ),
}

def choose_compile_safe_material(
    requested_material: str,
    map_width: int,
    map_height: int,
    use_smart_details: bool = False,
    textures_path: str | Path | None = None,
    vpk_index: set[str] | None = None,
) -> Tuple[str, Optional[str]]:
    """Return (material_name, optional_warning)."""
    # Smart Detail system handles detail props dynamically
    # so we no longer need to restrict materials or issue warnings here.
    return requested_material, None
