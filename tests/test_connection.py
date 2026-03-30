import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from pyatv.exceptions import ConnectionFailedError, NotSupportedError

from mcp_pyatv.connection import _CONNECT_BACKOFF, _CONNECT_RETRIES, ConnectionManager

from .conftest import (
    GoodAtv,
    HomePodAtv,
    PartialAtv,
    RaisingCloseAtv,
    make_apple_tv_config,
    make_homepod_config,
    make_mrp_config,
    make_raop_config,
)


class FakeAtv:
    """Minimal fake AppleTV that tracks whether its close tasks were awaited."""

    def __init__(self):
        self.task_was_awaited = False

    def close(self):
        async def _close():
            self.task_was_awaited = True

        return {asyncio.create_task(_close())}


# ---------------------------------------------------------------------------
# Existing test (fixed: _configs is intentionally retained after close_all)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_close_all_awaits_tasks():
    conn = ConnectionManager(storage=None)
    fake = FakeAtv()
    conn._connections["fake-id"] = fake
    conn._configs["fake-id"] = object()  # populate to verify retention

    await conn.close_all()

    assert fake.task_was_awaited, "close_all() did not await the tasks returned by atv.close()"
    assert conn._connections == {}
    # _configs is intentionally NOT cleared — retained for reconnection after restart
    assert "fake-id" in conn._configs


# ---------------------------------------------------------------------------
# TestConnect — _connect() probe + retry logic
# ---------------------------------------------------------------------------

