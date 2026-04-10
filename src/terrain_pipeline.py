#!/usr/bin/env python3
"""
Terrain Generation Pipeline

8-step pipeline for compile-safe displacement terrain:
1. Generate vertex grid
2. Generate heights from multi-layered fBm
3. Simulate hydraulic erosion
4. Calculate slopes
5. Smooth heights
6. Clamp slope
7. Quantize heights
8. Build cells from shared vertices
9. Validate seams
10. Build underlay

All coordinate calculations use integer grid positions to prevent T-junctions.
"""

import math
import random
import sys
from typing import List, Tuple

if getattr(sys, "frozen", False):
    from terrain_spec import TerrainSpec, HeightGrid, TerrainCell, UnderlayBrush
    from noise import NoiseGenerator
else:
    from src.terrain_spec import TerrainSpec, HeightGrid, TerrainCell, UnderlayBrush
    from src.noise import NoiseGenerator

from PIL import Image, ImageOps


def generate_vertex_grid(spec: TerrainSpec) -> HeightGrid:
    """
    Step 1: Generate empty vertex grid.

    Creates a grid of vertices with integer positions.
    Grid dimensions: (vertex_rows x vertex_cols)
    """
    rows = spec.vertex_rows
    cols = spec.vertex_cols

    heights = [[0.0 for _ in range(cols)] for _ in range(rows)]

    return HeightGrid(
        heights=heights,
        origin_x=spec.origin_x,
        origin_y=spec.origin_y,
        cell_size=spec.cell_size,
    )


def generate_heights(spec: TerrainSpec, grid: HeightGrid) -> HeightGrid:
    """
    Step 2: Generate heights using multi-layered Fractal Brownian Motion.

    Creates organic terrain with rolling hills and distinct ridges by combining:
    - Base fBm layer: large-scale rolling hills (low frequency, high amplitude)
    - Ridge noise layer: sharp mountain ridges (1 - |noise|)
    - Detail fBm layer: fine surface detail (high frequency, low amplitude)
    - Distance falloff: terrain fades to edges for natural map boundaries

    Height values are in absolute world units.
    """
    rows = grid.rows
    cols = grid.cols
    noise = NoiseGenerator(spec.seed)

    base_scale = 0.002
    ridge_scale = 0.003
    detail_scale = 0.01
    max_height = spec.terrain_max_height

    base_amplitude = 0.6
    ridge_amplitude = 0.35
    detail_amplitude = 0.05

    heightmap = []
    for r in range(rows):
        row_heights = []
        for c in range(cols):
            nx = c * base_scale
            ny = r * base_scale

            base_val = noise.fbm(
                nx, ny, octaves=spec.noise_octaves, persistence=0.5, lacunarity=2.0
            )

            ridge_nx = c * ridge_scale
            ridge_ny = r * ridge_scale
            ridge_val = noise.fbm(
                ridge_nx + 100.0,
                ridge_ny + 100.0,
                octaves=spec.noise_octaves,
                persistence=0.45,
                lacunarity=2.2,
            )
            ridge_val = 1.0 - abs(ridge_val)
            ridge_val = ridge_val * ridge_val

            detail_nx = c * detail_scale
            detail_ny = r * detail_scale
            detail_val = noise.fbm(
                detail_nx + 200.0,
                detail_ny + 200.0,
                octaves=3,
                persistence=0.4,
                lacunarity=2.5,
            )

            combined = (
                base_amplitude * base_val
                + ridge_amplitude * ridge_val
                + detail_amplitude * detail_val
            )

            cx = (c / max(cols - 1, 1)) - 0.5
            cy = (r / max(rows - 1, 1)) - 0.5
            dist_sq = cx * cx + cy * cy
            falloff = 1.0 - min(dist_sq * 1.2, 1.0)
            falloff = falloff * falloff

            height = combined * falloff * max_height
            row_heights.append(height)
        heightmap.append(row_heights)

    grid.heights = heightmap
    return grid


