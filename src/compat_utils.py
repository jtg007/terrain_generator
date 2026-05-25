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

def scipy_gaussian_filter_equivalent(img: np.ndarray, sigma: float, truncate: float = 4.0) -> np.ndarray:
    """
    Equivalent to scipy.ndimage.gaussian_filter(img, sigma, mode='reflect').
    Implemented in pure NumPy to avoid a SciPy dependency in frozen builds.
    Currently only supports 2D arrays.
    """
    if sigma == 0:
        return img

    lw = int(truncate * float(sigma) + 0.5)

    x = np.arange(-lw, lw + 1)
    kernel_1d = np.exp(-0.5 * (x / sigma) ** 2)
    kernel_1d = kernel_1d / kernel_1d.sum()

    def convolve1d(a, k, axis):
        pad_width = [(0, 0)] * a.ndim
        pad_width[axis] = (lw, lw)
        padded = np.pad(a, pad_width, mode='symmetric')
        return np.apply_along_axis(lambda m: np.convolve(m, k, mode='valid'), axis, padded)

    res = convolve1d(img, kernel_1d, axis=0)
    res = convolve1d(res, kernel_1d, axis=1)
    return res

def scipy_uniform_filter_equivalent(img: np.ndarray, size: int) -> np.ndarray:
    """
    Equivalent to scipy.ndimage.uniform_filter(img, size, mode='reflect').
    Implemented in pure NumPy to avoid a SciPy dependency in frozen builds.
    Currently only supports 2D arrays.
    """
    if isinstance(size, int):
        size = (size, size)

    def convolve1d_uniform(arr, s, axis=-1):
        if s <= 1:
            return arr

        kernel = np.ones(s) / s

        pad_width = [(0, 0)] * arr.ndim
        pad_width[axis] = (s // 2, s // 2)
        padded = np.pad(arr, pad_width, mode='symmetric')

        res = np.apply_along_axis(lambda m: np.convolve(m, kernel, mode='valid'), axis, padded)

        if s % 2 == 0:
            if axis == 0:
                res = res[1:, :]
            else:
                res = res[:, 1:]

        return res

    res = convolve1d_uniform(img, size[0], axis=0)
    res = convolve1d_uniform(res, size[1], axis=1)
    return res
