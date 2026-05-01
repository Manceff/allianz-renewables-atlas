"""Backtest production + revenue over a date range.

Two modes :

1. Recent (Open-Meteo archive) :
   GHI + temp from Open-Meteo Archive → live-style formula
   × hourly day-ahead prices for the same period
   → "what the park earned (estimated) over the last N days"

2. 2023 same period (PVGIS hourly cached) :
   PVGIS production for the same calendar week-of-year × 2023 spot prices
   → "what the park earned over the same week in 2023"

Comparing the two reveals how the market context has evolved
(cannibalisation aggravation), independent of the climatic year.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from src.lib.electricity_prices import fetch_period_prices
from src.lib.solar_model import compute_period_production

logger = logging.getLogger(__name__)


def backtest_recent_period(
    lat: float,
    lon: float,
    capacity_mwp: float,
    zone: str | None,
    start: date,
    end: date,
) -> dict | None:
    """Backtest a recent period — SAME pvlib pipeline as the baseline.

    Cohérence with backtest_baseline_period : both use compute_period_production
    so the only differences come from real climate + real prices, not from
    model differences.

    Returns dict with :
        production_mwh, revenue_eur, effective_price_eur_mwh,
        avg_dayahead_price_eur_mwh, cannibalisation_pct,
        hours_with_prices, days
    """
    period = compute_period_production(
        lat=lat, lon=lon, capacity_mwp=capacity_mwp,
        start_date=start, end_date=end,
    )
    if not period:
        return None

    hourly_prod_mwh = [x / 1000.0 for x in period["hourly_production_kwh"]]

    if not zone:
        return _summary_no_prices(hourly_prod_mwh, (end - start).days + 1)

    prices = fetch_period_prices(zone, str(start), str(end))
    if not prices:
        return _summary_no_prices(hourly_prod_mwh, (end - start).days + 1)

    return _combine(hourly_prod_mwh, prices["prices_eur_mwh"], (end - start).days + 1)


def backtest_baseline_period(
    baseline_hourly_kwh: list[float],
    baseline_year: int,
    zone: str | None,
    start: date,
    end: date,
) -> dict | None:
    """Backtest the same calendar week/month in a chosen baseline year.

    Slices the cached pvlib year-of-data (2023, 2024…) at the same calendar window,
    multiplies by spot prices for that year window. Lets the caller compare any
    pair of years.

    Args :
        baseline_hourly_kwh : 8760 hourly values for `baseline_year` (from solar_model).
        baseline_year : the year of the cached production data.
        zone : bidding zone for prices.
        start, end : the recent window — mapped to the same calendar in baseline_year.
    """
    bl_start = date(baseline_year, start.month, start.day)
    bl_end = date(baseline_year, end.month, end.day)

    doy_start = bl_start.timetuple().tm_yday
    doy_end = bl_end.timetuple().tm_yday
    if doy_end < doy_start or doy_end > 366:
        return None
    idx_start = (doy_start - 1) * 24
    idx_end = doy_end * 24
    if idx_end > len(baseline_hourly_kwh):
        idx_end = len(baseline_hourly_kwh)

    sliced_kwh = baseline_hourly_kwh[idx_start:idx_end]
    sliced_mwh = [x / 1000.0 for x in sliced_kwh]

    if not zone:
        return _summary_no_prices(sliced_mwh, (end - start).days + 1)

    prices_bl = fetch_period_prices(zone, str(bl_start), str(bl_end))
    if not prices_bl:
        return _summary_no_prices(sliced_mwh, (end - start).days + 1)

    return _combine(sliced_mwh, prices_bl["prices_eur_mwh"], (end - start).days + 1)


# Legacy alias for backward compat
def backtest_2023_same_period(pvgis_hourly_kwh, zone, start, end):
    return backtest_baseline_period(pvgis_hourly_kwh, 2023, zone, start, end)


def _combine(hourly_prod_mwh: list[float], hourly_prices: list[float | None], days: int) -> dict:
    n = min(len(hourly_prod_mwh), len(hourly_prices))
    revenue = 0.0
    total_prod = 0.0
    valid_prices: list[float] = []
    for i in range(n):
        prod = hourly_prod_mwh[i]
        price = hourly_prices[i]
        if price is None:
            continue
        revenue += prod * price
        total_prod += prod
        valid_prices.append(price)
    avg_price = sum(valid_prices) / len(valid_prices) if valid_prices else 0.0
    effective_price = (revenue / total_prod) if total_prod > 0 else 0.0
    cann = ((effective_price - avg_price) / avg_price * 100.0) if avg_price else 0.0
    return {
        "production_mwh": total_prod,
        "revenue_eur": revenue,
        "effective_price_eur_mwh": effective_price,
        "avg_dayahead_price_eur_mwh": avg_price,
        "cannibalisation_pct": cann,
        "hours_with_prices": len(valid_prices),
        "days": days,
    }


def _summary_no_prices(hourly_prod_mwh: list[float], days: int) -> dict:
    total_prod = sum(hourly_prod_mwh)
    return {
        "production_mwh": total_prod,
        "revenue_eur": None,
        "effective_price_eur_mwh": None,
        "avg_dayahead_price_eur_mwh": None,
        "cannibalisation_pct": None,
        "hours_with_prices": 0,
        "days": days,
    }


def get_recent_window(days: int = 7, end_offset_days: int = 5) -> tuple[date, date]:
    """Return the latest fully-available window.

    Open-Meteo Archive has a ~5-day publishing lag, so we end the window
    `end_offset_days` ago. By default returns the 7 days ending 5 days ago.
    """
    today = datetime.now(timezone.utc).date()
    end = today - timedelta(days=end_offset_days)
    start = end - timedelta(days=days - 1)
    return start, end
