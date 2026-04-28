"""Comparaison production solaire estimée (PVGIS) vs publiée (opérateur).

Severity bandes :
- green  : |delta| < 5%   → estimation alignée
- yellow : 5% ≤ |delta| < 10% → écart à investiguer
- red    : |delta| ≥ 10%  → écart significatif (perf, ombrage, dégradation, ou data quality)
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class Severity(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


GREEN_THRESHOLD_PCT = 5.0
YELLOW_THRESHOLD_PCT = 10.0


def severity_from_relative_delta(rel_pct: float) -> Severity:
    """Renvoie la severity correspondant au % d'écart relatif (signé)."""
    abs_pct = abs(rel_pct)
    if abs_pct < GREEN_THRESHOLD_PCT:
        return Severity.GREEN
    if abs_pct < YELLOW_THRESHOLD_PCT:
        return Severity.YELLOW
    return Severity.RED


def _interpretation(rel_pct: float, severity: Severity) -> str:
    if severity == Severity.GREEN:
        return (
            f"Écart de {rel_pct:+.1f}% — estimation PVGIS alignée avec la production publiée. "
            "Modélisation cohérente."
        )
    if severity == Severity.YELLOW:
        return (
            f"Écart de {rel_pct:+.1f}% — modéré. À vérifier : pertes système réelles, "
            "ombrages locaux, ou méthodologie de reporting de l'opérateur."
        )
    sense = "surestime" if rel_pct > 0 else "sous-estime"
    return (
        f"Écart de {rel_pct:+.1f}% — significatif. PVGIS {sense} de plus de 10%. "
        "Pistes : dégradation panneaux, curtailment, indisponibilités, ou data quality publiée."
    )


def compute_production_delta(
    estimated_annual_mwh: float,
    reported_annual_mwh: float,
) -> dict[str, Any]:
    """Calcule l'écart (estimée − reportée) / reportée et la severity.

    Args:
        estimated_annual_mwh: production annuelle estimée (PVGIS).
        reported_annual_mwh: production annuelle publiée par l'opérateur.

    Returns:
        Dict serialisable JSON avec estimated/reported/absolute_delta/relative_delta_pct/
        severity/interpretation.

    Raises:
        ValueError: inputs négatifs ou reported = 0.
    """
    if estimated_annual_mwh < 0:
        raise ValueError(f"estimated_annual_mwh doit être ≥ 0, reçu {estimated_annual_mwh}")
    if reported_annual_mwh < 0:
        raise ValueError(f"reported_annual_mwh doit être ≥ 0, reçu {reported_annual_mwh}")
    if reported_annual_mwh == 0:
        raise ValueError("reported_annual_mwh = 0 : impossible de calculer le delta relatif")

    absolute = estimated_annual_mwh - reported_annual_mwh
    relative_pct = absolute / reported_annual_mwh * 100.0
    severity = severity_from_relative_delta(relative_pct)

    return {
        "estimated_annual_mwh": estimated_annual_mwh,
        "reported_annual_mwh": reported_annual_mwh,
        "absolute_delta_mwh": absolute,
        "relative_delta_pct": relative_pct,
        "severity": severity.value,
        "interpretation": _interpretation(relative_pct, severity),
    }
