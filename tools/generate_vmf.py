#!/usr/bin/env python3
"""
VMF Generator - Main entry point for generating terrain VMF files.

Usage:
    python generate_vmf.py [heightmap] [options]

Examples:
    python generate_vmf.py heightmap.png
    python generate_vmf.py heightmap.png -o output/map.vmf -x 8 -y 8
"""

import numpy as np
from PIL import Image
from pathlib import Path
import sys

# Add project root to path to allow absolute imports from src. and tools.
# REQUIRED for direct invocation since tools/ is a package.
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.vmf_gen import PipelineSpec, DisplacementVMF  # noqa: E402


def create_test_heightmap():
    """Create a heightmap with varied terrain - flat plains and hills."""
    size = 257
    hm = np.zeros((size, size), dtype=np.float32)

    for y in range(size):
        for x in range(size):
            nx = x / size
            ny = y / size

            base = 0.0

            ridge_x = abs(nx - 0.3)
            ridge_y = abs(ny - 0.7)
            if ridge_x < 0.15 and ridge_y < 0.3:
                base = max(0, 1 - ridge_x / 0.15) * 0.8

            center_dist = np.sqrt((nx - 0.5) ** 2 + (ny - 0.5) ** 2)
            if center_dist < 0.15:
                base = max(base, (1 - center_dist / 0.15) * 0.5)

            h = base
            h += np.sin(x * 0.1) * np.cos(y * 0.1) * 0.15
            h += np.sin(x * 0.05 + 1) * np.cos(y * 0.08) * 0.2

            h = max(0, h)
            hm[y, x] = np.clip(h, 0, 1)

    return hm


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Source Engine Terrain VMF Generator")
    parser.add_argument("heightmap", nargs="?", help="Path to heightmap PNG")
    parser.add_argument(
        "-o", "--output", default="../output/terrain.vmf", help="Output VMF path"
    )
    parser.add_argument("-x", "--tiles-x", type=int, default=32, help="Tiles X")
    parser.add_argument("-y", "--tiles-y", type=int, default=32, help="Tiles Y")
    parser.add_argument("-s", "--tile-size", type=int, default=256, help="Tile size")
    parser.add_argument("-H", "--max-height", type=int, default=256, help="Max height")
    parser.add_argument(
        "-p", "--power", type=int, default=3, choices=[2, 3, 4], help="Disp power"
    )
    parser.add_argument(
        "-m", "--material", default="common/stene/grass02", help="Material"
    )
    parser.add_argument(
        "--test", action="store_true", help="Generate test heightmap first"
    )
    parser.add_argument(
        "--compile", action="store_true", help="Compile to BSP after generating"
    )

    args = parser.parse_args()

    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.test or not args.heightmap:
        print("Creating test heightmap...")
        hm = create_test_heightmap()
        hm_path = output_dir / "test_terrain_hm.png"
        hm_img = Image.fromarray((hm * 255).astype(np.uint8), mode="L")
        hm_img.save(hm_path)
        print(f"Saved: {hm_path}")
        args.heightmap = str(hm_path)

    print("\nGenerating VMF...")
    print(f"  Heightmap: {args.heightmap}")
    print(f"  Tiles: {args.tiles_x}x{args.tiles_y}")
    print(f"  Tile size: {args.tile_size}")
    print(f"  Max height: {args.max_height}")
    print(f"  Power: {args.power}")

    spec = PipelineSpec(
        map_name=Path(args.output).stem,
        heightmap_path=args.heightmap,
        terrain_max_height=args.max_height,
        terrain_tile_size=args.tile_size,
        terrain_power=args.power,
        terrain_material=args.material,
        terrain_tiles_x=args.tiles_x,
        terrain_tiles_y=args.tiles_y,
        output_dir=str(output_dir),
    )

    vmf_gen = DisplacementVMF(spec)
    vmf_gen.load_heightmap(args.heightmap, auto_resize=False)

    vmf_path = Path(args.output)
    vmf_gen.generate_vmf(str(vmf_path))

    map_name = vmf_path.stem
    map_width = args.tiles_x * args.tile_size
    map_height = args.tiles_y * args.tile_size

    resource_file = vmf_path.parent / f"{map_name}.txt"
    resource_content = f'''"{map_name}"
{{
	"image"		"maps/{map_name}"

	"min_image_x"	"0"
	"min_image_y"	"0"

	"max_image_x"	"1024"
	"max_image_y"	"1024"
	
	"min_bounds_x"	"0"
	"min_bounds_y"	"0"

	"max_bounds_x"	"{map_width}"
	"max_bounds_y"	"{map_height}"

	"sector_width"	"512"
	"sector_height"	"512"

	"min_zoom"	"1"
	"max_zoom"	"0.25"

	"nf_description" "Northern Faction - Defend your base and capture objectives."
	"nf_objective" "Objective: Build refineries to gain resources and destroy the enemy command vehicle."
	"imp_description" "Imperial Forces - Attack and capture strategic points."
	"imp_objective" "Objective: Build refineries to gain resources and destroy the enemy command vehicle."
}}
'''
    resource_file.write_text(resource_content)
    print(f"Resource file saved: {resource_file}")

    print(f"\nVMF saved: {vmf_path}")

    if args.compile:
        compile_vmfs(vmf_path, args)


