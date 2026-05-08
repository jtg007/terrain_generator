import json
import os

# Original list of materials from a known safe source if possible, 
# or just extract all paths from the current broken file.
def extract_paths(filename):
    paths = []
    with open(filename, 'r') as f:
        content = f.read()
        import re
        paths = re.findall(r'"path":\s*"([^"]+)"', content)
    return sorted(list(set(paths)))

materials = extract_paths('config/textures.json')

cheap_map = {}
main_materials = []
for mat in materials:
    if '_cheap' in mat or '_nodetail' in mat or '_nosprites' in mat:
        parent = mat.replace('_cheap', '').replace('_nodetail', '').replace('_nosprites', '')
        cheap_map[parent] = mat
    else:
        main_materials.append(mat)

def get_category(path):
    p = path.lower()
    if any(k in p for k in ['snow', 'ice', 'frozen']): return "Snow"
    if any(k in p for k in ['sand', 'arid', 'beach', 'reef', 'tropical']): return "Desert"
    if any(k in p for k in ['concrete', 'parking', 'paving', 'tarmac', 'road', 'asphalt', 'city']): return "Industrial"
    if any(k in p for k in ['red', 'valley', 'wasteland', 'rubble']): return "Wasteland"
    if any(k in p for k in ['grass', 'forest', 'mud', 'dirt', 'nature', 'moss', 'tree']): return "Temperate"
    return "Generic"

themes_config = {
    "Temperate": {
        "defaults": {
            "primary_floor": "common/nature/blend_grass_mud_003",
            "primary_cliff": "common/nature/mountain_wall_000",
            "cheap_floor": "common/terrain/blend_grass01a_dirt01a_nodetail",
            "cheap_cliff": "nature/cliffface001b",
            "skybox": "empsky_day1"
        },
        "materials": []
    },
    "Desert": {
        "defaults": {
            "primary_floor": "common/nature/blend_grass_sandfloor009a_000",
            "primary_cliff": "nature/cliff/stone_cliff_colorado",
            "cheap_floor": "maps/emp_arid/blenddirtdirt_silk",
            "cheap_cliff": "nature/cliffface001b",
            "skybox": "empsky_day3"
        },
        "materials": []
    },
    "Snow": {
        "defaults": {
            "primary_floor": "common/emp_snow/blend_snowsnow01a",
            "primary_cliff": "dz/blend_snow_wall",
            "cheap_floor": "common/emp_snow/snowfloor001b",
            "cheap_cliff": "dz/blend_snow_wall",
            "skybox": "empsky_overcast1"
        },
        "materials": []
    },
    "Industrial": {
        "defaults": {
            "primary_floor": "common/stene/dirtyconcrete",
            "primary_cliff": "common/nature/mountain_wall_000",
            "cheap_floor": "common/stene/dirtyconcrete",
            "cheap_cliff": "nature/cliffface001b",
            "skybox": "empsky_overcast2"
        },
        "materials": []
    },
    "Wasteland": {
        "defaults": {
            "primary_floor": "common/terrain/redground2",
            "primary_cliff": "nature/cliff/stone_cliff_colorado",
            "cheap_floor": "common/terrain/redground2",
            "cheap_cliff": "nature/cliffface001b",
            "skybox": "empsky_sunset2"
        },
        "materials": []
    },
    "Generic": {
        "defaults": {
            "primary_floor": "common/nature/blend_grass_mud_003",
            "primary_cliff": "common/nature/mountain_wall_000",
            "cheap_floor": "common/terrain/blend_grass01a_dirt01a_nodetail",
            "cheap_cliff": "nature/cliffface001b",
            "skybox": "empsky_overcast2"
        },
        "materials": []
    }
}

for mat in main_materials:
    cat = get_category(mat)
    entry = {
        "name": os.path.basename(mat).replace('_', ' ').title(),
        "path": mat
    }
    if mat in cheap_map:
        entry["cheap_path"] = cheap_map[mat]
    themes_config[cat]["materials"].append(entry)

final_data = {
    "themes": themes_config,
    "skyboxes": [
        "empsky_day1", "empsky_day2", "empsky_day3",
        "empsky_overcast1", "empsky_overcast2", "empsky_overcast3yellow",
        "empsky_sunset1", "empsky_sunset2"
    ]
}

with open('config/textures.json', 'w') as f:
    json.dump(final_data, f, indent=2)

print("textures.json rebuilt successfully.")
