"""
Japanese populated-place data for dense spatial sampling.

Downloads and caches (in order of preference):
  1. GeoNames JP dump      (~15 MB, 1700+ municipalities)  → .cache/japan_geonames.parquet
  2. Natural Earth 10 m    (fallback, ~70 cities)           → .cache/japan_ne10m.parquet
  3. Japan boundary polygon (Natural Earth 50 m)            → .cache/japan_geom.gpkg
"""

import io
import logging
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(__file__).parent.parent / ".cache"
_JAPAN_GEOM_PATH       = _CACHE_DIR / "japan_geom.gpkg"
_GEONAMES_CACHE_PATH   = _CACHE_DIR / "japan_geonames.parquet"
_NE10M_CACHE_PATH      = _CACHE_DIR / "japan_ne10m.parquet"

_NE_50M_COUNTRIES  = (
    "https://naturalearth.s3.amazonaws.com/50m_cultural/ne_50m_admin_0_countries.zip"
)
_NE_10M_PLACES = (
    "https://naturalearth.s3.amazonaws.com/10m_cultural/ne_10m_populated_places.zip"
)
_GEONAMES_JP_URL   = "https://download.geonames.org/export/dump/JP.zip"

# GeoNames admin1_code for Japan
# Source: admin1CodesASCII.txt  (JP.01-46 = alphabetical, JP.47 = Okinawa special)
_ADMIN1_REGION: dict[str, str] = {
    "01": "中部",   # Aichi
    "02": "東北",   # Akita
    "03": "東北",   # Aomori
    "04": "関東",   # Chiba
    "05": "四国",   # Ehime
    "06": "中部",   # Fukui
    "07": "九州",   # Fukuoka
    "08": "東北",   # Fukushima
    "09": "中部",   # Gifu
    "10": "関東",   # Gunma
    "11": "中国",   # Hiroshima
    "12": "北海道", # Hokkaido
    "13": "近畿",   # Hyogo
    "14": "関東",   # Ibaraki
    "15": "中部",   # Ishikawa
    "16": "東北",   # Iwate
    "17": "四国",   # Kagawa
    "18": "九州",   # Kagoshima
    "19": "関東",   # Kanagawa
    "20": "四国",   # Kochi
    "21": "九州",   # Kumamoto
    "22": "近畿",   # Kyoto
    "23": "近畿",   # Mie
    "24": "東北",   # Miyagi
    "25": "九州",   # Miyazaki
    "26": "中部",   # Nagano
    "27": "九州",   # Nagasaki
    "28": "近畿",   # Nara
    "29": "中部",   # Niigata
    "30": "九州",   # Oita
    "31": "中国",   # Okayama
    "32": "近畿",   # Osaka
    "33": "九州",   # Saga
    "34": "関東",   # Saitama
    "35": "近畿",   # Shiga
    "36": "中国",   # Shimane
    "37": "中部",   # Shizuoka
    "38": "関東",   # Tochigi
    "39": "四国",   # Tokushima
    "40": "関東",   # Tokyo
    "41": "中国",   # Tottori
    "42": "中部",   # Toyama
    "43": "近畿",   # Wakayama
    "44": "東北",   # Yamagata
    "45": "中国",   # Yamaguchi
    "46": "中部",   # Yamanashi
    "47": "沖縄",   # Okinawa (special: uses JIS code 47, not alphabetical)
}

# Natural Earth ADM1NAME (English) → region
_ADM1_REGION: dict[str, str] = {
    "Hokkaido": "北海道",
    "Aomori": "東北", "Iwate": "東北", "Miyagi": "東北",
    "Akita": "東北", "Yamagata": "東北", "Fukushima": "東北",
    "Ibaraki": "関東", "Tochigi": "関東", "Gunma": "関東",
    "Saitama": "関東", "Chiba": "関東", "Tokyo": "関東",
    "Kanagawa": "関東",
    "Niigata": "中部", "Toyama": "中部", "Ishikawa": "中部",
    "Fukui": "中部", "Yamanashi": "中部", "Nagano": "中部",
    "Gifu": "中部", "Shizuoka": "中部", "Aichi": "中部",
    "Mie": "近畿", "Shiga": "近畿", "Kyoto": "近畿",
    "Osaka": "近畿", "Hyogo": "近畿", "Nara": "近畿",
    "Wakayama": "近畿",
    "Tottori": "中国", "Shimane": "中国", "Okayama": "中国",
    "Hiroshima": "中国", "Yamaguchi": "中国",
    "Tokushima": "四国", "Kagawa": "四国",
    "Ehime": "四国", "Kochi": "四国",
    "Fukuoka": "九州", "Saga": "九州", "Nagasaki": "九州",
    "Kumamoto": "九州", "Oita": "九州", "Miyazaki": "九州",
    "Kagoshima": "九州",
    "Okinawa": "沖縄",
}

