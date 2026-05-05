"""US wholesale electricity prices — direct OASIS HTTPS fetch (no gridstatus).

CAISO SP15 (zone for Lotus Solar Farm in California) is fetched as real
hourly day-ahead LMP in USD/MWh via the OASIS public CSV endpoint.

Implementation note: we used to depend on `gridstatus` but it pulled 6 heavy
deps (pandas, bs4, lxml, tqdm, tabulate, requests) and called OASIS over plain
HTTP (302-redirected to HTTPS), which Streamlit Cloud's outbound network
rejects in some cases. Replaced with stdlib urllib + zipfile + csv, HTTPS-only,
~40 LoC. Same data, faster cold-start, no dependency footprint.

ERCOT West Hub (zone for Galloway 2 in West Texas) requires login on the
new MIS portal. We keep the "—" honest unavailable state for ERCOT.

USD-native — no EUR conversion. Display layer formats with $ symbol when
the park's zone is US.
"""

from __future__ import annotations

import csv
import datetime as _dt
import io
import logging
import urllib.error
import urllib.request
import zipfile
from typing import Any

logger = logging.getLogger(__name__)


CAISO_HUB_BY_ZONE = {
    "US-CAISO": "TH_SP15_GEN-APND",  # Southern California, Lotus location
}

ERCOT_HUB_BY_ZONE = {
    "US-ERCOT": "HB_WEST",  # West Hub, Galloway 2 location
}


_OASIS_BASE = "https://oasis.caiso.com/oasisapi/SingleZip"


class _OASISRateLimited(Exception):
    """Raised when OASIS returns HTTP 429 — abort retry loop, don't hammer further."""


def _fetch_oasis_csv(node: str, start: _dt.date, end: _dt.date) -> list[dict[str, str]] | None:
    """Direct OASIS HTTPS call → unzip → parse CSV → list[dict]. None on failure.

    Raises _OASISRateLimited on HTTP 429 so the caller can break out of any
    retry/walk-back loop. OASIS rate-limits aggressively per source IP — once
    you hit 429, hammering more makes it worse.
    """
    start_str = start.strftime("%Y%m%dT07:00-0000")
    end_str = end.strftime("%Y%m%dT07:00-0000")
    params = (
        "resultformat=6&queryname=PRC_LMP&version=12"
        f"&market_run_id=DAM&node={node}"
        f"&startdatetime={start_str}&enddatetime={end_str}"
    )
    url = f"{_OASIS_BASE}?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "allianz-renewables-atlas/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 429:
            logger.warning("OASIS rate-limited (429) on %s %s→%s — aborting", node, start, end)
            raise _OASISRateLimited() from e
        logger.warning("OASIS HTTPS fetch failed for %s %s→%s: HTTP %s", node, start, end, e.code)
        return None
    except (urllib.error.URLError, TimeoutError) as e:
        logger.warning("OASIS HTTPS fetch failed for %s %s→%s: %s", node, start, end, e)
        return None

    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            csv_name = zf.namelist()[0]
            with zf.open(csv_name) as f:
                text = f.read().decode("utf-8")
        rows = list(csv.DictReader(io.StringIO(text)))
    except (zipfile.BadZipFile, KeyError, IndexError, UnicodeDecodeError) as e:
        logger.warning("OASIS CSV parse failed: %s", e)
        return None

    # OASIS returns BOTH LMP_PRC (price) and component sub-rows (energy, congestion, loss)
    # in the same file. Filter to the price rows only.
    return [r for r in rows if r.get("LMP_TYPE") == "LMP" or r.get("XML_DATA_ITEM") == "LMP_PRC"]


def fetch_caiso_period_prices(zone: str, start: _dt.date, end: _dt.date) -> dict[str, Any] | None:
    """Fetch hourly day-ahead LMP for a CAISO trading hub between start and end.

    Returns dict with hourly arrays in USD/MWh, or None on failure. Walks back
    up to 7 days if the requested window returns empty (weekends, holidays,
    or pre-publication windows can leave today/yesterday empty even when OASIS
    itself is healthy — DAM publishes ~13:00 Pacific = 21:00 UTC).
    """
    hub = CAISO_HUB_BY_ZONE.get(zone)
    if not hub:
        return None

    rows = None
    # Walk back at most 3 days to find a published window. Each iteration is a
    # separate OASIS request, so we cap the retries to limit the rate-limit blast
    # radius. Break immediately on 429 — hammering further only extends the ban.
    for offset in range(0, 3):
        try_start = start - _dt.timedelta(days=offset)
        try_end = end - _dt.timedelta(days=offset)
        try:
            rows = _fetch_oasis_csv(hub, try_start, try_end)
        except _OASISRateLimited:
            break
        if rows:
            break

    if not rows:
        return None

    # Sort by interval start ascending — OASIS returns rows in arbitrary order
    rows.sort(key=lambda r: r.get("INTERVALSTARTTIME_GMT", ""))

    timestamps: list[int] = []
    prices: list[float | None] = []
    for r in rows:
        try:
            ts_str = r["INTERVALSTARTTIME_GMT"]
            # ISO 8601 like "2026-05-04T07:00:00-00:00"
            ts_dt = _dt.datetime.fromisoformat(ts_str.replace("-00:00", "+00:00"))
            timestamps.append(int(ts_dt.timestamp()))
        except (KeyError, ValueError):
            continue
        try:
            prices.append(float(r["MW"]))  # OASIS calls the LMP value column "MW"
        except (KeyError, ValueError, TypeError):
            prices.append(None)

    if not timestamps:
        return None

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
