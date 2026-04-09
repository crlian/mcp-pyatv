"""Tests for batch tools: execute_sequence and repeat_command."""
import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_pyatv.tools.batch import register_batch_tools


# ---------------------------------------------------------------------------
# Mock infrastructure
# ---------------------------------------------------------------------------

class MockAtv:
    """Fake AppleTV with remote_control, apps, audio, keyboard, power, metadata."""

    def __init__(self):
        self.remote_control = MagicMock()
        self.apps = MagicMock()
        self.audio = MagicMock()
        self.keyboard = MagicMock()
        self.power = MagicMock()
        self.metadata = MagicMock()

        # Make remote_control methods return awaitables
        for name in ("up", "down", "left", "right", "select", "menu",
                      "home", "top_menu", "play", "pause", "play_pause",
                      "stop", "next", "previous"):
            setattr(self.remote_control, name, AsyncMock())

        self.audio.set_volume = AsyncMock()
        self.audio.volume_up = AsyncMock()
        self.audio.volume_down = AsyncMock()
        self.keyboard.set_text = AsyncMock()
        self.keyboard.clear_text = AsyncMock()
        self.power.turn_on = AsyncMock()
        self.power.turn_off = AsyncMock()

        # apps.app_list returns a coroutine
        mock_app = MagicMock()
        mock_app.name = "Netflix"
        mock_app.identifier = "com.netflix.Netflix"
        self.apps.app_list = AsyncMock(return_value=[mock_app])
        self.apps.launch_app = AsyncMock()

        # metadata.playing returns a coroutine
        playing = MagicMock()
        playing.title = "Test Title"
        playing.artist = "Test Artist"
        playing.album = "Test Album"
        playing.genre = None
        playing.media_type = MagicMock(name="Music")
        playing.device_state = MagicMock(name="Playing")
        playing.position = 42
        playing.total_time = 200
        playing.shuffle = None
        playing.repeat = None
        playing.series_name = None
        playing.season_number = None
        playing.episode_number = None
        self.metadata.playing = AsyncMock(return_value=playing)
        self.metadata.app = MagicMock()
        self.metadata.app.identifier = "com.test.app"
        self.metadata.app.name = "TestApp"


class MockConn:
    """Mock ConnectionManager that runs operations on a MockAtv."""

    def __init__(self, mock_atv):
        self._atv = mock_atv

    async def execute(self, device, operation):
        result = operation(self._atv)
        if inspect.isawaitable(result):
            return await result
        return result


class FakeMcp:
    """Minimal mock for FastMCP that captures tool registrations."""

    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn
        return decorator


def _make_ctx(mock_conn):
    ctx = MagicMock()
    ctx.lifespan_context = {
        "get_connections": AsyncMock(return_value=mock_conn),
        "is_screen_state_checked": lambda: True,
    }
    return ctx


# ---------------------------------------------------------------------------
# Tests: execute_sequence
# ---------------------------------------------------------------------------

