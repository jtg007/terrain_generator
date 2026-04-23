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
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from steam_paths import is_windows, find_empires_path, find_empires_bin

COMPILE_SAFE_NODETAIL_MATERIAL = "common/terrain/blend_grass01a_dirt01a_nodetail"
DETAIL_HEAVY_TERRAIN_MATERIALS = [
    "common/nature/blend_grass_mountainwall_000",
    "common/nature/blend_grass_mud_003",
    "common/terrain/blend_grass01a_dirt01a",
    "nature/terrain/blend_grass1_dirt1",
    "nature/terrain/blend_grass1_rock1",
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
