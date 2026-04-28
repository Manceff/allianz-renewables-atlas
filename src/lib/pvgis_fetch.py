"""Client PVGIS PVcalc — Joint Research Centre EU, gratuit, sans clé.

Endpoint v5_2 documenté ici : https://re.jrc.ec.europa.eu/pvg_tools/en/tools.html
Renvoie un dict serialisable JSON : production mensuelle long-terme + total annuel.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

PVGIS_PVCALC_URL = "https://re.jrc.ec.europa.eu/api/v5_2/PVcalc"

DEFAULT_LOSS_PCT = 14.0  # pertes système standard PVGIS (câblage + onduleur + souillure)
DEFAULT_PVTECH = "crystSi"
DEFAULT_TIMEOUT_SEC = 30


class PvgisFetchError(RuntimeError):
    """Erreur opaque côté PVGIS (HTTP, parsing, payload invalide)."""


def fetch_pvgis_pvcalc(
    lat: float,
    lon: float,
    peakpower_mw: float,
    tilt: float | None = None,
    azimuth: float = 0.0,
    loss_pct: float = DEFAULT_LOSS_PCT,
    pv_technology: str = DEFAULT_PVTECH,
    timeout: int = DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    """Appelle PVGIS PVcalc et renvoie la production mensuelle long-terme.

    Args:
        lat, lon: coordonnées en degrés.
        peakpower_mw: puissance crête installée en MWp (convertie en kWp pour PVGIS).
        tilt: inclinaison en degrés ; défaut = max(0, lat - 10).
        azimuth: azimut PVGIS (0 = sud, négatif = est, positif = ouest).
        loss_pct: pertes système (% PVGIS).
        pv_technology: techno PV PVGIS (`crystSi`, `CIS`, `CdTe`).

    Returns:
        Dict serialisable JSON avec :
        - inputs: paramètres effectifs envoyés
        - monthly_production_kwh: list[float] de 12 valeurs (E_m par mois)
        - annual_total_kwh: float (E_y des totals fixed)
        - annual_total_mwh: float
        - metadata: {raddatabase, year_min, year_max}
        - raw: réponse PVGIS brute (clé `outputs.totals.fixed` complète pour debug)

    Raises:
        ValueError: paramètres invalides.
        PvgisFetchError: erreur HTTP ou payload inattendu.
    """
    if peakpower_mw <= 0:
        raise ValueError(f"peakpower_mw doit être > 0, reçu {peakpower_mw}")

    effective_tilt = max(0.0, lat - 10.0) if tilt is None else float(tilt)
    peakpower_kw = peakpower_mw * 1000.0

    params = {
        "lat": lat,
        "lon": lon,
        "peakpower": peakpower_kw,
        "loss": loss_pct,
        "angle": effective_tilt,
        "aspect": float(azimuth),
        "pvtechchoice": pv_technology,
        "mountingplace": "free",
        "fixed": 1,
        "outputformat": "json",
    }

    logger.info(
        "PVGIS PVcalc lat=%.4f lon=%.4f peakpower=%.1fkWp tilt=%.1f° azimuth=%.1f°",
        lat,
        lon,
        peakpower_kw,
        effective_tilt,
        azimuth,
    )

    try:
        resp = requests.get(PVGIS_PVCALC_URL, params=params, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise PvgisFetchError(f"PVGIS HTTP error: {e}") from e

    try:
        payload = resp.json()
    except ValueError as e:
        raise PvgisFetchError(f"PVGIS réponse non-JSON: {e}") from e

    return _parse_pvcalc_payload(payload, params)


def _parse_pvcalc_payload(payload: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    try:
        monthly_fixed = payload["outputs"]["monthly"]["fixed"]
        totals_fixed = payload["outputs"]["totals"]["fixed"]
    except (KeyError, TypeError) as e:
        raise PvgisFetchError(f"PVGIS payload structure inattendue: {e}") from e

    if not isinstance(monthly_fixed, list) or len(monthly_fixed) != 12:
        raise PvgisFetchError(
            f"PVGIS monthly.fixed devrait avoir 12 entrées, reçu {len(monthly_fixed) if isinstance(monthly_fixed, list) else type(monthly_fixed)}"
        )

    monthly_kwh = [float(m["E_m"]) for m in monthly_fixed]
    annual_kwh = float(totals_fixed.get("E_y", sum(monthly_kwh)))

    meteo = payload.get("inputs", {}).get("meteo_data", {})
    metadata = {
        "source": "PVGIS v5.2 (JRC EU)",
        "raddatabase": meteo.get("radiation_db"),
        "year_min": meteo.get("year_min"),
        "year_max": meteo.get("year_max"),
    }

    return {
        "inputs": {
            "lat": params["lat"],
            "lon": params["lon"],
            "peakpower_kw": params["peakpower"],
            "tilt_deg": params["angle"],
            "azimuth_deg": params["aspect"],
            "loss_pct": params["loss"],
            "pv_technology": params["pvtechchoice"],
        },
        "monthly_production_kwh": monthly_kwh,
        "annual_total_kwh": annual_kwh,
        "annual_total_mwh": annual_kwh / 1000.0,
        "metadata": metadata,
        "raw_totals_fixed": totals_fixed,
    }
