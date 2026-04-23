import numpy as np
import pytest
from scipy.ndimage import zoom
from src.compat_utils import scipy_zoom_equivalent

@pytest.mark.parametrize("shape, zoom_factors", [
    ((10, 10), (2.5, 2.5)),        # Upsampling
    ((20, 20), (0.5, 0.5)),        # Downsampling
    ((5, 10), (2.0, 3.0)),         # Asymmetric upsampling
    ((30, 20), (0.33, 0.5)),       # Asymmetric downsampling
    ((3, 3), (10.0, 10.0)),        # Large upsampling
    ((100, 100), (0.1, 0.1)),      # Large downsampling
    ((2, 2), (1.5, 1.5)),          # Edge case small input
    ((5, 5), (1.0, 1.0)),          # Identity
])
def test_scipy_zoom_equivalent(shape, zoom_factors):
    np.random.seed(42)
    # Test float32 (most common for heightmaps)
    arr = np.random.rand(*shape).astype(np.float32)

    scipy_res = zoom(arr, zoom_factors, order=1)
    compat_res = scipy_zoom_equivalent(arr, zoom_factors)

    assert scipy_res.shape == compat_res.shape, f"Shape mismatch: {scipy_res.shape} vs {compat_res.shape}"
    assert scipy_res.dtype == compat_res.dtype, f"Dtype mismatch: {scipy_res.dtype} vs {compat_res.dtype}"

    # Check max difference
    diff = np.max(np.abs(scipy_res - compat_res))
    assert diff < 1e-6, f"Results differ too much! Max diff: {diff}"

def test_1d_shape_handling():
    arr = np.array([[1.0, 2.0]], dtype=np.float32)
    scipy_res = zoom(arr, (1.0, 2.0), order=1)
    compat_res = scipy_zoom_equivalent(arr, (1.0, 2.0))

    assert scipy_res.shape == compat_res.shape
    diff = np.max(np.abs(scipy_res - compat_res))
    assert diff < 1e-6
