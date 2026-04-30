"""Helpers d'analyse pour les données PVGIS horaires (8760h).

Toutes les fonctions opèrent sur la liste hourly_production_kwh retournée par
fetch_pvgis_hourly. Pures, pas d'IO. Utilisées par la page Atlas pour les
widgets : heatmap 365×24, capacity factor mensuel, profile horaire saisonnier,
estimation pour la date du jour.
"""

from __future__ import annotations

import calendar
from datetime import datetime, timezone
from typing import Sequence

import numpy as np

HOURS_PER_DAY = 24
DAYS_NON_LEAP = 365


def hourly_to_daily(hourly_kwh: Sequence[float]) -> list[float]:
    """8760 → 365 valeurs journalières (somme des 24h)."""
    arr = np.asarray(hourly_kwh, dtype=float)
    if arr.size != DAYS_NON_LEAP * HOURS_PER_DAY:
        arr = arr[: DAYS_NON_LEAP * HOURS_PER_DAY]
    return arr.reshape(DAYS_NON_LEAP, HOURS_PER_DAY).sum(axis=1).tolist()


def hourly_heatmap_matrix(hourly_kwh: Sequence[float]) -> np.ndarray:
    """Matrice 24×365 (heure × jour) en kWh, format Plotly heatmap.

    Heure 0 (minuit) en haut, heure 23 (23h) en bas.
    Jour 0 (1er janvier) à gauche, jour 364 (31 déc) à droite.
    """
    arr = np.asarray(hourly_kwh, dtype=float)
    if arr.size != DAYS_NON_LEAP * HOURS_PER_DAY:
        arr = arr[: DAYS_NON_LEAP * HOURS_PER_DAY]
    return arr.reshape(DAYS_NON_LEAP, HOURS_PER_DAY).T


def monthly_aggregates(hourly_kwh: Sequence[float], year: int = 2019) -> list[dict]:
    """Pour chaque mois : production totale (MWh) + capacity factor (%).

    Returns list de 12 dicts : {month, days, production_mwh, capacity_factor_pct}.
    Le CF nécessite peakpower — utilise capacity_factor_monthly() pour ça.
    """
    daily = hourly_to_daily(hourly_kwh)
    out = []
    day_idx = 0
    for month in range(1, 13):
        n_days = calendar.monthrange(year, month)[1]
        if year == 2019:  # non-bissextile, mais sécurise
            n_days = min(n_days, DAYS_NON_LEAP - day_idx)
        prod_kwh = sum(daily[day_idx : day_idx + n_days])
        out.append(
            {
                "month": month,
                "days": n_days,
                "production_mwh": prod_kwh / 1000.0,
            }
        )
        day_idx += n_days
    return out


def capacity_factor_monthly(
    hourly_kwh: Sequence[float], peakpower_mw: float, year: int = 2019
) -> list[float]:
    """Capacity factor mensuel (%).

    CF = production_mwh / (peakpower_mw × hours_in_month) × 100.
    """
    if peakpower_mw <= 0:
        raise ValueError("peakpower_mw doit être > 0")
    aggregates = monthly_aggregates(hourly_kwh, year=year)
    out = []
    for agg in aggregates:
        max_possible_mwh = peakpower_mw * agg["days"] * HOURS_PER_DAY
        cf_pct = (agg["production_mwh"] / max_possible_mwh) * 100.0 if max_possible_mwh else 0.0
        out.append(cf_pct)
    return out


def capacity_factor_annual(hourly_kwh: Sequence[float], peakpower_mw: float) -> float:
    """Capacity factor annuel global (%)."""
    if peakpower_mw <= 0:
        raise ValueError("peakpower_mw doit être > 0")
    annual_kwh = float(np.sum(hourly_kwh))
    max_possible_kwh = peakpower_mw * 1000.0 * 8760.0  # MWp × 1000 × 8760h = kWh max
    return (annual_kwh / max_possible_kwh) * 100.0 if max_possible_kwh else 0.0


def estimate_for_date(
    hourly_kwh: Sequence[float],
    irradiance_wm2: Sequence[float],
    target_date: datetime | None = None,
    year: int = 2019,
) -> dict:
    """Production estimée pour la date du jour (climatique).

    Returns dict avec :
        date : ISO YYYY-MM-DD
        day_of_year : 1-365
        production_kwh : production journalière typique (kWh)
        avg_irradiance_kwh_m2 : ensoleillement moyen sur la journée (kWh/m²/jour)
        sunshine_hours : heures où irradiance > 50 W/m²
    """
    if target_date is None:
        target_date = datetime.now(timezone.utc)

    # Jour de l'année (1-365), ignore le 29 février si bissextile
    jan1 = datetime(target_date.year, 1, 1, tzinfo=timezone.utc)
    day_of_year = (target_date.replace(tzinfo=timezone.utc) - jan1).days + 1
    if day_of_year > DAYS_NON_LEAP:
        day_of_year = DAYS_NON_LEAP

    idx0 = (day_of_year - 1) * HOURS_PER_DAY
    idx1 = idx0 + HOURS_PER_DAY

    daily_kwh = float(np.sum(hourly_kwh[idx0:idx1]))
    daily_irr = irradiance_wm2[idx0:idx1]
    # Convertit W/m² heure-par-heure → kWh/m² sur la journée (somme × 1h / 1000)
    avg_irr_kwh_m2 = float(np.sum(daily_irr) / 1000.0)
    sunshine_hrs = int(sum(1 for w in daily_irr if w > 50.0))

    return {
        "date": target_date.strftime("%Y-%m-%d"),
        "day_of_year": day_of_year,
        "production_kwh": daily_kwh,
        "avg_irradiance_kwh_m2": avg_irr_kwh_m2,
        "sunshine_hours": sunshine_hrs,
    }


def seasonal_hourly_profile(hourly_kwh: Sequence[float]) -> dict[str, list[float]]:
    """Profil moyen horaire (24 valeurs) pour chaque saison météorologique.

    Returns dict : {winter, spring, summer, autumn} → list[float] de 24 valeurs.
    Saisons : winter = DJF, spring = MAM, summer = JJA, autumn = SON.
    """
    arr = np.asarray(hourly_kwh, dtype=float)[: DAYS_NON_LEAP * HOURS_PER_DAY]
    matrix = arr.reshape(DAYS_NON_LEAP, HOURS_PER_DAY)

    # Days-of-year boundaries (1-365, year=2019 non-bissextile)
    seasons = {
        "winter": list(range(0, 59)) + list(range(334, 365)),  # JF + D
        "spring": list(range(59, 151)),  # MAM
        "summer": list(range(151, 243)),  # JJA
        "autumn": list(range(243, 334)),  # SON
    }

    out: dict[str, list[float]] = {}
    for season, day_indices in seasons.items():
        season_mat = matrix[day_indices]
        out[season] = season_mat.mean(axis=0).tolist()
    return out