# GeoNames feature codes covering cities / towns / admin seats
_GEONAMES_PCODES = frozenset({
    "ADM2", "ADM3",               # administrative divisions (municipality level)
    "PPL",                         # populated place
    "PPLA", "PPLA2", "PPLA3", "PPLA4",  # seats of admin divisions
    "PPLC",                        # capital city
})


def _region_from_coords(lat: float, lon: float) -> str:
    """Fallback region estimation from lat/lon."""
    if lat >= 41.5:  return "北海道"
    if lat >= 37.0:  return "東北"
    if lat >= 35.5:  return "関東" if lon >= 138.5 else "中部"
    if lat >= 34.0:
        if lon >= 135.5: return "近畿"
        if lon >= 132.5: return "中国"
        return "四国" if lon >= 132.0 else "九州"
    if lat >= 30.0:  return "九州"
    return "沖縄"


# ---------------------------------------------------------------------------
# Japan boundary polygon
# ---------------------------------------------------------------------------

def get_japan_geometry():
    """Download and cache Japan's polygon from Natural Earth 50 m.

    Returns a shapely geometry (MultiPolygon / Polygon), or ``None`` on failure.
    Persisted to ``.cache/japan_geom.gpkg`` for subsequent calls.
    """
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if _JAPAN_GEOM_PATH.exists():
        try:
            gdf = gpd.read_file(str(_JAPAN_GEOM_PATH))
            return gdf.geometry.union_all()
        except Exception as exc:
            logger.warning("Cached geometry unreadable – re-downloading: %s", exc)
            _JAPAN_GEOM_PATH.unlink(missing_ok=True)

    try:
        logger.info("Downloading Japan boundary (Natural Earth 50 m)…")
        world = gpd.read_file(_NE_50M_COUNTRIES)
        japan = gpd.GeoDataFrame()
        for col in ("ADMIN", "NAME", "SOVEREIGNT", "NAME_LONG"):
            if col in world.columns:
                candidate = world[world[col] == "Japan"]
                if not candidate.empty:
                    japan = candidate.copy()
                    break
        if japan.empty:
            logger.error("Japan not found in Natural Earth 50 m data")
            return None
        japan[["geometry"]].to_file(str(_JAPAN_GEOM_PATH), driver="GPKG")
        return japan.geometry.union_all()
    except Exception as exc:
        logger.error("Failed to download Japan geometry: %s", exc)
        return None


# ---------------------------------------------------------------------------
# GeoNames JP (primary – comprehensive municipality data)
# ---------------------------------------------------------------------------

def _download_geonames() -> list[dict]:
    """Download GeoNames JP dump and extract municipality-level places.

    Returns a list of dicts with keys: name, name_en, lat, lon, region.
    Filters for populated-place / administrative feature codes and
    population >= 3000 to avoid tiny hamlets while keeping all cities
    and most towns.
    """
    logger.info("Downloading GeoNames Japan dump (~15 MB)…")
    try:
        resp = requests.get(_GEONAMES_JP_URL, timeout=120)
        resp.raise_for_status()
    except Exception as exc:
        logger.error("GeoNames download failed: %s", exc)
        return []

    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            with zf.open("JP.txt") as f:
                content = f.read().decode("utf-8")
    except Exception as exc:
        logger.error("GeoNames ZIP extraction failed: %s", exc)
        return []

    rows: list[dict] = []
    for line in content.splitlines():
        parts = line.split("\t")
        if len(parts) < 19:
            continue
        feature_class = parts[6]
        feature_code  = parts[7]
        if feature_class not in ("P", "A") or feature_code not in _GEONAMES_PCODES:
            continue
        try:
            lat = float(parts[4])
            lon = float(parts[5])
            pop = int(parts[14]) if parts[14] else 0
        except ValueError:
            continue
        # Keep all admin-division entries regardless of population;
        # for generic populated places require pop >= 3000
        if feature_class == "P" and feature_code == "PPL" and pop < 3000:
            continue
        admin1 = parts[10].zfill(2)
        region = _ADMIN1_REGION.get(admin1, _region_from_coords(lat, lon))
        rows.append({
            "name":     parts[1],
            "name_en":  parts[2] or parts[1],
            "lat":      round(lat, 6),
            "lon":      round(lon, 6),
            "region":   region,
        })

    logger.info("GeoNames: %d raw records for Japan", len(rows))
    return rows