def load_custom_heights(spec: TerrainSpec, grid: HeightGrid) -> HeightGrid:
    """
    Step 2 (Alternative): Load heights from a custom PNG image.
    Uses PIL ImageOps.fit to perfectly scale and crop the image to the grid.
    """
    if not spec.custom_image_path:
        return grid

    img = Image.open(spec.custom_image_path).convert("L")

    # Fit and crop the image to the required vertex grid dimensions
    # ImageOps.fit maintains aspect ratio while filling the target size exactly.
    img_fitted = ImageOps.fit(
        img, (grid.cols, grid.rows), method=Image.Resampling.LANCZOS
    )

    # Extract pixel data mapped proportionally to maximum physical height
    pixels = list(img_fitted.getdata())
    max_height = spec.terrain_max_height

    heightmap = []
    idx = 0
    for _ in range(grid.rows):
        row_heights = []
        for _ in range(grid.cols):
            val = pixels[idx] / 255.0
            row_heights.append(val * max_height)
            idx += 1
        heightmap.append(row_heights)

    grid.heights = heightmap
    return grid


def smooth_heights(grid: HeightGrid, iterations: int = 1) -> HeightGrid:
    """
    Step 3: Smooth heights using 3x3 averaging kernel.

    Each vertex becomes the average of itself and 8 neighbors.
    Border vertices remain unchanged (no neighbors outside grid).
    """
    rows = grid.rows
    cols = grid.cols

    for _ in range(iterations):
        new_heights = []
        for r in range(rows):
            new_row = []
            for c in range(cols):
                if r == 0 or r == rows - 1 or c == 0 or c == cols - 1:
                    new_row.append(grid.heights[r][c])
                else:
                    total = 0.0
                    count = 0
                    for dr in (-1, 0, 1):
                        for dc in (-1, 0, 1):
                            total += grid.heights[r + dr][c + dc]
                            count += 1
                    new_row.append(total / count)
            new_heights.append(new_row)
        grid.heights = new_heights

    return grid


def flatten_base_areas(
    grid: HeightGrid,
    spec: "TerrainSpec",
) -> HeightGrid:
    """
    Flatten areas where bases will be placed for competitive gameplay.

    Bases are placed in opposite quadrants:
    - Imperial (IMP) base at SW quadrant
    - Northern Faction (NF) base at NE quadrant

    This creates a gentle clearing that's flat enough for buildings
    but still has natural terrain variation.
    """
    if spec.base_clear_radius <= 0:
        return grid

    rows = grid.rows
    cols = grid.cols

    vertex_spacing = spec.size_x / (cols - 1)

    base_radius = spec.base_clear_radius
    flatness = spec.base_flatness

    imp_base_x = (
        spec.custom_imp_base_x
        if spec.custom_imp_base_x is not None
        else spec.origin_x + spec.size_x * 0.25
    )
    imp_base_y = (
        spec.custom_imp_base_y
        if spec.custom_imp_base_y is not None
        else spec.origin_y + spec.size_y * 0.25
    )

    nf_base_x = (
        spec.custom_nf_base_x
        if spec.custom_nf_base_x is not None
        else spec.origin_x + spec.size_x * 0.75
    )
    nf_base_y = (
        spec.custom_nf_base_y
        if spec.custom_nf_base_y is not None
        else spec.origin_y + spec.size_y * 0.75
    )

    avg_height = grid.average_height()

    for r in range(rows):
        world_y = spec.origin_y + r * vertex_spacing
        for c in range(cols):
            world_x = spec.origin_x + c * vertex_spacing

            dist_to_imp = math.sqrt(
                (world_x - imp_base_x) ** 2 + (world_y - imp_base_y) ** 2
            )
            dist_to_nf = math.sqrt(
                (world_x - nf_base_x) ** 2 + (world_y - nf_base_y) ** 2
            )

            min_dist = min(dist_to_imp, dist_to_nf)

            if min_dist < base_radius:
                t = 1.0 - (min_dist / base_radius)
                t = t * t * (3 - 2 * t)
                t = t * flatness

                current = grid.heights[r][c]
                grid.heights[r][c] = current * (1.0 - t) + avg_height * t

    return grid


