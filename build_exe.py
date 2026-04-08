#!/usr/bin/env python3
"""
Build script for Terrain Generator Windows executable.

This script sets up the environment and runs PyInstaller.

Usage:
    python build_exe.py           # Build in onefile mode
    python build_exe.py --onedir   # Build in directory mode
"""

import sys
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.absolute()
SPEC_FILE = PROJECT_ROOT / "terrain_generator.spec"


def install_pyinstaller():
    """Install PyInstaller if not present."""
    try:
        import PyInstaller

        print(f"PyInstaller already installed: {PyInstaller.__version__}")
        return True
    except ImportError:
        print("Installing PyInstaller...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "pyinstaller"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print("PyInstaller installed successfully")
            return True
        else:
            print(f"Failed to install PyInstaller: {result.stderr}")
            return False


def build(mode="onefile"):
    """Build the executable."""
    print(f"\nBuilding Terrain Generator ({mode} mode)...")

    # Build command
    if mode == "onedir":
        cmd = ["pyinstaller", str(SPEC_FILE), "--onedir"]
    else:
        cmd = ["pyinstaller", str(SPEC_FILE), "--onefile", "--windowed"]

    result = subprocess.run(cmd, cwd=PROJECT_ROOT)

    if result.returncode == 0:
        print("\nBuild successful!")

        # Find the output
        output_dir = PROJECT_ROOT / "dist"
        if mode == "onefile":
            exe_path = output_dir / "TerrainGenerator.exe"
            if exe_path.exists():
                size_mb = exe_path.stat().st_size / 1024 / 1024
                print(f"Executable: {exe_path}")
                print(f"Size: {size_mb:.1f} MB")
        else:
            print(f"Output directory: {output_dir / 'TerrainGenerator'}")
    else:
        print("\nBuild failed!")
        print(result.stderr)
        return False

    return True


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Build Terrain Generator executable")
    parser.add_argument(
        "--onedir",
        action="store_true",
        help="Build as directory instead of single file",
    )
    args = parser.parse_args()

    mode = "onedir" if args.onedir else "onefile"

    # Install PyInstaller
    if not install_pyinstaller():
        sys.exit(1)

    # Build
    if build(mode):
        print("\nDone! The executable is in the 'dist' folder.")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
