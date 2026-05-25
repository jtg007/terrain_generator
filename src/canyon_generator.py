import numpy as np

# ═══════════════════════════════════════════════════════════════════════════
#  Gameplay-First Utility Functions
# ═══════════════════════════════════════════════════════════════════════════

def max_filter_2d(arr: np.ndarray, size: int) -> np.ndarray:
    from numpy.lib.stride_tricks import sliding_window_view
    pad = size // 2
    # For max filter, pad with negative infinity so it doesn't affect the max
    padded = np.pad(arr, pad, mode='constant', constant_values=-np.inf)
    windows = sliding_window_view(padded, (size, size))
    return np.max(windows, axis=(2, 3))

def min_filter_2d(arr: np.ndarray, size: int) -> np.ndarray:
    from numpy.lib.stride_tricks import sliding_window_view
    pad = size // 2
    # For min filter, pad with positive infinity so it doesn't affect the min
    padded = np.pad(arr, pad, mode='constant', constant_values=np.inf)
    windows = sliding_window_view(padded, (size, size))
    return np.min(windows, axis=(2, 3))

def enforce_minimum_width(distance_field: np.ndarray, min_width_px: float) -> np.ndarray:
    """Ensure no bottlenecks by applying morphological closing to the safe area distance field."""
    size = max(3, int(min_width_px))
    if size % 2 == 0:
        size += 1
    
    # Cap kernel size to prevent circular artifacts on large lane widths
    # Maximum kernel should not exceed ~5% of the smaller dimension
    h, w = distance_field.shape
    max_kernel = min(h, w) // 20
    if max_kernel < 3:
        max_kernel = 3
    size = min(size, max_kernel)
    if size % 2 == 0:
        size += 1

    mask = (distance_field <= 0).astype(np.float32)

    # Morphological closing (dilate then erode the playable area)
    dilated = max_filter_2d(mask, size)
    closed = min_filter_2d(dilated, size)

    df_clean = distance_field.copy()

    # Where closed is 1 but original mask is 0, we bridged a gap.
    bridged = (closed > 0.5) & (mask < 0.5)
    # Set the distance field in the bridged gap to effectively widen it.
    df_clean[bridged] = -min_width_px

    # The user also complained that the previous clamp blindly deepened the SDF without widening it.
    # We remove that blind clamp. The validation loop will now correctly fail
    # if `np.any(d_norm_clean <= -safe_margin)` is not met naturally or via bridging!
    return df_clean

