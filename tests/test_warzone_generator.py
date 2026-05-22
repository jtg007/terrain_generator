import numpy as np
import pytest
from src.warzone_generator import generate_warzone_heightmap, generate_warzone_alpha
from src.warzone_spec import WarzoneSpec
from src.terrain_pipeline import HeightGrid
from src.terrain_spec import LayoutNode, LayoutConnection, ZoneType

def test_warzone_generator_smoke():
    spec = WarzoneSpec()
    spec.seed = 42
    spec.size_x = 1024
    spec.size_y = 1024
    spec.cell_size = 16

    rows = spec.size_y // spec.cell_size + 1
    cols = spec.size_x // spec.cell_size + 1

    heights = np.zeros((rows, cols), dtype=np.float32)
    grid = HeightGrid(
        heights=heights,
        origin_x=spec.origin_x,
        origin_y=spec.origin_y,
        cell_size=spec.cell_size,
    )

    nodes = [
        LayoutNode(100, 100, 64, ZoneType.BASE),
        LayoutNode(900, 900, 64, ZoneType.BASE)
    ]
    connections = [
        LayoutConnection(nodes[0], nodes[1], 128, ZoneType.MAIN_LANE, [(100, 100), (900, 900)])
    ]

    # Test heightmap generation
    updated_grid = generate_warzone_heightmap(spec, grid, nodes, connections)
    assert updated_grid.heights.shape == (rows, cols)
    assert not np.isnan(updated_grid.heights).any()

    # Test alpha generation
    alphas = generate_warzone_alpha(spec, updated_grid, nodes, connections)
    assert alphas.shape == (rows, cols)
    assert not np.isnan(alphas).any()
    assert np.all(alphas >= 0.0) and np.all(alphas <= 1.0)

if __name__ == "__main__":
    test_warzone_generator_smoke()