def compile_vmfs(vmf_path: Path, args) -> None:
    """Compile VMF to BSP using Source SDK tools via Proton."""
    import subprocess
    import shutil
    import os

    map_name = vmf_path.stem
    vmf_dir = vmf_path.parent

    # Import shared path detection
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from steam_paths import is_windows, find_empires_path, find_empires_bin

    compiler_bin = find_empires_bin()
    empires_dir = find_empires_path()

    if not compiler_bin:
        print("Error: Empires bin directory not found.")
        print("Please install Empires via Steam or specify the path manually.")
        return

    if not empires_dir:
        print("Error: Empires directory not found.")
        print("Please install Empires via Steam or specify the path manually.")
        return

    vbsp = os.path.join(compiler_bin, "vbsp.exe")
    if not os.path.exists(vbsp):
        print(f"Error: VBSP not found at {vbsp}")
        return

    print("\n=== Compiling with VBSP ===")
    print(f"Empires: {empires_dir}")
    print(f"VBSP: {vbsp}")

    temp_vmf = os.path.join(compiler_bin, f"{map_name}.vmf")
    shutil.copy2(str(vmf_path), temp_vmf)

    if is_windows():
        cmd = [vbsp, "-game", "..\\empires", f"{map_name}.vmf"]
    else:
        cmd = ["wine", "vbsp.exe", "-game", "../empires", f"{map_name}.vmf"]

    result = subprocess.run(
        cmd,
        cwd=compiler_bin,
        capture_output=True,
        text=True,
        timeout=300,
    )
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)

    if result.returncode != 0:
        print("VBSP failed with return code:", result.returncode)
        if os.path.exists(temp_vmf):
            os.remove(temp_vmf)
        return

    generated_bsp = os.path.join(compiler_bin, f"{map_name}.bsp")
    if not os.path.exists(generated_bsp):
        print("BSP not created!")
        if os.path.exists(temp_vmf):
            os.remove(temp_vmf)
        return

    bsp_path = vmf_dir / f"{map_name}.bsp"
    shutil.copy2(generated_bsp, bsp_path)
    os.remove(generated_bsp)
    if os.path.exists(temp_vmf):
        os.remove(temp_vmf)
    print(f"BSP saved: {bsp_path}")

    download_maps = os.path.join(empires_dir, "download", "maps")
    os.makedirs(download_maps, exist_ok=True)
    shutil.copy(bsp_path, os.path.join(download_maps, f"{map_name}.bsp"))

    resource_dir_path = os.path.join(empires_dir, "resource", "maps")
    os.makedirs(resource_dir_path, exist_ok=True)

    res_content = f'''"{map_name}"
{{
	"image"		"maps/{map_name}"

	"min_image_x"	"0"
	"min_image_y"	"0"

	"max_image_x"	"1024"
	"max_image_y"	"1024"
	
	"min_bounds_x"	"0"
	"min_bounds_y"	"0"

	"max_bounds_x"	"0"
	"max_bounds_y"	"0"

	"sector_width"	"512"
	"sector_height"	"512"

	"min_zoom"	"1"
	"max_zoom"	"0.25"

	"nf_description" "Procedurally generated terrain."
	"nf_objective" "Destroy enemy command vehicle."
	"imp_description" "Procedurally generated terrain."
	"imp_objective" "Destroy enemy command vehicle."
}}
'''
    with open(os.path.join(resource_dir_path, f"{map_name}.txt"), "w") as f:
        f.write(res_content)

    vmt_dest_dir = os.path.join(empires_dir, "materials", "maps")
    os.makedirs(vmt_dest_dir, exist_ok=True)
    vmt_content = f""""UnlitGeneric"
{{
	"$baseTexture" "maps/{map_name}"
	"$vertexcolor" 1
	"$vertexalpha" 1
	"$no_fullbright" 1
	"$ignorez" 1
	"%keywords" "empires"
}}"""
    with open(os.path.join(vmt_dest_dir, f"{map_name}.vmt"), "w") as f:
        f.write(vmt_content)

    print(f"Installed to Empires: {download_maps}/{map_name}.bsp")


if __name__ == "__main__":
    main()
