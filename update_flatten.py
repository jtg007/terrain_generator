import re

with open('src/terrain_pipeline.py', 'r') as f:
    content = f.read()

new_flatten_code = """def flatten_base_areas(
    grid: HeightGrid,
    spec: "TerrainSpec",
) -> HeightGrid:
    \"\"\"
    Flatten areas where bases will be placed for competitive gameplay.
    \"\"\"
    if spec.base_clear_radius <= 0 and spec.resource_clear_radius <= 0:
        return grid

    import numpy as np

    rows = grid.rows
    cols = grid.cols

    original_heights = grid.heights.copy()
    new_heights = grid.heights.copy()

    # Pre-calculate WX and WY grids like in playability mask
    x_coords = np.linspace(spec.origin_x, spec.origin_x + spec.size_x, cols)
    y_coords = np.linspace(spec.origin_y, spec.origin_y + spec.size_y, rows)
    WX, WY = np.meshgrid(x_coords, y_coords)

    base_radius = spec.base_clear_radius
    flatness = spec.base_flatness

    imp_base_x = spec.custom_imp_base_x
    imp_base_y = spec.custom_imp_base_y
    nf_base_x = spec.custom_nf_base_x
    nf_base_y = spec.custom_nf_base_y

    def get_local_avg(bx: float, by: float, r_area: float) -> float:
        if bx is None or by is None:
            return 0.0
        dist_sq = (WX - bx)**2 + (WY - by)**2
        mask = dist_sq <= r_area**2
        if np.any(mask):
            return float(np.mean(new_heights[mask]))
        return spec.terrain_max_height * 0.15

    imp_avg_height = get_local_avg(imp_base_x, imp_base_y, base_radius)
    nf_avg_height = get_local_avg(nf_base_x, nf_base_y, base_radius)

    if base_radius > 0:
        plateau_radius = base_radius * 0.6
        falloff_dist = base_radius - plateau_radius

        # Calculate imp base mask and heights
        if imp_base_x is not None and imp_base_y is not None:
            dist_imp = np.sqrt((WX - imp_base_x)**2 + (WY - imp_base_y)**2)
            mask_imp = dist_imp < base_radius

            t_imp = np.ones_like(dist_imp)
            falloff_mask = mask_imp & (dist_imp > plateau_radius)
            t_imp[falloff_mask] = 1.0 - ((dist_imp[falloff_mask] - plateau_radius) / falloff_dist)
            t_imp[falloff_mask] = t_imp[falloff_mask] * t_imp[falloff_mask] * (3 - 2 * t_imp[falloff_mask])
            t_imp = t_imp * flatness

            new_heights[mask_imp] = new_heights[mask_imp] * (1.0 - t_imp[mask_imp]) + imp_avg_height * t_imp[mask_imp]

        # Calculate nf base mask and heights
        if nf_base_x is not None and nf_base_y is not None:
            dist_nf = np.sqrt((WX - nf_base_x)**2 + (WY - nf_base_y)**2)
            mask_nf = dist_nf < base_radius

            # Create a combined mask to not override imp heights if they overlap
            if imp_base_x is not None and imp_base_y is not None:
                mask_nf = mask_nf & ~mask_imp

            t_nf = np.ones_like(dist_nf)
            falloff_mask = mask_nf & (dist_nf > plateau_radius)
            t_nf[falloff_mask] = 1.0 - ((dist_nf[falloff_mask] - plateau_radius) / falloff_dist)
            t_nf[falloff_mask] = t_nf[falloff_mask] * t_nf[falloff_mask] * (3 - 2 * t_nf[falloff_mask])
            t_nf = t_nf * flatness

            new_heights[mask_nf] = new_heights[mask_nf] * (1.0 - t_nf[mask_nf]) + nf_avg_height * t_nf[mask_nf]

    avg_height = spec.terrain_max_height * 0.15  # Fallback for resource nodes
    # Flatten resource nodes
    if spec.resource_clear_radius > 0 and spec.custom_resources:
        res_radius = spec.resource_clear_radius
        res_flatness = spec.base_flatness * 0.6

        for res_x, res_y in spec.custom_resources:
            local_avg_height = get_local_avg(res_x, res_y, res_radius)

            dist_res = np.sqrt((WX - res_x)**2 + (WY - res_y)**2)
            mask_res = dist_res < res_radius

            t_res = 1.0 - (dist_res[mask_res] / res_radius)
            t_res = t_res * t_res * (3 - 2 * t_res)
            t_res = t_res * res_flatness

            new_heights[mask_res] = new_heights[mask_res] * (1.0 - t_res) + local_avg_height * t_res

    grid.heights = np.where(grid.global_selection_mask, new_heights, original_heights)

    return grid"""

pattern = re.compile(r'def flatten_base_areas\(\s*grid: HeightGrid,\s*spec: "TerrainSpec",\s*\) -> HeightGrid:(.*?)\n\s*return grid', re.DOTALL)
content = pattern.sub(new_flatten_code.strip() + '\n', content)

with open('src/terrain_pipeline.py', 'w') as f:
    f.write(content)
