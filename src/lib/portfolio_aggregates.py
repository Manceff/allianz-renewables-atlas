"""Agrégats portfolio à partir de la liste des parcs (vue IC Snapshot)."""

from __future__ import annotations

from pydantic import BaseModel

from src.lib.parks_loader import ParkModel


class PortfolioAggregates(BaseModel):
    """Métriques portefeuille calculées à partir de `parks_index.yaml`."""

    total_capacity_mw: float
    count_parks: int
    count_countries: int
    count_techs: int
    capacity_by_tech: dict[str, float]
    capacity_by_country: dict[str, float]
    vintage_distribution: dict[int, float]
    top5_by_capacity: list[str]


def compute_aggregates(parks: list[ParkModel]) -> PortfolioAggregates:
    """Calcule les métriques portfolio à partir d'une liste de ParkModel.

    Pure function : aucun IO. Les parcs sans `capacity_mwp` sont exclus
    des sommes mais comptés dans `count_parks`.
    """
    parks_with_capacity = [p for p in parks if p.capacity_mwp is not None]

    total = sum(p.capacity_mwp for p in parks_with_capacity)

    by_tech: dict[str, float] = {}
    for p in parks_with_capacity:
        key = p.technology.value
        by_tech[key] = by_tech.get(key, 0.0) + p.capacity_mwp

    by_country: dict[str, float] = {}
    for p in parks_with_capacity:
        by_country[p.country] = by_country.get(p.country, 0.0) + p.capacity_mwp

    vintage: dict[int, float] = {}
    for p in parks_with_capacity:
        year = p.commissioning_year
        vintage[year] = vintage.get(year, 0.0) + p.capacity_mwp

    top5 = sorted(
        parks_with_capacity, key=lambda p: p.capacity_mwp, reverse=True
    )[:5]

    return PortfolioAggregates(
        total_capacity_mw=total,
        count_parks=len(parks),
        count_countries=len(by_country),
        count_techs=len(by_tech),
        capacity_by_tech=by_tech,
        capacity_by_country=by_country,
        vintage_distribution=vintage,
        top5_by_capacity=[p.id for p in top5],
    )
