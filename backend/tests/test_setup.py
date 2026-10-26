"""Smoke test to confirm pytest and imports work. Delete once you have real tests."""

import app


def test_app_package_imports():
    assert app is not None
