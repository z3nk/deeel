"""Shared test setup."""

import pytest

import snapshot


@pytest.fixture(autouse=True)
def no_real_snapshot(tmp_path, monkeypatch):
    """Never let tests load the real seed/approved.json into their temp databases."""
    monkeypatch.setattr(snapshot, "SNAPSHOT_PATH", tmp_path / "no-snapshot.json")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Tests never call Open Food Facts; tests that need it patch these themselves."""
    import openfoodfacts
    monkeypatch.setattr(openfoodfacts, "_fetch", lambda barcode: None)
    monkeypatch.setattr(openfoodfacts, "_search", lambda terms: [])
    openfoodfacts._cache.clear()
    openfoodfacts._search_cache.clear()
