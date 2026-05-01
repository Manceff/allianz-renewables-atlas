"""Day-ahead electricity prices — energy-charts.info (ENTSO-E mirror, no auth).

Fetches hourly day-ahead prices in EUR/MWh per bidding zone, caches locally
in data/electricity_prices/{zone}_{year}.json so we hit the API at most once
per (zone, year).

Mapping country (ISO2) → ENTSO-E bidding zone is defined in COUNTRY_TO_ZONE.
US zones are not covered by energy-charts (Europe-only) — those parks
return None and the UI displays "—" for revenue metrics.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Sequence

import requests

logger = logging.getLogger(__name__)

API_URL = "https://api.energy-charts.info/price"

# Country ISO2 → primary ENTSO-E bidding zone for energy-charts.info
COUNTRY_TO_ZONE: dict[str, str] = {
    "PT": "PT",                # Portugal
    "ES": "ES",                # Spain (MIBEL)
    "FR": "FR",                # France
    "IT": "IT-South",          # Italie sud (default — Brindisi, SiSen, Foggia)
    "DE": "DE-LU",             # Germany / Luxembourg
    # IE (Ireland SEM) intentionally absent : energy-charts.info doesn't
    # currently publish prices for IE-SEM. Falls back to "—" with explicit help.
    # US (ERCOT, CAISO) absent too : energy-charts is Europe only.
    # Future : connect ENTSO-E API direct or EIA for full coverage.
}

# Override per park_id when we know the precise zone (e.g. Manzano = North Italy)
PARK_ZONE_OVERRIDE: dict[str, str] = {
    "manzano-solar": "IT-North",  # Manzano is in Friuli (northern zone)
}

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "electricity_prices"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_zone(country: str, park_id: str | None = None) -> str | None:
    """Return the ENTSO-E zone code for a country (with park-specific overrides)."""
    if park_id and park_id in PARK_ZONE_OVERRIDE:
        return PARK_ZONE_OVERRIDE[park_id]
    return COUNTRY_TO_ZONE.get(country)


ITALIAN_ZONES = {"IT-North", "IT-Centre-North", "IT-Centre-South", "IT-South", "IT-Sicily", "IT-Sardinia", "IT-Calabria"}


def interpret_spot_price(price_eur_mwh: float | None, zone: str) -> dict:
    """Return a human label + context for a spot price.

    Returns dict with :
        label : short tag ("floor", "negative", "low", "normal", "elevated", "high")
        warn : True if the value warrants a contextual disclaimer
        explain : 1-line explanation
    """
    if price_eur_mwh is None:
        return {"label": "—", "warn": False, "explain": "no data"}

    if price_eur_mwh < -1.0:
        return {
            "label": "negative",
            "warn": True,
            "explain": (
                "Solar cannibalisation peak. The market is paying consumers "
                "to take electricity because solar/wind production exceeds demand."
            ),
        }
    if price_eur_mwh <= 0.5 and zone in ITALIAN_ZONES:
        return {
            "label": "italian floor",
            "warn": True,
            "explain": (
                "Italian day-ahead has a regulatory floor at 0 €/MWh — "
                "the market cannot price negatively. This signals supply ≥ demand."
            ),
        }
    if price_eur_mwh <= 0.5:
        return {
            "label": "near zero",
            "warn": True,
            "explain": "Supply matches demand. Solar likely saturating the grid this hour.",
        }
    if price_eur_mwh < 20:
        return {"label": "very low", "warn": False, "explain": "Below typical baseload cost."}
    if price_eur_mwh < 50:
        return {"label": "low", "warn": False, "explain": "Below 2023-2025 average."}
    if price_eur_mwh < 100:
        return {"label": "normal", "warn": False, "explain": "Within typical daytime range."}
    if price_eur_mwh < 200:
        return {"label": "elevated", "warn": False, "explain": "Above typical — peak demand or supply tight."}
    return {"label": "high", "warn": False, "explain": "Significantly above normal."}


def fetch_period_prices(zone: str, start: str, end: str) -> dict | None:
    """Fetch hourly day-ahead prices for an arbitrary date range.

    Resamples 15-min resolution to 1h average if the API returns 15-min steps
    (energy-charts.info recently switched to 15-min for newer data).

    Args :
        zone : ENTSO-E bidding zone code (PT, ES, FR, IT-North, IT-South…).
        start, end : 'YYYY-MM-DD' inclusive.

    Returns dict with :
        timestamps : list[int] unix seconds (hourly)
        prices_eur_mwh : list[float | None]
    """
    try:
        resp = requests.get(
            API_URL,
            params={"bzn": zone, "start": start, "end": end},
            timeout=30,
        )
        if resp.status_code != 200:
            logger.warning("energy-charts %s [%s..%s] HTTP %d", zone, start, end, resp.status_code)
            return None
        payload = resp.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning("energy-charts fetch failed for %s : %s", zone, e)
        return None

    timestamps = payload.get("unix_seconds") or []
    prices = payload.get("price") or []
    if not timestamps or not prices:
        return None

    # Detect resolution from first delta. 900s = 15min, 3600s = 1h.
    if len(timestamps) >= 2:
        delta = timestamps[1] - timestamps[0]
    else:
        delta = 3600

    if delta == 900:
        # Resample 15-min → 1h by averaging 4 quarter-hours
        hourly_ts = []
        hourly_prices = []
        bucket: list[float] = []
        bucket_start_ts = None
        for ts, p in zip(timestamps, prices):
            ts_hour = ts - (ts % 3600)
            if bucket_start_ts is None:
                bucket_start_ts = ts_hour
            if ts_hour != bucket_start_ts and bucket:
                valid = [x for x in bucket if x is not None]
                hourly_ts.append(bucket_start_ts)
                hourly_prices.append(sum(valid) / len(valid) if valid else None)
                bucket = []
                bucket_start_ts = ts_hour
            bucket.append(float(p) if p is not None else None)
        if bucket and bucket_start_ts is not None:
            valid = [x for x in bucket if x is not None]
            hourly_ts.append(bucket_start_ts)
            hourly_prices.append(sum(valid) / len(valid) if valid else None)
        return {"timestamps": hourly_ts, "prices_eur_mwh": hourly_prices}

    return {
        "timestamps": list(timestamps),
        "prices_eur_mwh": [float(p) if p is not None else None for p in prices],
    }


def fetch_today_curve(zone: str) -> dict | None:
    """Fetch today's hourly day-ahead curve for visualisation. Not cached.

    Returns dict with :
        timestamps : list of unix seconds
        prices : list of floats (€/MWh)
    """
    import datetime as _dt
    today = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")
    try:
        resp = requests.get(
            API_URL,
            params={"bzn": zone, "start": today, "end": today},
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        payload = resp.json()
    except (requests.RequestException, ValueError):
        return None

    prices = payload.get("price")
    timestamps = payload.get("unix_seconds")
    if not prices or not timestamps:
        return None

    return {"timestamps": timestamps, "prices": prices}


def fetch_current_spot_price(zone: str) -> dict | None:
    """Return the current-hour day-ahead spot price for a zone.

    Fetches a 2-day window around today and picks the hour matching now.
    Not cached — caller should wrap in @st.cache_data with TTL ~1 hour.

    Returns dict with:
        price_eur_mwh: current-hour spot price
        time_iso: timestamp of the picked hour
        zone: bidding zone
    """
    import datetime as _dt

    now = _dt.datetime.now(_dt.timezone.utc)
    start = (now - _dt.timedelta(days=1)).strftime("%Y-%m-%d")
    end = (now + _dt.timedelta(days=1)).strftime("%Y-%m-%d")

    try:
        resp = requests.get(
            API_URL,
            params={"bzn": zone, "start": start, "end": end},
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        payload = resp.json()
    except (requests.RequestException, ValueError):
        return None

    timestamps = payload.get("unix_seconds") or []
    prices = payload.get("price") or []
    if not timestamps or not prices:
        return None

    # Pick the timestamp closest to (but not after) now
    now_ts = int(now.timestamp())
    best_idx = None
    best_delta = None
    for i, ts in enumerate(timestamps):
        if ts > now_ts:
            continue
        delta = now_ts - ts
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best_idx = i

    if best_idx is None:
        return None

    return {
        "price_eur_mwh": float(prices[best_idx]) if prices[best_idx] is not None else None,
        "time_iso": _dt.datetime.fromtimestamp(timestamps[best_idx], _dt.timezone.utc).isoformat(),
        "zone": zone,
    }


def fetch_hourly_prices(zone: str, year: int, force_refresh: bool = False) -> list[float] | None:
    """Fetch hourly day-ahead prices (EUR/MWh) for a zone+year. Cached locally.

    Returns:
        list of 8760 (or 8784) hourly prices in EUR/MWh, or None if zone not supported.
    """
    cache_path = CACHE_DIR / f"{zone}_{year}.json"

    if cache_path.exists() and not force_refresh:
        try:
            with open(cache_path) as f:
                data = json.load(f)
            return data.get("prices")
        except (OSError, json.JSONDecodeError):
            pass  # corrupted cache, refetch

    params = {
        "bzn": zone,
        "start": f"{year}-01-01",
        "end": f"{year}-12-31",
    }

    try:
        resp = requests.get(API_URL, params=params, timeout=30)
        if resp.status_code == 429:
            logger.warning("energy-charts.info rate-limited for zone=%s year=%d", zone, year)
            return None
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning("energy-charts.info fetch failed: %s", e)
        return None

    prices = payload.get("price")
    timestamps = payload.get("unix_seconds")

    if not prices or not timestamps:
        return None

    # Persist to cache
    try:
        with open(cache_path, "w") as f:
            json.dump({"zone": zone, "year": year, "prices": prices, "timestamps": timestamps}, f)
    except OSError as e:
        logger.warning("Cache write failed: %s", e)

    return prices


def compute_revenue_metrics(
    hourly_production_kwh: Sequence[float],
    hourly_prices_eur_mwh: Sequence[float],
) -> dict:
    """Compute annual revenue + effective sale price from production × price hourly matching.

    Hourly revenue (EUR) = production_kwh / 1000 × price_eur_per_mwh
    Sums to annual revenue. Effective price = revenue / production_mwh.

    Args:
        hourly_production_kwh: 8760+ hourly production values from PVGIS.
        hourly_prices_eur_mwh: 8760+ hourly prices from energy-charts.

    Returns:
        dict with keys:
            annual_revenue_eur: total revenue
            effective_price_eur_mwh: revenue / total_production_mwh
            avg_dayahead_price_eur_mwh: simple time-average of all prices
            production_mwh: total production
            cannibalization_pct: (effective - avg) / avg × 100, % discount due to solar overproducing during low-price hours
    """
    # Truncate to common length
    n = min(len(hourly_production_kwh), len(hourly_prices_eur_mwh))
    if n == 0:
        return {}

    prod = hourly_production_kwh[:n]
    prices = hourly_prices_eur_mwh[:n]

    annual_revenue = 0.0
    annual_prod_kwh = 0.0
    for kwh, price in zip(prod, prices):
        # price might be None or NaN if zone has missing hours
        if price is None or kwh is None:
            continue
        annual_revenue += (kwh / 1000.0) * float(price)
        annual_prod_kwh += kwh

    annual_prod_mwh = annual_prod_kwh / 1000.0
    valid_prices = [float(p) for p in prices if p is not None]
    avg_price = sum(valid_prices) / len(valid_prices) if valid_prices else 0.0
    effective_price = (annual_revenue / annual_prod_mwh) if annual_prod_mwh > 0 else 0.0
    cannibalization = ((effective_price - avg_price) / avg_price * 100.0) if avg_price else 0.0

    return {
        "annual_revenue_eur": annual_revenue,
        "effective_price_eur_mwh": effective_price,
        "avg_dayahead_price_eur_mwh": avg_price,
        "production_mwh": annual_prod_mwh,
        "cannibalization_pct": cannibalization,
    }