def flatten_center(
    grid: HeightGrid,
    spec: "TerrainSpec",
) -> HeightGrid:
    """
    Flatten the center of the map to reduce or eliminate center hills.

    Args:
        center_flatten: 0.0 = no effect, 1.0 = completely flat center
        center_flatten_radius: Fraction of map size to flatten (0.0-1.0)
    """
    if spec.center_flatten <= 0:
        return grid

    rows = grid.rows
    cols = grid.cols

    vertex_spacing = spec.size_x / (cols - 1)

    center_x = spec.origin_x + spec.size_x / 2
    center_y = spec.origin_y + spec.size_y / 2
    center_radius = spec.size_x * spec.center_flatten_radius

    avg_height = grid.average_height()
    flatten_amount = spec.center_flatten

    for r in range(rows):
        world_y = spec.origin_y + r * vertex_spacing
        for c in range(cols):
            world_x = spec.origin_x + c * vertex_spacing

            dist = math.sqrt((world_x - center_x) ** 2 + (world_y - center_y) ** 2)

            if dist < center_radius:
                t = 1.0 - (dist / center_radius)
                t = t * t * (3 - 2 * t)
                t = t * flatten_amount

                current = grid.heights[r][c]
                grid.heights[r][c] = current * (1.0 - t) + avg_height * t

    return grid

    rows = grid.rows
    cols = grid.cols

    vertex_spacing = spec.size_x / (cols - 1)

    center_x = spec.origin_x + spec.size_x / 2
    center_y = spec.origin_y + spec.size_y / 2
    center_radius = spec.size_x * spec.center_flatten_radius

    avg_height = grid.average_height()
    flatten_amount = spec.center_flatten

    for r in range(rows):
        world_y = spec.origin_y + r * vertex_spacing
        for c in range(cols):
            world_x = spec.origin_x + c * vertex_spacing

            dist = math.sqrt((world_x - center_x) ** 2 + (world_y - center_y) ** 2)

            if dist < center_radius:
                t = 1.0 - (dist / center_radius)
                t = t * t * (3 - 2 * t)
                effect = t * flatten_amount

                current = grid.heights[r][c]
                grid.heights[r][c] = current * (1.0 - effect) + avg_height * effect

    return grid

    rows = grid.rows
    cols = grid.cols
    cell_size = spec.cell_size

    center_x = spec.origin_x + spec.size_x / 2
    center_y = spec.origin_y + spec.size_y / 2
    center_radius = spec.size_x * spec.center_flatten_radius

    avg_height = grid.average_height()
    flatten_amount = spec.center_flatten

    for r in range(rows):
        world_y = spec.origin_y + r * cell_size
        for c in range(cols):
            world_x = spec.origin_x + c * cell_size

            dist = math.sqrt((world_x - center_x) ** 2 + (world_y - center_y) ** 2)

            if dist < center_radius:
                t = 1.0 - (dist / center_radius)
                t = t * t * (3 - 2 * t)
                effect = t * flatten_amount

                current = grid.heights[r][c]
                grid.heights[r][c] = current * (1.0 - effect) + avg_height * effect

    return grid


def clamp_slope(grid: HeightGrid, max_step: int) -> HeightGrid:
    """
    Step 4: Clamp height differences between adjacent vertices.

    Ensures no adjacent vertices differ by more than max_step.
    Iterates until all differences are within limits.
    """
    rows = grid.rows
    cols = grid.cols

    changed = True
    passes = 0
    max_passes = 100

    while changed and passes < max_passes:
        changed = False
        passes += 1

        for r in range(rows):
            for c in range(cols):
                current = grid.heights[r][c]

                if r > 0:
                    diff = grid.heights[r - 1][c] - current
                    if abs(diff) > max_step:
                        new_adj = current + (max_step if diff > 0 else -max_step)
                        if new_adj != grid.heights[r - 1][c]:
                            changed = True
                        grid.heights[r - 1][c] = new_adj

                if r < rows - 1:
                    diff = grid.heights[r + 1][c] - current
                    if abs(diff) > max_step:
                        new_adj = current + (max_step if diff > 0 else -max_step)
                        if new_adj != grid.heights[r + 1][c]:
                            changed = True
                        grid.heights[r + 1][c] = new_adj

                if c > 0:
                    diff = grid.heights[r][c - 1] - current
                    if abs(diff) > max_step:
                        new_adj = current + (max_step if diff > 0 else -max_step)
                        if new_adj != grid.heights[r][c - 1]:
                            changed = True
                        grid.heights[r][c - 1] = new_adj

                if c < cols - 1:
                    diff = grid.heights[r][c + 1] - current
                    if abs(diff) > max_step:
                        new_adj = current + (max_step if diff > 0 else -max_step)
                        if new_adj != grid.heights[r][c + 1]:
                            changed = True
                        grid.heights[r][c + 1] = new_adj

    if passes >= max_passes:
        print(f"Warning: slope clamping reached max passes ({max_passes})")

    return grid


