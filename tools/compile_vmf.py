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

    if empires_path:
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
        cmd = ["vbsp.exe", "-game", "..\\empires", vmf_name]
    else:
        # Linux: Run via Wine
        cmd = ["wine", "vbsp.exe", "-game", "../empires", vmf_name]

    if nodetail:
        cmd.insert(2, "-nodetail")

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

            if vmf_dest_dir and bsp_dest_dir:
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

                # Automatically generate a .vmt for the minimap to prevent crash
                vmt_dest_dir = os.path.join(empires_path, "materials", "maps")
                os.makedirs(vmt_dest_dir, exist_ok=True)
                final_vmt = os.path.join(vmt_dest_dir, f"{vmf_path.stem}.vmt")
                vmt_content = f""""UnlitGeneric"
{{
	"$baseTexture" "maps/{vmf_path.stem}"
	"$vertexcolor" 1
	"$vertexalpha" 1
	"$no_fullbright" 1
	"$ignorez" 1
	"%keywords" "empires"
}}"""
                with open(final_vmt, "w") as f:
                    f.write(vmt_content)
                print(f"VMT minimap material generated at: {final_vmt}")

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

    args = parser.parse_args()

    success = compile_vmf(args.vmf, args.sdk, args.empires_path, args.nodetail)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
