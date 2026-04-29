"""Intervalle de confiance PVGIS via sensibilité au paramètre `loss_pct`.

PVGIS PVcalc est déterministe pour un jeu d'inputs donné ; la sensibilité aux
pertes système (`loss_pct`) sert ici de proxy pour encadrer la production
annuelle long-terme. On exécute trois scénarios (par défaut 10% / 14% / 18%) et
on les ordonne en `low / mid / high` :

- `low_mwh`  ← pertes les plus élevées (production la plus faible, conservatrice)
- `mid_mwh`  ← scénario médian
- `high_mwh` ← pertes les plus faibles (production la plus haute, optimiste)
"""

from __future__ import annotations

import logging

from src.lib.pvgis_fetch import fetch_pvgis_pvcalc
from src.lib.schemas import ConfidenceInterval, LossScenario

logger = logging.getLogger(__name__)

DEFAULT_LOSS_SCENARIOS: tuple[float, ...] = (10.0, 14.0, 18.0)


def compute_pvgis_range(
    lat: float,
    lon: float,
    peakpower_mw: float,
    loss_scenarios: tuple[float, ...] = DEFAULT_LOSS_SCENARIOS,
) -> ConfidenceInterval:
    """Lance `fetch_pvgis_pvcalc` une fois par scénario et renvoie un `ConfidenceInterval`.

    Args:
        lat, lon: coordonnées en degrés.
        peakpower_mw: puissance crête en MWp (cohérent avec `fetch_pvgis_pvcalc`).
        loss_scenarios: tuple de `loss_pct` à balayer (au moins 1 valeur).

    Returns:
        `ConfidenceInterval` avec `low_mwh` (pertes max), `mid_mwh` (médiane des
        scénarios triés par `loss_pct` croissant), `high_mwh` (pertes min) et la
        liste complète des `LossScenario` dans l'ordre d'appel.
    """
    if not loss_scenarios:
        raise ValueError("loss_scenarios doit contenir au moins une valeur")

    scenarios: list[LossScenario] = []
    for loss_pct in loss_scenarios:
        result = fetch_pvgis_pvcalc(
            lat=lat,
            lon=lon,
            peakpower_mw=peakpower_mw,
            loss_pct=loss_pct,
        )
        annual_kwh = float(result["annual_total_kwh"])
        scenarios.append(LossScenario(loss_pct=loss_pct, annual_kwh=annual_kwh))

    sorted_by_loss_asc = sorted(scenarios, key=lambda s: s.loss_pct)
    high = sorted_by_loss_asc[0].annual_kwh / 1000.0  # pertes min → production max
    low = sorted_by_loss_asc[-1].annual_kwh / 1000.0  # pertes max → production min
    mid = sorted_by_loss_asc[len(sorted_by_loss_asc) // 2].annual_kwh / 1000.0

    return ConfidenceInterval(
        low_mwh=low,
        mid_mwh=mid,
        high_mwh=high,
        scenarios=scenarios,
    )