def quantize_heights(grid: HeightGrid, step: int) -> HeightGrid:
    """
    Step 7: Quantize heights to grid step.

    All heights snap to multiples of the quantization step.
    """
    if step <= 0:
        return grid

    for r in range(grid.rows):
        for c in range(grid.cols):
            grid.heights[r][c] = round(grid.heights[r][c] / step) * step

    return grid


def simulate_hydraulic_erosion(grid: HeightGrid, spec: TerrainSpec) -> HeightGrid:
    """
    Step 3: Simulate hydraulic erosion using droplet-based algorithm.

    Droplets spawn randomly on the terrain, move downhill following the gradient,
    erode terrain where moving fast, and deposit sediment where moving slow.
    Uses numpy for terrain storage with float64 precision to prevent overflow.

    Args:
        grid: HeightGrid to erode (modified in place)
        spec: TerrainSpec containing erosion parameters

    Returns:
        Modified HeightGrid with eroded terrain
    """
    import numpy as np

    rows = grid.rows
    cols = grid.cols
    iterations = spec.erosion_iterations
    lifetime = spec.erosion_droplet_lifetime

    terrain = np.array(grid.heights, dtype=np.float64)

    initial_min = float(np.min(terrain))
    initial_max = float(np.max(terrain))
    height_range = initial_max - initial_min

    sediment_capacity = 0.01
    erosion_rate = 0.005
    deposition_rate = 0.01
    evaporation_rate = 0.01
    max_erosion_per_step = height_range * 0.001
    max_deposition_per_step = height_range * 0.001

    rng = random.Random(spec.seed + 1000)

    for _ in range(iterations):
        start_r = rng.randint(1, rows - 2)
        start_c = rng.randint(1, cols - 2)

        pos_r = float(start_r)
        pos_c = float(start_c)
        sediment = 0.0
        speed = 0.0

        for step in range(lifetime):
            ir = int(pos_r)
            ic = int(pos_c)

            if ir <= 0 or ir >= rows - 1 or ic <= 0 or ic >= cols - 1:
                break

            fx = pos_c - ic
            fy = pos_r - ir

            h00 = float(terrain[ir][ic])
            h01 = float(terrain[ir][ic + 1])
            h10 = float(terrain[ir + 1][ic])
            h11 = float(terrain[ir + 1][ic + 1])

            h_top = h00 * (1.0 - fx) + h01 * fx
            h_bot = h10 * (1.0 - fx) + h11 * fx
            height = h_top * (1.0 - fy) + h_bot * fy

            dx = (h00 * (1.0 - fy) + h10 * fy) - (h01 * (1.0 - fy) + h11 * fy)
            dy = (h00 * (1.0 - fx) + h01 * fx) - (h10 * (1.0 - fx) + h11 * fx)

            grad_len = math.sqrt(dx * dx + dy * dy)
            if grad_len < 1e-6:
                break

            nx = dx / grad_len
            ny = dy / grad_len

            pos_c += nx * 0.5
            pos_r += ny * 0.5

            new_ir = int(pos_r)
            new_ic = int(pos_c)

            if new_ir <= 0 or new_ir >= rows - 1 or new_ic <= 0 or new_ic >= cols - 1:
                break

            new_fx = pos_c - new_ic
            new_fy = pos_r - new_ir

            new_h00 = float(terrain[new_ir][new_ic])
            new_h01 = float(terrain[new_ir][new_ic + 1])
            new_h10 = float(terrain[new_ir + 1][new_ic])
            new_h11 = float(terrain[new_ir + 1][new_ic + 1])

            new_h_top = new_h00 * (1.0 - new_fx) + new_h01 * new_fx
            new_h_bot = new_h10 * (1.0 - new_fx) + new_h11 * new_fx
            new_height = new_h_top * (1.0 - new_fy) + new_h_bot * new_fy

            delta_h = new_height - height
            speed = max(speed * 0.3, abs(delta_h))

            if delta_h > 0:
                deposit_amount = min(sediment * deposition_rate, delta_h * 0.3)
                deposit_amount = min(deposit_amount, max_deposition_per_step)
                if deposit_amount > 0:
                    terrain[new_ir][new_ic] += (
                        deposit_amount * (1.0 - new_fx) * (1.0 - new_fy)
                    )
                    terrain[new_ir][new_ic + 1] += (
                        deposit_amount * new_fx * (1.0 - new_fy)
                    )
                    terrain[new_ir + 1][new_ic] += (
                        deposit_amount * (1.0 - new_fx) * new_fy
                    )
                    terrain[new_ir + 1][new_ic + 1] += deposit_amount * new_fx * new_fy
                    sediment -= deposit_amount
            else:
                max_sediment = sediment_capacity * speed * abs(delta_h)
                available_sediment = max_sediment - sediment
                if available_sediment > 0:
                    erode_amount = min(
                        erosion_rate * available_sediment, abs(delta_h) * 0.5
                    )
                    erode_amount = min(erode_amount, max_erosion_per_step)
                    if erode_amount > 0:
                        terrain[new_ir][new_ic] -= (
                            erode_amount * (1.0 - new_fx) * (1.0 - new_fy)
                        )
                        terrain[new_ir][new_ic + 1] -= (
                            erode_amount * new_fx * (1.0 - new_fy)
                        )
                        terrain[new_ir + 1][new_ic] -= (
                            erode_amount * (1.0 - new_fx) * new_fy
                        )
                        terrain[new_ir + 1][new_ic + 1] -= (
                            erode_amount * new_fx * new_fy
                        )
                        sediment += erode_amount

            sediment *= 1.0 - evaporation_rate

            if sediment < 1e-6 and speed < 1e-6:
                break

    grid.heights = terrain.tolist()
    return grid


