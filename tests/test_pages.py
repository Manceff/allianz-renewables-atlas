"""Smoke test pour la single-page app."""

from __future__ import annotations


def test_app_renders_default(monkeypatch):
    """L'app monte sans exception, sans parc sélectionné."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("src/app.py").run(timeout=20)
    assert not at.exception
