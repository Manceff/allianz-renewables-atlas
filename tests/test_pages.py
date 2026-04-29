"""Smoke tests pour les pages Streamlit — vérifie qu'elles render sans exception."""

from __future__ import annotations


def test_methodology_page_renders():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("src/pages/5_📐_Methodology.py").run()
    assert not at.exception
