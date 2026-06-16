"""Weather data fetching and discomfort index calculation for Japanese prefectures."""

import logging
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

logger = logging.getLogger(__name__)

_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
_REQUEST_TIMEOUT = 10  # seconds
_HOURS_PER_DAY = 24

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

# Base humidity offsets by region (% relative to a mid-summer baseline)
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


def calculate_discomfort_index(temp_c: float, humidity: float) -> float:
    """Calculate the discomfort index (不快指数) from temperature and humidity.

    Formula: DI = 0.81 * T + 0.01 * U * (0.99 * T - 14.3) + 46.3

    Args:
        temp_c: Dry-bulb air temperature in degrees Celsius.
        humidity: Relative humidity in percent (0–100).

    Returns:
        The discomfort index value (dimensionless).
    """
    return 0.81 * temp_c + 0.01 * humidity * (0.99 * temp_c - 14.3) + 46.3


def fetch_weather_for_location(lat: float, lon: float) -> dict | None:
    """Fetch hourly temperature and humidity for a single location from Open-Meteo.

    Args:
        lat: Latitude of the location.
        lon: Longitude of the location.

    Returns:
        A dict with keys:
            - ``hours``: list of ISO-8601 datetime strings (48 h max)
            - ``temperature``: list of floats (°C)
            - ``humidity``: list of floats (%)
        Returns ``None`` if the request fails or the response is malformed.
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
        hours: list[str] = hourly.get("time", [])
        temperature: list[float] = hourly.get("temperature_2m", [])
        humidity: list[float] = hourly.get("relative_humidity_2m", [])

        if not hours or not temperature or not humidity:
            logger.warning("Empty hourly data for lat=%s, lon=%s", lat, lon)
            return None

        return {"hours": hours, "temperature": temperature, "humidity": humidity}

    except requests.exceptions.Timeout:
        logger.error("Request timed out for lat=%s, lon=%s", lat, lon)
    except requests.exceptions.RequestException as exc:
        logger.error("HTTP error for lat=%s, lon=%s: %s", lat, lon, exc)
    except (KeyError, ValueError) as exc:
        logger.error("Failed to parse response for lat=%s, lon=%s: %s", lat, lon, exc)

    return None


def _make_mock_hours(
    region: str,
    rng: np.random.Generator,
) -> tuple[list[float], list[float]]:
    """Generate 24 hours of mock temperature and humidity for a region.

    Args:
        region: Japanese region name used to apply climate offsets.
        rng: NumPy random generator for reproducible noise.

    Returns:
        A tuple of (temperatures, humidities) each of length 24.
    """
    temp_offset = _REGION_TEMP_OFFSET.get(region, 0.0)
    humidity_offset = _REGION_HUMIDITY_OFFSET.get(region, 0.0)

    hours = np.arange(_HOURS_PER_DAY, dtype=float)

    # Daily temperature cycle: coolest around 05:00, hottest around 14:00
    base_temp = 28.0 + temp_offset
    temps = base_temp + 5.0 * np.sin((hours - 5.0) / 12.0 * math.pi)
    temps += rng.uniform(-2.0, 2.0, size=_HOURS_PER_DAY)

    # Humidity is inversely correlated with temperature (higher at night)
    base_humidity = 70.0 + humidity_offset
    humidities = base_humidity + 10.0 * np.sin(hours / 8.0 * math.pi)
    humidities = np.clip(humidities + rng.uniform(-5.0, 5.0, size=_HOURS_PER_DAY), 20.0, 100.0)

    return temps.tolist(), humidities.tolist()


def fetch_all_prefectures(prefectures: list[dict]) -> pd.DataFrame:
    """Fetch live weather data for all prefectures and return a tidy DataFrame.

    For each prefecture the first 24 hours of forecast data are used. If the
    API call fails for any location, realistic mock data is substituted so the
    returned DataFrame always contains a complete set of rows.

    Args:
        prefectures: List of prefecture dicts with keys ``name``, ``name_en``,
            ``lat``, ``lon``, and ``region``.

    Returns:
        A ``pd.DataFrame`` with one row per (prefecture, hour) and columns:
        ``name``, ``name_en``, ``lat``, ``lon``, ``region``, ``hour``,
        ``time``, ``temperature``, ``humidity``, ``discomfort_index``.
    """
    rng = np.random.default_rng()
    rows: list[dict] = []

    for i, pref in enumerate(prefectures, start=1):
        name: str = pref["name"]
        logger.info(
            "Fetching weather [%d/%d]: %s (%s)",
            i,
            len(prefectures),
            name,
            pref["name_en"],
        )

        weather = fetch_weather_for_location(pref["lat"], pref["lon"])

        if weather is not None:
            hours_iso = weather["hours"][:_HOURS_PER_DAY]
            temperatures = weather["temperature"][:_HOURS_PER_DAY]
            humidities = weather["humidity"][:_HOURS_PER_DAY]
        else:
            logger.warning("Using mock data for %s", name)
            temperatures, humidities = _make_mock_hours(pref["region"], rng)
            # Build synthetic ISO timestamps anchored to today's midnight JST
            today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
            hours_iso = [f"{today}T{h:02d}:00" for h in range(_HOURS_PER_DAY)]

        for hour_idx, (iso_str, temp, hum) in enumerate(
            zip(hours_iso, temperatures, humidities)
        ):
            rows.append(
                {
                    "name": name,
                    "name_en": pref["name_en"],
                    "lat": pref["lat"],
                    "lon": pref["lon"],
                    "region": pref["region"],
                    "hour": hour_idx,
                    "time": pd.Timestamp(iso_str),
                    "temperature": round(float(temp), 1),
                    "humidity": round(float(hum), 1),
                    "discomfort_index": round(
                        calculate_discomfort_index(float(temp), float(hum)), 1
                    ),
                }
            )

    df = pd.DataFrame(rows)
    logger.info("Fetched data: %d rows for %d prefectures", len(df), len(prefectures))
    return df


def get_mock_data(prefectures: list[dict]) -> pd.DataFrame:
    """Generate realistic mock weather data for all prefectures across 24 hours.

    Temperature and humidity vary by region (e.g. 北海道 is cooler, 沖縄 is
    hotter and more humid) and follow a plausible diurnal cycle.

    Args:
        prefectures: List of prefecture dicts with keys ``name``, ``name_en``,
            ``lat``, ``lon``, and ``region``.

    Returns:
        A ``pd.DataFrame`` with one row per (prefecture, hour) and columns:
        ``name``, ``name_en``, ``lat``, ``lon``, ``region``, ``hour``,
        ``time``, ``temperature``, ``humidity``, ``discomfort_index``.
    """
    # Use a fixed seed for reproducibility during development / testing
    rng = np.random.default_rng(seed=42)
    rows: list[dict] = []

    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    for pref in prefectures:
        name: str = pref["name"]
        temperatures, humidities = _make_mock_hours(pref["region"], rng)

        for hour_idx, (temp, hum) in enumerate(zip(temperatures, humidities)):
            rows.append(
                {
                    "name": name,
                    "name_en": pref["name_en"],
                    "lat": pref["lat"],
                    "lon": pref["lon"],
                    "region": pref["region"],
                    "hour": hour_idx,
                    "time": pd.Timestamp(f"{today}T{hour_idx:02d}:00"),
                    "temperature": round(float(temp), 1),
                    "humidity": round(float(hum), 1),
                    "discomfort_index": round(
                        calculate_discomfort_index(float(temp), float(hum)), 1
                    ),
                }
            )

    df = pd.DataFrame(rows)
    logger.debug("Generated mock data: %d rows for %d prefectures", len(df), len(prefectures))
    return df
