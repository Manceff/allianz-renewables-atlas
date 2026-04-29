"""Tests pour src.lib.portfolio_aggregates sur le YAML réel."""

from __future__ import annotations

from src.lib.parks_loader import load_parks_index
from src.lib.portfolio_aggregates import PortfolioAggregates, compute_aggregates


def test_aggregates_on_real_parks() -> None:
    idx = load_parks_index()
    agg = compute_aggregates(idx.parks)

    assert isinstance(agg, PortfolioAggregates)
    assert agg.count_parks == len(idx.parks)
    assert agg.total_capacity_mw > 0
    assert agg.count_countries >= 5
    assert "solar" in agg.capacity_by_tech or "onshore_wind" in agg.capacity_by_tech
    assert len(agg.top5_by_capacity) <= 5
    assert all(isinstance(park_id, str) for park_id in agg.top5_by_capacity)


def test_aggregates_handles_missing_capacity() -> None:
    """Un parc à capacité nulle (ex: brindisi) ne casse pas l'agrégation."""
    idx = load_parks_index()
    agg = compute_aggregates(idx.parks)
    # On doit toujours produire des agrégats valides.
    assert agg.total_capacity_mw > 0
    # count_parks inclut TOUS les parcs (même sans capacité connue).
    assert agg.count_parks == len(idx.parks)


def test_aggregates_top5_sorted_descending() -> None:
    idx = load_parks_index()
    agg = compute_aggregates(idx.parks)

    by_id = {p.id: p for p in idx.parks}
    capacities = [by_id[pid].capacity_mwp for pid in agg.top5_by_capacity]
    # Tri décroissant.
    assert capacities == sorted(capacities, reverse=True)


def test_aggregates_capacity_sum_matches_buckets() -> None:
    """La somme des buckets tech doit égaler total_capacity_mw."""
    idx = load_parks_index()
    agg = compute_aggregates(idx.parks)

    assert sum(agg.capacity_by_tech.values()) == agg.total_capacity_mw
    assert sum(agg.capacity_by_country.values()) == agg.total_capacity_mw