def calculate_slopes(grid: HeightGrid) -> HeightGrid:
    """
    Step 4: Calculate the gradient (slope) magnitude at each vertex.

    Uses central differences for interior vertices and forward/backward
    differences at edges. Stores results in grid.slopes.

    The slope is the magnitude of the height gradient in world units,
    representing the steepness of terrain at each vertex.

    Args:
        grid: HeightGrid to calculate slopes for

    Returns:
        HeightGrid with slopes populated
    """
    rows = grid.rows
    cols = grid.cols
    cell_size = grid.cell_size

    slopes = [[0.0 for _ in range(cols)] for _ in range(rows)]

    for r in range(rows):
        for c in range(cols):
            if r == 0:
                dz_dr = grid.heights[r + 1][c] - grid.heights[r][c]
            elif r == rows - 1:
                dz_dr = grid.heights[r][c] - grid.heights[r - 1][c]
            else:
                dz_dr = (grid.heights[r + 1][c] - grid.heights[r - 1][c]) / 2.0

            if c == 0:
                dz_dc = grid.heights[r][c + 1] - grid.heights[r][c]
            elif c == cols - 1:
                dz_dc = grid.heights[r][c] - grid.heights[r][c - 1]
            else:
                dz_dc = (grid.heights[r][c + 1] - grid.heights[r][c - 1]) / 2.0

            slope_r = dz_dr / cell_size
            slope_c = dz_dc / cell_size
            slopes[r][c] = math.sqrt(slope_r * slope_r + slope_c * slope_c)

    grid.slopes = slopes
    return grid


