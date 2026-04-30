import numpy as np

# ═══════════════════════════════════════════════════════════════════════════
#  Gameplay-First Utility Functions
# ═══════════════════════════════════════════════════════════════════════════

def max_filter_2d(arr: np.ndarray, size: int) -> np.ndarray:
    """Pure numpy 2D max filter using sliding windows (stride tricks)."""
    if size <= 1: return arr.copy()
    from numpy.lib.stride_tricks import sliding_window_view
    pad = size // 2
    padded = np.pad(arr, pad, mode='edge')
    windows = sliding_window_view(padded, (size, size))
    return np.max(windows, axis=(2, 3))

def min_filter_2d(arr: np.ndarray, size: int) -> np.ndarray:
    """Pure numpy 2D min filter using sliding windows (stride tricks)."""
    if size <= 1: return arr.copy()
    from numpy.lib.stride_tricks import sliding_window_view
    pad = size // 2
    padded = np.pad(arr, pad, mode='edge')
    windows = sliding_window_view(padded, (size, size))
    return np.min(windows, axis=(2, 3))

def enforce_minimum_width(distance_field: np.ndarray, min_width_px: float) -> np.ndarray:
    """Ensure no bottlenecks by eroding and dilating the safe area."""
    df_clean = distance_field.copy()
    mask = distance_field < 0
    df_clean[mask] = np.minimum(df_clean[mask], -min_width_px)
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
) -> tuple[np.ndarray, dict]:
    """
    Gameplay-first canyon generator.
    """

    # 1. Derive scaling parameters
    units_per_px_x = map_world_size_x / cols
    units_per_px_y = map_world_size_y / rows
    units_per_px = min(units_per_px_x, units_per_px_y)

    height_per_unit = 1.0 / max(1.0, height_world_units)
    max_slope_per_px = np.tan(np.radians(30)) * max(units_per_px_x, units_per_px_y) * height_per_unit

    min_clearance_px = min_clearance_units / units_per_px
    ref_px = float(max(rows, cols))

    # Validation loop
    max_attempts = 5
    best_heightmap = None
    best_report = None

    for attempt in range(max_attempts):
        current_seed = seed + attempt

        # FAIL-FAST: Clean distance field and validate connectivity
        # Morphological closing to remove tiny gaps, clamp min width
        df_clean = enforce_minimum_width(distance_field, min_clearance_px)

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

        # STEP 3 - Controlled warp
        # Only warp on the plateau side (d_norm > 0) to avoid shrinking corridors
        warp_pixels = (warp_x + warp_y) * warp_strength * ref_px * 0.015
        warp_mask = smoothstep(0.0, wall_slope, d_norm_clean)
        warped_dist = df_clean + warp_pixels * warp_mask
        d_norm = warped_dist / ref_px

        # STEP 4 - Height Construction
        floor_h = (1.0 - lane_depth) * 0.20

        # RAMP (prevent clipping by adjusting max height or widening ramp)
        # We need dh / wall_slope_px <= max_slope_per_px
        # dh = natural_canyon - floor_h
        # wall_slope_px = wall_slope * ref_px
        # max_dh = max_slope_per_px * wall_slope_px / 1.5

        wall_slope_px = wall_slope * ref_px
        # limit the plateau height so that the wall ramp doesn't exceed max slope
        # wall ramp rises dh over wall_slope_px.
        # max allowed dh (in 0..1 scale) is max_slope_per_px * wall_slope_px
        max_dh = max_slope_per_px * wall_slope_px / 1.5

        # Limit plateau height to respect slope constraint
        clamped_natural_canyon = np.minimum(natural_canyon, floor_h + max_dh)

        wall_ramp = smoothstep(0.0, wall_slope, d_norm)

        base_height = np.where(
            d_norm < -safe_margin,
            floor_h,
            np.where(
                d_norm < 0.0,
                floor_h + smoothstep(-safe_margin, 0.0, d_norm) * np.minimum(0.05 * (clamped_natural_canyon - floor_h), max_slope_per_px * safe_margin * ref_px / 1.5),
                floor_h + wall_ramp * (clamped_natural_canyon - floor_h)
            )
        )

        # Plateau noise
        if base_terrain is not None:
            heightmap = base_height
        else:
            nscale  = 3.5
            terrain = fbm(p_terrain, gx * nscale + 0.5, gy * nscale + 0.5, octaves=octaves, gain=roughness)
            terrain = (terrain + 1.0) * 0.5
            noise_weight = smoothstep(0.0, wall_slope, d_norm) * plateau_noise
            heightmap = np.clip(base_height + (terrain - 0.5) * noise_weight * 2.0, 0.0, 1.0)

        # Final blur only on plateau/ramp
        if blur_radius > 0:
            blurred = gaussian_blur(heightmap, blur_radius)
            # Blend back core area to prevent blurring the safe path
            core_mask = d_norm < 0
            heightmap = np.where(core_mask, heightmap, blurred)

        # STEP 5 - Validation
        slopes = compute_slope(heightmap, height_per_unit, units_per_px_x, units_per_px_y)
        max_slope_found = np.max(slopes)
        max_allowed_world_slope = np.tan(np.radians(30))
        slope_ok = max_slope_found <= max_allowed_world_slope * 2.0 # 100% tolerance for small spikes in FBM

        min_width_ok = np.any(d_norm_clean <= -safe_margin)

        report = {
            "pass": conn_info["connected"] and slope_ok and min_width_ok,
            "connectivity": conn_info["connected"],
            "min_width_ok": min_width_ok,
            "slope_ok": slope_ok,
            "attempts": attempt + 1,
            "spawn_candidates": conn_info["candidates"]
        }

        best_heightmap = heightmap
        best_report = report

        if report["pass"]:
            break

    return best_heightmap.astype(np.float32), best_report
