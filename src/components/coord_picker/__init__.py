"""Custom Streamlit component — satellite view with double-click coord pick.

Renders an Esri World Imagery satellite map centered on the given lat/lon.
On double-click, captures the new lat/lon and returns them to Streamlit
so the caller can persist the override.
"""

from __future__ import annotations

from pathlib import Path

import streamlit.components.v1 as components

_FRONTEND = Path(__file__).resolve().parent / "frontend"

_component_func = components.declare_component(
    "coord_picker",
    path=str(_FRONTEND),
)


def coord_picker(
    lat: float,
    lon: float,
    label: str,
    height: int = 360,
    key: str = "coord_picker",
) -> list[float] | None:
    """Render a satellite map and return [lat, lon] when user double-clicks.

    Args:
        lat, lon: initial center / marker position.
        label: park name shown in the marker popup.
        height: iframe height in px.
        key: unique key (use park_id to reset state when park changes).

    Returns:
        [lat, lon] if the user has double-clicked since last render, None otherwise.
    """
    return _component_func(
        lat=lat, lon=lon, label=label, height=height,
        key=key, default=None,
    )