# ---------------------------------------------------------------------------
# Natural Earth 10 m (fallback – ~70 cities)
# ---------------------------------------------------------------------------

def _download_ne10m() -> list[dict]:
    """Download Natural Earth 10 m populated places for Japan (fallback)."""
    try:
        logger.info("Downloading Natural Earth 10 m populated places (fallback)…")
        places = gpd.read_file(_NE_10M_PLACES)
        japan = gpd.GeoDataFrame()
        for col, val in [("ADM0_A3", "JPN"), ("ADM0NAME", "Japan"), ("SOV0NAME", "Japan")]:
            if col in places.columns:
                candidate = places[places[col] == val]
                if not candidate.empty:
                    japan = candidate.copy()
                    break
        if japan.empty:
            return []
        rows = []
        for _, row in japan.iterrows():
            lat   = float(row.geometry.y)
            lon   = float(row.geometry.x)
            adm1  = str(row.get("ADM1NAME") or "")
            region = _ADM1_REGION.get(adm1, _region_from_coords(lat, lon))
            name  = str(row.get("NAME") or row.get("NAMEASCII") or "")
            rows.append({"name": name, "name_en": name,
                         "lat": round(lat, 6), "lon": round(lon, 6), "region": region})
        return rows
    except Exception as exc:
        logger.error("Natural Earth 10 m download failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_all_municipalities() -> list[dict]:
    """Return Japanese municipality / city coordinates, cached to disk.

    Strategy (in order):
      1. Load ``japan_geonames.parquet`` from disk cache if present.
      2. Download GeoNames JP dump (1700+ municipalities; ~15 MB, once only).
      3. If GeoNames fails, fall back to Natural Earth 10 m (~70 cities).
      4. Return empty list on complete failure (caller falls back to PREFECTURES).
    """
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # ── Try GeoNames cache ────────────────────────────────────────────────────
    if _GEONAMES_CACHE_PATH.exists():
        try:
            df = pd.read_parquet(str(_GEONAMES_CACHE_PATH))
            logger.info("Loaded %d municipalities from GeoNames cache", len(df))
            return df.to_dict("records")
        except Exception as exc:
            logger.warning("GeoNames cache unreadable – re-downloading: %s", exc)
            _GEONAMES_CACHE_PATH.unlink(missing_ok=True)

    # ── Try Natural Earth 10 m cache (legacy) ─────────────────────────────────
    # (kept for backward compatibility; will be superseded by GeoNames on next download)
    if _NE10M_CACHE_PATH.exists():
        try:
            df = pd.read_parquet(str(_NE10M_CACHE_PATH))
            if len(df) >= 100:
                logger.info("Loaded %d municipalities from NE10m cache", len(df))
                return df.to_dict("records")
            # Too few – fall through to fresh download
        except Exception:
            pass

    # ── Download GeoNames (primary) ───────────────────────────────────────────
    rows = _download_geonames()

    if not rows:
        # ── Fall back to Natural Earth 10 m ──────────────────────────────────
        logger.warning("GeoNames failed – falling back to Natural Earth 10 m")
        rows = _download_ne10m()
        if not rows:
            logger.error("All municipality downloads failed")
            return []
        df = (
            pd.DataFrame(rows)
            .dropna(subset=["lat", "lon"])
            .drop_duplicates(subset=["lat", "lon"])
            .reset_index(drop=True)
        )
        df.to_parquet(str(_NE10M_CACHE_PATH))
        logger.info("Saved %d municipalities (NE10m) to cache", len(df))
        return df.to_dict("records")

    # GeoNames succeeded
    df = (
        pd.DataFrame(rows)
        .dropna(subset=["lat", "lon"])
        .drop_duplicates(subset=["lat", "lon"])
        .reset_index(drop=True)
    )
    df.to_parquet(str(_GEONAMES_CACHE_PATH))
    logger.info("Saved %d municipalities (GeoNames) to cache", len(df))
    return df.to_dict("records")
