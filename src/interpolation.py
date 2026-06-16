"""
Spatial interpolation utilities for Japan Discomfort Index (不快指数) visualization.

Provides:
  - IDW interpolation (original, fast)
  - CloughTocher2D smooth interpolation (C1 cubic, high quality)
  - Japan-coastline-clipped grid generation
  - Delaunay TIN wireframe for LineLayer
  - Color mapping utilities
"""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Color stop table: (DI threshold, (R, G, B))
# ---------------------------------------------------------------------------
_COLOR_STOPS: list[tuple[float, tuple[int, int, int]]] = [
    (55.0, (0,   100, 200)),   # blue        – 不快でない
    (60.0, (0,   200, 180)),   # cyan-green  – やや不快手前
    (65.0, (80,  220,  50)),   # yellow-green – やや不快
    (70.0, (255, 180,   0)),   # orange      – 不快
    (75.0, (255,  60,   0)),   # red-orange  – かなり不快
    (80.0, (200,   0,  80)),   # dark red/magenta – 非常に不快
]

_ALPHA_HEATMAP = 180
_ALPHA_SINGLE  = 220


# ---------------------------------------------------------------------------
# 1. IDW interpolation (fast fallback / standalone use)
# ---------------------------------------------------------------------------

def idw_interpolate(
    known_lats: np.ndarray,
    known_lons: np.ndarray,
    known_values: np.ndarray,
    grid_lats: np.ndarray,
    grid_lons: np.ndarray,
    power: float = 2,
) -> np.ndarray:
    """Inverse Distance Weighting interpolation (vectorised).

    Returns interpolated values at ``(grid_lats, grid_lons)`` using the
    weighted average of all known points.  Points that coincide exactly with
    a known point return that point's value directly.
    """
    known_lats   = np.asarray(known_lats,   dtype=float)
    known_lons   = np.asarray(known_lons,   dtype=float)
    known_values = np.asarray(known_values, dtype=float)
    grid_lats    = np.asarray(grid_lats,    dtype=float)
    grid_lons    = np.asarray(grid_lons,    dtype=float)

    dlat = grid_lats[:, np.newaxis] - known_lats[np.newaxis, :]
    dlon = grid_lons[:, np.newaxis] - known_lons[np.newaxis, :]
    dist = np.sqrt(dlat ** 2 + dlon ** 2)

    n_grid  = len(grid_lats)
    result  = np.empty(n_grid, dtype=float)

    exact_mask = np.any(dist == 0.0, axis=1)
    if np.any(exact_mask):
        for gi in np.where(exact_mask)[0]:
            result[gi] = known_values[np.argmin(dist[gi])]

    non_exact = ~exact_mask
    if np.any(non_exact):
        d_sub   = dist[non_exact]
        weights = 1.0 / (d_sub ** power)
        result[non_exact] = (
            np.sum(weights * known_values[np.newaxis, :], axis=1)
            / np.sum(weights, axis=1)
        )

    return result


# ---------------------------------------------------------------------------
# 2. Grid factories
# ---------------------------------------------------------------------------

def create_japan_grid(
    lat_min: float = 24.0,
    lat_max: float = 46.0,
    lon_min: float = 122.0,
    lon_max: float = 146.0,
    resolution: float = 0.5,
) -> tuple[np.ndarray, np.ndarray]:
    """Create a regular lat/lon grid covering Japan (full rectangular bbox)."""
    lats = np.arange(lat_min, lat_max + resolution * 0.5, resolution)
    lons = np.arange(lon_min, lon_max + resolution * 0.5, resolution)
    lon_grid, lat_grid = np.meshgrid(lons, lats)
    return lat_grid.ravel(), lon_grid.ravel()


