#!/usr/bin/env python3
"""
Compile VMF to BSP using Source SDK tools.

On Windows: Runs VBSP.exe directly
On Linux: Runs VBSP.exe via Wine

Usage:
    venv/bin/python tools/compile_vmf.py output/terrain_test.vmf
    venv/bin/python tools/compile_vmf.py output/terrain_test.vmf --sdk /path/to/Empires/bin
    venv/bin/python tools/compile_vmf.py output/terrain_test.vmf --empires-path /path/to/Empires
"""

import sys
import os
import subprocess
import argparse
import shutil
from pathlib import Path

# Import shared path detection
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.steam_paths import is_windows, find_empires_path, find_empires_bin
from src.export_utils import COMPILE_SAFE_NODETAIL_MATERIAL

DETAIL_HEAVY_TERRAIN_MATERIALS = [
    # Temperate
    "common/nature/blend_grass_mountainwall_000",
    "common/nature/blend_grass_mud_003",
    "common/nature/grass_001",
    "common/nature/grassfloor01",
    "common/nature/grassfloor12",
    # Terrain blends
    "common/terrain/blend_grass01a_dirt01a",
    "common/terrain/blend_grass01a_rock01a",
    "common/terrain/blend_grass01b_dirt01a",
    "common/terrain/blend_grass01c_dirt01a",
    "common/terrain/terrain_grass_01a",
    "common/terrain/redground2",
    "common/terrain/redground3",
    "common/terrain/redground4",
    "common/terrain/blend_red2_red3",
    "common/terrain/blend_red2_red4",
    "common/terrain/blend_red3_red4",
    "common/terrain/blend_snow01_rock01a",
    "common/terrain/blend_sand02a_rock01a",
    "common/terrain/blend_grass01c_sand01a",
    "common/terrain/blend_grass01c_sand01b",
    # Nature terrain
    "nature/terrain/blend_grass1_dirt1",
    "nature/terrain/blend_grass1_rock1",
    "nature/terrain/blend_grass1_dirt2",
    "nature/terrain/tarmac_01",
    "nature/terrain/tarmac_02",
    # Stene (dirt/grass/concrete)
    "common/stene/dirtyconcrete",
    "common/stene/grass02",
    "common/stene/grassymud",
    "common/stene/grassymud02",
    "common/stene/dirtfloor001",
    "common/stene/dirtfloor002",
    "common/stene/drygrass",
    "common/stene/grass01",
    "common/stene/grass03",
    # Desert
    "common/nature/blend_grass_sandfloor009a_000",
    "common/nature/sandfloor009a",
    "common/stene/sand01",
    "common/stene/grainysand",
    "common/stene/shittysand",
    "common/terrain/blend_grass01c_sand01a",
    "common/terrain/blend_grass01c_sand01b",
    # Snow
    "common/emp_snow/blend_snowsnow01a",
    "common/emp_snow/blend_snowsnow02b",
    "common/emp_snow/snowfloor001b",
    "common/emp_snow/snowfloor002b",
    "common/emp_snow/snowfloor003b",
    # Concrete / Industrial
    "common/concrete/pavingground01",
    "common/concrete/pavingground01b",
    "common/concrete/pavingground02a",
    "common/concrete/pavingground03a",
    "common/concrete/pavingground03b",
    # Nature blends
    "nature/blenddirtgrass001a",
    "nature/blenddirtgrass008a",
    "nature/blenddirtgrass008b",
    "nature/blendrockdirt008d",
    "nature/blendrockgrass004a",
    "nature/blendrockgrass008d",
    "nature/dirtfloor009c",
    "nature/ground/ground_dirt_pebbles",
    "nature/cliffface001b",
    "nature/cliff/stone_cliff_colorado",
    "nature/blend_colorado_cliff_dirt_pebbles",
    # Nature terrain
    "nature/water/water_ocean_beneath",
    # Nature broad
    "common/nature/mountain_wall_000",
    # Generic blends
    "generic/l01/blend_dirt01grass_01",
    "generic/l01/blend_earth_01grass_01",
    "generic/l01/l01_grass_01",
    "generic/l01/l01_grasscliff_01",
    "generic/l01/blend_sandpebbles01grass_01",
    "generic/l01/blend_rocklayered01grass_01",
    "generic/l01/blend_rocklayered01grass_01skybox",
    "generic/l04/l04_cliff_a03islegrass",
    # Johnshandy world
    "johnshandy/world/blendgrassrock",
    "johnshandy/world/grass2dirtisle",
    "johnshandy/world/isle_hilltopgrass01",
    "johnshandy/world/blendsandpebblesgrass",
    "johnshandy/world/blendsandpebbleskeefrock",
    "johnshandy/world/blendsandpebblesreef",
    "johnshandy/world/blendsandpebblesrock",
    "johnshandy/world/grass2sandpebbles02",
    "johnshandy/world/sandpebbles2sandpebbles",
    "johnshandy/world/isle_cliffsiderock01",
    # Mayama
    "mayama/overlaydirt1",
    # Wolandic
    "wolandic/blenddirtgrass01",
    "wolandic/blendsandgrass01",
    # DZ
    "dz/blend_snow_wall",
    # Silk blends
    "silk/silk_canyon_grass05a_grass09c",
    "silk/silk_canyon_grass05a_ground02a",
    "silk/silk_canyon_grass05a_rock05b",
    "silk/silk_canyon_grass08c_grass09c",
    "silk/silk_canyon_grass08c_rock05b",
    "silk/silk_canyon_grass08d_rock05b",
    "silk/silk_canyon_grass09c_rock05b",
    "silk/silk_canyon_ground08c_grass09c",
    "silk/silk_canyon_ground03a_ground02a",
    "silk/silk_canyon_ground03a_ground06b",
    "silk/silk_canyon_ground06b_rock05b",
    "silk/silk_canyon_rock04c_rock05b",
    "silk/silk_rock04a_rock05a",
    "silk/silk_rock04b_rock05a",
    "silk/silk_snow02b_concretefloor10b",
    "silk/silk_snow02b_pavingground03a",
    "silk/silk_snow02b_roadfloor06",
    "silk/silk_snow02b_snow03b_seamless",
    "silk/silk_pavingground02a",
    "silk/silk_beach01a_sand02a",
    "silk/silk_beach01a_sand02a_clouds",
    "silk/silk_beach01b_ground02a",
    "silk/silk_beach01b_ground02a_clouds",
    "silk/silk_sand01a_sand02a",
    "silk/silk_sand01a_sand02a_clouds",
    "silk/silk_sand01b_sand02b",
    "silk/silk_sand01b_sand02b_clouds",
    "silk/silk_sand03a_ground06b",
    "silk/silk_sand03a_ground06b_clouds",
    "silk/silk_sand03b_ground06a",
    "silk/silk_sand03b_ground06a_clouds",
    "silk/silk_sand03c_ground06b",
    "silk/silk_sand03c_ground06b_clouds",
    # Silk desert blends
    "silk/arid_blendcearth1rock6",
    "silk/arid_blendcearth3rock6",
    "silk/arid_blendcearth3rock6_x2",
    # Map-specific (emp_coast)
    "maps/emp_coast/blendgrass1dirt1",
    "maps/emp_coast/blendvalvemuddirt1",
    "maps/emp_coast/dirt_1",
    "maps/emp_coast/grass_1",
    # Map-specific (emp_mvalley)
    "maps/emp_mvalley/blenddirtdirt",
    "maps/emp_mvalley/blenddirtdirt2",
    "maps/emp_mvalley/blenddirtsand",
    "maps/emp_mvalley/blenddirtterra",
    "maps/emp_mvalley/blendgraveldirt3",
    "maps/emp_mvalley/redsand",
    "maps/emp_mvalley/redground2",
    "maps/emp_mvalley/redground3",
    "maps/emp_mvalley/redground4",
    # Map-specific (emp_arid)
    "maps/emp_arid/blenddirtdirt_silk",
    # Map-specific (emp_bush)
    "maps/emp_bush/silk_blenddirt01grass07",
    "maps/emp_bush/silk_blendgrass02bgrass07",
    "maps/emp_bush/silk_blendgrass04grass07",
    "maps/emp_bush/silk_blendgrassfloor002abgrass07",
    # Map-specific (emp_canyon)
    "maps/emp_canyon/silk_canyon_grass10a_grass10a",
    "maps/emp_canyon/silk_canyon_grass10a_grass10a_b",
    "maps/emp_canyon/silk_canyon_grass10a_ground09",
    "maps/emp_canyon/silk_canyon_grass10a_ground09_lessdetail",
    # Map-specific (emp_chain)
    "maps/emp_chain/silk_chain_blendgrass5bbground2db",
    "maps/emp_chain/silk_chain_blendgrass5bbground2db_detail",
    "maps/emp_chain/silk_chain_blendgrass5bbground5db",
    "maps/emp_chain/silk_chain_blendgrass5bbground5db_detail",
    "maps/emp_chain/silk_chain_blendgrass5bbground5db_clouds_detail",
    "maps/emp_chain/silk_chain_blendgrass5bbground7ab",
    "maps/emp_chain/silk_chain_blendgrass5bbground7ab_detail",
    "maps/emp_chain/silk_chain_blendgrass5bbground7ab_clouds_detail",
    "maps/emp_chain/silk_chain_blendgrass5bbground8ab_clouds_detail",
    "maps/emp_chain/silk_chain_blendmoss1a4xground5db_detail",
    "maps/emp_chain/silk_chain_blendmoss1a4xground5db_clouds_detail",
    "maps/emp_chain/silk_chain_blendrock9bbgrass5bb",
    "maps/emp_chain/silk_chain_blendrock9bbmoss2a4x",
    "maps/emp_chain/silk_chain_blendrock9bbground2db",
    "maps/emp_chain/silk_chain_blendrock9bbground5db",
    "maps/emp_chain/silk_chain_blendrock9bbground7ab",
    "maps/emp_chain/silk_chain_blendrock9bbrock10b",
    "maps/emp_chain/silk_chain_blendrock9bbsnow1a",
    "maps/emp_chain/silk_chain_blendground4cbground7ab_clouds_detail",
    "maps/emp_chain/silk_chain_blendgrass5bbground8ab_detail",
    # Rubble
    "common/rubble/blend_rubblefloor04_rubblefloor05",
    # Nature tree/foliage (not terrain, but used on displacements in some tiles)
    "common/nature/treebark01",
    "common/nature/treebark02",
    "common/nature/treebark05",
    "common/nature/treebark05b",
    # Legacy Empires texture reference
    "nature/terrain/blend_dirt_grass_dmz_sscale",
]


