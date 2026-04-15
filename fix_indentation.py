with open('src/terrain_pipeline.py', 'r') as f:
    lines = f.readlines()

# Remove the duplicated line 564
# Note that python lists are 0-indexed, so line 564 is index 563.
if lines[563].strip() == "def load_custom_heights(spec: TerrainSpec, grid: HeightGrid) -> HeightGrid:" and \
   lines[564].strip() == "def load_custom_heights(spec: TerrainSpec, grid: HeightGrid) -> HeightGrid:":
    lines.pop(563)

with open('src/terrain_pipeline.py', 'w') as f:
    f.writelines(lines)
