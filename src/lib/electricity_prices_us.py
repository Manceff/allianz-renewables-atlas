"""US wholesale electricity prices via gridstatus.

CAISO SP15 (zone for Lotus Solar Farm in California) is fetched as real
hourly day-ahead LMP in USD/MWh via the OASIS public CSV endpoint.

ERCOT West Hub (zone for Galloway 2 in West Texas) requires login on the
new MIS portal — gridstatus returns HTTP 403 without credentials. We keep
the flat-price proxy fallback for ERCOT until proper auth is configured.

USD-native — no EUR conversion. Display layer formats with $ symbol when
the park's zone is US.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Any

logger = logging.getLogger(__name__)


CAISO_HUB_BY_ZONE = {
    "US-CAISO": "TH_SP15_GEN-APND",  # Southern California, Lotus location
}

# ERCOT hubs (kept here for documentation — currently unreachable without MIS auth)
ERCOT_HUB_BY_ZONE = {
    "US-ERCOT": "HB_WEST",  # West Hub, Galloway 2 location
}


def fetch_caiso_period_prices(zone: str, start: _dt.date, end: _dt.date) -> dict[str, Any] | None:
    """Fetch hourly day-ahead LMP for a CAISO trading hub between start and end.

    Returns dict with hourly arrays in USD/MWh, or None on failure.
    """
    hub = CAISO_HUB_BY_ZONE.get(zone)
    if not hub:
        return None

    try:
        from gridstatus import CAISO
        caiso = CAISO()
        df = caiso.get_lmp(
            start=start, end=end,
            market="DAY_AHEAD_HOURLY",
            locations=[hub],
        )
    except Exception as e:
        logger.warning("CAISO LMP fetch failed: %s", e)
        return None

    if df is None or df.empty:
        return None

    # gridstatus columns: Time, Interval Start, Interval End, Location, Market, LMP, Energy, Congestion, Loss
    timestamps = [int(t.timestamp()) for t in df["Interval Start"]]
    prices = [float(p) if p is not None else None for p in df["LMP"]]
    return {
        "zone": zone,
        "currency": "USD",
        "timestamps": timestamps,
        "prices_usd_mwh": prices,
    }


def fetch_caiso_current_spot(zone: str) -> dict[str, Any] | None:
    """Fetch the most recent hour's day-ahead LMP as a 'live' spot proxy.

    CAISO publishes the next-day DAM around 13:00 PT, so we fetch yesterday's
    last hour as the most recent settled price.
    """
    today = _dt.date.today()
    yesterday = today - _dt.timedelta(days=1)
    data = fetch_caiso_period_prices(zone, yesterday, today)
    if not data or not data.get("prices_usd_mwh"):
        return None
    valid = [(ts, p) for ts, p in zip(data["timestamps"], data["prices_usd_mwh"]) if p is not None]
    if not valid:
        return None
    last_ts, last_price = valid[-1]
    return {
        "zone": zone,
        "currency": "USD",
        "price_usd_mwh": last_price,
        "time_iso": _dt.datetime.fromtimestamp(last_ts).isoformat(),
    }


def is_us_zone(zone: str | None) -> bool:
    return zone is not None and zone.startswith("US-")


def park_currency(zone: str | None, fallback_zone: str | None = None) -> str:
    """Return 'USD' for US parks, 'EUR' otherwise."""
    z = zone or fallback_zone
    return "USD" if is_us_zone(z) else "EUR"


def format_money(value: float, currency: str, *, m_suffix: bool = False) -> str:
    """USD: $X.XX M / $XX,XXX. EUR: € X.XX M / € XX,XXX."""
    if currency == "USD":
        if m_suffix:
            return f"$ {value:,.2f} M"
        return f"$ {value:,.0f}"
    if m_suffix:
        return f"€ {value:,.2f} M"
    return f"€ {value:,.0f}"


def format_price(value: float, currency: str) -> str:
    """Format €/MWh or $/MWh."""
    if currency == "USD":
        return f"$ {value:,.1f}/MWh"
    return f"{value:,.1f} €/MWh"