class TestConnect:

    @pytest.mark.asyncio
    async def test_homepod_connects_without_probe(self):
        """AirPlay-only device: connects once, never calls features.in_state."""
        conn = ConnectionManager(storage=None)
        cfg = make_homepod_config()
        atv = HomePodAtv()  # no .features — AttributeError if probe called

        with patch("mcp_pyatv.connection.pyatv.connect", AsyncMock(return_value=atv)) as mock_connect, \
             patch("mcp_pyatv.connection.pyatv.scan", new=AsyncMock()) as mock_scan:
            result = await conn._connect(cfg)

        mock_connect.assert_awaited_once()
        mock_scan.assert_not_awaited()
        assert result is atv
        assert conn._connections[cfg.identifier] is atv

    @pytest.mark.asyncio
    async def test_raop_only_connects_without_probe(self):
        """RAOP-only AirPlay speaker: same path as HomePod, no probe."""
        conn = ConnectionManager(storage=None)
        cfg = make_raop_config()
        atv = HomePodAtv()

        with patch("mcp_pyatv.connection.pyatv.connect", AsyncMock(return_value=atv)) as mock_connect:
            result = await conn._connect(cfg)

        mock_connect.assert_awaited_once()
        assert result is atv

    @pytest.mark.asyncio
    async def test_apple_tv_probe_passes_first_attempt(self):
        """Apple TV with Companion: probe passes immediately, no retries, no re-scan."""
        conn = ConnectionManager(storage=None)
        cfg = make_apple_tv_config()
        atv = GoodAtv()

        with patch("mcp_pyatv.connection.pyatv.connect", AsyncMock(return_value=atv)) as mock_connect, \
             patch("mcp_pyatv.connection.pyatv.scan", new=AsyncMock()) as mock_scan, \
             patch("mcp_pyatv.connection.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            result = await conn._connect(cfg)

        mock_connect.assert_awaited_once()
        mock_scan.assert_not_awaited()
        mock_sleep.assert_not_awaited()
        assert result is atv
        assert conn._connections[cfg.identifier] is atv
        assert conn._configs[cfg.identifier] is cfg

    @pytest.mark.asyncio
    async def test_mrp_protocol_triggers_probe(self):
        """Older Apple TV with MRP also uses needs_probe=True path."""
        conn = ConnectionManager(storage=None)
        cfg = make_mrp_config()
        atv = GoodAtv()

        with patch("mcp_pyatv.connection.pyatv.connect", AsyncMock(return_value=atv)), \
             patch("mcp_pyatv.connection.pyatv.scan", new=AsyncMock()) as mock_scan:
            result = await conn._connect(cfg)

        mock_scan.assert_not_awaited()  # probe passed, no retry needed
        assert result is atv

    @pytest.mark.asyncio
    async def test_probe_fails_then_passes_on_second_attempt(self):
        """Probe fails attempt 1, re-scan + retry, probe passes attempt 2."""
        conn = ConnectionManager(storage=None)
        cfg = make_apple_tv_config()
        partial = PartialAtv()
        good = GoodAtv()
        fresh_cfg = make_apple_tv_config()  # fresh config from re-scan

        mock_connect = AsyncMock(side_effect=[partial, good])
        mock_scan = AsyncMock(return_value=[fresh_cfg])
        mock_sleep = AsyncMock()

        with patch("mcp_pyatv.connection.pyatv.connect", mock_connect), \
             patch("mcp_pyatv.connection.pyatv.scan", mock_scan), \
             patch("mcp_pyatv.connection.asyncio.sleep", mock_sleep):
            result = await conn._connect(cfg)

        assert mock_connect.await_count == 2
        mock_sleep.assert_awaited_once_with(_CONNECT_BACKOFF[0])
        mock_scan.assert_awaited_once()
        assert mock_scan.call_args.kwargs["timeout"] == 5
        assert partial.was_closed is True
        assert result is good
        assert conn._connections[cfg.identifier] is good
        assert conn._configs[cfg.identifier] is fresh_cfg

    @pytest.mark.asyncio
    async def test_all_retries_exhausted_raises_connection_failed_error(self):
        """After _CONNECT_RETRIES failures, ConnectionFailedError is raised, device not cached."""
        conn = ConnectionManager(storage=None)
        cfg = make_apple_tv_config()
        partials = [PartialAtv() for _ in range(_CONNECT_RETRIES)]

        mock_connect = AsyncMock(side_effect=partials)
        mock_scan = AsyncMock(return_value=[])
        mock_sleep = AsyncMock()

        with patch("mcp_pyatv.connection.pyatv.connect", mock_connect), \
             patch("mcp_pyatv.connection.pyatv.scan", mock_scan), \
             patch("mcp_pyatv.connection.asyncio.sleep", mock_sleep):
            with pytest.raises(ConnectionFailedError) as exc_info:
                await conn._connect(cfg)

        assert mock_connect.await_count == _CONNECT_RETRIES
        assert mock_sleep.await_count == _CONNECT_RETRIES - 1
        assert cfg.name in str(exc_info.value)
        assert cfg.identifier not in conn._connections

    @pytest.mark.asyncio
    async def test_stale_atv_close_called_on_probe_failure(self):
        """close() is invoked on each partial atv after its probe fails."""
        conn = ConnectionManager(storage=None)
        cfg = make_apple_tv_config()
        partial = PartialAtv()
        good = GoodAtv()

        with patch("mcp_pyatv.connection.pyatv.connect", AsyncMock(side_effect=[partial, good])), \
             patch("mcp_pyatv.connection.pyatv.scan", AsyncMock(return_value=[])), \
             patch("mcp_pyatv.connection.asyncio.sleep", AsyncMock()):
            result = await conn._connect(cfg)

        assert partial.was_closed is True
        assert result is good

    @pytest.mark.asyncio
    async def test_stale_atv_close_exception_swallowed(self):
        """If close() itself raises, the exception is swallowed and retry continues."""
        conn = ConnectionManager(storage=None)
        cfg = make_apple_tv_config()
        raising = RaisingCloseAtv()
        good = GoodAtv()

        with patch("mcp_pyatv.connection.pyatv.connect", AsyncMock(side_effect=[raising, good])), \
             patch("mcp_pyatv.connection.pyatv.scan", AsyncMock(return_value=[])), \
             patch("mcp_pyatv.connection.asyncio.sleep", AsyncMock()):
            result = await conn._connect(cfg)  # must not raise RuntimeError

        assert result is good

    @pytest.mark.asyncio
    async def test_rescan_uses_timeout_5_and_backoff_increases(self):
        """Re-scan always uses timeout=5; sleep delays follow _CONNECT_BACKOFF."""
        conn = ConnectionManager(storage=None)
        cfg = make_apple_tv_config()
        partial1, partial2 = PartialAtv(), PartialAtv()
        good = GoodAtv()

        mock_connect = AsyncMock(side_effect=[partial1, partial2, good])
        mock_scan = AsyncMock(return_value=[])
        mock_sleep = AsyncMock()

        with patch("mcp_pyatv.connection.pyatv.connect", mock_connect), \
             patch("mcp_pyatv.connection.pyatv.scan", mock_scan), \
             patch("mcp_pyatv.connection.asyncio.sleep", mock_sleep):
            result = await conn._connect(cfg)

        assert mock_scan.await_count == 2
        for call in mock_scan.call_args_list:
            assert call.kwargs["timeout"] == 5

        sleep_delays = [c.args[0] for c in mock_sleep.call_args_list]
        assert sleep_delays == list(_CONNECT_BACKOFF)
        assert result is good

    @pytest.mark.asyncio
    async def test_fresh_config_from_rescan_used_for_retry(self):
        """If re-scan finds the device, the fresh config is used for the next connect."""
        conn = ConnectionManager(storage=None)
        original_cfg = make_apple_tv_config(identifier="AA:BB:CC:DD:EE:FF")
        fresh_cfg = make_apple_tv_config(identifier="AA:BB:CC:DD:EE:FF", name="Updated Name")

        partial = PartialAtv()
        good = GoodAtv()
        mock_connect = AsyncMock(side_effect=[partial, good])

        with patch("mcp_pyatv.connection.pyatv.connect", mock_connect), \
             patch("mcp_pyatv.connection.pyatv.scan", AsyncMock(return_value=[fresh_cfg])), \
             patch("mcp_pyatv.connection.asyncio.sleep", AsyncMock()):
            result = await conn._connect(original_cfg)

        second_call_cfg = mock_connect.call_args_list[1].args[0]
        assert second_call_cfg is fresh_cfg
        assert conn._configs[original_cfg.identifier] is fresh_cfg
        assert result is good

    @pytest.mark.asyncio
    async def test_device_not_in_rescan_uses_original_config(self):
        """If re-scan returns empty list, retry uses the original config."""
        conn = ConnectionManager(storage=None)
        cfg = make_apple_tv_config()
        partial = PartialAtv()
        good = GoodAtv()

        mock_connect = AsyncMock(side_effect=[partial, good])

        with patch("mcp_pyatv.connection.pyatv.connect", mock_connect), \
             patch("mcp_pyatv.connection.pyatv.scan", AsyncMock(return_value=[])), \
             patch("mcp_pyatv.connection.asyncio.sleep", AsyncMock()):
            result = await conn._connect(cfg)

        second_call_cfg = mock_connect.call_args_list[1].args[0]
        assert second_call_cfg is cfg
        assert result is good

    @pytest.mark.asyncio
    async def test_connect_returns_cached_if_already_connected(self):
        """_connect() returns immediately if identifier already in _connections."""
        conn = ConnectionManager(storage=None)
        cfg = make_apple_tv_config()
        existing = GoodAtv()
        conn._connections[cfg.identifier] = existing

        mock_connect = AsyncMock()

        with patch("mcp_pyatv.connection.pyatv.connect", mock_connect):
            result = await conn._connect(cfg)

        mock_connect.assert_not_awaited()
        assert result is existing


# ---------------------------------------------------------------------------
# TestExecuteNotSupported — execute() NotSupportedError path
# ---------------------------------------------------------------------------

class TestExecuteNotSupported:

    @pytest.mark.asyncio
    async def test_not_supported_triggers_reconnect_and_retry(self):
        """First operation raises NotSupportedError; reconnect + retry succeeds."""
        conn = ConnectionManager(storage=None)
        cfg = make_apple_tv_config()
        identifier = cfg.identifier
        first_atv = GoodAtv()
        fresh_atv = GoodAtv()
        conn._connections[identifier] = first_atv
        conn._configs[identifier] = cfg

        call_count = 0

        async def operation(atv):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise NotSupportedError("protocol not established")
            return "ok"

        with patch("mcp_pyatv.connection.pyatv.connect", AsyncMock(return_value=fresh_atv)):
            result = await conn.execute(device=identifier, operation=operation)

        assert result == "ok"
        assert call_count == 2
        assert conn._connections[identifier] is fresh_atv

    @pytest.mark.asyncio
    async def test_connections_evicted_before_force_reconnect(self):
        """execute() pops _connections[identifier] BEFORE calling _force_reconnect."""
        conn = ConnectionManager(storage=None)
        cfg = make_apple_tv_config()
        identifier = cfg.identifier
        first_atv = GoodAtv()
        fresh_atv = GoodAtv()
        conn._connections[identifier] = first_atv
        conn._configs[identifier] = cfg

        eviction_state = {}
        original_force_reconnect = conn._force_reconnect

        async def spy_force_reconnect(id_):
            eviction_state["had_connection"] = id_ in conn._connections
            return await original_force_reconnect(id_)

        async def operation(atv):
            if atv is first_atv:
                raise NotSupportedError("not supported")
            return "ok"

        with patch("mcp_pyatv.connection.pyatv.connect", AsyncMock(return_value=fresh_atv)), \
             patch.object(conn, "_force_reconnect", new=spy_force_reconnect):
            await conn.execute(device=identifier, operation=operation)

        assert eviction_state["had_connection"] is False

    @pytest.mark.asyncio
    async def test_not_supported_second_attempt_raises(self):
        """If retry after reconnect also fails, the exception propagates."""
        conn = ConnectionManager(storage=None)
        cfg = make_apple_tv_config()
        identifier = cfg.identifier
        conn._connections[identifier] = GoodAtv()
        conn._configs[identifier] = cfg

        async def always_raises(atv):
            raise NotSupportedError("still not supported")

        fresh_atv = GoodAtv()
        with patch("mcp_pyatv.connection.pyatv.connect", AsyncMock(return_value=fresh_atv)):
            with pytest.raises(NotSupportedError):
                await conn.execute(device=identifier, operation=always_raises)

        mock_connect = AsyncMock(return_value=fresh_atv)
        with patch("mcp_pyatv.connection.pyatv.connect", mock_connect):
            with pytest.raises(NotSupportedError):
                conn._connections[identifier] = GoodAtv()
                await conn.execute(device=identifier, operation=always_raises)
        mock_connect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_supported_only_one_reconnect_attempt(self):
        """execute() makes exactly one reconnect attempt — no infinite loop."""
        conn = ConnectionManager(storage=None)
        cfg = make_apple_tv_config()
        identifier = cfg.identifier
        conn._connections[identifier] = GoodAtv()
        conn._configs[identifier] = cfg

        reconnect_count = 0
        original_force_reconnect = conn._force_reconnect

        async def counting_force_reconnect(id_):
            nonlocal reconnect_count
            reconnect_count += 1
            return await original_force_reconnect(id_)

        async def always_raises(atv):
            raise NotSupportedError("not supported")

        fresh_atv = GoodAtv()
        with patch("mcp_pyatv.connection.pyatv.connect", AsyncMock(return_value=fresh_atv)), \
             patch.object(conn, "_force_reconnect", new=counting_force_reconnect):
            with pytest.raises(NotSupportedError):
                await conn.execute(device=identifier, operation=always_raises)

        assert reconnect_count == 1

    @pytest.mark.asyncio
    async def test_not_supported_reconnect_runs_probe_path(self):
        """Reconnect after NotSupportedError goes through _connect() probe logic."""
        conn = ConnectionManager(storage=None)
        cfg = make_apple_tv_config()  # Companion -> needs_probe=True
        identifier = cfg.identifier
        conn._connections[identifier] = GoodAtv()
        conn._configs[identifier] = cfg

        call_count = 0

        async def operation(atv):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise NotSupportedError("not supported")
            return "reconnected"

        fresh_atv = GoodAtv()  # probe will pass (features.in_state returns True)
        mock_connect = AsyncMock(return_value=fresh_atv)
        mock_scan = AsyncMock(return_value=[])
        mock_sleep = AsyncMock()

        with patch("mcp_pyatv.connection.pyatv.connect", mock_connect), \
             patch("mcp_pyatv.connection.pyatv.scan", mock_scan), \
             patch("mcp_pyatv.connection.asyncio.sleep", mock_sleep):
            result = await conn.execute(device=identifier, operation=operation)

        assert result == "reconnected"
        # Probe passed on first attempt of _connect — no re-scan or sleep needed
        mock_scan.assert_not_awaited()
        mock_sleep.assert_not_awaited()
