import json
import os

with open('config/textures.json', 'r') as f:
    data = json.load(f)

materials = data.get('terrain_materials', [])

categories = {
    "Temperate": [],
    "Desert": [],
    "Snow": [],
    "Industrial": [],
    "Wasteland": [],
    "Generic": []
}

# Materials to hide (cheap variants)
cheap_map = {}
main_materials = []

# First pass: find cheap variants and identify main materials
for mat in materials:
    mat_lower = mat.lower()
    if '_cheap' in mat_lower or '_nodetail' in mat_lower or '_nosprites' in mat_lower:
        # Try to find parent
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

reorganized = {
    "themes": {
        "Temperate": [],
        "Desert": [],
        "Snow": [],
        "Industrial": [],
        "Wasteland": [],
        "Generic": []
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
    
    reorganized["themes"][cat].append(entry)

# Cleanup: if a theme is too small or generic is too big, manually move some
# For now, just save the result
with open('config/textures_new.json', 'w') as f:
    json.dump(reorganized, f, indent=2)

print("Reorganization complete. Check config/textures_new.json")