def create_japan_grid_clipped(
    lat_min: float = 24.0,
    lat_max: float = 46.0,
    lon_min: float = 122.0,
    lon_max: float = 146.0,
    resolution: float = 0.5,
) -> tuple[np.ndarray, np.ndarray]:
    """Create a grid clipped to Japan's actual coastline polygon.

    Downloads Japan's boundary from Natural Earth on the first call
    (cached to ``.cache/japan_geom.gpkg``).  Falls back to the full
    rectangular grid when the geometry is unavailable.

    Uses ``shapely.contains_xy`` for fast vectorised point-in-polygon.
    """
    grid_lats, grid_lons = create_japan_grid(
        lat_min=lat_min, lat_max=lat_max,
        lon_min=lon_min, lon_max=lon_max,
        resolution=resolution,
    )

    japan_geom = _get_japan_geom()
    if japan_geom is None:
        logger.warning("Japan geometry unavailable – using full rectangular grid")
        return grid_lats, grid_lons

    try:
        from shapely import contains_xy
        # Small buffer (~5 km) to include coastal/island points
        buffered = japan_geom.buffer(0.05)
        mask = contains_xy(buffered, grid_lons, grid_lats)
    except Exception as exc:
        logger.warning("shapely.contains_xy failed (%s) – falling back to geopandas", exc)
        try:
            import geopandas as gpd
            pts  = gpd.GeoSeries.from_xy(grid_lons, grid_lats, crs="EPSG:4326")
            mask = pts.within(japan_geom.buffer(0.05)).values
        except Exception as exc2:
            logger.error("Grid clipping failed: %s", exc2)
            return grid_lats, grid_lons

    clipped_lats = grid_lats[mask]
    clipped_lons = grid_lons[mask]
    logger.info(
        "Grid clipped to Japan: %d / %d points retained (resolution=%.2f°)",
        len(clipped_lats), len(grid_lats), resolution,
    )
    return clipped_lats, clipped_lons


def _get_japan_geom():
    """Lazy import wrapper so interpolation.py has no hard dep on municipalities."""
    try:
        from municipalities import get_japan_geometry
        return get_japan_geometry()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 3. Color helpers
# ---------------------------------------------------------------------------

def di_to_normalized(
    di_value: float,
    di_min: float = 55.0,
    di_max: float = 85.0,
) -> float:
    """Normalise a DI value to [0, 1]."""
    if di_max == di_min:
        return 0.0
    return float(np.clip((di_value - di_min) / (di_max - di_min), 0.0, 1.0))


def _di_to_rgb(di_value: float) -> tuple[int, int, int]:
    """Piecewise-linear colour interpolation between ``_COLOR_STOPS``."""
    stops = _COLOR_STOPS
    if di_value <= stops[0][0]:
        return stops[0][1]
    if di_value >= stops[-1][0]:
        return stops[-1][1]
    for i in range(len(stops) - 1):
        lo_di, lo_rgb = stops[i]
        hi_di, hi_rgb = stops[i + 1]
        if lo_di <= di_value <= hi_di:
            t = (di_value - lo_di) / (hi_di - lo_di)
            r = int(np.clip(round(lo_rgb[0] + t * (hi_rgb[0] - lo_rgb[0])), 0, 255))
            g = int(np.clip(round(lo_rgb[1] + t * (hi_rgb[1] - lo_rgb[1])), 0, 255))
            b = int(np.clip(round(lo_rgb[2] + t * (hi_rgb[2] - lo_rgb[2])), 0, 255))
            return (r, g, b)
    return stops[-1][1]


def get_di_color(di_value: float) -> tuple[int, int, int, int]:
    """Return ``(r, g, b, a)`` for a single DI value (a=220)."""
    r, g, b = _di_to_rgb(di_value)
    return (r, g, b, _ALPHA_SINGLE)


def _add_colors(df: pd.DataFrame) -> pd.DataFrame:
    """Add color_r/g/b/a columns derived from discomfort_index."""
    n = len(df)
    cr = np.empty(n, dtype=np.uint8)
    cg = np.empty(n, dtype=np.uint8)
    cb = np.empty(n, dtype=np.uint8)
    for i, di in enumerate(df["discomfort_index"].to_numpy(dtype=float)):
        r, g, b = _di_to_rgb(float(di))
        cr[i] = r; cg[i] = g; cb[i] = b
    df = df.copy()
    df["color_r"] = cr
    df["color_g"] = cg
    df["color_b"] = cb
    df["color_a"] = np.full(n, _ALPHA_HEATMAP, dtype=np.uint8)
    return df


# ---------------------------------------------------------------------------
# 4. IDW interpolation pipeline (original, rectangular grid)
# ---------------------------------------------------------------------------

def interpolate_discomfort_for_hour(
    df_hour: pd.DataFrame,
    resolution: float = 0.5,
) -> pd.DataFrame:
    """IDW interpolation onto a full rectangular Japan grid (original method)."""
    known_lats   = df_hour["lat"].to_numpy(dtype=float)
    known_lons   = df_hour["lon"].to_numpy(dtype=float)
    known_values = df_hour["discomfort_index"].to_numpy(dtype=float)

    grid_lats, grid_lons = create_japan_grid(resolution=resolution)
    interpolated = idw_interpolate(
        known_lats, known_lons, known_values, grid_lats, grid_lons,
    )

    result = pd.DataFrame({
        "lat":              grid_lats,
        "lon":              grid_lons,
        "discomfort_index": np.round(interpolated, 1),
    })
    return _add_colors(result)