def force_nodetail_materials(vmf_path: str) -> int:
    """
    Rewrite known terrain blend materials to a nodetail-safe material.
    Returns replacement count.
    """
    path = Path(vmf_path)
    content = path.read_text(encoding="utf-8", errors="ignore")
    replacement_count = 0
    for mat in DETAIL_HEAVY_TERRAIN_MATERIALS:
        old = f'"material" "{mat}"'
        new = f'"material" "{COMPILE_SAFE_NODETAIL_MATERIAL}"'
        occurrences = content.count(old)
        if occurrences > 0:
            content = content.replace(old, new)
            replacement_count += occurrences
    path.write_text(content, encoding="utf-8")
    return replacement_count


def compile_vmf(
    vmf_path: str,
    sdk_path: str = "",
    empires_path: str = "",
    nodetail: bool = False,
    auto_copy: bool = True,
    custom_output: str = "",
) -> bool:
    """Compile VMF to BSP using VBSP via wine."""
    vmf_path = Path(vmf_path).resolve()
    if not vmf_path.exists():
        print(f"Error: VMF not found: {vmf_path}")
        return False

    vmf_name = vmf_path.name
    # Project root is the parent of mapsrc/
    project_root = vmf_path.parent.parent
    mapsrc_dir = project_root / "mapsrc"
    maps_dir = project_root / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)

    bsp_path = maps_dir / f"{vmf_path.stem}.bsp"

    if not sdk_path:
        if empires_path:
            # empires_path is the "empires" directory inside the Empires game directory
            # e.g., /path/to/Empires/empires
            # The bin directory is at /path/to/Empires/bin
            empires_game_dir = os.path.dirname(os.path.normpath(empires_path))
            sdk_path = os.path.join(empires_game_dir, "bin")
        else:
            sdk_path = find_empires_bin()

    if not sdk_path or not os.path.exists(sdk_path):
        print("Error: Empires bin not found.")
        print("Please specify path with --sdk or --empires-path")
        return False

    if not empires_path:
        empires_path = find_empires_path()

    if auto_copy and empires_path:
        vmf_dest_dir = os.path.join(empires_path, "maps", "prefabs")
        bsp_dest_dir = os.path.join(empires_path, "download", "maps")
        bsp_primary_dest_dir = os.path.join(empires_path, "maps")
    else:
        vmf_dest_dir = None
        bsp_dest_dir = None
        bsp_primary_dest_dir = None

    vbsp_exe = os.path.join(sdk_path, "vbsp.exe")
    if not os.path.exists(vbsp_exe):
        print(f"Error: VBSP not found at: {vbsp_exe}")
        return False

    print(f"Compiling: {vmf_path.name}")
    print(f"VBSP: {vbsp_exe}")
    print("-" * 60)

    temp_vmf = os.path.join(sdk_path, vmf_name)
    shutil.copy2(str(vmf_path), temp_vmf)
    if nodetail:
        replaced = force_nodetail_materials(temp_vmf)
        if replaced > 0:
            print(
                "Nodetail material override enabled:"
                f" replaced {replaced} terrain material reference(s)."
            )

    def build_cmd(use_nodetail: bool) -> list:
        if is_windows():
            cmd = [vbsp_exe, "-game", empires_path]
        else:
            cmd = ["wine", "vbsp.exe", "-game", empires_path]
        if use_nodetail:
            cmd.append("-nodetail")
        cmd.append(vmf_name)
        return cmd

    def print_failure_hint(combined_output: str) -> None:
        if "bounds out of range" in combined_output:
            print(
                "Tip: Map/skybox extents exceeded Hammer coordinate limits. "
                "Reduce map size (Tiles X/Y or Tile Size)."
            )
        elif "HashVec: point outside valid range" in combined_output:
            print(
                "Tip: Map is too close to world limits (±16384). "
                "Reduce Tiles X/Y or Tile Size."
            )
        elif "Too many detail props emitted" in combined_output:
            print("Tip: Enable 'Use nodetail texture' in Settings.")
        else:
            print("Tip: Check geometry and entity placement near map bounds.")

    try:
        result = subprocess.run(
            build_cmd(nodetail),
            cwd=sdk_path,
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)

        print("-" * 60)

        if result.returncode != 0:
            combined_output = f"{result.stdout}\n{result.stderr}"
            if (not nodetail) and ("Too many detail props emitted" in combined_output):
                print("Detail prop limit hit. Retrying compile with nodetail fallback...")
                replaced = force_nodetail_materials(temp_vmf)
                if replaced > 0:
                    print(
                        "Nodetail material override enabled:"
                        f" replaced {replaced} terrain material reference(s)."
                    )
                retry_result = subprocess.run(
                    build_cmd(True),
                    cwd=sdk_path,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                if retry_result.stdout:
                    print(retry_result.stdout)
                if retry_result.stderr:
                    print("STDERR:", retry_result.stderr)
                print("-" * 60)
                if retry_result.returncode != 0:
                    print("Compile failed.")
                    combined_output = f"{retry_result.stdout}\n{retry_result.stderr}"
                    print_failure_hint(combined_output)
                    print(f"Error output:\n{retry_result.stdout}\n{retry_result.stderr}")
                    return False
            else:
                print("Compile failed.")
                print_failure_hint(combined_output)
                print(f"Error output:\n{result.stdout}\n{result.stderr}")
                return False

        generated_bsp = os.path.join(sdk_path, vmf_name.replace(".vmf", ".bsp"))
        if os.path.exists(generated_bsp):
            shutil.copy2(generated_bsp, bsp_path)
            os.remove(generated_bsp)
            print(f"BSP created: {bsp_path}")
            print(f"Size: {bsp_path.stat().st_size / 1024 / 1024:.2f} MB")

            if auto_copy and vmf_dest_dir and bsp_dest_dir:
                os.makedirs(vmf_dest_dir, exist_ok=True)
                os.makedirs(bsp_dest_dir, exist_ok=True)
                if bsp_primary_dest_dir:
                    os.makedirs(bsp_primary_dest_dir, exist_ok=True)
                final_vmf = os.path.join(vmf_dest_dir, vmf_name)
                final_bsp_download = os.path.join(bsp_dest_dir, vmf_path.stem + ".bsp")
                shutil.copy2(str(vmf_path), final_vmf)
                shutil.copy2(bsp_path, final_bsp_download)
                print(f"VMF copied to: {final_vmf}")

                if bsp_primary_dest_dir:
                    final_bsp_primary = os.path.join(
                        bsp_primary_dest_dir, vmf_path.stem + ".bsp"
                    )
                    shutil.copy2(bsp_path, final_bsp_primary)
                    print(f"BSP copied to: {final_bsp_primary}")
                print(f"BSP copied to: {final_bsp_download}")

                # Also copy the resource .txt script if it exists
                txt_path = project_root / "resource" / "maps" / f"{vmf_path.stem}.txt"
                if txt_path.exists():
                    txt_dest_dir = os.path.join(empires_path, "resource", "maps")
                    os.makedirs(txt_dest_dir, exist_ok=True)
                    final_txt = os.path.join(txt_dest_dir, f"{vmf_path.stem}.txt")
                    shutil.copy2(str(txt_path), final_txt)
                    print(f"TXT script copied to: {final_txt}")

                    # Also copy to download/resource/maps
                    txt_download_dir = os.path.join(empires_path, "download", "resource", "maps")
                    os.makedirs(txt_download_dir, exist_ok=True)
                    final_txt_download = os.path.join(txt_download_dir, f"{vmf_path.stem}.txt")
                    shutil.copy2(str(txt_path), final_txt_download)
                    print(f"TXT script copied to download: {final_txt_download}")

                # Copy minimap VMT and VTF to materials
                vmt_dest_dir = os.path.join(empires_path, "materials", "maps")
                os.makedirs(vmt_dest_dir, exist_ok=True)

                vmt_src = project_root / "materials" / "maps" / f"{vmf_path.stem}.vmt"
                if vmt_src.exists():
                    final_vmt = os.path.join(vmt_dest_dir, f"{vmf_path.stem}.vmt")
                    shutil.copy2(str(vmt_src), final_vmt)
                    print(f"VMT minimap material copied to: {final_vmt}")

                    # Also copy to download/materials/maps
                    vmt_download_dir = os.path.join(empires_path, "download", "materials", "maps")
                    os.makedirs(vmt_download_dir, exist_ok=True)
                    final_vmt_download = os.path.join(vmt_download_dir, f"{vmf_path.stem}.vmt")
                    shutil.copy2(str(vmt_src), final_vmt_download)
                    print(f"VMT copied to download: {final_vmt_download}")

                vtf_src = project_root / "materials" / "maps" / f"{vmf_path.stem}.vtf"
                if vtf_src.exists():
                    final_vtf = os.path.join(vmt_dest_dir, f"{vmf_path.stem}.vtf")
                    shutil.copy2(str(vtf_src), final_vtf)
                    print(f"VTF minimap texture copied to: {final_vtf}")

                    # Also copy to download/materials/maps
                    vtf_download_dir = os.path.join(empires_path, "download", "materials", "maps")
                    os.makedirs(vtf_download_dir, exist_ok=True)
                    final_vtf_download = os.path.join(vtf_download_dir, f"{vmf_path.stem}.vtf")
                    shutil.copy2(str(vtf_src), final_vtf_download)
                    print(f"VTF copied to download: {final_vtf_download}")

            elif not auto_copy and custom_output:
                custom_path = Path(custom_output)
                if custom_path.exists():
                    # If the custom folder doesn't look like a standardized project root, 
                    # create the maps/ folder inside it.
                    # Actually, if the user provided a custom_output, we should just mirror 
                    # the project_root into it if it's the same structure, 
                    # but here we are just copying the results of compilation.
                    
                    # Copy BSP to custom_folder/maps/
                    custom_maps_dir = custom_path / "maps"
                    custom_maps_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(bsp_path, custom_maps_dir / f"{vmf_path.stem}.bsp")
                    print(f"BSP copied to custom folder: {custom_maps_dir}")

                    # Mirror other assets if they exist in project_root
                    for subdir in ["mapsrc", "materials", "resource"]:
                        src_dir = project_root / subdir
                        if src_dir.exists():
                            dest_dir = custom_path / subdir
                            if dest_dir.exists():
                                # Use a safe copy that doesn't overwrite the whole dir if it exists
                                for item in src_dir.rglob("*"):
                                    if item.is_file():
                                        rel_path = item.relative_to(src_dir)
                                        target = dest_dir / rel_path
                                        target.parent.mkdir(parents=True, exist_ok=True)
                                        shutil.copy2(item, target)
                            else:
                                shutil.copytree(src_dir, dest_dir)
                    print(f"Assets mirrored to custom folder: {custom_path}")

            return True
        else:
            print("Compile failed - BSP not found.")
            return False

    except subprocess.TimeoutExpired:
        print("Error: Compile timed out (5 minutes)")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False
    finally:
        if os.path.exists(temp_vmf):
            os.remove(temp_vmf)


def main():
    parser = argparse.ArgumentParser(description="Compile VMF to BSP")
    parser.add_argument("vmf", help="Path to VMF file")
    parser.add_argument("--sdk", help="Path to Empires bin directory")
    parser.add_argument("--empires-path", help="Path to Empires root directory")
    parser.add_argument(
        "--nodetail", action="store_true", help="Skip detail props (for large maps)"
    )
    parser.add_argument(
        "--no-auto-copy", action="store_true", help="Disable auto copying to Empires folder"
    )
    parser.add_argument(
        "--custom-output", help="Path to custom output folder for VMF, BSP, and TXT"
    )

    args = parser.parse_args()

    success = compile_vmf(args.vmf, args.sdk, args.empires_path, args.nodetail, not args.no_auto_copy, args.custom_output)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