class TestExecuteSequence:

    @pytest.fixture
    def setup(self):
        mock_atv = MockAtv()
        mock_conn = MockConn(mock_atv)
        fake_mcp = FakeMcp()
        register_batch_tools(fake_mcp, pymobiledevice3_path=None)
        ctx = _make_ctx(mock_conn)
        return fake_mcp, mock_atv, ctx

    @pytest.mark.asyncio
    async def test_navigate_steps(self, setup):
        fake_mcp, mock_atv, ctx = setup
        execute_sequence = fake_mcp.tools["execute_sequence"]

        steps = [
            {"action": "navigate", "direction": "down"},
            {"action": "navigate", "direction": "down"},
            {"action": "navigate", "direction": "select"},
        ]
        result = await execute_sequence(steps=steps, device=None, ctx=ctx)

        assert len(result) == 3
        for r in result:
            assert "error" not in r
        assert result[0]["result"] == "Navigated: down (single_tap)"
        assert result[2]["result"] == "Navigated: select (single_tap)"

    @pytest.mark.asyncio
    async def test_stops_on_error(self, setup):
        fake_mcp, mock_atv, ctx = setup
        execute_sequence = fake_mcp.tools["execute_sequence"]

        steps = [
            {"action": "navigate", "direction": "down"},
            {"action": "bogus_action"},
            {"action": "navigate", "direction": "up"},
        ]
        result = await execute_sequence(steps=steps, device=None, ctx=ctx)

        assert len(result) == 2
        assert "error" not in result[0]
        assert "error" in result[1]
        assert "Unknown action" in result[1]["error"]

    @pytest.mark.asyncio
    async def test_wait(self, setup):
        fake_mcp, mock_atv, ctx = setup
        execute_sequence = fake_mcp.tools["execute_sequence"]

        steps = [{"action": "wait", "seconds": 0.01}]
        with patch("mcp_pyatv.tools.batch.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            result = await execute_sequence(steps=steps, device=None, ctx=ctx)
            mock_sleep.assert_awaited_once_with(0.01)

        assert len(result) == 1
        assert "Waited" in result[0]["result"]

    @pytest.mark.asyncio
    async def test_max_steps(self, setup):
        fake_mcp, mock_atv, ctx = setup
        execute_sequence = fake_mcp.tools["execute_sequence"]

        steps = [{"action": "play"}] * 31
        result = await execute_sequence(steps=steps, device=None, ctx=ctx)

        assert "Too many steps" in result

    @pytest.mark.asyncio
    async def test_empty(self, setup):
        fake_mcp, mock_atv, ctx = setup
        execute_sequence = fake_mcp.tools["execute_sequence"]

        result = await execute_sequence(steps=[], device=None, ctx=ctx)
        assert "No steps" in result

    @pytest.mark.asyncio
    async def test_launch_app(self, setup):
        fake_mcp, mock_atv, ctx = setup
        execute_sequence = fake_mcp.tools["execute_sequence"]

        steps = [{"action": "launch_app", "app": "Netflix"}]
        result = await execute_sequence(steps=steps, device=None, ctx=ctx)

        assert len(result) == 1
        assert "Launched Netflix" in result[0]["result"]

    @pytest.mark.asyncio
    async def test_set_volume(self, setup):
        fake_mcp, mock_atv, ctx = setup
        execute_sequence = fake_mcp.tools["execute_sequence"]

        steps = [{"action": "set_volume", "level": 50}]
        result = await execute_sequence(steps=steps, device=None, ctx=ctx)

        assert len(result) == 1
        assert "Volume set to 50" in result[0]["result"]


# ---------------------------------------------------------------------------
# Tests: repeat_command
# ---------------------------------------------------------------------------

class TestRepeatCommand:

    @pytest.fixture
    def setup(self):
        mock_atv = MockAtv()
        mock_conn = MockConn(mock_atv)
        fake_mcp = FakeMcp()
        register_batch_tools(fake_mcp, pymobiledevice3_path=None)
        ctx = _make_ctx(mock_conn)
        return fake_mcp, mock_atv, ctx

    @pytest.mark.asyncio
    async def test_basic(self, setup):
        fake_mcp, mock_atv, ctx = setup
        repeat_command = fake_mcp.tools["repeat_command"]

        with patch("mcp_pyatv.tools.batch.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            result = await repeat_command(
                direction="down", count=5, delay_ms=100, device=None, ctx=ctx
            )
            # 4 sleeps between 5 presses
            assert mock_sleep.await_count == 4

        assert "5 time(s)" in result
        assert "down" in result

    @pytest.mark.asyncio
    async def test_max_exceeded(self, setup):
        fake_mcp, mock_atv, ctx = setup
        repeat_command = fake_mcp.tools["repeat_command"]

        result = await repeat_command(
            direction="down", count=21, device=None, ctx=ctx
        )
        assert "too high" in result.lower()

    @pytest.mark.asyncio
    async def test_invalid_direction(self, setup):
        fake_mcp, mock_atv, ctx = setup
        repeat_command = fake_mcp.tools["repeat_command"]

        result = await repeat_command(
            direction="diagonal", count=1, device=None, ctx=ctx
        )
        assert "Unknown direction" in result
