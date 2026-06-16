"""Weather data fetching and discomfort index calculation for Japanese prefectures."""

import logging
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

logger = logging.getLogger(__name__)

_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
_REQUEST_TIMEOUT = 10  # seconds
_HOURS_PER_DAY = 24
_MAX_STATIONS = 3000   # guard against accidentally huge station lists

# Base temperature offsets by region (°C relative to a mid-summer baseline)
_REGION_TEMP_OFFSET: dict[str, float] = {
    "北海道": -6.0,
    "東北": -4.0,
    "関東": 0.0,
    "中部": -1.0,
    "近畿": 1.0,
    "中国": 0.5,
    "四国": 1.0,
    "九州": 1.5,
    "沖縄": 4.0,
}

_REGION_HUMIDITY_OFFSET: dict[str, float] = {
    "北海道": -10.0,
    "東北": -5.0,
    "関東": 0.0,
    "中部": -2.0,
    "近畿": 2.0,
    "中国": 0.0,
    "四国": 3.0,
    "九州": 4.0,
    "沖縄": 8.0,
}


# ---------------------------------------------------------------------------
# Core formula
# ---------------------------------------------------------------------------

def calculate_discomfort_index(temp_c: float, humidity: float) -> float:
    """DI = 0.81*T + 0.01*U*(0.99*T - 14.3) + 46.3"""
    return 0.81 * temp_c + 0.01 * humidity * (0.99 * temp_c - 14.3) + 46.3


# ---------------------------------------------------------------------------
# Single-location fetch
# ---------------------------------------------------------------------------

