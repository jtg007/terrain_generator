#!/usr/bin/env python3
"""
Deterministic Value Noise / Perlin-style Noise Generator

Pure Python implementation - no external dependencies.
Uses seeded permutation table for reproducible results.
"""

import math
from typing import List


class SeededRandom:
    """Simple deterministic pseudo-random number generator."""

    def __init__(self, seed: int):
        self._seed = seed
        self._state = seed

    def next(self) -> float:
        """Return float in [0, 1) using linear congruential generator."""
        self._state = (self._state * 1103515245 + 12345) & 0x7FFFFFFF
        return self._state / 0x80000000

    def randint(self, a: int, b: int) -> int:
        """Return integer in [a, b]."""
        return a + int(self.next() * (b - a + 1))


def _fade(t: float) -> float:
    """Fade function for smooth interpolation (6t^5 - 15t^4 + 10t^3)."""
    return t * t * t * (t * (t * 6 - 15) + 10)


def _lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation."""
    return a + t * (b - a)


def _grad(hash_val: int, x: float, y: float) -> float:
    """Gradient function for Perlin noise."""
    h = hash_val & 3
    if h == 0:
        return x + y
    elif h == 1:
        return -x + y
    elif h == 2:
        return x - y
    else:
        return -x - y


class NoiseGenerator:
    """Seeded Perlin-style value noise generator."""

    def __init__(self, seed: int):
        self.seed = seed
        self._perm = self._generate_permutation(seed)
        self._perm_ext = self._perm + self._perm

    def _generate_permutation(self, seed: int) -> List[int]:
        """Generate permutation table from seed."""
        rng = SeededRandom(seed)
        perm = list(range(256))
        for i in range(255, 0, -1):
            j = rng.randint(0, i)
            perm[i], perm[j] = perm[j], perm[i]
        return perm

    def noise2d(self, x: float, y: float) -> float:
        """Generate noise value at (x, y)."""
        xi = int(math.floor(x)) & 255
        yi = int(math.floor(y)) & 255

        xf = x - math.floor(x)
        yf = y - math.floor(y)

        u = _fade(xf)
        v = _fade(yf)

        p = self._perm_ext

        aa = p[p[xi] + yi]
        ab = p[p[xi] + yi + 1]
        ba = p[p[xi + 1] + yi]
        bb = p[p[xi + 1] + yi + 1]

        x1 = _lerp(_grad(aa, xf, yf), _grad(ba, xf - 1, yf), u)
        x2 = _lerp(_grad(ab, xf, yf - 1), _grad(bb, xf - 1, yf - 1), u)

        return (_lerp(x1, x2, v) + 1) / 2

    def fbm(
        self,
        x: float,
        y: float,
        octaves: int = 4,
        persistence: float = 0.5,
        lacunarity: float = 2.0,
    ) -> float:
        """Fractional Brownian Motion - layered noise."""
        total = 0.0
        frequency = 1.0
        amplitude = 1.0
        max_value = 0.0

        for _ in range(octaves):
            total += self.noise2d(x * frequency, y * frequency) * amplitude
            max_value += amplitude
            amplitude *= persistence
            frequency *= lacunarity

        return total / max_value


def generate_heightmap(
    seed: int,
    cols: int,
    rows: int,
    scale: float = 0.01,
    octaves: int = 4,
    persistence: float = 0.5,
    amplitude: float = 128.0,
    base_height: float = 0.0,
) -> List[List[float]]:
    """
    Generate a 2D heightmap using seeded noise.

    Args:
        seed: Integer seed for reproducible generation
        cols: Number of columns (width)
        rows: Number of rows (height)
        scale: Frequency multiplier for noise sampling
        octaves: Number of noise layers
        persistence: Amplitude decay per octave
        lacunarity: Frequency increase per octave
        amplitude: Maximum height variation
        base_height: Base height offset

    Returns:
        2D list of height values in absolute world units
    """
    noise = NoiseGenerator(seed)

    heightmap = []
    for y in range(rows):
        row = []
        for x in range(cols):
            nx = x * scale
            ny = y * scale

            value = noise.fbm(nx, ny, octaves=octaves, persistence=persistence)
            height = base_height + value * amplitude
            row.append(height)
        heightmap.append(row)

    return heightmap


def generate_heightmap_from_spec(
    seed: int,
    cols: int,
    rows: int,
    noise_scale: float = 0.01,
    octaves: int = 4,
    max_height: float = 256.0,
) -> List[List[float]]:
    """
    Generate heightmap for terrain specification.

    Args:
        seed: Seed for noise generation
        cols: Number of vertex columns
        rows: Number of vertex rows
        noise_scale: Scale factor for noise frequency
        octaves: Number of FBM octaves
        max_height: Maximum height in world units

    Returns:
        2D list of heights in world units
    """
    return generate_heightmap(
        seed=seed,
        cols=cols,
        rows=rows,
        scale=noise_scale,
        octaves=octaves,
        persistence=0.5,
        amplitude=max_height,
        base_height=0.0,
    )


if __name__ == "__main__":
    hm = generate_heightmap(12345, 17, 17, scale=0.02, octaves=4, amplitude=256)

    print("Generated 17x17 heightmap with seed 12345:")
    print(f"  Min height: {min(min(row) for row in hm):.2f}")
    print(f"  Max height: {max(max(row) for row in hm):.2f}")
    print(f"  Center: ({hm[8][8]:.2f})")