# ---------------------------------------------------------------------------
# 5. CloughTocher2D smooth interpolation (C1 cubic) – coastline-clipped grid
# ---------------------------------------------------------------------------

def interpolate_discomfort_smooth(
    df_hour: pd.DataFrame,
    resolution: float = 0.3,
) -> pd.DataFrame:
    """High-quality C1-cubic interpolation using CloughTocher2DInterpolator.

    The interpolation is performed on a grid clipped to Japan's coastline
    polygon, so ocean cells are removed.

    Points outside the convex hull of the input data (where CloughTocher
    returns NaN) are filled with IDW as a fallback, ensuring full coverage
    over the clipped grid.

    Args:
        df_hour: DataFrame for a single hour.  Must contain ``lat``, ``lon``,
            and ``discomfort_index`` columns.
        resolution: Grid spacing in degrees.  Default 0.3 (~33 km).

    Returns:
        DataFrame with lat, lon, discomfort_index, color_r/g/b/a columns.
    """
    from scipy.interpolate import CloughTocher2DInterpolator

    lons = df_hour["lon"].to_numpy(dtype=float)
    lats = df_hour["lat"].to_numpy(dtype=float)
    dis  = df_hour["discomfort_index"].to_numpy(dtype=float)

    grid_lats, grid_lons = create_japan_grid_clipped(resolution=resolution)

    ct = CloughTocher2DInterpolator(
        np.column_stack([lons, lats]),
        dis,
        fill_value=np.nan,
    )
    interpolated = ct(np.column_stack([grid_lons, grid_lats]))

    # Fill NaN (outside convex hull) with IDW
    nan_mask = np.isnan(interpolated)
    if nan_mask.any():
        fallback = idw_interpolate(
            lats, lons, dis,
            grid_lats[nan_mask], grid_lons[nan_mask],
        )
        interpolated[nan_mask] = fallback

    result = pd.DataFrame({
        "lat":              grid_lats,
        "lon":              grid_lons,
        "discomfort_index": np.round(interpolated, 1),
    })
    return _add_colors(result)


# ---------------------------------------------------------------------------
# 6. Delaunay TIN wireframe for pydeck LineLayer
# ---------------------------------------------------------------------------

def create_tin_wireframe(
    df_hour: pd.DataFrame,
    elevation_scale: float = 9000.0,
    base_di: float = 55.0,
) -> list[dict]:
    """Build Delaunay TIN edge list for pydeck ``LineLayer`` (3-D lines).

    Each edge is a dict with::

        {
          "source": [lon_a, lat_a, elevation_a],
          "target": [lon_b, lat_b, elevation_b],
        }

    The elevation encodes the discomfort index so the wireframe follows the
    same height profile as the surface layer.

    Args:
        df_hour: DataFrame for a single hour.
        elevation_scale: Metres per DI unit above ``base_di``.
        base_di: DI value at elevation 0.

    Returns:
        List of edge dicts ready to be passed as ``data`` to a pydeck Layer.
    """
    from scipy.spatial import Delaunay

    lons = df_hour["lon"].to_numpy(dtype=float)
    lats = df_hour["lat"].to_numpy(dtype=float)
    dis  = df_hour["discomfort_index"].to_numpy(dtype=float)

    pts = np.column_stack([lons, lats])
    tri = Delaunay(pts)

    seen: set[tuple[int, int]] = set()
    edges: list[dict] = []
    for simplex in tri.simplices:
        for i in range(3):
            a, b = simplex[i], simplex[(i + 1) % 3]
            key = (min(a, b), max(a, b))
            if key not in seen:
                seen.add(key)
                ea = float(max(0.0, (dis[a] - base_di) * elevation_scale))
                eb = float(max(0.0, (dis[b] - base_di) * elevation_scale))
                edges.append({
                    "source": [float(lons[a]), float(lats[a]), ea],
                    "target": [float(lons[b]), float(lats[b]), eb],
                })

    logger.debug("TIN wireframe: %d edges from %d points", len(edges), len(lons))
    return edges
