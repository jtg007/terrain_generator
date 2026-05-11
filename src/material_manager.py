from typing import Optional, Tuple
from pathlib import Path

COMPILE_SAFE_NODETAIL_MATERIAL = "common/terrain/blend_grass01a_dirt01a_nodetail"

# All _nodetail material paths that actually exist in Empires Mod VPKs.
# Keyed by full vpk-index path (lowercase) for direct set membership tests.
KNOWN_NODETAIL_MATERIALS: set[str] = {
    "materials/common/terrain/blend_grass01a_dirt01a_nodetail.vmt",
    "materials/common/terrain/blend_grass01c_dirt01a_nodetail.vmt",
    "materials/maps/emp_bush/silk_blendgrass04grass07_nodetail.vmt",
    "materials/maps/emp_bush/silk_bush_blendgrass07rock8a_nodetail.vmt",
    "materials/maps/emp_bush/silk_bush_blendgrass4cgrass4b_nodetail.vmt",
    "materials/maps/emp_bush/silk_bush_blendgrass4crock8a_nodetail.vmt",
    "materials/maps/emp_bush/silk_bush_blendgrass5bgrass02b_nodetail.vmt",
    "materials/maps/emp_bush/silk_bush_blendgrass5brock8a_nodetail.vmt",
    "materials/maps/emp_canyon/silk_canyon_grass10a_ground09_nodetail.vmt",
    "materials/maps/emp_chain/silk_chain_blendgrass5bbground2db_nodetail.vmt",
    "materials/maps/emp_chain/silk_chain_blendgrass5bbground5db_nodetail.vmt",
    "materials/maps/emp_chain/silk_chain_blendgrass5bbground7ab_nodetail.vmt",
    "materials/maps/emp_chain/silk_chain_blendgrass5bbground8ab_nodetail.vmt",
    "materials/maps/emp_chain/silk_chain_blendground4cbground7ab_nodetail.vmt",
}

SAFE_TEXTURE_PATTERNS = [
    "snow",
    "concrete",
    "paving",
    "water",
    "tarmac",
]

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

def has_nodetail_variant(material: str, vpk_index: set[str] | None = None) -> bool:
    """Check if a _nodetail variant exists in the VPK index or known set."""
    candidate = f"materials/{material}_nodetail.vmt"
    if vpk_index is not None:
        return candidate.lower() in vpk_index
    return candidate.lower() in KNOWN_NODETAIL_MATERIALS

def get_nodetail_variant(material: str, vpk_index: set[str] | None = None) -> str:
    """Return the nodetail variant path or a safe fallback."""
    if material.endswith("_nodetail"):
        return material
    if has_nodetail_variant(material, vpk_index):
        return f"{material}_nodetail"
    return COMPILE_SAFE_NODETAIL_MATERIAL

def _is_texture_safe_for_large_maps(texture_path: str) -> bool:
    """Check if a texture is safe for large maps based on known safe patterns.

    Textures containing safe patterns (snow, concrete, paving, water, tarmac)
    don't spawn detail props and are safe for any map size.
    """
    tex_lower = texture_path.lower()
    return any(pattern in tex_lower for pattern in SAFE_TEXTURE_PATTERNS)

def get_texture_safety_status(textures_path: str | Path | None = None) -> dict[str, bool]:
    """Return a dict mapping texture paths to whether they're safe for large maps.

    Uses pattern matching to identify safe textures (snow, concrete, water, etc.).
    Textures that spawn detail props (grass, dirt, rock blends) are marked unsafe.
    """
    if textures_path is None:
        textures_path = Path(__file__).parent.parent / "config" / "textures.json"

    textures_path = Path(textures_path)
    if not textures_path.exists():
        return {}

    import json
    with open(textures_path, "r") as f:
        data = json.load(f)

    all_textures = data.get("terrain_materials", [])

    return {
        tex: _is_texture_safe_for_large_maps(tex)
        for tex in all_textures
    }

def choose_compile_safe_material(
    requested_material: str,
    map_width: int,
    map_height: int,
    use_nodetail_texture: bool = False,
    textures_path: str | Path | None = None,
    vpk_index: set[str] | None = None,
) -> Tuple[str, Optional[str]]:
    """Return (material_name, optional_warning)."""
    map_area = map_width * map_height
    large_map_threshold = 8192 * 8192

    if use_nodetail_texture:
        if requested_material.endswith("_nodetail"):
            return requested_material, None

        if has_nodetail_variant(requested_material, vpk_index):
            return f"{requested_material}_nodetail", None

        warning = (
            f"Material '{requested_material}' has no _nodetail variant. "
            f"Falling back to '{COMPILE_SAFE_NODETAIL_MATERIAL}'. "
            "Large maps may still hit the detail prop limit."
        )
        return COMPILE_SAFE_NODETAIL_MATERIAL, warning

    if map_area > large_map_threshold:
        texture_safety = get_texture_safety_status(textures_path)

        is_unsafe = texture_safety.get(requested_material, False) is False

        if is_unsafe:
            warning = (
                f"Texture '{requested_material}' spawns detail props. On large maps, "
                "this may impact performance. Single blend material mode is active: "
                "all tiles use unified material for seamless alpha blending."
            )
            return requested_material, warning

    return requested_material, None
