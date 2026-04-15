import re

with open('src/terrain_pipeline.py', 'r') as f:
    content = f.read()

new_generate_heights = """
def generate_heights(spec: TerrainSpec, grid: HeightGrid) -> HeightGrid:
    rows = grid.rows
    cols = grid.cols
    from src.noise import NoiseGenerator
    noise = NoiseGenerator(spec.seed)
    roughness = getattr(spec, "roughness", 0.5)
    max_height = spec.terrain_max_height

    nodes, connections = generate_strategic_layout(spec)

    # 1. Fetch the pre-computed playability masks
    playable_mask_grid, choke_block_mask_grid = generate_playability_mask(spec, rows, cols, nodes, connections)

    floor_height = max_height * 0.15
    base_mountain_height = max_height * 0.85
    scaled_mountain_height = spec.mountain_height_scale ** 2
    mountain_height = floor_height + (base_mountain_height - floor_height) * scaled_mountain_height

    warp_scale = 0.005
    warp_strength = 150.0 * roughness
    macro_scale = 0.0015
    ridge_scale = 0.0025

    heightmap = []

    for r in range(rows):
        row_heights = []
        wy = spec.origin_y + r * spec.size_y / max(1, rows - 1)
        for c in range(cols):
            wx = spec.origin_x + c * spec.size_x / max(1, cols - 1)

            wx_warp = wx + noise.fbm(wx * warp_scale, wy * warp_scale, octaves=2) * warp_strength
            wy_warp = wy + noise.fbm(wx * warp_scale + 100, wy * warp_scale + 100, octaves=2) * warp_strength

            # Retrieve mask values for this specific coordinate
            playable_mask = float(playable_mask_grid[r, c])
            choke_block_mask = float(choke_block_mask_grid[r, c])

            # Noise generation
            base_noise = noise.fbm(wx_warp * macro_scale, wy_warp * macro_scale, octaves=spec.noise_octaves)
            ridge_val = noise.fbm(wx_warp * ridge_scale + 50, wy_warp * ridge_scale + 50, octaves=spec.noise_octaves)
            ridge_val = (1.0 - abs(ridge_val)) ** 2
            detail_val = noise.fbm(wx_warp * 0.008, wy_warp * 0.008, octaves=3)

            noise_combined = ((0.5 - 0.2 * roughness) * base_noise
                              + (0.3 + 0.4 * roughness) * ridge_val
                              + 0.05 * detail_val)

            # Noise suppression near paths
            noise_suppression_margin = 0.3
            suppressed_noise = noise_combined * max(0.0, 1.0 - noise_suppression_margin * (1.0 - playable_mask))

            # Target heights
            playable_height = floor_height + (max_height * 0.03 * base_noise) # Blend of lane/base targets
            wilderness_target = floor_height + (mountain_height - floor_height) * suppressed_noise
            base_choke_wall_target = base_mountain_height * (0.8 + 0.2 * ridge_val)
            choke_wall_target = floor_height + (base_choke_wall_target - floor_height) * scaled_mountain_height

            # Blend
            final_height = playable_height * playable_mask + wilderness_target * (1.0 - playable_mask)

            if choke_block_mask > 0.0:
                final_height = choke_wall_target * choke_block_mask + final_height * (1.0 - choke_block_mask)

            row_heights.append(final_height)
        heightmap.append(row_heights)

    grid.heights = heightmap

    # Attach mask to grid so later steps (like erosion) can use it without recalculating
    grid.playability_mask = playable_mask_grid

    return grid

def load_custom_heights(spec: TerrainSpec, grid: HeightGrid) -> HeightGrid:
"""

# replace the block between `def generate_heights` and `def load_custom_heights`
start_idx = content.find("def generate_heights(")
end_idx = content.find("def load_custom_heights(")

if start_idx != -1 and end_idx != -1:
    content = content[:start_idx] + new_generate_heights + content[end_idx + len("def load_custom_heights(spec: TerrainSpec, grid: HeightGrid) -> HeightGrid:\n") - len("def load_custom_heights(spec: TerrainSpec, grid: HeightGrid) -> HeightGrid:\n"):]
    # Wait, the string in new_generate_heights includes "def load_custom_heights(spec: TerrainSpec, grid: HeightGrid) -> HeightGrid:\n" at the end.
    # Better to just use regex or split.

# A safer approach using split
import re
new_content = re.sub(
    r'def generate_heights\(spec: TerrainSpec, grid: HeightGrid\) -> HeightGrid:.*?def load_custom_heights',
    new_generate_heights[:-len("def load_custom_heights(spec: TerrainSpec, grid: HeightGrid) -> HeightGrid:\n")] + "\ndef load_custom_heights",
    content,
    flags=re.DOTALL
)

with open('src/terrain_pipeline.py', 'w') as f:
    f.write(new_content)
