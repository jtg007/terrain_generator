import numpy as np

def scipy_zoom_equivalent(arr: np.ndarray, zoom_factors: tuple) -> np.ndarray:
    """
    Equivalent to scipy.ndimage.zoom(arr, zoom_factors, order=1).
    Implemented in pure NumPy to avoid a SciPy dependency in frozen builds.
    Currently only supports 2D arrays and order=1 (bilinear interpolation).
    """
    if arr.ndim != 2:
        raise ValueError("Only 2D arrays are supported in this compatibility wrapper.")

    h, w = arr.shape
    new_h = int(np.round(h * zoom_factors[0]))
    new_w = int(np.round(w * zoom_factors[1]))

    # SciPy's map_coordinates (used by zoom) evaluates at linearly spaced points
    # from 0 to h-1 and 0 to w-1.
    row_coords = np.linspace(0, h - 1, new_h) if new_h > 1 else np.zeros(new_h)
    col_coords = np.linspace(0, w - 1, new_w) if new_w > 1 else np.zeros(new_w)

    rows_floor = np.floor(row_coords).astype(int)
    cols_floor = np.floor(col_coords).astype(int)
    rows_ceil = np.clip(rows_floor + 1, 0, h - 1)
    cols_ceil = np.clip(cols_floor + 1, 0, w - 1)

    row_weight = row_coords - rows_floor
    col_weight = col_coords - cols_floor

    row_weight = row_weight[:, np.newaxis]
    col_weight = col_weight[np.newaxis, :]

    q11 = arr[np.ix_(rows_floor, cols_floor)]
    q12 = arr[np.ix_(rows_floor, cols_ceil)]
    q21 = arr[np.ix_(rows_ceil, cols_floor)]
    q22 = arr[np.ix_(rows_ceil, cols_ceil)]

    res = (q11 * (1 - row_weight) * (1 - col_weight) +
           q21 * row_weight * (1 - col_weight) +
           q12 * (1 - row_weight) * col_weight +
           q22 * row_weight * col_weight)

    return res.astype(arr.dtype)
