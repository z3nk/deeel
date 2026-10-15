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


def _fix_apptest_single_select_button_group() -> None:
    """
    Streamlit 1.45's AppTest iterates a single-select segmented_control's value
    character by character ("any" → "a", "n", "y") and crashes. Treat a scalar
    value as a one-item list. Test harness only; the app itself is unaffected.
    """
    from streamlit.testing.v1 import element_tree as et

    original = et.ButtonGroup.indices.fget

    def indices(self):
        value = self.value
        if value is None:
            return []
        if isinstance(value, (str, int, float)):
            return [self.options.index(self.format_func(value))]
        return original(self)

    et.ButtonGroup.indices = property(indices)


_fix_apptest_single_select_button_group()
