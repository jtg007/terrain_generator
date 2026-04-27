import numpy as np

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
    value = np.zeros_like(x)
    amplitude = 1.0
    frequency = 1.0
    total_amp  = 0.0
    for _ in range(octaves):
        value     += perlin2(perm, x * frequency, y * frequency) * amplitude
        total_amp += amplitude
        amplitude *= gain
        frequency *= 2.0
    return value / total_amp

def _box_blur_1d(arr: np.ndarray, radius: int, axis: int) -> np.ndarray:
    if radius < 1:
        return arr
    n = arr.shape[axis]
    pad = [(0, 0)] * arr.ndim
    pad[axis] = (radius, radius)
    padded = np.pad(arr, pad, mode='edge')
    cs = np.cumsum(padded, axis=axis)
    slc_hi = [slice(None)] * arr.ndim
    slc_lo = [slice(None)] * arr.ndim
    slc_hi[axis] = slice(2 * radius, 2 * radius + n)
    slc_lo[axis] = slice(0, n)
    return (cs[tuple(slc_hi)] - cs[tuple(slc_lo)]) / (2 * radius + n)

def gaussian_blur(arr: np.ndarray, radius: int) -> np.ndarray:
    if radius < 1:
        return arr
    for _ in range(3):
        arr = _box_blur_1d(arr, radius, axis=0)
        arr = _box_blur_1d(arr, radius, axis=1)
    return arr

def smoothstep(e0: float, e1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def canyon_transfer(t: np.ndarray,
                    plateau_threshold: float = 0.60,
                    canyon_threshold:  float = 0.42) -> np.ndarray:
    out = np.empty_like(t)

    plateau_mask = t >= plateau_threshold
    canyon_mask  = t <= canyon_threshold
    wall_mask    = ~plateau_mask & ~canyon_mask

    out[plateau_mask] = 0.52 + smoothstep(plateau_threshold, 1.0, t[plateau_mask]) * 0.48
    out[canyon_mask]  = smoothstep(0.0, canyon_threshold, t[canyon_mask]) * 0.18
    out[wall_mask]    = 0.18 + smoothstep(canyon_threshold, plateau_threshold, t[wall_mask]) * 0.34

    return out

def generate_canyon_base(
    rows: int,
    cols: int,
    distance_field: np.ndarray,
    seed: int = 42,
    feature_scale: float = 1.8,
    warp_strength: float = 1.0,
    lane_width: float = 0.10,
    lane_depth: float = 0.72,
    wall_slope: float = 0.06,
    plateau_noise: float = 0.12,
    roughness: float = 0.50,
    blur_radius: int = 2,
    octaves: int = 4
) -> np.ndarray:
    rng1 = np.random.default_rng(seed * 2654435761 % (2**32))
    rng2 = np.random.default_rng((seed + 500) * 1664525  % (2**32))
    rng3 = np.random.default_rng((seed + 999) * 22695477 % (2**32))

    p1 = _build_perm(rng1)
    p_warp1 = _build_perm(rng2)
    p_warp2 = _build_perm(rng3)

    xs = np.linspace(0.0, 1.0 * feature_scale, cols, endpoint=False)
    ys = np.linspace(0.0, 1.0 * feature_scale, rows, endpoint=False)
    gx, gy = np.meshgrid(xs, ys)

    wscale = 4.0
    warp_x = fbm(p_warp1, gx*wscale + 1.7, gy*wscale + 9.2, octaves=4, gain=0.5) * warp_strength
    warp_y = fbm(p_warp2, gx*wscale + 8.3, gy*wscale + 2.8, octaves=4, gain=0.5) * warp_strength

    if distance_field is None or np.all(distance_field == np.inf):
        # Fall back to natural noise-based canyons
        base = fbm(p1, gx + warp_x, gy + warp_y, octaves=octaves, gain=0.45)
        t = (base + 1.0) * 0.5
        heightmap = canyon_transfer(t, 1.0 - wall_slope, 1.0 - lane_depth)
        heightmap = gaussian_blur(heightmap, blur_radius)
        return heightmap.astype(np.float32)

    max_d = max(rows, cols) * 0.05
    warped_distance = distance_field + (warp_x + warp_y) * max_d

    # Normalize physical SDF to 0..1 scale based on max grid dimension for parameter compatibility
    d_norm = warped_distance / float(max(rows, cols))

    # Since distance_field is negative inside the lane (playable area) and positive outside,
    # we want the lane boundary to be at 0. But the reference script expects d to be distance from the centerline.
    # So we'll map negative values (inside lane) to the floor, and positive values (outside) to the wall climb.
    # We will adjust smoothstep boundaries accordingly.
    # D is 0 at the lane boundary. We climb starting at 0 up to 'wall_slope'.

    # in_lane: D <= 0
    in_lane = smoothstep(wall_slope, 0.0, d_norm)

    # on_wall: climbs from 0 to wall_slope
    on_wall = smoothstep(0.0, wall_slope, d_norm) * smoothstep(wall_slope*2.0, wall_slope, d_norm)

    # plateau: beyond wall_slope
    plateau = smoothstep(wall_slope, wall_slope*2.0, d_norm)

    floor_h   = 0.0
    wall_h    = 0.25 + smoothstep(0, 1, on_wall) * 0.30
    plateau_h = 0.55

    base_height = (floor_h * in_lane + wall_h * on_wall + plateau_h * plateau)

    nscale  = 3.5
    terrain = fbm(p1, gx*nscale + 0.5, gy*nscale + 0.5, octaves=octaves, gain=roughness)
    terrain = (terrain + 1.0) * 0.5

    noise_mask  = plateau * plateau_noise
    heightmap   = np.clip(base_height + (terrain - 0.5) * noise_mask * 2.0, 0.0, 1.0)

    heightmap = gaussian_blur(heightmap, blur_radius)

    return heightmap.astype(np.float32)
