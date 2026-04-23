#!/usr/bin/env python3
"""
Generate VMF from the new organic terrain pipeline (fBm + hydraulic erosion).

Bridges terrain_pipeline.py (height generation) with vmf_gen.py (VMF output).

Usage:
    venv/bin/python tools/generate_organic_vmf.py
    venv/bin/python tools/generate_organic_vmf.py --seed 42 --tiles-x 8 --tiles-y 8
    venv/bin/python tools/generate_organic_vmf.py --erosion-iterations 100000
"""

import sys
import numpy as np
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from terrain_spec import TerrainSpec, HeightGrid
from terrain_pipeline import run_pipeline
from vmf_gen import (
    PipelineSpec,
    DisplacementVMF,
    DEFAULT_SAFE_SKYBOX,
    MAX_MAP_DISPINFO,
)


def choose_compile_safe_material(
    requested_material: str, map_width: int, map_height: int
) -> str:
    """Return the requested material (nodetail is now user-controlled via settings)."""
    return requested_material


def heightgrid_to_heightmap(
    grid: HeightGrid, target_rows: int = 0, target_cols: int = 0
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


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate organic terrain VMF (fBm + erosion)"
    )
    parser.add_argument(
        "-o",
        "--output",
        default="../output/organic_terrain.vmf",
        help="Output VMF path",
    )
    parser.add_argument(
        "-x", "--tiles-x", type=int, default=8, help="Displacement tiles X"
    )
    parser.add_argument(
        "-y", "--tiles-y", type=int, default=8, help="Displacement tiles Y"
    )
    parser.add_argument(
        "-s", "--tile-size", type=int, default=512, help="Tile size in world units"
    )
    parser.add_argument(
        "-H",
        "--max-height",
        type=int,
        default=None,
        help="Max terrain height (auto: tiles*tile_size/8)",
    )
    parser.add_argument(
        "-p",
        "--power",
        type=int,
        default=3,
        choices=[2, 3, 4],
        help="Displacement power",
    )
    parser.add_argument(
        "-m",
        "--material",
        default="common/nature/blend_grass_mountainwall_000",
        help="Terrain material",
    )
    parser.add_argument("--seed", type=int, default=12345, help="Noise seed")
    parser.add_argument("--octaves", type=int, default=4, help="fBm octaves")
    parser.add_argument(
        "--erosion-iterations", type=int, default=50000, help="Erosion droplet count"
    )
    parser.add_argument(
        "--erosion-lifetime", type=int, default=30, help="Droplet lifetime"
    )
    parser.add_argument(
        "--skip-erosion", action="store_true", help="Skip hydraulic erosion"
    )
    parser.add_argument(
        "--export-heightmap",
        action="store_true",
        help="Save intermediate heightmap PNG",
    )
    parser.add_argument(
        "--no-enhanced",
        action="store_true",
        help="Disable enhanced entity spawning",
    )
    parser.add_argument(
        "--skybox",
        default=DEFAULT_SAFE_SKYBOX,
        help="Skybox name (defaults to a known-safe Empires skybox)",
    )

    args = parser.parse_args()

    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    rules_path = Path(__file__).parent.parent / "map_rules.json"
    if rules_path.exists():
        import json

        with open(rules_path) as f:
            rules = json.load(f)
        target_width = rules["map_dimensions"]["map_bbox"]["width"]["max"]
        target_height = rules["map_dimensions"]["map_bbox"]["height"]["max"]
    else:
        target_width = 16384
        target_height = 16384

    # Keep a compile-safe margin from ±16384 world bounds.
    max_map_size = 16320
    target_width = min(target_width, max_map_size)
    target_height = min(target_height, max_map_size)

    grid_size = (2**args.power) + 1
    tile_size = args.tile_size
    max_tiles = max_map_size // tile_size
    calc_tiles_x = int(target_width / tile_size)
    calc_tiles_y = int(target_height / tile_size)

    if args.tiles_x == 8 and args.tiles_y == 8:
        tiles_x = calc_tiles_x
        tiles_y = calc_tiles_y
    else:
        tiles_x = min(args.tiles_x, max_tiles)
        tiles_y = min(args.tiles_y, max_tiles)
    disp_count = tiles_x * tiles_y
    if disp_count > MAX_MAP_DISPINFO:
        print(
            f"Error: too many displacement tiles ({disp_count} > {MAX_MAP_DISPINFO}). "
            "Reduce --tiles-x/--tiles-y or increase --tile-size."
        )
        sys.exit(2)

    vertex_cols = tiles_x * (grid_size - 1) + 1
    vertex_rows = tiles_y * (grid_size - 1) + 1

    calculated_max_height = (
        args.max_height if args.max_height else tile_size * tiles_y // 16
    )
    map_width = tiles_x * tile_size
    map_height = tiles_y * tile_size
    compile_safe_material = choose_compile_safe_material(
        args.material, map_width, map_height
    )

    spec = TerrainSpec(
        origin_x=0,
        origin_y=0,
        size_x=tiles_x * tile_size,
        size_y=tiles_y * tile_size,
        cell_size=tile_size,
        displacement_power=args.power,
        seed=args.seed,
        max_slope_step=64,
        height_quantization=1,
        noise_octaves=args.octaves,
        erosion_iterations=0 if args.skip_erosion else args.erosion_iterations,
        erosion_droplet_lifetime=args.erosion_lifetime,
        terrain_max_height=calculated_max_height,
        material=compile_safe_material,
        underlay_material="TOOLS/TOOLSSKIP",
        underlay_height=128,
    )

    print("Organic Terrain Generator")
    print(f"  Map: {spec.size_x}x{spec.size_y}, tiles={tiles_x}x{tiles_y}")
    print(f"  Grid: {vertex_cols}x{vertex_rows} vertices, power={args.power}")
    print(f"  Seed: {args.seed}, octaves: {args.octaves}")
    print(f"  Max height: {calculated_max_height} units")
    print(
        f"  Erosion: {'skipped' if args.skip_erosion else f'{args.erosion_iterations} droplets, lifetime={args.erosion_lifetime}'}"
    )
    print(f"  Enhanced spawning: {'enabled' if not args.no_enhanced else 'disabled'}")
    print()

    map_name = Path(args.output).stem
    result = run_pipeline(spec, map_name=map_name, output_dir=str(output_dir))

    if result["errors"]:
        print("\nPipeline errors:")
        for e in result["errors"]:
            print(f"  - {e}")
        sys.exit(1)

    grid = result["grid"]
    heightmap = heightgrid_to_heightmap(
        grid, target_rows=vertex_rows, target_cols=vertex_cols
    )

    if args.export_heightmap:
        hm_path = output_dir / "organic_terrain_heightmap.png"
        img = Image.fromarray((heightmap * 255).astype(np.uint8), mode="L")
        img.save(hm_path)
        print(f"\nHeightmap saved: {hm_path}")

    hm_for_vmf = (heightmap * 255).astype(np.uint8)
    hm_img = Image.fromarray(hm_for_vmf, mode="L")
    hm_path = output_dir / "organic_terrain_temp.png"
    hm_img.save(hm_path)

    vmf_spec = PipelineSpec(
        map_name=Path(args.output).stem,
        heightmap_path=str(hm_path),
        terrain_max_height=calculated_max_height,
        terrain_actual_max=grid.max_height(),
        terrain_tile_size=tile_size,
        terrain_power=args.power,
        terrain_material=compile_safe_material,
        skybox=args.skybox,
        terrain_tiles_x=tiles_x,
        terrain_tiles_y=tiles_y,
        output_dir=str(output_dir),
        use_enhanced_spawning=not args.no_enhanced,
    )
    print(
        f"DEBUG: Creating PipelineSpec with terrain_actual_max={vmf_spec.terrain_actual_max}"
    )

    vmf_gen = DisplacementVMF(vmf_spec)
    print(
        f"DEBUG: After DisplacementVMF: terrain_actual_max={vmf_gen.spec.terrain_actual_max}"
    )
    vmf_gen.load_heightmap(str(hm_path), auto_resize=False)

    vmf_path = output_dir / Path(args.output).name
    vmf_gen.generate_vmf(str(vmf_path))

    map_name = vmf_path.stem
    origin_x = -(map_width // 2)
    origin_y = -(map_height // 2)
    resource_content = f'''"{map_name}"
{{
	"image"		"maps/{map_name}"

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

	"nf_description" "Organic procedural terrain - fBm + hydraulic erosion."
	"nf_objective" "Build refineries to gain resources and destroy the enemy command vehicle."
	"imp_description" "Organic procedural terrain - fBm + hydraulic erosion."
	"imp_objective" "Build refineries to gain resources and destroy the enemy command vehicle."
}}
'''
    resource_file = output_dir / f"{map_name}.txt"
    resource_file.write_text(resource_content)
    print(f"Resource file saved: {resource_file}")

    hm_path.unlink(missing_ok=True)

    print(f"\nDone! VMF saved: {vmf_path}")


if __name__ == "__main__":
    main()
