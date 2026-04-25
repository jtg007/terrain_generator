import numpy as np

def _build_perm(rng: np.random.Generator) -> np.ndarray:
    """Fisher-Yates shuffled permutation table (512 entries)."""
    p = np.arange(256, dtype=np.uint8)
    rng.shuffle(p)
    return np.tile(p, 2)

def _fade(t: np.ndarray) -> np.ndarray:
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)

def _grad2(h: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """2-D gradient lookup - 4 possible gradient directions."""
    h = h & 3
    u = np.where(h < 2, x, y)
    v = np.where(h < 2, y, x)
    return np.where(h & 1, -u, u) + np.where(h & 2, -v, v)

def perlin2(perm: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Vectorised 2-D Perlin noise; x and y must be same-shape float arrays."""
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
    """Uniform box blur along one axis using cumulative sum trick."""
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
    return (cs[tuple(slc_hi)] - cs[tuple(slc_lo)]) / (2 * radius + 1)

def gaussian_blur(arr: np.ndarray, radius: int) -> np.ndarray:
    """Three-pass box blur approximation of a Gaussian (no scipy)."""
    if radius < 1:
        return arr
    for _ in range(3):
        arr = _box_blur_1d(arr, radius, axis=0)
        arr = _box_blur_1d(arr, radius, axis=1)
    return arr

def _smoothstep(e0: float, e1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)

def canyon_transfer(t: np.ndarray,
                    plateau_threshold: float = 0.60,
                    canyon_threshold:  float = 0.42) -> np.ndarray:
    """
    Map normalised noise [0,1] -> heightmap value [0,1].
    """
    out = np.empty_like(t)

    plateau_mask = t >= plateau_threshold
    canyon_mask  = t <= canyon_threshold
    wall_mask    = ~plateau_mask & ~canyon_mask

    out[plateau_mask] = 0.52 + _smoothstep(plateau_threshold, 1.0, t[plateau_mask]) * 0.48
    out[canyon_mask]  = _smoothstep(0.0, canyon_threshold, t[canyon_mask]) * 0.18
    out[wall_mask]    = 0.18 + _smoothstep(canyon_threshold, plateau_threshold, t[wall_mask]) * 0.34

    return out

def generate_canyon_base(
    rows: int,
    cols: int,
    seed: int = 42,
    feature_scale: float = 1.8,
    warp_strength: float = 1.0,
    plateau_threshold: float = 0.60,
    canyon_threshold: float = 0.42,
    blur_radius: int = 14,
    octaves: int = 4
) -> np.ndarray:
    """
    Returns a float32 array of shape (rows, cols) with values in [0, 1].
    """
    rng1 = np.random.default_rng(seed * 2654435761 % (2**32))
    rng2 = np.random.default_rng((seed + 500) * 1664525  % (2**32))
    rng3 = np.random.default_rng((seed + 999) * 22695477 % (2**32))

    p1 = _build_perm(rng1)
    p2 = _build_perm(rng2)
    p3 = _build_perm(rng3)

    # Coordinate grids mapped to the feature scale
    xs = np.linspace(0.0, feature_scale, cols, endpoint=False)
    ys = np.linspace(0.0, feature_scale, rows, endpoint=False)
    gx, gy = np.meshgrid(xs, ys)

    # Domain warp offsets
    wx = fbm(p2, gx + 1.7, gy + 9.2, octaves=octaves, gain=0.5) * warp_strength
    wy = fbm(p3, gx + 8.3, gy + 2.8, octaves=octaves, gain=0.5) * warp_strength

    # Base terrain noise
    base = fbm(p1, gx + wx, gy + wy, octaves=octaves, gain=0.45)

    # Normalise from roughly [-1, 1] -> [0, 1]
    t = (base + 1.0) * 0.5

    # Apply canyon transfer function
    heightmap = canyon_transfer(t, plateau_threshold, canyon_threshold)

    # Soften with Gaussian blur
    heightmap = gaussian_blur(heightmap, blur_radius)

    return heightmap.astype(np.float32)
