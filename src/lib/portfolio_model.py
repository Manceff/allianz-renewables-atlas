"""Aggregated pvlib computation for multi-site solar portfolios.

For a portfolio with N sub-sites that may be 200+ km apart, the irradiance,
temperature and wind differ significantly between sites. We must run pvlib
**per site** at its own coordinates, then aggregate the hourly outputs.

Used in particular for forward-sale portfolios (Elgin Ireland, Allianz Dec 2023):
the panels are not yet grid-connected, so we compute a *theoretical* annual
production assuming full energization across all sites, using the typical-year
weather from the most recent historical year available via Open-Meteo Archive.
"""

from __future__ import annotations

import logging
from datetime import date

from src.lib.solar_model import compute_period_production

logger = logging.getLogger(__name__)


def compute_portfolio_typical_year(
    sub_sites: list[dict],
    baseline_start: date,
    baseline_end: date,
    dc_ac_ratio: float = 1.30,
) -> dict | None:
    """Compute aggregate hourly production for a portfolio across N sites.

    Each sub-site has its own (lat, lon, capacity_mw_ac). The DC peak capacity used
    by pvlib is `capacity_mw_ac × dc_ac_ratio` (so panel array ≈ 1.30-1.40× the
    inverter rating, standard utility-scale).

    Args:
        sub_sites: list of dicts with keys {name, lat, lon, capacity_mw}.
        baseline_start, baseline_end: date range to use for the typical-year reconstruction.
        dc_ac_ratio: DC/AC over-build factor — panel-DC = AC × ratio.

    Returns:
        dict with :
            timestamps : list[str] (UTC, hourly)
            hourly_production_kwh : list[float] (sum across all sites)
            per_site : list[dict] {name, annual_mwh, capacity_mw_ac, lat, lon}
            total_capacity_mw_ac : float
            total_capacity_mwp_dc : float
    """
    if not sub_sites:
        return None

    per_site_results = []
    aggregate_kwh: list[float] | None = None
    timestamps: list[str] | None = None

    for s in sub_sites:
        cap_dc = float(s["capacity_mw"]) * dc_ac_ratio
        period = compute_period_production(
            lat=float(s["lat"]),
            lon=float(s["lon"]),
            capacity_mwp=cap_dc,
            start_date=baseline_start,
            end_date=baseline_end,
        )
        if not period:
            logger.warning("No pvlib output for sub-site %s", s.get("name"))
            continue

        hourly = period["hourly_production_kwh"]
        annual_mwh = sum(hourly) / 1000.0
        per_site_results.append({
            "name": s["name"],
            "lat": float(s["lat"]),
            "lon": float(s["lon"]),
            "capacity_mw_ac": float(s["capacity_mw"]),
            "capacity_mwp_dc": cap_dc,
            "annual_mwh": annual_mwh,
            "capacity_factor_pct": (annual_mwh * 1000.0) / (cap_dc * 1000.0 * 8760.0) * 100.0,
        })

        if aggregate_kwh is None:
            aggregate_kwh = list(hourly)
            timestamps = list(period["timestamps"])
        else:
            n = min(len(aggregate_kwh), len(hourly))
            for i in range(n):
                aggregate_kwh[i] += hourly[i]

    if aggregate_kwh is None:
        return None

    total_cap_ac = sum(s["capacity_mw_ac"] for s in per_site_results)
    total_cap_dc = sum(s["capacity_mwp_dc"] for s in per_site_results)
    return {
        "timestamps": timestamps,
        "hourly_production_kwh": aggregate_kwh,
        "annual_total_mwh": sum(aggregate_kwh) / 1000.0,
        "per_site": per_site_results,
        "total_capacity_mw_ac": total_cap_ac,
        "total_capacity_mwp_dc": total_cap_dc,
    }


def compute_portfolio_revenue_flat(
    annual_production_mwh: float,
    strike_price_eur_mwh: float,
) -> dict:
    """Annual revenue at a flat strike price (RESS-secured 2-way CfD, no cannibalisation)."""
    revenue_eur = annual_production_mwh * strike_price_eur_mwh
    return {
        "annual_revenue_eur": revenue_eur,
        "annual_revenue_meur": revenue_eur / 1_000_000.0,
        "effective_price_eur_mwh": strike_price_eur_mwh,
        "pricing_model": "RESS 2-way CfD — flat strike, no cannibalisation",
    }
