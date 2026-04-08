#!/usr/bin/env python3
"""
Config Manager - Saves and loads user settings
"""

import sys
import json
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from steam_paths import find_empires_path, validate_empires_path


class Config:
    DEFAULT_CONFIG = {
        "empires_path": "",
        "auto_copy_to_empires": True,
        "last_resolution": 1024,
        "last_filename": "terrain",
        "vmf_tiles_x": 4,
        "vmf_tiles_y": 4,
        "vmf_tile_size": 512,
        "vmf_max_height": 512,
        "vmf_disp_power": 3,
        "vmf_material": "nature/terrain/blend_dirt_grass_dmz_sscale",
        "first_run": True,
        "window_geometry": "900x800",
    }

    def __init__(self, config_dir=None):
        if config_dir is None:
            config_dir = Path(__file__).parent
        self.config_file = config_dir / "config.json"
        self.config_dir = config_dir
        self.config = {}
        self.load()

    def load(self):
        """Load config from file or create default"""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r") as f:
                    loaded = json.load(f)
                    self.config = {**self.DEFAULT_CONFIG, **loaded}
            except (json.JSONDecodeError, IOError):
                self.config = self.DEFAULT_CONFIG.copy()
        else:
            self.config = self.DEFAULT_CONFIG.copy()
            self.first_run_setup()

    def save(self):
        """Save config to file"""
        try:
            with open(self.config_file, "w") as f:
                json.dump(self.config, f, indent=4)
        except IOError as e:
            print(f"Could not save config: {e}")

    def get(self, key, default=None):
        """Get a config value"""
        return self.config.get(key, default)

    def set(self, key, value):
        """Set a config value"""
        self.config[key] = value
        self.save()

    def get_empires_maps_path(self):
        """Get the Empires maps folder path"""
        empires_path = self.config.get("empires_path", "")
        if not empires_path:
            return None

        maps_path = Path(empires_path) / "empires" / "maps"
        if maps_path.exists():
            return str(maps_path)
        return None

    def get_prefabs_path(self):
        """Get the Empires prefabs folder path"""
        empires_path = self.config.get("empires_path", "")
        if not empires_path:
            return None

        prefabs_path = Path(empires_path) / "empires" / "maps" / "prefabs"
        return str(prefabs_path)

    def first_run_setup(self):
        """Setup for first run - try to find Empires automatically"""
        self.config["first_run"] = True

        # Try auto-detection using platform-appropriate Steam library paths
        detected_path = find_empires_path()
        if detected_path:
            self.config["empires_path"] = detected_path
            self.config["first_run"] = False
            # Save the detected path
            self.save()

    def validate_empires_path(self):
        """Check if the configured path is valid"""
        empires_path = self.config.get("empires_path", "")
        return validate_empires_path(empires_path)

    def get_hammerplusplus_path(self):
        """Get the path to hammerplusplus.exe"""
        empires_path = self.config.get("empires_path", "")
        if not empires_path:
            return None

        hpp_path = Path(empires_path) / "bin" / "hammerplusplus.exe"
        if hpp_path.exists():
            return str(hpp_path)
        return None

    def get_proton_path(self):
        """Get the path to Proton (tries multiple versions)"""
        empires_path = self.config.get("empires_path", "")
        if not empires_path:
            return None

        common = Path(empires_path).parent
        steamapps = common.parent
        steam_library = steamapps.parent

        proton_versions = [
            "Proton 10.0/proton",
            "Proton 9.0 (Beta)/proton",
            "Proton - Experimental/proton",
        ]

        for proton in proton_versions:
            proton_path = steam_library / "steamapps" / "common" / proton
            if proton_path.exists():
                return str(proton_path)

        return None

    def get_compat_data_path(self):
        """Get the Proton compatdata path for Empires"""
        empires_path = self.config.get("empires_path", "")
        if not empires_path:
            return None

        common = Path(empires_path).parent
        steamapps = common.parent
        steam_library = steamapps.parent

        compat_path = steam_library / "steamapps" / "compatdata" / "17740" / "pfx"
        if compat_path.exists():
            return str(compat_path)
        return None

    def get_steam_path(self):
        """Get the Steam executable path"""
        empires_path = self.config.get("empires_path", "")
        if not empires_path:
            return None

        common = Path(empires_path).parent
        steamapps = common.parent
        steam_library = steamapps.parent

        steam_path = steam_library / "steamapps" / "common" / "Steam" / "steam.sh"
        if steam_path.exists():
            return str(steam_path)
        return None


if __name__ == "__main__":
    config = Config()
    print("Config loaded:")
    for key, value in config.config.items():
        print(f"  {key}: {value}")