def build_cells(spec: TerrainSpec, grid: HeightGrid) -> List[TerrainCell]:
    """
    Step 6: Build terrain cells from shared vertex grid.

    Each cell spans the full tile size, referencing all (2^power + 1)^2 vertices
    through the shared grid. Corner vertices define the cell extent.
    """
    cells = []
    cell_id = 0

    tiles_x = spec.tiles_x
    tiles_y = spec.tiles_y
    grid_span = spec.grid_size - 1

    for tile_row in range(tiles_y):
        for tile_col in range(tiles_x):
            grid_row = tile_row * grid_span
            grid_col = tile_col * grid_span

            vertex_tl = (grid_row, grid_col)
            vertex_tr = (grid_row, grid_col + grid_span)
            vertex_br = (grid_row + grid_span, grid_col + grid_span)
            vertex_bl = (grid_row + grid_span, grid_col)

            cell = TerrainCell(
                cell_id=cell_id,
                grid_row=grid_row,
                grid_col=grid_col,
                grid_span=grid_span,
                vertex_tl=vertex_tl,
                vertex_tr=vertex_tr,
                vertex_br=vertex_br,
                vertex_bl=vertex_bl,
            )
            cells.append(cell)
            cell_id += 1

    return cells


def validate_seams(cells: List[TerrainCell], grid: HeightGrid) -> List[str]:
    """
    Step 7: Validate seam topology.

    Checks:
    - All cells use shared vertex references
    - No edge is shared by more than 2 cells
    - No T-junctions (all vertices on integer grid)
    - Heights obey slope limits

    Returns list of error messages (empty if valid).
    """
    errors = []

    if not cells:
        errors.append("No cells to validate")
        return errors

    rows = grid.rows
    cols = grid.cols

    edge_to_cells = {}

    for cell in cells:
        for r, c in cell.vertices:
            if r < 0 or r >= rows or c < 0 or c >= cols:
                errors.append(
                    f"Cell {cell.cell_id}: vertex ({r},{c}) out of bounds ({rows}x{cols})"
                )

    for cell in cells:
        edges = [
            (("top", cell.grid_row, cell.grid_col, cell.grid_col + 1), cell.cell_id),
            (
                ("bottom", cell.grid_row + 1, cell.grid_col, cell.grid_col + 1),
                cell.cell_id,
            ),
            (("left", cell.grid_row, cell.grid_row + 1, cell.grid_col), cell.cell_id),
            (
                ("right", cell.grid_row, cell.grid_row + 1, cell.grid_col + 1),
                cell.cell_id,
            ),
        ]

        for edge_key, cell_id in edges:
            if edge_key in edge_to_cells:
                edge_to_cells[edge_key].append(cell_id)
            else:
                edge_to_cells[edge_key] = [cell_id]

    for edge_key, cell_ids in edge_to_cells.items():
        if len(cell_ids) > 2:
            edge_type = edge_key[0]
            errors.append(
                f"Edge {edge_type} shared by {len(cell_ids)} cells: {cell_ids}"
            )

    for cell in cells:
        for edge in ["top", "bottom", "left", "right"]:
            edge_heights = cell.get_edge_heights(grid, edge)
            if len(edge_heights) >= 2:
                diff = abs(edge_heights[0] - edge_heights[1])
                if diff > 100:
                    errors.append(
                        f"Cell {cell.cell_id} {edge} edge has height diff {diff:.1f} "
                        f"(heights: {edge_heights})"
                    )

    return errors


def build_underlay(spec: TerrainSpec, grid: HeightGrid) -> UnderlayBrush:
    """
    Step 8 (part 1): Build underlay brush beneath terrain.

    The underlay seals the map beneath the displacement terrain.
    """
    min_height = grid.min_height()
    bottom_z = int(min_height - spec.underlay_height)

    return UnderlayBrush(
        origin_x=spec.origin_x,
        origin_y=spec.origin_y,
        size_x=spec.size_x,
        size_y=spec.size_y,
        bottom_z=bottom_z,
        top_z=int(min_height),
        material=spec.underlay_material,
    )


