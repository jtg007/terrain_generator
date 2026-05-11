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

def compile_vmf(
    vmf_path: str,
    sdk_path: str = "",
    empires_path: str = "",
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

    def build_cmd() -> list:
        if is_windows():
            cmd = [vbsp_exe, "-game", empires_path]
        else:
            cmd = ["wine", "vbsp.exe", "-game", empires_path]
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
            print("Tip: Engine limit exceeded for detail props. Use Smart Details.")
        else:
            print("Tip: Check geometry and entity placement near map bounds.")

    try:
        result = subprocess.run(
            build_cmd(),
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
            print("Compile failed.")
            print_failure_hint(combined_output)
            print(f"Error output:\n{result.stdout}\n{result.stderr}")
            return False

        generated_bsp = os.path.join(sdk_path, vmf_name.replace(".vmf", ".bsp"))
        if os.path.exists(generated_bsp):

            # --- BSPZIP Packing ---
            bspzip_exe = os.path.join(sdk_path, "bspzip.exe")
            vmf_assets_dir = project_root / "materials" / "vmf_generator_assets"

            if os.path.exists(bspzip_exe) and vmf_assets_dir.exists():
                print("Running bspzip to pack custom VMTs and detail scripts...")
                packlist_path = project_root / "temp_packlist.txt"

                packlist_lines = []
                for asset in vmf_assets_dir.rglob("*"):
                    if asset.is_file():
                        # Internal path inside BSP
                        rel_internal = f"materials/vmf_generator_assets/{asset.name}"
                        # External absolute path
                        abs_external = str(asset.resolve())
                        packlist_lines.append(rel_internal)
                        packlist_lines.append(abs_external)

                if packlist_lines:
                    packlist_path.write_text("\n".join(packlist_lines) + "\n")

                    bspzip_cmd = [bspzip_exe, "-addlist", generated_bsp, str(packlist_path), generated_bsp]
                    if not is_windows():
                        bspzip_cmd = ["wine"] + bspzip_cmd

                    try:
                        subprocess.run(
                            bspzip_cmd,
                            cwd=sdk_path,
                            capture_output=True,
                            text=True,
                            timeout=60,
                        )
                        print(f"Packed {len(packlist_lines)//2} files into BSP.")
                    except Exception as e:
                        print(f"Warning: Failed to run bspzip: {e}")
                    finally:
                        packlist_path.unlink(missing_ok=True)

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
        "--no-auto-copy", action="store_true", help="Disable auto copying to Empires folder"
    )
    parser.add_argument(
        "--custom-output", help="Path to custom output folder for VMF, BSP, and TXT"
    )

    args = parser.parse_args()

    success = compile_vmf(args.vmf, args.sdk, args.empires_path, not args.no_auto_copy, args.custom_output)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
