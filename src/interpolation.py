"""
Spatial interpolation utilities for Japan Discomfort Index (不快指数) visualization.

Provides IDW (Inverse Distance Weighting) interpolation to create smooth
surfaces of discomfort index values across Japan, suitable for use with
Pydeck's HeatmapLayer.
"""

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Color stop table: (DI threshold, (R, G, B))
# Interpolated linearly between stops.
# ---------------------------------------------------------------------------
_COLOR_STOPS: list[tuple[float, tuple[int, int, int]]] = [
    (55.0, (0,   100, 200)),   # blue        – 不快でない
    (60.0, (0,   200, 180)),   # cyan-green  – やや不快手前
    (65.0, (80,  220,  50)),   # yellow-green – やや不快
    (70.0, (255, 180,   0)),   # orange      – 不快
    (75.0, (255,  60,   0)),   # red-orange  – かなり不快
    (80.0, (200,   0,  80)),   # dark red/magenta – 非常に不快 / 暑くてたまらない
]

_ALPHA_HEATMAP = 180   # alpha for heatmap grid points
_ALPHA_SINGLE  = 220   # alpha for get_di_color()


# ---------------------------------------------------------------------------
# 1. Pure IDW implementation
# ---------------------------------------------------------------------------

def idw_interpolate(
    known_lats: np.ndarray,
    known_lons: np.ndarray,
    known_values: np.ndarray,
    grid_lats: np.ndarray,
    grid_lons: np.ndarray,
    power: float = 2,
) -> np.ndarray:
    """Interpolate values at grid points using Inverse Distance Weighting (IDW).

    For each target grid point the interpolated value is:

        z(x) = sum(v_i / d_i^p) / sum(1 / d_i^p)

    where d_i is the Euclidean distance (in degrees) to known point i and p is
    the IDW power parameter.  When a grid point coincides exactly with a known
    point the known value is returned directly to avoid division by zero.

    Parameters
    ----------
    known_lats:
        1-D array of latitudes for the source data points.
    known_lons:
        1-D array of longitudes for the source data points.
    known_values:
        1-D array of values at the source data points.
    grid_lats:
        1-D array of latitudes for the target grid points.
    grid_lons:
        1-D array of longitudes for the target grid points.
    power:
        IDW power parameter controlling how quickly influence decays with
        distance.  Higher values give more local influence to nearby points.
        Default is 2.

    Returns
    -------
    np.ndarray
        1-D array of interpolated values with the same length as *grid_lats* /
        *grid_lons*.
    """
    known_lats   = np.asarray(known_lats,   dtype=float)
    known_lons   = np.asarray(known_lons,   dtype=float)
    known_values = np.asarray(known_values, dtype=float)
    grid_lats    = np.asarray(grid_lats,    dtype=float)
    grid_lons    = np.asarray(grid_lons,    dtype=float)

    n_grid   = len(grid_lats)
    n_known  = len(known_lats)

    # Vectorised distance matrix: shape (n_grid, n_known)
    dlat = grid_lats[:, np.newaxis] - known_lats[np.newaxis, :]   # (G, K)
    dlon = grid_lons[:, np.newaxis] - known_lons[np.newaxis, :]   # (G, K)
    dist = np.sqrt(dlat ** 2 + dlon ** 2)                          # (G, K)

    result = np.empty(n_grid, dtype=float)

    # Identify grid points that coincide exactly with a known point.
    exact_mask = np.any(dist == 0.0, axis=1)   # (G,)

    # --- Exact coincidences: return the known value directly ---------------
    if np.any(exact_mask):
        exact_indices = np.where(exact_mask)[0]
        for gi in exact_indices:
            ki = np.argmin(dist[gi])   # index of the coinciding known point
            result[gi] = known_values[ki]

    # --- All other grid points: weighted average ---------------------------
    non_exact = ~exact_mask
    if np.any(non_exact):
        d_sub   = dist[non_exact]                  # (M, K)
        weights = 1.0 / (d_sub ** power)           # (M, K)
        result[non_exact] = (
            np.sum(weights * known_values[np.newaxis, :], axis=1)
            / np.sum(weights, axis=1)
        )

    return result


# ---------------------------------------------------------------------------
# 2. Japan grid factory
# ---------------------------------------------------------------------------

def create_japan_grid(
    lat_min: float = 24.0,
    lat_max: float = 46.0,
    lon_min: float = 122.0,
    lon_max: float = 146.0,
    resolution: float = 0.5,
) -> tuple[np.ndarray, np.ndarray]:
    """Create a regular latitude/longitude grid covering Japan.

    Parameters
    ----------
    lat_min:
        Southern boundary in decimal degrees.  Default 24.0 (Okinawa).
    lat_max:
        Northern boundary in decimal degrees.  Default 46.0 (Hokkaido).
    lon_min:
        Western boundary in decimal degrees.  Default 122.0.
    lon_max:
        Eastern boundary in decimal degrees.  Default 146.0.
    resolution:
        Grid spacing in degrees.  Default 0.5.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        ``(grid_lats, grid_lons)`` – both 1-D arrays produced by
        :func:`numpy.meshgrid` (flattened).  Together they enumerate every
        grid point in row-major order.
    """
    lats = np.arange(lat_min, lat_max + resolution * 0.5, resolution)
    lons = np.arange(lon_min, lon_max + resolution * 0.5, resolution)

    lon_grid, lat_grid = np.meshgrid(lons, lats)   # (rows=lat, cols=lon)

    return lat_grid.ravel(), lon_grid.ravel()


# ---------------------------------------------------------------------------
# 3. Color helpers
# ---------------------------------------------------------------------------