def fetch_weather_for_location(lat: float, lon: float) -> dict | None:
    """Fetch 48-hour hourly temperature and humidity from Open-Meteo.

    Returns ``{"hours": [...], "temperature": [...], "humidity": [...]}``
    or ``None`` on any failure.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,relative_humidity_2m",
        "forecast_days": 2,
        "timezone": "Asia/Tokyo",
    }
    try:
        response = requests.get(_OPEN_METEO_URL, params=params, timeout=_REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        hourly = data.get("hourly", {})
        hours       = hourly.get("time", [])
        temperature = hourly.get("temperature_2m", [])
        humidity    = hourly.get("relative_humidity_2m", [])
        if not hours or not temperature or not humidity:
            logger.warning("Empty hourly data for lat=%s, lon=%s", lat, lon)
            return None
        return {"hours": hours, "temperature": temperature, "humidity": humidity}
    except requests.exceptions.Timeout:
        logger.error("Timeout for lat=%s, lon=%s", lat, lon)
    except requests.exceptions.RequestException as exc:
        logger.error("HTTP error for lat=%s, lon=%s: %s", lat, lon, exc)
    except (KeyError, ValueError) as exc:
        logger.error("Parse error for lat=%s, lon=%s: %s", lat, lon, exc)
    return None


# ---------------------------------------------------------------------------
# Mock data helpers
# ---------------------------------------------------------------------------

def _make_mock_hours(
    region: str,
    rng: np.random.Generator,
) -> tuple[list[float], list[float]]:
    """Generate 24 hours of synthetic temperature and humidity for a region."""
    temp_offset     = _REGION_TEMP_OFFSET.get(region, 0.0)
    humidity_offset = _REGION_HUMIDITY_OFFSET.get(region, 0.0)
    hours = np.arange(_HOURS_PER_DAY, dtype=float)

    base_temp  = 28.0 + temp_offset
    temps      = base_temp + 5.0 * np.sin((hours - 5.0) / 12.0 * math.pi)
    temps     += rng.uniform(-2.0, 2.0, size=_HOURS_PER_DAY)

    base_hum   = 70.0 + humidity_offset
    humidities = base_hum + 10.0 * np.sin(hours / 8.0 * math.pi)
    humidities = np.clip(
        humidities + rng.uniform(-5.0, 5.0, size=_HOURS_PER_DAY), 20.0, 100.0
    )
    return temps.tolist(), humidities.tolist()


def _build_rows(
    station: dict,
    hours_iso: list[str],
    temperatures: list[float],
    humidities: list[float],
) -> list[dict]:
    """Convert parallel lists into per-hour row dicts."""
    rows = []
    for hour_idx, (iso_str, temp, hum) in enumerate(
        zip(hours_iso, temperatures, humidities)
    ):
        rows.append(
            {
                "name":             station["name"],
                "name_en":          station["name_en"],
                "lat":              station["lat"],
                "lon":              station["lon"],
                "region":           station["region"],
                "hour":             hour_idx,
                "time":             pd.Timestamp(iso_str),
                "temperature":      round(float(temp), 1),
                "humidity":         round(float(hum), 1),
                "discomfort_index": round(
                    calculate_discomfort_index(float(temp), float(hum)), 1
                ),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Sequential fetch (47 prefectures – original)
# ---------------------------------------------------------------------------

def fetch_all_prefectures(prefectures: list[dict]) -> pd.DataFrame:
    """Sequential fetch for 47 prefecture capitals."""
    rng  = np.random.default_rng()
    rows: list[dict] = []
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    for i, pref in enumerate(prefectures, start=1):
        logger.info("Fetching [%d/%d]: %s", i, len(prefectures), pref["name"])
        weather = fetch_weather_for_location(pref["lat"], pref["lon"])
        if weather is not None:
            hours_iso    = weather["hours"][:_HOURS_PER_DAY]
            temperatures = weather["temperature"][:_HOURS_PER_DAY]
            humidities   = weather["humidity"][:_HOURS_PER_DAY]
        else:
            logger.warning("Mock fallback for %s", pref["name"])
            temperatures, humidities = _make_mock_hours(pref["region"], rng)
            hours_iso = [f"{today}T{h:02d}:00" for h in range(_HOURS_PER_DAY)]
        rows.extend(_build_rows(pref, hours_iso, temperatures, humidities))

    df = pd.DataFrame(rows)
    logger.info("Sequential fetch done: %d rows, %d stations", len(df), len(prefectures))
    return df


# ---------------------------------------------------------------------------
# Parallel fetch (全市町村 mode)
# ---------------------------------------------------------------------------

def fetch_all_parallel(
    stations: list[dict],
    max_workers: int = 15,
) -> pd.DataFrame:
    """Fetch weather for all stations concurrently using a thread pool.

    Stations that fail the API call fall back to mock data so the returned
    DataFrame is always complete.

    Args:
        stations:    List of station dicts (name, name_en, lat, lon, region).
        max_workers: Max concurrent HTTP requests.  Default 15.

    Returns:
        DataFrame with the same schema as ``fetch_all_prefectures``.
    """
    if len(stations) > _MAX_STATIONS:
        logger.warning(
            "Station list truncated from %d to %d", len(stations), _MAX_STATIONS
        )
        stations = stations[:_MAX_STATIONS]

    rng   = np.random.default_rng()
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    # Parallel HTTP requests
    results: dict[str, tuple[dict, dict | None]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_station = {
            executor.submit(fetch_weather_for_location, s["lat"], s["lon"]): s
            for s in stations
        }
        for future in as_completed(future_to_station):
            s = future_to_station[future]
            try:
                weather = future.result()
            except Exception as exc:
                logger.error("Fetch error for %s: %s", s["name"], exc)
                weather = None
            results[s["name"]] = (s, weather)

    n_ok = sum(1 for _, (_, w) in results.items() if w is not None)
    logger.info(
        "Parallel fetch done: %d/%d succeeded (%d workers)",
        n_ok, len(stations), max_workers,
    )

    # Build rows
    rows: list[dict] = []
    for _name, (station, weather) in results.items():
        if weather is not None:
            hours_iso    = weather["hours"][:_HOURS_PER_DAY]
            temperatures = weather["temperature"][:_HOURS_PER_DAY]
            humidities   = weather["humidity"][:_HOURS_PER_DAY]
        else:
            temperatures, humidities = _make_mock_hours(station["region"], rng)
            hours_iso = [f"{today}T{h:02d}:00" for h in range(_HOURS_PER_DAY)]
        rows.extend(_build_rows(station, hours_iso, temperatures, humidities))

    df = pd.DataFrame(rows)
    logger.info("Built DataFrame: %d rows, %d stations", len(df), len(stations))
    return df


# ---------------------------------------------------------------------------
# Pure mock (no network)
# ---------------------------------------------------------------------------

def get_mock_data(prefectures: list[dict]) -> pd.DataFrame:
    """Generate deterministic mock weather data (no network calls)."""
    rng   = np.random.default_rng(seed=42)
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    rows: list[dict] = []
    for pref in prefectures:
        temperatures, humidities = _make_mock_hours(pref["region"], rng)
        hours_iso = [f"{today}T{h:02d}:00" for h in range(_HOURS_PER_DAY)]
        rows.extend(_build_rows(pref, hours_iso, temperatures, humidities))
    df = pd.DataFrame(rows)
    logger.debug("Mock data: %d rows, %d stations", len(df), len(prefectures))
    return df
