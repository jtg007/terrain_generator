import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.terrain_pipeline import run_pipeline  # noqa: E402
from src.terrain_spec import create_default_spec  # noqa: E402


def test_terrain_shape():
    """Validates that the generated terrain grid has the exact expected dimensions."""
    spec = create_default_spec()
    spec.erosion_iterations = 0
    res = run_pipeline(spec)

    grid = res["grid"]
    rows = grid.rows
    cols = grid.cols
    actual_rows = len(grid.heights)

    assert rows == actual_rows, (
        f"Row count mismatch: expected {rows}, got {actual_rows}"
    )

    for i, row in enumerate(grid.heights):
        actual_cols = len(row)
        assert cols == actual_cols, (
            f"Column count mismatch at row {i}: expected {cols}, got {actual_cols}"
        )

    print("Shape test passed successfully.")


if __name__ == "__main__":
    test_terrain_shape()
