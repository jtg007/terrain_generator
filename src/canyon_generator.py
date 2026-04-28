import numpy as np

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
    cs = np.cumsum(padded, axis=axis)
    slc_hi = [slice(None)] * arr.ndim
    slc_lo = [slice(None)] * arr.ndim
    slc_hi[axis] = slice(2 * radius, 2 * radius + n)
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
    physical_map_size: float = 8192.0,   # kept for API compatibility, not used for normalisation
    seed:              int   = 42,
    feature_scale:     float = 1.8,
    warp_strength:     float = 1.0,
    lane_width:        float = 0.10,     # not used directly (SDF already encodes lane boundary)
    lane_depth:        float = 0.72,     # 0=shallow floor  1=very dark/deep floor
    wall_slope:        float = 0.06,     # fraction of map width over which wall rises
    plateau_noise:     float = 0.12,     # FBM amplitude on plateau surface
    roughness:         float = 0.50,
    blur_radius:       float = 2.0,
    octaves:           int   = 4,
    base_terrain:      Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Carve a heightmap from `distance_field`.

    distance_field sign convention (from generate_playability_mask):
        negative  →  inside playable lane
        positive  →  outside (wall / plateau side)
        zero      →  lane boundary

    `wall_slope` and all normalised distances are expressed as a fraction
    of max(rows, cols), so the parameters are resolution-independent.
    """

    rng1 = np.random.default_rng(seed * 2654435761 % (2**32))
    rng2 = np.random.default_rng((seed + 500) * 1664525  % (2**32))
    rng3 = np.random.default_rng((seed + 999) * 22695477 % (2**32))

    p_terrain = _build_perm(rng1)
    p_warp1   = _build_perm(rng2)
    p_warp2   = _build_perm(rng3)

    # Coordinate grids in [0, feature_scale] for noise sampling
    xs = np.linspace(0.0, feature_scale, cols, endpoint=False)
    ys = np.linspace(0.0, feature_scale, rows, endpoint=False)
    gx, gy = np.meshgrid(xs, ys)

    # ── Warp noise (in [0,1] grid coords, scale=4 for medium-frequency bumps)
    wscale = 4.0
    warp_x = fbm(p_warp1, gx * wscale + 1.7, gy * wscale + 9.2, octaves=4, gain=0.5)
    warp_y = fbm(p_warp2, gx * wscale + 8.3, gy * wscale + 2.8, octaves=4, gain=0.5)

    # ── Natural Canyon base generation ──────────────────
    if base_terrain is not None:
        # Use provided terrain as the natural base, normalized to [0, 1]
        t_min = base_terrain.min()
        t_max = base_terrain.max()
        if t_max > t_min:
            natural_canyon = (base_terrain - t_min) / (t_max - t_min)
        else:
            natural_canyon = np.zeros_like(base_terrain)
    else:
        base = fbm(p_terrain, gx + warp_x * warp_strength,
                              gy + warp_y * warp_strength,
                   octaves=octaves, gain=roughness)
        t = (base + 1.0) * 0.5
        natural_canyon = canyon_transfer(t, 1.0 - wall_slope, 1.0 - lane_depth)

    # ── Fallback: no distance field → pure noise canyons ──────────────────
    if distance_field is None or np.all(distance_field == np.inf):
        return gaussian_blur(natural_canyon, blur_radius).astype(np.float32)

    # ══════════════════════════════════════════════════════════════════════
    #  FIX 1 – normalise SDF by pixel dimensions, not physical_map_size.
    #
    #  distance_field is in pixel (or identical-unit) coordinates.
    #  Dividing by physical_map_size (8192) when the grid is e.g. 512×512
    #  made every distance ~16× too small, so wall_slope=0.06 covered only
    #  ~0.3% of the map instead of 6%.  Normalise by the actual pixel extent.
    # ══════════════════════════════════════════════════════════════════════
    ref_px = float(max(rows, cols))

    # FIX 2 – apply warp in pixel units consistent with the SDF.
    #          warp_x/y are in [-~0.5, ~0.5] after FBM normalisation.
    #          Multiply by ref_px * small_fraction so the wiggle is ~1-3% of
    #          map width — enough for organic edges, not enough to destroy lanes.
    warp_pixels = (warp_x + warp_y) * warp_strength * ref_px * 0.015
    warped_dist = distance_field + warp_pixels

    # Normalised signed distance: 0 at lane boundary, fractions of map width
    d_norm = warped_dist / ref_px

    # ══════════════════════════════════════════════════════════════════════
    #  FIX 3 – three-zone height as a clean monotone ramp, not a broken
    #           product of two smoothsteps that collapsed back to 0.
    #
    #  Zone layout (d_norm is signed, negative = inside lane):
    #
    #   d_norm < 0               →  canyon floor  (dark)
    #   0 <= d_norm < wall_slope →  cliff wall     (ramp up)
    #   d_norm >= wall_slope     →  plateau        (bright)
    # ══════════════════════════════════════════════════════════════════════

    # FIX 4 – floor_h must not be 0.  Pure-black floors never appear in
    #          Empires maps; the darkest areas are a dark grey (~0.05-0.10).
    #          lane_depth=0.72 → floor_h ≈ 0.056  (very dark but not black)
    floor_h   = (1.0 - lane_depth) * 0.20   # 0.0 < floor_h < 0.20

    # Ramp: 0.0 at the lane edge → 1.0 at wall_slope distance
    wall_ramp = smoothstep(0.0, wall_slope, d_norm)

    # Smooth height: floor inside lane, continuous ramp on wall, natural canyon outside
    base_height = np.where(
        d_norm < 0.0,
        floor_h,                                           # canyon floor
        floor_h + wall_ramp * (natural_canyon - floor_h)  # wall → natural canyon
    )

    # ── Terrain noise on plateau surface ──────────────────────────────────
    if base_terrain is not None:
        heightmap = base_height
    else:
        # Sample noise at a frequency that gives medium-sized bumps on the plateau
        nscale  = 3.5
        terrain = fbm(p_terrain, gx * nscale + 0.5, gy * nscale + 0.5,
                      octaves=octaves, gain=roughness)
        terrain = (terrain + 1.0) * 0.5   # → [0, 1]

        # Noise weight: full amplitude on plateau, fades to zero inside lanes
        # so canyon floors stay clean and flat. We use natural_canyon as base,
        # so the added noise here should just be a small extra bump if any.
        noise_weight = smoothstep(0.0, wall_slope, d_norm) * plateau_noise
        heightmap    = np.clip(
            base_height + (terrain - 0.5) * noise_weight * 2.0,
            0.0, 1.0
        )

    # ── Final blur (replicates Source engine heightmap softness) ──────────
    heightmap = gaussian_blur(heightmap, blur_radius)

    return heightmap.astype(np.float32)
