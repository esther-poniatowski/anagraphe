"""Pytest configuration and shared fixtures for anagraphe tests."""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolated_cache(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Point the cache of the states to a folder of the test, so that no test reads or fills the
    cache of the machine."""
    cache = tmp_path_factory.mktemp("cache") / "states"
    monkeypatch.setenv("ANAGRAPHE_CACHE", str(cache))
    return cache
