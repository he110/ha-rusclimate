"""Import the HA-independent api package without running the integration __init__ (it imports HA)."""

import contextlib
import pathlib
import sys
import types

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
pkg = types.ModuleType("rc")
pkg.__path__ = [str(ROOT / "custom_components" / "rusclimate")]
sys.modules.setdefault("rc", pkg)


@pytest.fixture(autouse=True)
def _allow_sockets(request):
    """With the Home Assistant pytest plugin installed, sockets are blocked unless enabled."""
    with contextlib.suppress(pytest.FixtureLookupError):
        request.getfixturevalue("socket_enabled")
