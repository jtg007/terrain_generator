#!/usr/bin/env python3
"""
Terrain Generator - Main Entry Point

Generates compile-safe displacement terrain for Source Engine.
"""

import json
import sys
from pathlib import Path

from terrain_spec import TerrainSpec, create_default_spec
from terrain_pipeline import run_pipeline
from vmf_writer import export_vmf


def load_spec(path: str) -> TerrainSpec:
    """Load terrain specification from JSON file."""
    with open(path, "r") as f:
        data = json.load(f)
    return TerrainSpec.from_dict(data)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate compile-safe displacement terrain for Source Engine"
    )
    parser.add_argument(
        "-c",
        "--config",
        default="example_spec.json",
        help="Path to configuration JSON file",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="output/terrain_compilesafe.vmf",
        help="Output VMF path",
    )
    parser.add_argument("--seed", type=int, help="Override seed value")
    parser.add_argument(
        "--power", type=int, choices=[2, 3, 4], help="Override displacement power"
    )
    parser.add_argument("--size", type=int, help="Override cell size (tile size)")

    args = parser.parse_args()

    config_path = Path(args.config)
    if config_path.exists():
        print(f"Loading spec from: {config_path}")
        spec = load_spec(str(config_path))
    else:
        print(f"Config not found: {config_path}, using defaults")
        spec = create_default_spec()

    if args.seed is not None:
        spec.seed = args.seed
        print(f"Override seed: {args.seed}")

    if args.power is not None:
        spec.displacement_power = args.power
        print(f"Override power: {args.power}")

    if args.size is not None:
        spec.cell_size = args.size
        print(f"Override cell_size: {args.size}")

    print(f"\n{'=' * 60}")
    print(f"Terrain Generator - Compile-Safe Displacement")
    print(f"{'=' * 60}")
    print(f"  Size: {spec.size_x} x {spec.size_y}")
    print(f"  Cell size: {spec.cell_size}")
    print(f"  Tiles: {spec.tiles_x} x {spec.tiles_y}")
    print(f"  Displacement power: {spec.displacement_power}")
    print(f"  Seed: {spec.seed}")
    print(f"  Max slope step: {spec.max_slope_step}")
    print(f"  Quantization: {spec.height_quantization}")
    print(f"  Material: {spec.material}")
    print(f"{'=' * 60}\n")

    result = run_pipeline(spec)

    if result["errors"]:
        print("\n" + "=" * 60)
        print("VALIDATION FAILED")
        print("=" * 60)
        for e in result["errors"]:
            print(f"  ERROR: {e}")
        print("\nExport aborted - fix errors before generating VMF")
        sys.exit(1)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    export_vmf(
        result["cells"],
        result["underlay"],
        result["grid"],
        result["spec"],
        str(output_path),
    )

    print(f"\n{'=' * 60}")
    print(f"SUCCESS")
    print(f"{'=' * 60}")
    print(f"  VMF: {output_path}")
    print(f"  Cells: {len(result['cells'])}")
    print(f"  Vertices: {result['grid'].rows} x {result['grid'].cols}")
    print(
        f"  Height range: {result['grid'].min_height():.1f} to {result['grid'].max_height():.1f}"
    )
    print(f"  Underlay: z={result['underlay'].bottom_z} to {result['underlay'].top_z}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
