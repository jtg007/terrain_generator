from typing import Optional, Tuple
import numpy as np
from pathlib import Path
from PIL import Image

COMPILE_SAFE_NODETAIL_MATERIAL = "common/terrain/blend_grass01a_dirt01a_nodetail"


def heightgrid_to_heightmap(
    grid, target_rows: int = 0, target_cols: int = 0
) -> np.ndarray:
    min_h = grid.min_height()
    max_h = grid.max_height()
    h_range = max_h - min_h
    if h_range < 1e-6:
        return np.zeros((grid.rows, grid.cols), dtype=np.float32)

    normalized = np.array(
        [
            [(grid.heights[r][c] - min_h) / h_range for c in range(grid.cols)]
            for r in range(grid.rows)
        ],
        dtype=np.float32,
    )
    normalized = np.clip(normalized, 0.0, 1.0)

    if target_rows > grid.rows or target_cols > grid.cols:
        from scipy.ndimage import zoom

        scale_y = target_rows / grid.rows
        scale_x = target_cols / grid.cols
        normalized = zoom(normalized, (scale_y, scale_x), order=1)

    return normalized


def choose_compile_safe_material(
    requested_material: str,
    map_width: int,
    map_height: int,
    use_nodetail_texture: bool = False,
) -> Tuple[str, Optional[str]]:
    """Return (material_name, optional_warning)."""
    if use_nodetail_texture:
        # Default materials from config and spec
        defaults = [
            "common/nature/blend_grass_mountainwall_000",
            "nature/terrain/blend_dirt_grass_dmz_sscale",
            "common/stene/grass02",
        ]
        if requested_material in defaults:
            return COMPILE_SAFE_NODETAIL_MATERIAL, None

        if requested_material.endswith("_nodetail"):
            return requested_material, None

        # User picked a custom texture but "nodetail" is checked.
        # We allow it, but provide a warning.
        warning = (
            f"Custom material '{requested_material}' is used without a nodetail version. "
            "Large maps may hit the detail prop limit."
        )
        return requested_material, warning

    return requested_material, None


from src.vmf_gen import PipelineSpec, DisplacementVMF


def get_versioned_path(base_dir: Path, name: str) -> Path:
    """Returns a versioned Path like 'base_dir/name', 'base_dir/name_01', etc."""
    path = base_dir / name
    if not path.exists():
        return path

    counter = 1
    while True:
        versioned_name = f"{name}_{counter:02d}"
        path = base_dir / versioned_name
        if not path.exists():
            return path
        counter += 1


def export_vmf(
    grid, config_model, project_root: Path, output_filename: str
) -> Tuple[str, Optional[str]]:
    """Exports the given height grid and config to a VMF file, returns (success_msg, warning_msg)."""
    spec = config_model.make_spec()
    tile_size = config_model.cell_size
    displacement_power = config_model.displacement_power

    # Create subdirectories
    mapsrc_dir = project_root / "mapsrc"
    mapsrc_dir.mkdir(parents=True, exist_ok=True)
    resource_dir = project_root / "resource" / "maps"
    resource_dir.mkdir(parents=True, exist_ok=True)

    grid_size = (2**displacement_power) + 1
    tiles_x = spec.size_x // tile_size
    tiles_y = spec.size_y // tile_size
    map_width = tiles_x * tile_size
    map_height = tiles_y * tile_size
    compile_safe_material, warning = choose_compile_safe_material(
        config_model.terrain_material,
        map_width,
        map_height,
        config_model.use_nodetail_texture,
    )

    vertex_cols = tiles_x * (grid_size - 1) + 1
    vertex_rows = tiles_y * (grid_size - 1) + 1

    heightmap = heightgrid_to_heightmap(grid, vertex_rows, vertex_cols)

    hm_array = (heightmap * 255).astype(np.uint8)

    hm_img = Image.fromarray(hm_array, mode="L")
    hm_path = mapsrc_dir / f"{output_filename}_temp.png"
    hm_img.save(hm_path)

    calculated_max_height = config_model.height_scale

    vmf_spec = PipelineSpec(
        map_name=output_filename,
        heightmap_path=str(hm_path),
        terrain_max_height=grid.max_height(),
        terrain_actual_max=grid.max_height(),
        terrain_tile_size=tile_size,
        terrain_power=config_model.displacement_power,
        terrain_material=compile_safe_material,
        skybox=config_model.skybox,
        terrain_tiles_x=tiles_x,
        terrain_tiles_y=tiles_y,
        output_dir=str(mapsrc_dir),
        rules_file="map_rules.json",
        use_enhanced_spawning=True,
        base_clear_radius=config_model.base_clear_radius,
        base_flatness=config_model.base_flatness,
        disable_commander=config_model.disable_commander,
        disable_buildings=config_model.disable_buildings,
        disable_resource_nodes=config_model.disable_resource_nodes,
        minimal_map=config_model.minimal_map,
        terrain_only=config_model.terrain_only,
        custom_imp_base_x=config_model.custom_imp_base_x,
        custom_imp_base_y=config_model.custom_imp_base_y,
        custom_nf_base_x=config_model.custom_nf_base_x,
        custom_nf_base_y=config_model.custom_nf_base_y,
        custom_resources=config_model.custom_resources,
        manual_terrain=config_model.manual_terrain,
    )

    vmf_gen = DisplacementVMF(vmf_spec)
    vmf_gen.load_heightmap(str(hm_path), auto_resize=False)

    vmf_path = mapsrc_dir / f"{output_filename}.vmf"
    vmf_gen.generate_vmf(str(vmf_path))

    origin_x = -(map_width // 2)
    origin_y = -(map_height // 2)
    resource_content = f""""{output_filename}"
{{
	"image"		"maps/{output_filename}"

	"min_image_x"	"0"
	"min_image_y"	"0"

	"max_image_x"	"1024"
	"max_image_y"	"1024"

	"min_bounds_x"	"{origin_x}"
	"min_bounds_y"	"{origin_y + map_height}"

	"max_bounds_x"	"{origin_x + map_width}"
	"max_bounds_y"	"{origin_y}"

	"sector_width"	"512"
	"sector_height"	"512"

	"min_zoom"	"1"
	"max_zoom"	"0.25"

	"nf_description" "GUI generated terrain."
	"nf_objective" "Build refineries to gain resources and destroy the enemy command vehicle."
	"imp_description" "GUI generated terrain."
	"imp_objective" "Build refineries to gain resources and destroy the enemy command vehicle."
}}
"""
    resource_file = resource_dir / f"{output_filename}.txt"
    resource_file.write_text(resource_content)

    hm_path.unlink(missing_ok=True)

    message = f"VMF saved: {vmf_path}"
    return message, warning
