"""Shared test helpers and fake objects for mcp-pyatv tests."""
import asyncio
from unittest.mock import MagicMock

from pyatv.const import FeatureName, Protocol


# ---------------------------------------------------------------------------
# Feature mock
# ---------------------------------------------------------------------------

class MockFeatures:
    """Synchronous mock for atv.features interface.

    Matches pyatv's signature: in_state(states, *feature_names) -> bool
    """

    def __init__(self, up_available: bool = True):
        self._up_available = up_available

    def in_state(self, state, *feature_names) -> bool:
        if FeatureName.Up in feature_names:
            return self._up_available
        return False


# ---------------------------------------------------------------------------
# Fake ATV classes
# ---------------------------------------------------------------------------

class GoodAtv:
    """Simulates a fully established Apple TV connection (probe passes)."""

    def __init__(self):
        self.features = MockFeatures(up_available=True)
        self.was_closed = False

    def close(self) -> set:
        self.was_closed = True
        return set()


class PartialAtv:
    """Simulates pyatv connecting without Companion/MRP established (probe fails)."""

    def __init__(self):
        self.features = MockFeatures(up_available=False)
        self.was_closed = False

    def close(self) -> set:
        self.was_closed = True
        return set()


class RaisingCloseAtv:
    """PartialAtv variant where close() itself raises — tests exception swallowing."""

    def __init__(self):
        self.features = MockFeatures(up_available=False)

    def close(self) -> set:
        raise RuntimeError("simulated close failure")


class HomePodAtv:
    """Simulates a HomePod / AirPlay-only device.

    Deliberately has NO .features attribute — if _connect() incorrectly calls
    atv.features.in_state(...) for a needs_probe=False device, the test will
    fail with AttributeError, making the bug immediately obvious.
    """

    def __init__(self):
        self.was_closed = False

    def close(self) -> set:
        self.was_closed = True
        return set()


# ---------------------------------------------------------------------------
# Config factories
# ---------------------------------------------------------------------------

def make_apple_tv_config(
    name: str = "Living Room",
    identifier: str = "AA:BB:CC:DD:EE:FF",
) -> MagicMock:
    """Config for an Apple TV with Companion protocol service (needs_probe=True)."""
    svc = MagicMock()
    svc.protocol = Protocol.Companion
    cfg = MagicMock()
    cfg.name = name
    cfg.identifier = identifier
    cfg.services = [svc]
    return cfg


def make_mrp_config(
    name: str = "Apple TV 4K",
    identifier: str = "CC:DD:EE:FF:AA:BB",
) -> MagicMock:
    """Config for an older Apple TV with MRP protocol service (needs_probe=True)."""
    svc = MagicMock()
    svc.protocol = Protocol.MRP
    cfg = MagicMock()
    cfg.name = name
    cfg.identifier = identifier
    cfg.services = [svc]
    return cfg


def make_homepod_config(
    name: str = "HomePod",
    identifier: str = "BB:CC:DD:EE:FF:AA",
) -> MagicMock:
    """Config for a HomePod with AirPlay-only service (needs_probe=False)."""
    svc = MagicMock()
    svc.protocol = Protocol.AirPlay
    cfg = MagicMock()
    cfg.name = name
    cfg.identifier = identifier
    cfg.services = [svc]
    return cfg


def make_raop_config(
    name: str = "AirPlay Speaker",
    identifier: str = "DD:EE:FF:AA:BB:CC",
) -> MagicMock:
    """Config for a RAOP-only AirPlay speaker (needs_probe=False)."""
    svc = MagicMock()
    svc.protocol = Protocol.RAOP
    cfg = MagicMock()
    cfg.name = name
    cfg.identifier = identifier
    cfg.services = [svc]
    return cfg