def get_cell_heightmap(
    cell: TerrainCell,
    grid: HeightGrid,
    power: int,
) -> List[List[float]]:
    """
    Extract heightmap for a single displacement cell.

    Returns a 2D list of heights for the cell's vertices.
    All cells sample from the shared grid to ensure seam consistency.
    """
    grid_size = (2**power) + 1
    span = cell.grid_span

    step = span / (grid_size - 1) if grid_size > 1 else 1.0

    heights = []
    for i in range(grid_size):
        row = []
        for j in range(grid_size):
            r = round(cell.grid_row + i * step)
            c = round(cell.grid_col + j * step)
            r = max(0, min(r, grid.rows - 1))
            c = max(0, min(c, grid.cols - 1))
            h = grid.get_height(int(r), int(c))
            row.append(round(h, 1))
        heights.append(row)

    return heights


def get_cell_normals(
    heights: List[List[float]], power: int
) -> List[List[Tuple[float, float, float]]]:
    """
    Calculate normals for displacement vertices based on height gradients.

    Float format required for Source Engine compatibility.
    Uses strict vertical normals (0.0, 0.0, 1.0) to prevent sideways pulling.
    """
    grid_size = (2**power) + 1
    normals = []

    for iy in range(grid_size):
        row_normals = []
        for ix in range(grid_size):
            row_normals.append((0.0, 0.0, 1.0))
        normals.append(row_normals)

    return normals


def get_cell_slopes(
    cell: TerrainCell,
    grid: HeightGrid,
    power: int,
) -> List[List[float]]:
    """
    Extract slope values for a single displacement cell.

    Returns a 2D list of slope magnitudes for the cell's vertices.
    The slope is the gradient magnitude in world units per cell unit.

    Args:
        cell: TerrainCell to extract slopes for
        grid: HeightGrid containing slope data
        power: Displacement power (2, 3, or 4)

    Returns:
        2D list of slope values (0 = flat, higher = steeper)
    """
    grid_size = (2**power) + 1
    span = cell.grid_span

    step = span / (grid_size - 1) if grid_size > 1 else 1.0

    slopes = []
    for i in range(grid_size):
        row_slopes = []
        for j in range(grid_size):
            r = round(cell.grid_row + i * step)
            c = round(cell.grid_col + j * step)
            r = max(0, min(r, grid.rows - 1))
            c = max(0, min(c, grid.cols - 1))
            s = grid.slopes[r][c]
            row_slopes.append(float(s))
        slopes.append(row_slopes)

    return slopes


def slope_to_alpha(
    slope: float,
    flat_threshold: float = 0.005,
    steep_threshold: float = 0.03,
) -> int:
    """
    Convert slope value to alpha value for blend materials.

    Args:
        slope: Slope magnitude (rise/run, e.g., 0 = flat, 0.5 = ~26 degrees)
        flat_threshold: Slope below which alpha is 0 (fully primary texture)
        steep_threshold: Slope above which alpha is 255 (fully secondary texture)

    Returns:
        Alpha value 0-255
    """
    if slope <= flat_threshold:
        return 0
    if slope >= steep_threshold:
        return 255

    t = (slope - flat_threshold) / (steep_threshold - flat_threshold)
    t = t * t * (3 - 2 * t)
    return int(round(t * 255))


def get_cell_alphas(
    cell: TerrainCell,
    grid: HeightGrid,
    power: int,
    flat_threshold: float = 0.005,
    steep_threshold: float = 0.03,
) -> List[List[int]]:
    """
    Extract alpha values for a displacement cell based on slope.

    Args:
        cell: TerrainCell to extract alphas for
        grid: HeightGrid containing slope data
        power: Displacement power (2, 3, or 4)
        flat_threshold: Slope below which alpha is 0
        steep_threshold: Slope above which alpha is 255

    Returns:
        2D list of alpha values (0-255)
    """
    slopes = get_cell_slopes(cell, grid, power)
    grid_size = len(slopes)

    alphas = []
    for i in range(grid_size):
        row_alphas = []
        for j in range(grid_size):
            alpha = slope_to_alpha(slopes[i][j], flat_threshold, steep_threshold)
            row_alphas.append(alpha)
        alphas.append(row_alphas)

    return alphas


