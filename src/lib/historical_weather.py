"""Historical weather (hourly GHI + temperature) via Open-Meteo Archive.

Free, no auth. Open-Meteo aggregates ECMWF reanalysis. Goes back to 1940,
updated with a 5-day publishing lag.

Used to backtest "live-style" production estimates over recent periods :
GHI + temperature hour-by-hour are fed through the same formula
estimate_current_output_mw used in the live section.
"""

from __future__ import annotations

import logging
from datetime import date

import requests

logger = logging.getLogger(__name__)

API_URL = "https://archive-api.open-meteo.com/v1/archive"
TIMEOUT_SEC = 30


def fetch_archive_weather(
    lat: float,
    lon: float,
    start: date | str,
    end: date | str,
) -> dict | None:
    """Fetch historical hourly GHI + air temperature for a date range.

    Args :
        lat, lon : coords.
        start, end : date or 'YYYY-MM-DD' string. Inclusive.

    Returns dict with :
        timestamps : list[str] ISO 8601 hourly timestamps
        ghi_w_m2 : list[float] Global Horizontal Irradiance W/m²
        temp_c : list[float] air temperature 2 m °C
    None on any failure.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": str(start),
        "end_date": str(end),
        "hourly": "shortwave_radiation,temperature_2m",
        "timezone": "UTC",
    }
    try:
        resp = requests.get(API_URL, params=params, timeout=TIMEOUT_SEC)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning("Open-Meteo Archive fetch failed: %s", e)
        return None

    hourly = payload.get("hourly") or {}
    ts = hourly.get("time") or []
    ghi = hourly.get("shortwave_radiation") or []
    temp = hourly.get("temperature_2m") or []
    if not ts or not ghi or not temp:
        return None

    return {
        "timestamps": ts,
        "ghi_w_m2": [float(x) if x is not None else 0.0 for x in ghi],
        "temp_c": [float(x) if x is not None else 20.0 for x in temp],
    }
