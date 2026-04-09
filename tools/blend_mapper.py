#!/usr/bin/env python3
"""
Terrain Blending System - Realistic multi-layer terrain texturing

Generates alpha maps for displacement terrain based on height data:
- Grass at low elevations
- Rock/cliff at medium elevations
- Snow at high elevations
- Smooth transitions between zones

Usage:
    python blend_mapper.py <heightmap.png> <output_folder> [--blend-type <type>]
"""

import os
import sys
import json
import argparse
import numpy as np
from PIL import Image
from pathlib import Path


class TerrainBlender:
    """Generate multi-layer blend materials for terrain."""

    # Predefined blend configurations for Empires
    BLEND_CONFIGS = {
        "grass_rock_snow": {
            "name": "Grass → Rock → Snow",
            "layers": [
                {
                    "name": "grass",
                    "material": "bgv3_grass_01",
                    "height_min": 0.0,
                    "height_max": 0.35,
                },
                {
                    "name": "rock",
                    "material": "bgv3_rock_01",
                    "height_min": 0.25,
                    "height_max": 0.65,
                },
                {
                    "name": "snow",
                    "material": "highpass_snow1024",
                    "height_min": 0.55,
                    "height_max": 1.0,
                },
            ],
            "transitions": [
                {"from": "grass", "to": "rock", "smoothness": 0.08},
                {"from": "rock", "to": "snow", "smoothness": 0.08},
            ],
        },
        "dirt_grass": {
            "name": "Dirt → Grass",
            "layers": [
                {
                    "name": "dirt",
                    "material": "dirt01c",
                    "height_min": 0.0,
                    "height_max": 0.4,
                },
                {
                    "name": "grass",
                    "material": "bgv3_grass_01",
                    "height_min": 0.3,
                    "height_max": 1.0,
                },
            ],
            "transitions": [
                {"from": "dirt", "to": "grass", "smoothness": 0.1},
            ],
        },
        "sand_grass": {
            "name": "Sand → Grass",
            "layers": [
                {
                    "name": "sand",
                    "material": "sand02",
                    "height_min": 0.0,
                    "height_max": 0.35,
                },
                {
                    "name": "grass",
                    "material": "grass_hires",
                    "height_min": 0.25,
                    "height_max": 1.0,
                },
            ],
            "transitions": [
                {"from": "sand", "to": "grass", "smoothness": 0.1},
            ],
        },
        "forest": {
            "name": "Forest (Grass → Moss → Rock)",
            "layers": [
                {
                    "name": "grass",
                    "material": "keefgrass01",
                    "height_min": 0.0,
                    "height_max": 0.4,
                },
                {
                    "name": "moss",
                    "material": "keefmoss01",
                    "height_min": 0.3,
                    "height_max": 0.7,
                },
                {
                    "name": "rock",
                    "material": "rockmesa1",
                    "height_min": 0.6,
                    "height_max": 1.0,
                },
            ],
            "transitions": [
                {"from": "grass", "to": "moss", "smoothness": 0.1},
                {"from": "moss", "to": "rock", "smoothness": 0.08},
            ],
        },
    }

    def __init__(self, heightmap_path: str, blend_type: str = "grass_rock_snow"):
        self.heightmap_path = Path(heightmap_path)
        self.blend_type = blend_type
        self.config = self.BLEND_CONFIGS.get(
            blend_type, self.BLEND_CONFIGS["grass_rock_snow"]
        )

        # Load heightmap
        self.heightmap = self._load_heightmap()
        self.height, self.width = self.heightmap.shape

    def _load_heightmap(self) -> np.ndarray:
        """Load heightmap from file."""
        img = Image.open(self.heightmap_path)

        if img.mode == "I;16" or img.mode == "I":
            arr = np.array(img, dtype=np.float32)
            arr = arr / 65535.0
        elif img.mode == "L":
            arr = np.array(img.convert("L"), dtype=np.float32) / 255.0
        else:
            arr = np.array(img.convert("L"), dtype=np.float32) / 255.0

        return arr

    def _smoothstep(self, x: float) -> float:
        """Smoothstep function for smooth transitions."""
        return x * x * (3.0 - 2.0 * x)

    def _generate_layer_weights(self, height: np.ndarray) -> dict:
        """Generate weight maps for each layer."""
        weights = {}

        # Normalize height to 0-1 range
        h_min = height.min()
        h_max = height.max()
        if h_max > h_min:
            normalized = (height - h_min) / (h_max - h_min)
        else:
            normalized = np.zeros_like(height)

        # Calculate weights for each layer
        layers = self.config["layers"]

        for i, layer in enumerate(layers):
            layer_name = layer["name"]
            h_min = layer["height_min"]
            h_max = layer["height_max"]

            # Create base weight (1.0 in range, 0.0 outside)
            weight = np.ones_like(normalized)

            # Lower bound (smooth transition upward)
            if h_min > 0:
                lower_dist = (normalized - h_min) / (1.0 - h_min + 0.001)
                lower_weight = 1.0 - self._smoothstep(np.clip(lower_dist * 3, 0, 1))
                weight *= lower_weight

            # Upper bound (smooth transition downward)
            if h_max < 1.0:
                upper_dist = (h_max - normalized) / (h_max + 0.001)
                upper_weight = self._smoothstep(np.clip(upper_dist * 3, 0, 1))
                weight *= upper_weight

            # Apply additional smoothing from transitions
            for trans in self.config["transitions"]:
                if trans["from"] == layer_name or trans["to"] == layer_name:
                    smoothness = trans["smoothness"]
                    # Add extra smoothness at boundaries
                    edge_dist = np.abs(normalized - h_min) + np.abs(normalized - h_max)
                    edge_weight = 1.0 - self._smoothstep(
                        np.clip(edge_dist / smoothness, 0, 1)
                    )
                    weight = np.maximum(weight, edge_weight * 0.3)

            weights[layer_name] = weight

        return weights

    def generate_blend_maps(self, output_dir: str) -> dict:
        """Generate alpha maps for each blend transition."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        weights = self._generate_layer_weights(self.heightmap)

        # Generate blend maps for each transition
        blend_maps = {}

        for trans in self.config["transitions"]:
            from_layer = trans["from"]
            to_layer = trans["to"]

            if from_layer in weights and to_layer in weights:
                # Calculate blend: 0 = from_layer, 255 = to_layer
                from_weight = weights[from_layer]
                to_weight = weights[to_layer]

                total = from_weight + to_weight
                total = np.where(total > 0, total, 1.0)  # Avoid division by zero

                blend = (to_weight / total * 255).astype(np.uint8)

                # Save blend map
                blend_path = output_dir / f"blend_{from_layer}_to_{to_layer}.png"
                Image.fromarray(blend).save(blend_path)

                blend_maps[f"{from_layer}_to_{to_layer}"] = str(blend_path)

                print(f"Created: {blend_path}")

        # Save heightmap for reference
        height_path = output_dir / "heightmap_normalized.png"

        # Normalize heightmap properly
        h_min = self.heightmap.min()
        h_max = self.heightmap.max()
        if h_max > h_min:
            normalized = ((self.heightmap - h_min) / (h_max - h_min) * 255).astype(
                np.uint8
            )
        else:
            normalized = np.zeros_like(self.heightmap, dtype=np.uint8)

        Image.fromarray(normalized).save(height_path)

        # Save config
        config_path = output_dir / "blend_config.json"
        with open(config_path, "w") as f:
            json.dump(self.config, f, indent=2)

        return {
            "blend_maps": blend_maps,
            "config": self.config,
            "layers": [l["material"] for l in self.config["layers"]],
            "output_dir": str(output_dir),
        }

    def generate_vmf_blend_data(
        self, power: int, tile_size: int, num_tiles: int
    ) -> dict:
        """Generate alpha data for VMF displacement faces."""
        sample_size = (2**power) + 1
        num_vertices = sample_size * sample_size

        blend_data = {}

        for trans in self.config["transitions"]:
            from_layer = trans["from"]
            to_layer = trans["to"]

            # Sample at displacement resolution
            xs = np.linspace(0, self.width - 1, sample_size)
            ys = np.linspace(0, self.height - 1, sample_size)

            alpha_values = []

            for y in ys:
                row_values = []
                for x in xs:
                    px = int(np.clip(x, 0, self.width - 1))
                    py = int(np.clip(y, 0, self.height - 1))

                    h_val = self.height[py, px]

                    # Find position between layers
                    from_layer_info = next(
                        (l for l in self.config["layers"] if l["name"] == from_layer),
                        None,
                    )
                    to_layer_info = next(
                        (l for l in self.config["layers"] if l["name"] == to_layer),
                        None,
                    )

                    if from_layer_info and to_layer_info:
                        # Calculate blend value
                        mid_point = (
                            from_layer_info["height_max"] + to_layer_info["height_min"]
                        ) / 2
                        smooth_range = trans["smoothness"]

                        diff = (h_val - mid_point) / smooth_range
                        blend = 1.0 - self._smoothstep(np.clip(0.5 + diff, 0, 1))
                        alpha = int(blend * 255)
                    else:
                        alpha = 128

                    row_values.append(str(alpha))

                alpha_values.append(" ".join(row_values))

            blend_data[f"{from_layer}_to_{to_layer}"] = alpha_values

        return {
            "blend_data": blend_data,
            "sample_size": sample_size,
            "num_vertices": num_vertices,
            "layers": self.config["layers"],
        }


def main():
    parser = argparse.ArgumentParser(description="Terrain Blending System")
    parser.add_argument("heightmap", help="Path to heightmap PNG")
    parser.add_argument("output_dir", help="Output directory for blend maps")
    parser.add_argument(
        "--blend-type",
        choices=list(TerrainBlender.BLEND_CONFIGS.keys()),
        default="grass_rock_snow",
        help="Blend type",
    )
    parser.add_argument("--power", type=int, default=3, help="Displacement power")
    parser.add_argument("--tile-size", type=int, default=512, help="Tile size")

    args = parser.parse_args()

    if not os.path.exists(args.heightmap):
        print(f"Error: Heightmap not found: {args.heightmap}")
        sys.exit(1)

    print("=== Terrain Blending System ===")
    print(f"Heightmap: {args.heightmap}")
    print(f"Blend Type: {args.blend_type}")
    print()

    blender = TerrainBlender(args.heightmap, args.blend_type)

    # Generate blend maps
    result = blender.generate_blend_maps(args.output_dir)

    print()
    print("=== Blend Maps Generated ===")
    for key, path in result["blend_maps"].items():
        print(f"  {key}: {path}")

    print()
    print(f"Config: {result['config']['name']}")
    for layer in result["config"]["layers"]:
        print(f"  - {layer['name']}: {layer['material']}")

    print()
    print("Done!")


if __name__ == "__main__":
    main()