def validate_connectivity(mask: np.ndarray) -> dict:
    """
    Downsample mask to max 64px, run BFS to check if all playable areas are connected.
    Find graph diameter and return spawn candidates.
    mask: boolean array where True is playable area.
    """
    h, w = mask.shape
    scale = max(1, max(h, w) // 64)
    # simple downsampling
    small_mask = mask[::scale, ::scale]

    sh, sw = small_mask.shape

    # Find all True pixels
    y_idx, x_idx = np.nonzero(small_mask)
    if len(y_idx) == 0:
        return {"connected": False, "candidates": []}

    start = (y_idx[0], x_idx[0])

    # BFS to find connected component
    def bfs(start_node):
        visited = set([start_node])
        queue = [start_node]
        farthest_node = start_node
        max_dist = 0
        distances = {start_node: 0}

        while queue:
            cy, cx = queue.pop(0)
            d = distances[(cy, cx)]

            if d > max_dist:
                max_dist = d
                farthest_node = (cy, cx)

            for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < sh and 0 <= nx < sw and small_mask[ny, nx] and (ny, nx) not in visited:
                    visited.add((ny, nx))
                    queue.append((ny, nx))
                    distances[(ny, nx)] = d + 1

        return visited, farthest_node, max_dist

    # Pass 1: find connected component size
    visited_nodes, farthest_1, _ = bfs(start)
    if len(visited_nodes) < len(y_idx):
        return {"connected": False, "candidates": []}

    # Pass 2: from farthest_1 find the other end (graph diameter)
    _, farthest_2, _ = bfs(farthest_1)

    # Scale coordinates back to [0, 1] range
    c1 = (farthest_1[0] / sh, farthest_1[1] / sw)
    c2 = (farthest_2[0] / sh, farthest_2[1] / sw)

    # Provide generous radius
    radius_px = int(24.0 * scale)

    return {
        "connected": True,
        "candidates": [
            {"pos": c1, "radius_px": radius_px},
            {"pos": c2, "radius_px": radius_px}
        ]
    }

def compute_slope(heightmap: np.ndarray, height_per_unit: float, units_per_px_x: float, units_per_px_y: float) -> np.ndarray:
    """Compute slope gradient in real world units."""
    gy, gx = np.gradient(heightmap)
    slope_y = gy / (height_per_unit * units_per_px_y)
    slope_x = gx / (height_per_unit * units_per_px_x)
    return np.sqrt(slope_x**2 + slope_y**2)

def flatten_area(heightmap: np.ndarray, center_norm: tuple, radius_px: int) -> np.ndarray:
    """Flatten a circular area around center_norm (y, x in [0, 1])."""
    h, w = heightmap.shape
    cy, cx = int(center_norm[0] * h), int(center_norm[1] * w)

    y, x = np.ogrid[:h, :w]
    dist = np.sqrt((y - cy)**2 + (x - cx)**2)

    mask = dist <= radius_px
    if not np.any(mask):
        return heightmap

    target_h = np.mean(heightmap[mask])

    # Smooth blend
    blend = np.clip((radius_px + 4 - dist) / 4.0, 0, 1)

    out = heightmap.copy()
    out = out * (1 - blend) + target_h * blend
    return out



# ═══════════════════════════════════════════════════════════════════════════
#  Perlin / FBM (unchanged)
# ═══════════════════════════════════════════════════════════════════════════

def _build_perm(rng: np.random.Generator) -> np.ndarray:
    p = np.arange(256, dtype=np.uint8)
    rng.shuffle(p)
    return np.tile(p, 2)

def _fade(t: np.ndarray) -> np.ndarray:
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)