def di_to_normalized(
    di_value: float,
    di_min: float = 55.0,
    di_max: float = 85.0,
) -> float:
    """Normalize a discomfort index value to the [0, 1] range.

    Values below *di_min* clamp to 0.0; values above *di_max* clamp to 1.0.

    Parameters
    ----------
    di_value:
        Raw discomfort index value.
    di_min:
        Lower bound of the expected DI range.  Default 55.0.
    di_max:
        Upper bound of the expected DI range.  Default 85.0.

    Returns
    -------
    float
        Normalized value in ``[0.0, 1.0]``.
    """
    if di_max == di_min:
        return 0.0
    return float(np.clip((di_value - di_min) / (di_max - di_min), 0.0, 1.0))


def _di_to_rgb(di_value: float) -> tuple[int, int, int]:
    """Return the (R, G, B) colour for *di_value* by linearly interpolating
    between the entries in ``_COLOR_STOPS``.

    Values below the first stop return the first stop's colour; values above
    the last stop return the last stop's colour.
    """
    stops = _COLOR_STOPS

    if di_value <= stops[0][0]:
        return stops[0][1]
    if di_value >= stops[-1][0]:
        return stops[-1][1]

    # Find the surrounding pair of stops.
    for i in range(len(stops) - 1):
        lo_di, lo_rgb = stops[i]
        hi_di, hi_rgb = stops[i + 1]
        if lo_di <= di_value <= hi_di:
            t = (di_value - lo_di) / (hi_di - lo_di)   # 0..1 within segment
            r = int(round(lo_rgb[0] + t * (hi_rgb[0] - lo_rgb[0])))
            g = int(round(lo_rgb[1] + t * (hi_rgb[1] - lo_rgb[1])))
            b = int(round(lo_rgb[2] + t * (hi_rgb[2] - lo_rgb[2])))
            return (
                int(np.clip(r, 0, 255)),
                int(np.clip(g, 0, 255)),
                int(np.clip(b, 0, 255)),
            )

    # Fallback (should not be reached).
    return stops[-1][1]


def get_di_color(di_value: float) -> tuple[int, int, int, int]:
    """Return an RGBA colour tuple for a single discomfort index value.

    The colour scale maps the perceived thermal comfort level (不快指数) to
    a cool-to-hot palette:

    +---------+--------------------+----------------------------+
    | DI      | Japanese label     | Colour                     |
    +=========+====================+============================+
    | ≤ 55    | 不快でない         | Blue                       |
    +---------+--------------------+----------------------------+
    | 60–65   | やや不快           | Cyan → Yellow-green        |
    +---------+--------------------+----------------------------+
    | 65–70   | 不快               | Yellow-green → Orange      |
    +---------+--------------------+----------------------------+
    | 70–75   | かなり不快         | Orange → Red               |
    +---------+--------------------+----------------------------+
    | ≥ 80    | 暑くてたまらない   | Dark red / Magenta         |
    +---------+--------------------+----------------------------+

    Parameters
    ----------
    di_value:
        Discomfort index value.

    Returns
    -------
    tuple[int, int, int, int]
        ``(r, g, b, a)`` where each component is in ``[0, 255]`` and
        ``a`` is fixed at 220.
    """
    r, g, b = _di_to_rgb(di_value)
    return (r, g, b, _ALPHA_SINGLE)


# ---------------------------------------------------------------------------
# 4. High-level interpolation entry-point
# ---------------------------------------------------------------------------

def interpolate_discomfort_for_hour(
    df_hour: pd.DataFrame,
    resolution: float = 0.5,
) -> pd.DataFrame:
    """Interpolate discomfort index values to a regular Japan grid for one hour.

    Reads observed station values from *df_hour*, creates a regular grid with
    :func:`create_japan_grid`, runs :func:`idw_interpolate`, and attaches
    per-point RGBA colour values ready for use with Pydeck's HeatmapLayer.

    Parameters
    ----------
    df_hour:
        DataFrame filtered to a single hour.  Must contain the columns
        ``lat``, ``lon``, and ``discomfort_index``.
    resolution:
        Grid spacing in degrees passed to :func:`create_japan_grid`.
        Default 0.5.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns:

        * ``lat``               – grid point latitude
        * ``lon``               – grid point longitude
        * ``discomfort_index``  – IDW-interpolated DI value
        * ``color_r``           – red channel (0-255)
        * ``color_g``           – green channel (0-255)
        * ``color_b``           – blue channel (0-255)
        * ``color_a``           – alpha channel (fixed at 180)
    """
    known_lats   = df_hour["lat"].to_numpy(dtype=float)
    known_lons   = df_hour["lon"].to_numpy(dtype=float)
    known_values = df_hour["discomfort_index"].to_numpy(dtype=float)

    grid_lats, grid_lons = create_japan_grid(resolution=resolution)

    interpolated = idw_interpolate(
        known_lats, known_lons, known_values,
        grid_lats, grid_lons,
    )

    # Vectorised colour mapping.
    n = len(interpolated)
    color_r = np.empty(n, dtype=np.uint8)
    color_g = np.empty(n, dtype=np.uint8)
    color_b = np.empty(n, dtype=np.uint8)

    for i, di in enumerate(interpolated):
        r, g, b = _di_to_rgb(float(di))
        color_r[i] = r
        color_g[i] = g
        color_b[i] = b

    return pd.DataFrame(
        {
            "lat":              grid_lats,
            "lon":              grid_lons,
            "discomfort_index": interpolated,
            "color_r":          color_r,
            "color_g":          color_g,
            "color_b":          color_b,
            "color_a":          np.full(n, _ALPHA_HEATMAP, dtype=np.uint8),
        }
    )
