from typing import Optional, Tuple
import numpy as np
from pathlib import Path
from PIL import Image

from src.material_manager import choose_compile_safe_material


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
        from src.compat_utils import scipy_zoom_equivalent

        scale_y = target_rows / grid.rows
        scale_x = target_cols / grid.cols
        normalized = scipy_zoom_equivalent(normalized, (scale_y, scale_x))

    return normalized


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
        config_model.use_smart_details,
        vpk_index=getattr(config_model, "vpk_index", None),
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
        seed=config_model.seed,
        terrain_max_height=grid.max_height(),
        skybox_ceiling=config_model.skybox_ceiling,
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
        use_smart_details=config_model.use_smart_details,
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
        custom_layout_nodes=getattr(spec, "custom_layout_nodes", None),
        custom_layout_connections=getattr(spec, "custom_layout_connections", None),
        current_theme=getattr(config_model, "current_theme", "Temperate"),
        terrain_texture_scale=getattr(config_model, "terrain_texture_scale", None),
        corridor_detail_width=getattr(config_model, "corridor_detail_width", 2048),
        transition_width=getattr(config_model, "transition_width", 1536),
        scenery_variation_noise=getattr(config_model, "scenery_variation_noise", 0.4),
        hero_prop_density=getattr(config_model, "hero_prop_density", 0.5),
        custom_tile_materials=spec.custom_tile_materials,
        custom_tile_paint_target=getattr(spec, "custom_tile_paint_target", "floor"),
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
