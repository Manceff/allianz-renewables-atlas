"""Custom Streamlit component — globe.gl interactive picker.

Renders a 3D Earth globe with clickable solar park markers. On click,
returns the park_id back to Streamlit, allowing the caller to render
the detail panel below without using a separate selectbox.
"""

from __future__ import annotations

from pathlib import Path

import streamlit.components.v1 as components

_FRONTEND = Path(__file__).resolve().parent / "frontend"

_component_func = components.declare_component(
    "globe_picker",
    path=str(_FRONTEND),
)


def globe_picker(parks: list[dict], height: int = 620, key: str = "globe_picker") -> str | None:
    """Render the interactive globe and return the clicked park_id.

    Args:
        parks: list of dicts with keys id, name, country, cap, lat, lng.
        height: iframe height in px.
        key: Streamlit widget key for state persistence.

    Returns:
        park_id (str) of the clicked park, or None if no click yet.
    """
    return _component_func(parks=parks, height=height, key=key, default=None)