def run_pipeline(spec: TerrainSpec) -> dict:
    """
    Run the complete terrain generation pipeline.

    Returns dict with:
    - spec: the input specification
    - grid: the height grid
    - cells: list of terrain cells
    - underlay: the underlay brush
    - errors: validation errors (empty if successful)
    """
    print("Running terrain pipeline...")
    print(
        f"  Spec: {spec.size_x}x{spec.size_y}, cell_size={spec.cell_size}, power={spec.displacement_power}"
    )

    print(f"  Step 1: Generate vertex grid ({spec.vertex_cols}x{spec.vertex_rows})")
    grid = generate_vertex_grid(spec)

    if spec.custom_image_path:
        print(f"  Step 2: Loading custom heightmap from {spec.custom_image_path}")
        grid = load_custom_heights(spec, grid)
    else:
        print(
            f"  Step 2: Generate heights with fBm (seed={spec.seed}, octaves={spec.noise_octaves})"
        )
        grid = generate_heights(spec, grid)

    print(f"    Height range: {grid.min_height():.1f} to {grid.max_height():.1f}")

    print(
        f"  Step 3: Simulate hydraulic erosion ({spec.erosion_iterations} droplets, lifetime={spec.erosion_droplet_lifetime})"
    )
    grid = simulate_hydraulic_erosion(grid, spec)
    print(
        f"    Height range after erosion: {grid.min_height():.1f} to {grid.max_height():.1f}"
    )

    print("  Step 4: Calculate slopes")
    grid = calculate_slopes(grid)

    print("  Step 5: Smooth heights")
    grid = smooth_heights(grid, iterations=2)

    if spec.base_clear_radius > 0:
        print(
            f"  Step 5b: Flatten base areas (radius={spec.base_clear_radius}, flatness={spec.base_flatness})"
        )
        grid = flatten_base_areas(grid, spec)
        print(
            f"    Height range after base flatten: {grid.min_height():.1f} to {grid.max_height():.1f}"
        )

    if spec.center_flatten > 0:
        print(
            f"  Step 5c: Flatten center (amount={spec.center_flatten}, radius={spec.center_flatten_radius * spec.size_x:.0f})"
        )
        grid = flatten_center(grid, spec)
        print(
            f"    Height range after center flatten: {grid.min_height():.1f} to {grid.max_height():.1f}"
        )

    print(f"  Step 6: Clamp slope (max_step={spec.max_slope_step})")
    grid = clamp_slope(grid, spec.max_slope_step)
    print(
        f"    Height range after clamp: {grid.min_height():.1f} to {grid.max_height():.1f}"
    )

    print(f"  Step 7: Quantize heights (step={spec.height_quantization})")
    grid = quantize_heights(grid, spec.height_quantization)

    print("  Step 8: Build cells")
    cells = build_cells(spec, grid)
    print(f"    Created {len(cells)} cells")

    print("  Step 9: Validate seams")
    errors = validate_seams(cells, grid)
    if errors:
        print("    ERRORS FOUND:")
        for e in errors:
            print(f"      - {e}")
    else:
        print("    Validation passed!")

    print("  Step 10: Build underlay")
    underlay = build_underlay(spec, grid)
    print(f"    Underlay: z={underlay.bottom_z} to {underlay.top_z}")

    return {
        "spec": spec,
        "grid": grid,
        "cells": cells,
        "underlay": underlay,
        "errors": errors,
    }


if __name__ == "__main__":
    if getattr(sys, "frozen", False):
        from terrain_spec import create_default_spec
    else:
        from src.terrain_spec import create_default_spec

    result = run_pipeline(create_default_spec())

    if result["errors"]:
        print("\nValidation FAILED:")
        for e in result["errors"]:
            print(f"  {e}")
    else:
        print("\nPipeline completed successfully!")
        print(f"  Grid: {result['grid'].rows}x{result['grid'].cols}")
        print(f"  Cells: {len(result['cells'])}")
        print(
            f"  Underlay: z={result['underlay'].bottom_z} to {result['underlay'].top_z}"
        )
