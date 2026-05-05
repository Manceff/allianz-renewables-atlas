"""Live weather (irradiance + temp + cloud) via Open-Meteo — free, no auth.

Open-Meteo aggregates ECMWF + GFS + Meteo-France etc. Updates every ~15 min.
Used to estimate the current power output of a solar park from public data.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

API_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_SEC = 15


def fetch_current_weather(lat: float, lon: float) -> dict[str, Any] | None:
    """Return current weather for the given coords, or None on failure.

    Returns dict with keys:
        ghi_w_m2 : Global Horizontal Irradiance (W/m²)
        temp_c : air temperature at 2 m (°C)
        cloud_cover_pct : cloud cover (%)
        wind_ms : wind speed at 10 m (m/s)
        direct_w_m2 : direct on horizontal (W/m²)
        diffuse_w_m2 : diffuse horizontal (W/m²)
        dni_w_m2 : direct normal irradiance (W/m²)
        time_iso : timestamp of the measurement (ISO 8601)
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": (
            "shortwave_radiation,temperature_2m,cloud_cover,"
            "wind_speed_10m,direct_radiation,diffuse_radiation,"
            "direct_normal_irradiance"
        ),
        "timezone": "auto",
    }
    try:
        resp = requests.get(API_URL, params=params, timeout=TIMEOUT_SEC)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning("Open-Meteo fetch failed: %s", e)
        return None

    current = payload.get("current") or {}
    if not current:
        return None

    return {
        "ghi_w_m2": float(current.get("shortwave_radiation") or 0.0),
        "temp_c": float(current.get("temperature_2m") or 20.0),
        "cloud_cover_pct": float(current.get("cloud_cover") or 0.0),
        "wind_ms": float(current.get("wind_speed_10m") or 0.0),
        "direct_w_m2": float(current.get("direct_radiation") or 0.0),
        "diffuse_w_m2": float(current.get("diffuse_radiation") or 0.0),
        "dni_w_m2": float(current.get("direct_normal_irradiance") or 0.0),
        "time_iso": str(current.get("time") or ""),
    }


def fetch_today_hourly_weather(lat: float, lon: float) -> dict[str, Any] | None:
    """Fetch hourly weather for today (past hours have actuals, future is forecast).

    Returns dict with parallel hourly arrays :
        timestamps : list[str] ISO 8601, local timezone
        ghi_w_m2 : list[float]
        temp_c : list[float]
        wind_ms : list[float]
        is_past : list[bool] — whether the hour has already passed
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "shortwave_radiation,temperature_2m,wind_speed_10m,is_day",
        "timezone": "auto",
        "forecast_days": 1,
        "past_days": 0,
    }
    try:
        resp = requests.get(API_URL, params=params, timeout=TIMEOUT_SEC)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning("Open-Meteo today-hourly fetch failed: %s", e)
        return None

    hourly = payload.get("hourly") or {}
    times = hourly.get("time", [])
    ghi = hourly.get("shortwave_radiation", [])
    temp = hourly.get("temperature_2m", [])
    wind = hourly.get("wind_speed_10m", [])
    if not times or not ghi:
        return None

    # Determine which hours are "past" relative to local now
    import datetime as _dt
    tz = payload.get("timezone", "UTC")
    # Open-Meteo returns local-zone strings (e.g. "2026-05-05T14:00")
    # Compare to current time at the same location
    current_time_str = (payload.get("current_weather") or {}).get("time", "")
    if not current_time_str:
        # Fallback: assume "now" by best-effort
        now_local = _dt.datetime.utcnow()
    else:
        try:
            now_local = _dt.datetime.fromisoformat(current_time_str)
        except ValueError:
            now_local = _dt.datetime.utcnow()

    is_past = []
    for t in times:
        try:
            t_dt = _dt.datetime.fromisoformat(t)
            is_past.append(t_dt <= now_local)
        except ValueError:
            is_past.append(False)

    return {
        "timestamps": list(times),
        "ghi_w_m2": [float(x or 0.0) for x in ghi],
        "temp_c": [float(x or 20.0) for x in temp],
        "wind_ms": [float(x or 1.0) for x in wind],
        "is_past": is_past,
        "timezone": tz,
    }


def estimate_current_output_mw(
    capacity_mwp: float,
    ghi_w_m2: float,
    temp_c: float,
    loss_pct: float = 14.0,
) -> float:
    """Estimate the current AC power output of a solar park (MW).

    Simple defensible model :
        P_AC = capacity_MWp × (GHI / 1000) × (1 - loss%) × temperature_derating

    where:
        T_cell ≈ T_air + 25°C × (GHI / 800)   — rough panel-temperature model
        temp_derating = 1 - 0.004 × max(0, T_cell - 25°C)

    Capacity factor is the panel reference at 1000 W/m² (STC). Above 1000 W/m²
    is rare in realistic conditions, so we don't clip.

    Args:
        capacity_mwp: park peak capacity in MWp.
        ghi_w_m2: current Global Horizontal Irradiance in W/m².
        temp_c: current air temperature in °C.
        loss_pct: system losses (default 14% per PVGIS standard).

    Returns:
        Estimated AC power output in MW. Always >= 0.
    """
    if capacity_mwp <= 0 or ghi_w_m2 <= 0:
        return 0.0

    irradiance_factor = ghi_w_m2 / 1000.0
    loss_factor = 1.0 - (loss_pct / 100.0)

    # Panel cell temperature approximation (Sandia / NOCT-like simplification)
    t_cell = temp_c + 25.0 * (ghi_w_m2 / 800.0)
    temp_derating = 1.0 - 0.004 * max(0.0, t_cell - 25.0)
    temp_derating = max(0.5, temp_derating)  # safety floor

    return capacity_mwp * irradiance_factor * loss_factor * temp_derating