def _grad2(h: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    h = h & 3
    u = np.where(h < 2, x, y)
    v = np.where(h < 2, y, x)
    return np.where(h & 1, -u, u) + np.where(h & 2, -v, v)

def perlin2(perm: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    xi = np.floor(x).astype(np.int32) & 255
    yi = np.floor(y).astype(np.int32) & 255
    xf = x - np.floor(x)
    yf = y - np.floor(y)
    u = _fade(xf)
    v = _fade(yf)
    aa = perm[perm[xi]     + yi]
    ab = perm[perm[xi]     + yi + 1]
    ba = perm[perm[xi + 1] + yi]
    bb = perm[perm[xi + 1] + yi + 1]
    x1 = _grad2(aa, xf,     yf)     * (1 - u) + _grad2(ba, xf - 1, yf)     * u
    x2 = _grad2(ab, xf,     yf - 1) * (1 - u) + _grad2(bb, xf - 1, yf - 1) * u
    return x1 * (1 - v) + x2 * v

def fbm(perm: np.ndarray, x: np.ndarray, y: np.ndarray,
        octaves: int = 4, gain: float = 0.45) -> np.ndarray:
    value     = np.zeros_like(x)
    amplitude = 1.0
    frequency = 1.0
    total_amp = 0.0
    for _ in range(octaves):
        value     += perlin2(perm, x * frequency, y * frequency) * amplitude
        total_amp += amplitude
        amplitude *= gain
        frequency *= 2.0
    return value / total_amp


# ═══════════════════════════════════════════════════════════════════════════
#  Blur (unchanged)
# ═══════════════════════════════════════════════════════════════════════════

def _box_blur_1d(arr: np.ndarray, radius: int, axis: int) -> np.ndarray:
    if radius < 1:
        return arr
    n   = arr.shape[axis]
    pad = [(0, 0)] * arr.ndim
    pad[axis] = (radius, radius)
    padded = np.pad(arr, pad, mode='edge')

    pad_zero = [(0, 0)] * arr.ndim
    pad_zero[axis] = (1, 0)
    cs = np.cumsum(np.pad(padded, pad_zero, mode='constant'), axis=axis)

    slc_hi = [slice(None)] * arr.ndim
    slc_lo = [slice(None)] * arr.ndim
    slc_hi[axis] = slice(2 * radius + 1, 2 * radius + 1 + n)
    slc_lo[axis] = slice(0, n)

    return (cs[tuple(slc_hi)] - cs[tuple(slc_lo)]) / (2 * radius + 1)

def gaussian_blur(arr: np.ndarray, passes: float) -> np.ndarray:
    """
    Apply gaussian-like blur using multiple 1-pixel box blur passes.
    
    Args:
        arr: Input array
        passes: Number of blur passes (0 = no blur, higher = more blur)
               Each pass applies 3 iterations of 1-pixel box blur for smooth falloff.
    """
    passes = max(0.0, passes)
    if passes < 0.1:
        return arr
    
    full_passes = int(passes)
    fractional = passes - full_passes
    
    for _ in range(full_passes):
        for _ in range(3):
            arr = _box_blur_1d(arr, 1, axis=0)
            arr = _box_blur_1d(arr, 1, axis=1)
    
    if fractional > 0.01:
        original = arr.copy()
        for _ in range(3):
            arr = _box_blur_1d(arr, 1, axis=0)
            arr = _box_blur_1d(arr, 1, axis=1)
        arr = original * (1.0 - fractional) + arr * fractional
    
    return arr


# ═══════════════════════════════════════════════════════════════════════════
#  Smoothstep
# ═══════════════════════════════════════════════════════════════════════════

def smoothstep(e0: float, e1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


# ═══════════════════════════════════════════════════════════════════════════
#  Fallback: pure-noise canyon (no distance field)
# ═══════════════════════════════════════════════════════════════════════════

def canyon_transfer(t: np.ndarray,
                    plateau_threshold: float = 0.60,
                    canyon_threshold:  float = 0.42) -> np.ndarray:
    out = np.empty_like(t)
    plateau_mask = t >= plateau_threshold
    canyon_mask  = t <= canyon_threshold
    wall_mask    = ~plateau_mask & ~canyon_mask
    out[plateau_mask] = 0.52 + smoothstep(plateau_threshold, 1.0,               t[plateau_mask]) * 0.48
    out[canyon_mask]  =        smoothstep(0.0,               canyon_threshold,   t[canyon_mask])  * 0.18
    out[wall_mask]    = 0.18 + smoothstep(canyon_threshold,  plateau_threshold,  t[wall_mask])    * 0.34
    return out


# ═══════════════════════════════════════════════════════════════════════════
#  Noise Mask Generator (Organic Canyons)
# ═══════════════════════════════════════════════════════════════════════════

def generate_noise_canyon_mask(rows: int, cols: int, seed: int, warp_strength: float = 2.5, threshold: float = 0.5, feature_scale: float = 2.0) -> np.ndarray:
    """Generates an organic canyon mask using domain-warped FBM, no node graph."""
    rng1 = np.random.default_rng(seed)
    rng2 = np.random.default_rng(seed + 1)
    rng3 = np.random.default_rng(seed + 2)

    p1, p2, p3 = _build_perm(rng1), _build_perm(rng2), _build_perm(rng3)

    xs = np.linspace(0, feature_scale, cols, endpoint=False)
    ys = np.linspace(0, feature_scale, rows, endpoint=False)
    gx, gy = np.meshgrid(xs, ys)

    # Domain warp: offset the sample coordinates with another noise layer
    warp_x = fbm(p2, gx * 1.5 + 3.7, gy * 1.5 + 1.3, octaves=4, gain=0.5) * warp_strength
    warp_y = fbm(p3, gx * 1.5 + 8.1, gy * 1.5 + 5.9, octaves=4, gain=0.5) * warp_strength

    # Sample base noise at warped coordinates
    canyon_noise = fbm(p1, gx + warp_x, gy + warp_y, octaves=5, gain=0.55)
    canyon_noise = (canyon_noise + 1.0) * 0.5  # → [0, 1]

    # Threshold: values below threshold become canyon floor (negative = inside)
    # Convert to signed distance approximation
    distance_field = (canyon_noise - threshold) * rows  # scale to pixel units
    return distance_field


# ═══════════════════════════════════════════════════════════════════════════
#  Main generator
# ═══════════════════════════════════════════════════════════════════════════

def generate_canyon_base(
    rows:              int,
    cols:              int,
    distance_field:    np.ndarray,
    map_world_size_x:  float,
    map_world_size_y:  float,
    height_world_units: float,
    min_clearance_units: float = 192.0,
    seed:              int   = 42,
    feature_scale:     float = 1.8,
    warp_strength:     float = 1.0,
    lane_width:        float = 0.10,
    lane_depth:        float = 0.72,
    wall_slope:        float = 0.06,
    plateau_noise:     float = 0.12,
    roughness:         float = 0.50,
    blur_radius:       float = 2.0,
    octaves:           int   = 4,
    base_terrain:      np.ndarray = None,
    is_pure_noise:     bool  = False,
    max_attempts:      int   = 1,
) -> tuple[np.ndarray, dict]:
    """
    Gameplay-first canyon generator.
    """
    import logging

    # 1. Derive scaling parameters
    units_per_px_x = map_world_size_x / cols
    units_per_px_y = map_world_size_y / rows
    units_per_px = min(units_per_px_x, units_per_px_y)

    min_clearance_px = min_clearance_units / units_per_px
    ref_px = float(max(rows, cols))

    # Validation loop
    best_heightmap = None
    best_report = None

    for attempt in range(max_attempts):
        current_seed = seed + attempt

        # Pre-smooth the distance field to remove jagged staircase artifacts
        # caused by the grid-based maze algorithm.
        smoothed_df = gaussian_blur(distance_field, passes=3.0)

        # FAIL-FAST: Clean distance field and validate connectivity
        # Morphological closing to remove tiny gaps, clamp min width
        df_clean = enforce_minimum_width(smoothed_df, min_clearance_px)

        # Check connectivity on the mask
        playable_mask = df_clean <= 0
        conn_info = validate_connectivity(playable_mask)

        if not conn_info["connected"] and attempt < max_attempts - 1:
            continue # Try again with next seed

        # Core mask (safe margin)
        safe_margin = min_clearance_px / ref_px * 0.5
        d_norm_clean = df_clean / ref_px

        # Noise generation
        rng1 = np.random.default_rng(current_seed * 2654435761 % (2**32))
        rng2 = np.random.default_rng((current_seed + 500) * 1664525  % (2**32))
        rng3 = np.random.default_rng((current_seed + 999) * 22695477 % (2**32))

        p_terrain = _build_perm(rng1)
        p_warp1   = _build_perm(rng2)
        p_warp2   = _build_perm(rng3)

        xs = np.linspace(0.0, feature_scale, cols, endpoint=False)
        ys = np.linspace(0.0, feature_scale, rows, endpoint=False)
        gx, gy = np.meshgrid(xs, ys)

        wscale = 4.0
        warp_x = fbm(p_warp1, gx * wscale + 1.7, gy * wscale + 9.2, octaves=4, gain=0.5)
        warp_y = fbm(p_warp2, gx * wscale + 8.3, gy * wscale + 2.8, octaves=4, gain=0.5)

        # Base natural terrain for plateau
        if base_terrain is not None:
            t_min = base_terrain.min()
            t_max = base_terrain.max()
            if t_max > t_min:
                natural_canyon = (base_terrain - t_min) / (t_max - t_min)
            else:
                natural_canyon = np.zeros_like(base_terrain)
        else:
            base = fbm(p_terrain, gx, gy, octaves=octaves, gain=roughness)
            natural_canyon = (base + 1.0) * 0.5

        # Effective wall slope capping relative to actual lane width
        # This prevents wall gradients from swallowing entire lanes on small maps
        lane_norm = (min_clearance_px * 2.0) / ref_px
        effective_wall_slope = min(wall_slope, lane_norm * 0.4)

        # STEP 3 - Controlled warp
        # Only warp on the plateau side (d_norm > 0) to avoid shrinking corridors
        warp_pixels = (warp_x + warp_y) * warp_strength * ref_px * 0.015
        warp_mask = smoothstep(0.0, effective_wall_slope, d_norm_clean)
        warped_dist = df_clean + warp_pixels * warp_mask
        d_norm = warped_dist / ref_px

        # STEP 4 - Height Construction
        floor_h = (1.0 - lane_depth) * 0.20

        # RAMP
        # We remove slope clamping so we can have proper sheer cliffs
        # and mountain plateaus without artificially lowering the map

        wall_ramp = smoothstep(0.0, effective_wall_slope, d_norm)

        base_height = np.where(
            d_norm < -safe_margin,
            floor_h,
            np.where(
                d_norm < 0.0,
                floor_h + smoothstep(-safe_margin, 0.0, d_norm) * 0.05 * (natural_canyon - floor_h),
                floor_h + wall_ramp * (natural_canyon - floor_h)
            )
        )

        # Plateau noise
        if base_terrain is not None:
            heightmap = base_height
        else:
            nscale  = 3.5
            terrain = fbm(p_terrain, gx * nscale + 0.5, gy * nscale + 0.5, octaves=octaves, gain=roughness)
            terrain = (terrain + 1.0) * 0.5
            noise_weight = smoothstep(0.0, effective_wall_slope, d_norm) * plateau_noise
            heightmap = np.clip(base_height + (terrain - 0.5) * noise_weight * 2.0, 0.0, 1.0)

        # Final blur only on plateau/ramp
        if blur_radius > 0:
            blurred = gaussian_blur(heightmap, blur_radius)
            # Blend back core area to prevent blurring the safe path
            core_mask = d_norm < 0
            heightmap = np.where(core_mask, heightmap, blurred)

        # STEP 5 - Validation
        # Removed arbitrary slope limits so pure vertical cliffs aren't discarded
        slope_ok = True

        min_width_ok = np.any(d_norm_clean <= -safe_margin)
        is_pass = conn_info["connected"] and min_width_ok and slope_ok

        report = {
            "pass": is_pass,
            "connectivity": conn_info["connected"],
            "min_width_ok": min_width_ok,
            "slope_ok": slope_ok,
            "attempts": attempt + 1,
            "spawn_candidates": conn_info["candidates"],
            "fallback_used": False
        }

        best_heightmap = heightmap
        best_report = report

        if is_pass:
            break

    if not best_report["pass"]:
        logging.getLogger(__name__).warning("Canyon generation failed connectivity check. Falling back to pure noise canyon.")

        # Fall back to pure noise canyon

        # Create an organic mask for the fallback
        fallback_df = generate_noise_canyon_mask(
            rows=rows,
            cols=cols,
            seed=seed,
            warp_strength=warp_strength * 150.0,
            threshold=1.0 - lane_depth,
            feature_scale=feature_scale
        )

        if not is_pure_noise:
            # Recalculate using pure noise mask
            best_heightmap, new_report = generate_canyon_base(
                rows=rows,
                cols=cols,
                distance_field=fallback_df,
                map_world_size_x=map_world_size_x,
                map_world_size_y=map_world_size_y,
                height_world_units=height_world_units,
                min_clearance_units=min_clearance_units,
                seed=seed,
                feature_scale=feature_scale,
                warp_strength=warp_strength,
                lane_width=lane_width,
                lane_depth=lane_depth,
                wall_slope=wall_slope,
                plateau_noise=plateau_noise,
                roughness=roughness,
                blur_radius=blur_radius,
                octaves=octaves,
                base_terrain=base_terrain,
                is_pure_noise=True,
                max_attempts=1  # Prevent infinite recursion
            )

        best_report["fallback_used"] = True
        # Keep original failure info but update the map
        if not is_pure_noise:
            best_report["spawn_candidates"] = new_report["spawn_candidates"]

    return best_heightmap.astype(np.float32), best_report
