"""Shared test setup."""

import pytest

import snapshot


@pytest.fixture(autouse=True)
def no_real_snapshot(tmp_path, monkeypatch):
    """Never let tests load the real seed/approved.json into their temp databases."""
    monkeypatch.setattr(snapshot, "SNAPSHOT_PATH", tmp_path / "no-snapshot.json")
