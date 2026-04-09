"""
Terrain Generator Core Logic
Generates heightmaps for Source Engine using WorldEngine
"""

import json
import numpy as np
from PIL import Image
from pathlib import Path


class TerrainGenerator:
    def __init__(self, base_path=None):
        if base_path is None:
            base_path = Path(__file__).parent
        self.base_path = Path(base_path)
        self.presets = self._load_presets()
        self.textures = self._load_textures()

    def _load_presets(self):
        """Load preset definitions from JSON"""
        presets_file = self.base_path / "presets.json"
        with open(presets_file, "r") as f:
            return json.load(f)

    def _load_textures(self):
        """Load texture mappings from JSON"""
        textures_file = self.base_path / "textures.json"
        with open(textures_file, "r") as f:
            return json.load(f)

    def get_preset_names(self):
        """Return list of available preset names"""
        return list(self.presets["presets"].keys())

    def get_preset(self, name):
        """Get preset by name"""
        return self.presets["presets"].get(name)

    def get_parameter_range(self, param_name):
        """Get parameter range for sliders"""
        return self.presets["parameters"].get(param_name, {})

    def generate_heightmap(
        self,
        resolution=1024,
        elevation=0.30,
        steepness=0.20,
        water_level=0.25,
        erosion=0.20,
        seed=None,
        preset_name=None,
    ):
        """
        Generate a heightmap using WorldEngine 0.20+

        Args:
            resolution: Output resolution (512, 1024, or 2048)
            elevation: Maximum height (0.05 - 0.50)
            steepness: How steep the terrain is (0.05 - 0.50)
            water_level: Water level threshold (0.00 - 0.60)
            erosion: Erosion amount (0.00 - 0.50)
            seed: Random seed for reproducibility
            preset_name: Name of preset to use

        Returns:
            numpy array of heightmap values (0-1)
        """
        try:
            import worldengine
        except ImportError:
            raise ImportError(
                "WorldEngine not installed. Please run:\npip install worldengine"
            )

        if seed is None:
            import time

            seed = int(time.time())

        print(f"Generating terrain with seed: {seed}")
        print(f"  Resolution: {resolution}x{resolution}")
        print(f"  Height: {elevation:.2f}")
        print(f"  Steepness: {steepness:.2f}")
        print(f"  Water: {water_level:.2f}")
        print(f"  Erosion: {erosion:.2f}")

        from worldengine.plates import world_gen, Step, GenerationParameters

        gen_params = GenerationParameters(
            n_plates=int(5 + steepness * 20), ocean_level=water_level, step=Step("full")
        )

        world = world_gen(
            name="terrain",
            width=resolution,
            height=resolution,
            seed=seed,
            num_plates=int(5 + steepness * 15),
            ocean_level=water_level,
            step=Step("full"),
            verbose=False,
        )

        elevation_data = world.layers["elevation"].data

        elevation_normalized = (elevation_data - elevation_data.min()) / (
            elevation_data.max() - elevation_data.min()
        )

        elevation_normalized = elevation_normalized * (elevation * 2)
        elevation_normalized = np.clip(elevation_normalized, 0, 1)

        heightmap_array = np.array(elevation_normalized, dtype=np.float32)

        return heightmap_array, world

    def generate_preview(self, resolution=256, **kwargs):
        """Generate a small preview heightmap"""
        return self.generate_heightmap(resolution=resolution, **kwargs)

    def save_heightmap_raw(self, heightmap, filename, byte_order="little"):
        """
        Save heightmap as RAW file (16-bit unsigned)

        Args:
            heightmap: numpy array with values 0-1
            filename: output filename
            byte_order: 'little' (Intel) or 'big' (Motorola)
        """
        heightmap_16bit = (heightmap * 65535).astype(np.uint16)

        if byte_order == "little":
            heightmap_16bit = heightmap_16bit.byteswap()

        heightmap_16bit.tofile(filename)
        print(f"RAW gespeichert: {filename}")

    def save_heightmap_png(self, heightmap, filename, grayscale=True):
        """
        Save heightmap as 16-bit PNG

        Args:
            heightmap: numpy array with values 0-1
            filename: output filename
            grayscale: save as grayscale (16-bit)
        """
        heightmap_16bit = (heightmap * 65535).astype(np.uint16)

        if grayscale:
            img = Image.fromarray(heightmap_16bit, mode="I;16")
        else:
            rgb_array = np.stack(
                [
                    (heightmap * 255).astype(np.uint8),
                    (heightmap * 255).astype(np.uint8),
                    (heightmap * 255).astype(np.uint8),
                ],
                axis=-1,
            )
            img = Image.fromarray(rgb_array, mode="RGB")

        img.save(filename)
        print(f"PNG gespeichert: {filename}")

    def save_heightmap_tiff(self, heightmap, filename):
        """Save heightmap as TIFF (32-bit float)"""
        heightmap_float = heightmap.astype(np.float32)
        img = Image.fromarray(heightmap_float, mode="F")
        img.save(filename)
        print(f"TIFF gespeichert: {filename}")

    def generate_and_save(
        self, output_path, filename="terrain", resolution=1024, format="both", **kwargs
    ):
        """
        Generate terrain and save to files

        Args:
            output_path: Directory to save files
            filename: Base filename (without extension)
            resolution: Output resolution
            format: 'raw', 'png', 'tiff', or 'both'
            **kwargs: Parameters for heightmap generation
        """
        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)

        heightmap, world = self.generate_heightmap(resolution=resolution, **kwargs)

        base_path = output_path / filename

        if format in ("raw", "both"):
            raw_path = f"{base_path}.raw"
            self.save_heightmap_raw(heightmap, raw_path)

        if format in ("png", "both"):
            png_path = f"{base_path}_16bit.png"
            self.save_heightmap_png(heightmap, png_path)

            preview_path = f"{base_path}_preview.jpg"
            preview_array = (heightmap * 255).astype(np.uint8)
            preview_img = Image.fromarray(preview_array, mode="L")
            preview_img.save(preview_path)

        if format == "tiff":
            tiff_path = f"{base_path}.tiff"
            self.save_heightmap_tiff(heightmap, tiff_path)

        result = {
            "heightmap": heightmap,
            "world": world,
            "paths": {
                "base": str(base_path),
            },
        }

        if format in ("raw", "both"):
            result["paths"]["raw"] = str(base_path) + ".raw"
        if format in ("png", "both"):
            result["paths"]["png"] = str(base_path) + "_16bit.png"
            result["paths"]["preview"] = str(base_path) + "_preview.jpg"

        return result

    def get_texture_suggestions(
        self, elevation=0.30, water_level=0.25, preset_name=None
    ):
        """
        Get texture suggestions based on terrain parameters

        Returns dict with suggested textures for each terrain type
        """
        suggestions = {
            "ground": [],
            "high": [],
            "water": [],
            "snow": [],
            "blend": [],
            "info": [],
        }

        if preset_name:
            preset = self.get_preset(preset_name)
            if preset and "suggested_textures" in preset:
                textures = preset["suggested_textures"]
                suggestions["ground"] = textures.get("low", []) + textures.get(
                    "medium", []
                )
                suggestions["high"] = textures.get("high", [])
                suggestions["water"] = textures.get("water", [])
                suggestions["snow"] = textures.get("snow", [])

                tex_data = self.textures.get("terrain", {})
                suggestions["blend"] = tex_data.get("grass", {}).get("blend", [])[:3]

                suggestions["info"].append(preset.get("description", ""))

        if not suggestions["ground"]:
            if elevation < 0.15:
                suggestions["ground"] = self.textures["terrain"]["grass"]["low"]
                suggestions["blend"] = self.textures["terrain"]["grass"]["blend"][:2]
            elif elevation < 0.30:
                suggestions["ground"] = self.textures["terrain"]["grass"]["medium"]
                suggestions["high"] = self.textures["terrain"]["grass"]["high"][:2]
            else:
                suggestions["ground"] = self.textures["terrain"]["rock"]["low"]
                suggestions["high"] = self.textures["terrain"]["rock"]["medium"]

        if water_level > 0.10:
            suggestions["water"] = self.textures["water"]["low"]

        if elevation > 0.35:
            suggestions["snow"] = self.textures["terrain"]["snow"]["medium"][:2]

        return suggestions

    def get_hamming_instructions(self, heightmap_path, resolution=1024):
        """
        Get instructions for importing into Hammer++

        Returns dict with import instructions
        """
        return {
            "filename": str(heightmap_path),
            "resolution": resolution,
            "compression": "None",
            "flags": resolution * 4,
            "steps": [
                "1. Open Hammer++ Editor",
                "2. Create a large brush for the terrain",
                "3. Texture one side with 'tools/toolstrigger'",
                "4. Select the face → 'Displacement' → 'Create'",
                "5. Click 'Load...' → Select the .raw file",
                "6. Settings:",
                "   - Compression: None",
                f"   - Dimension: {resolution}x{resolution}",
                f"   - Flags: ~{resolution * 4}",
                "7. Click 'Apply'",
                "8. Assign textures using 'Paint Geometry'",
            ],
        }
