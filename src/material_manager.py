import json
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

THEME_TEXTURE_SCALES: dict[str, float] = {
    "Temperate": 0.5,
    "Desert": 1.0,
    "Snow": 1.0,
    "Industrial": 0.25,
    "Wasteland": 0.5,
    "Generic": 0.5,
}


def get_theme_texture_scale(theme: str) -> float:
    """Return ideal texture scale for given theme name."""
    return THEME_TEXTURE_SCALES.get(theme, 0.5)


def choose_compile_safe_material(
    requested_material: str,
    map_width: int,
    map_height: int,
    use_smart_details: bool = False,
    textures_path: str | Path | None = None,
    vpk_index: list[str] | None = None,
) -> Tuple[str, Optional[str]]:
    """Return (material_name, optional_warning)."""
    # Smart Detail system handles detail props dynamically
    # so we no longer need to restrict materials or issue warnings here.
    return requested_material, None


def get_texture_safety_status(textures_path: str | Path) -> dict[str, bool]:
    """Return dict mapping each material path to safety bool.

    All materials listed in textures.json are curated and considered safe.
    """
    with open(textures_path) as f:
        data = json.load(f)
    safety: dict[str, bool] = {}
    for theme in data.get("themes", {}).values():
        for entry in theme.get("materials", []):
            safety[entry["path"]] = True
    return safety
