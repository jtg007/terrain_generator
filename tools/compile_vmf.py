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

    output_dir = vmf_path.parent
    bsp_path = output_dir / f"{vmf_path.stem}.bsp"
    vmf_name = vmf_path.name

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

    # Run VBSP with OS-appropriate command
    if is_windows():
        # Windows: Run VBSP directly
        cmd = [vbsp_exe, "-game", "..\\empires"]
    else:
        # Linux: Run via Wine
        cmd = ["wine", "vbsp.exe", "-game", "../empires"]

    if nodetail:
        cmd.append("-nodetail")

    cmd.append(vmf_name)

    try:
        result = subprocess.run(
            cmd,
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
                txt_path = output_dir / f"{vmf_path.stem}.txt"
                if txt_path.exists():
                    txt_dest_dir = os.path.join(empires_path, "resource", "maps")
                    os.makedirs(txt_dest_dir, exist_ok=True)
                    final_txt = os.path.join(txt_dest_dir, f"{vmf_path.stem}.txt")
                    shutil.copy2(str(txt_path), final_txt)
                    print(f"TXT script copied to: {final_txt}")

                # Copy minimap VMT and VTF to materials
                vmt_dest_dir = os.path.join(empires_path, "materials", "maps")
                os.makedirs(vmt_dest_dir, exist_ok=True)

                vmt_src = output_dir / f"{vmf_path.stem}.vmt"
                if vmt_src.exists():
                    final_vmt = os.path.join(vmt_dest_dir, f"{vmf_path.stem}.vmt")
                    shutil.copy2(str(vmt_src), final_vmt)
                    print(f"VMT minimap material copied to: {final_vmt}")

                vtf_src = output_dir / f"{vmf_path.stem}.vtf"
                if vtf_src.exists():
                    final_vtf = os.path.join(vmt_dest_dir, f"{vmf_path.stem}.vtf")
                    shutil.copy2(str(vtf_src), final_vtf)
                    print(f"VTF minimap texture copied to: {final_vtf}")

            elif not auto_copy and custom_output:
                custom_path = Path(custom_output)
                if custom_path.exists():
                    # Copy BSP to custom_folder/bsp/
                    custom_bsp_dir = custom_path / "bsp"
                    custom_bsp_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(bsp_path, custom_bsp_dir / f"{vmf_path.stem}.bsp")
                    print(f"BSP copied to custom folder: {custom_bsp_dir}")

                    # Also copy VMF to custom_folder/vmf/
                    custom_vmf_dir = custom_path / "vmf"
                    custom_vmf_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(vmf_path), custom_vmf_dir / vmf_name)
                    print(f"VMF copied to custom folder: {custom_vmf_dir}")

                    # Also copy TXT
                    txt_path = output_dir / f"{vmf_path.stem}.txt"
                    if txt_path.exists():
                        custom_txt_dir = custom_path / "txt"
                        custom_txt_dir.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(str(txt_path), custom_txt_dir / f"{vmf_path.stem}.txt")
                        print(f"TXT copied to custom folder: {custom_txt_dir}")

                    # Also copy minimap
                    custom_minimap_dir = custom_path / "minimap"
                    custom_minimap_dir.mkdir(parents=True, exist_ok=True)
                    vmt_src = output_dir / f"{vmf_path.stem}.vmt"
                    if vmt_src.exists():
                        shutil.copy2(str(vmt_src), custom_minimap_dir / f"{vmf_path.stem}.vmt")
                        print(f"VMT copied to custom folder: {custom_minimap_dir}")

                    vtf_src = output_dir / f"{vmf_path.stem}.vtf"
                    if vtf_src.exists():
                        shutil.copy2(str(vtf_src), custom_minimap_dir / f"{vmf_path.stem}.vtf")
                        print(f"VTF copied to custom folder: {custom_minimap_dir}")

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
