import re

with open('src/terrain_pipeline.py', 'r') as f:
    content = f.read()

# Add numba kernel for clamp_slope
kernel_code = """
@njit(cache=True)
def _clamp_slope_kernel(heights: np.ndarray, rows: int, cols: int, max_step: float) -> np.ndarray:
    new_heights = heights.copy()
    changed = True
    passes = 0
    max_passes = 100

    while changed and passes < max_passes:
        changed = False
        passes += 1

        for r in range(rows):
            for c in range(cols):
                current = new_heights[r, c]

                if r > 0:
                    diff = new_heights[r - 1, c] - current
                    if abs(diff) > max_step:
                        new_adj = current + (max_step if diff > 0 else -max_step)
                        if new_adj != new_heights[r - 1, c]:
                            changed = True
                        new_heights[r - 1, c] = new_adj

                if r < rows - 1:
                    diff = new_heights[r + 1, c] - current
                    if abs(diff) > max_step:
                        new_adj = current + (max_step if diff > 0 else -max_step)
                        if new_adj != new_heights[r + 1, c]:
                            changed = True
                        new_heights[r + 1, c] = new_adj

                if c > 0:
                    diff = new_heights[r, c - 1] - current
                    if abs(diff) > max_step:
                        new_adj = current + (max_step if diff > 0 else -max_step)
                        if new_adj != new_heights[r, c - 1]:
                            changed = True
                        new_heights[r, c - 1] = new_adj

                if c < cols - 1:
                    diff = new_heights[r, c + 1] - current
                    if abs(diff) > max_step:
                        new_adj = current + (max_step if diff > 0 else -max_step)
                        if new_adj != new_heights[r, c + 1]:
                            changed = True
                        new_heights[r, c + 1] = new_adj

    return new_heights, passes

def clamp_slope(grid: HeightGrid, max_step: int, use_mask: bool = True) -> HeightGrid:
    \"\"\"
    Step 4: Clamp height differences between adjacent vertices.

    Ensures no adjacent vertices differ by more than max_step.
    Iterates until all differences are within limits.
    \"\"\"
    rows = grid.rows
    cols = grid.cols

    original_heights = grid.heights.copy()

    # Run the optimized numba kernel
    new_heights, passes = _clamp_slope_kernel(original_heights, rows, cols, float(max_step))

    if passes >= 100:
        # Check if any vertex still violates max_slope_step
        violations = 0
        max_violation = 0.0

        for r in range(rows):
            for c in range(cols):
                current = new_heights[r, c]
                if r > 0:
                    diff = abs(new_heights[r - 1, c] - current)
                    if diff > max_step:
                        violations += 1
                        max_violation = max(max_violation, diff)
                if r < rows - 1:
                    diff = abs(new_heights[r + 1, c] - current)
                    if diff > max_step:
                        violations += 1
                        max_violation = max(max_violation, diff)
                if c > 0:
                    diff = abs(new_heights[r, c - 1] - current)
                    if diff > max_step:
                        violations += 1
                        max_violation = max(max_violation, diff)
                if c < cols - 1:
                    diff = abs(new_heights[r, c + 1] - current)
                    if diff > max_step:
                        violations += 1
                        max_violation = max(max_violation, diff)

        if violations > 0:
            logging.getLogger(__name__).warning(
                f"slope clamping reached max passes (100). "
                f"{violations} adjacent pairs still violate max_slope_step. "
                f"Maximum remaining slope difference: {max_violation:.2f}"
            )
        else:
            print(f"Warning: slope clamping reached max passes (100) but all vertices are within limits.")

    if use_mask:
        grid.heights = np.where(
            grid.global_selection_mask, new_heights, original_heights
        )
    else:
        grid.heights = new_heights

    return grid
"""

old_clamp_code = """def clamp_slope(grid: HeightGrid, max_step: int, use_mask: bool = True) -> HeightGrid:
    \"\"\"
    Step 4: Clamp height differences between adjacent vertices.

    Ensures no adjacent vertices differ by more than max_step.
    Iterates until all differences are within limits.
    \"\"\"
    rows = grid.rows
    cols = grid.cols

    original_heights = grid.heights.copy()
    new_heights = grid.heights.copy()

    changed = True
    passes = 0
    max_passes = 100

    while changed and passes < max_passes:
        changed = False
        passes += 1

        for r in range(rows):
            for c in range(cols):
                current = new_heights[r, c]

                if r > 0:
                    diff = new_heights[r - 1, c] - current
                    if abs(diff) > max_step:
                        new_adj = current + (max_step if diff > 0 else -max_step)
                        if new_adj != new_heights[r - 1, c]:
                            changed = True
                        new_heights[r - 1, c] = new_adj

                if r < rows - 1:
                    diff = new_heights[r + 1, c] - current
                    if abs(diff) > max_step:
                        new_adj = current + (max_step if diff > 0 else -max_step)
                        if new_adj != new_heights[r + 1, c]:
                            changed = True
                        new_heights[r + 1, c] = new_adj

                if c > 0:
                    diff = new_heights[r, c - 1] - current
                    if abs(diff) > max_step:
                        new_adj = current + (max_step if diff > 0 else -max_step)
                        if new_adj != new_heights[r, c - 1]:
                            changed = True
                        new_heights[r, c - 1] = new_adj

                if c < cols - 1:
                    diff = new_heights[r, c + 1] - current
                    if abs(diff) > max_step:
                        new_adj = current + (max_step if diff > 0 else -max_step)
                        if new_adj != new_heights[r, c + 1]:
                            changed = True
                        new_heights[r, c + 1] = new_adj

    if passes >= max_passes:
        # Check if any vertex still violates max_slope_step
        rows, cols = grid.rows, grid.cols
        violations = 0
        max_violation = 0.0

        for r in range(rows):
            for c in range(cols):
                current = new_heights[r, c]
                if r > 0:
                    diff = abs(new_heights[r - 1, c] - current)
                    if diff > max_step:
                        violations += 1
                        max_violation = max(max_violation, diff)
                if r < rows - 1:
                    diff = abs(new_heights[r + 1, c] - current)
                    if diff > max_step:
                        violations += 1
                        max_violation = max(max_violation, diff)
                if c > 0:
                    diff = abs(new_heights[r, c - 1] - current)
                    if diff > max_step:
                        violations += 1
                        max_violation = max(max_violation, diff)
                if c < cols - 1:
                    diff = abs(new_heights[r, c + 1] - current)
                    if diff > max_step:
                        violations += 1
                        max_violation = max(max_violation, diff)

        if violations > 0:
            logging.getLogger(__name__).warning(
                f"slope clamping reached max passes ({max_passes}). "
                f"{violations} adjacent pairs still violate max_slope_step. "
                f"Maximum remaining slope difference: {max_violation:.2f}"
            )
        else:
            print(f"Warning: slope clamping reached max passes ({max_passes}) but all vertices are within limits.")

    if use_mask:
        grid.heights = np.where(
            grid.global_selection_mask, new_heights, original_heights
        )
    else:
        grid.heights = new_heights

    return grid"""

content = content.replace(old_clamp_code, kernel_code)

with open('src/terrain_pipeline.py', 'w') as f:
    f.write(content)
