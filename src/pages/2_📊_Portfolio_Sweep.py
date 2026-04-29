"""Page Portfolio Sweep — vue hero du signal quantitatif (estimé vs publié).

Hero page : lecture en 15 secondes. Aucun appel PVGIS — on lit le snapshot
statique `data/portfolio_sweep.json` validé via `PortfolioSweep`.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.lib.schemas import PortfolioSweep

logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Portfolio Sweep — Allianz Renewables Atlas",
    page_icon="📊",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Constantes & loaders
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent.parent
SWEEP_PATH = ROOT / "data" / "portfolio_sweep.json"

SEVERITY_COLORS = {
    "green": "rgb(34,197,94)",
    "yellow": "rgb(234,179,8)",
    "red": "rgb(239,68,68)",
    "unknown": "rgb(148,163,184)",
}

SEVERITY_EMOJI = {
    "green": "🟢",
    "yellow": "🟡",
    "red": "🔴",
    "unknown": "⚪",
}


def _load_sweep() -> PortfolioSweep | None:
    """Charge `portfolio_sweep.json` validé Pydantic. Retourne None si absent."""
    if not SWEEP_PATH.exists():
        return None
    raw = SWEEP_PATH.read_text(encoding="utf-8")
    return PortfolioSweep.model_validate_json(raw)


def _format_park_name(park_id: str) -> str:
    """Normalise le slug en label lisible (ex: `grenergy-spain-300` → `Grenergy Spain 300`)."""
    return park_id.replace("-", " ").replace("_", " ").title()


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title("📊 Portfolio Sweep — Estimated vs Reported Production")
st.caption(
    "PVGIS estimate (with 10/14/18% loss confidence interval) compared to publicly "
    "reported production figures, for solar parks where both are available."
)

sweep = _load_sweep()

if sweep is None or not sweep.entries:
    st.error(
        "Snapshot `data/portfolio_sweep.json` indisponible ou vide. "
        "Régénérer via `scripts/precompute_all.py`."
    )
    st.stop()

# Tri par park_id pour un ordre stable (lisibilité analyste).
entries = sorted(sweep.entries, key=lambda e: e.park_id)

# ---------------------------------------------------------------------------
# Plotly horizontal bar chart — confidence interval + reported marker
# ---------------------------------------------------------------------------

park_labels = [_format_park_name(e.park_id) for e in entries]
low_values = [e.confidence_interval.low_mwh for e in entries]
mid_values = [e.confidence_interval.mid_mwh for e in entries]
high_values = [e.confidence_interval.high_mwh for e in entries]
reported_values = [e.reported_mwh for e in entries]
severities = [e.severity for e in entries]
bar_colors = [SEVERITY_COLORS.get(sev, SEVERITY_COLORS["unknown"]) for sev in severities]

fig = go.Figure()

# Bande low → high (confidence interval) en barre horizontale.
# Astuce Plotly : on trace une barre `base=low` de longueur `high - low`.
fig.add_trace(
    go.Bar(
        y=park_labels,
        x=[high - low for high, low in zip(high_values, low_values)],
        base=low_values,
        orientation="h",
        marker=dict(color=bar_colors, opacity=0.35, line=dict(width=0)),
        name="Confidence interval (10–18% loss)",
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Low: %{base:,.0f} MWh<br>"
            "High: %{customdata:,.0f} MWh<extra></extra>"
        ),
        customdata=high_values,
        showlegend=True,
    )
)

# Marker mid (estimation centrale, loss=14%).
fig.add_trace(
    go.Scatter(
        y=park_labels,
        x=mid_values,
        mode="markers",
        marker=dict(
            symbol="diamond",
            size=14,
            color=bar_colors,
            line=dict(color="white", width=1.5),
        ),
        name="PVGIS mid (loss=14%)",
        hovertemplate="<b>%{y}</b><br>Mid: %{x:,.0f} MWh<extra></extra>",
    )
)

# Marker reported (production publiée).
fig.add_trace(
    go.Scatter(
        y=park_labels,
        x=reported_values,
        mode="markers",
        marker=dict(
            symbol="square",
            size=13,
            color="#0f172a",
            line=dict(color="white", width=1.5),
        ),
        name="Reported (operator)",
        hovertemplate="<b>%{y}</b><br>Reported: %{x:,.0f} MWh<extra></extra>",
    )
)

fig.update_layout(
    xaxis_title="Annual production (MWh)",
    yaxis_title=None,
    bargap=0.45,
    height=120 + 70 * len(entries),
    margin=dict(l=20, r=20, t=30, b=40),
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1,
    ),
    plot_bgcolor="rgba(0,0,0,0)",
)
fig.update_xaxes(
    tickformat=",.0f",
    showgrid=True,
    gridcolor="rgba(148,163,184,0.2)",
    zeroline=False,
)
fig.update_yaxes(
    showgrid=False,
    autorange="reversed",  # premier parc en haut
)

st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------------------------
# Detail table
# ---------------------------------------------------------------------------

st.subheader("Detail")


def _format_mwh(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:,.0f}"


def _format_range(low: float, high: float) -> str:
    return f"{low:,.0f} — {high:,.0f}"


def _format_delta(delta_pct: float | None) -> str:
    if delta_pct is None:
        return "n/a"
    return f"{delta_pct:+.1f}%"


def _format_severity(sev: str) -> str:
    return f"{SEVERITY_EMOJI.get(sev, '⚪')} {sev}"


rows = [
    {
        "Park": _format_park_name(e.park_id),
        "Capacity (MWp)": f"{e.capacity_mwp:,.1f}" if e.capacity_mwp is not None else "n/a",
        "Reported (MWh)": _format_mwh(e.reported_mwh),
        "Estimated mid (MWh)": _format_mwh(e.confidence_interval.mid_mwh),
        "Range (MWh)": _format_range(
            e.confidence_interval.low_mwh, e.confidence_interval.high_mwh
        ),
        "Δ% vs reported": _format_delta(e.delta_pct),
        "Severity": _format_severity(e.severity),
        "Source": str(e.source_url) if e.source_url else "",
    }
    for e in entries
]

df = pd.DataFrame(rows)

st.dataframe(
    df,
    hide_index=True,
    width="stretch",
    column_config={
        "Source": st.column_config.LinkColumn(
            "Source",
            display_text="press release",
        ),
    },
)

# ---------------------------------------------------------------------------
# Footer caption
# ---------------------------------------------------------------------------

st.caption(
    f"Sweep generated: {sweep.generated_at.strftime('%Y-%m-%d')}. "
    "Severity thresholds: 🟢 |Δ| < 5% · 🟡 5%–10% · 🔴 ≥ 10% "
    "(see Methodology page for the full convention)."
)
