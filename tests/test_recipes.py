"""Tests for the recipes system: storage and recipe tools."""
import asyncio
import inspect
import json
import os
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_pyatv.recipes import (
    Recipe,
    load_recipes,
    save_recipe as save_recipe_storage,
    delete_recipe as delete_recipe_storage,
    _apply_decay,
)
from mcp_pyatv.tools.recipes import register_recipe_tools


# ---------------------------------------------------------------------------
# Mock infrastructure (mirrors test_batch.py)
# ---------------------------------------------------------------------------

class MockAtv:
    def __init__(self):
        self.remote_control = MagicMock()
        self.apps = MagicMock()
        self.audio = MagicMock()
        self.keyboard = MagicMock()
        self.power = MagicMock()
        self.metadata = MagicMock()

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

        mock_app = MagicMock()
        mock_app.name = "Netflix"
        mock_app.identifier = "com.netflix.Netflix"
        self.apps.app_list = AsyncMock(return_value=[mock_app])
        self.apps.launch_app = AsyncMock()

        playing = MagicMock()
        playing.title = "Test Title"
        playing.artist = "Test Artist"
        playing.album = "Test Album"
        playing.genre = None
        playing.media_type = MagicMock(name="Music")
        playing.device_state = MagicMock(name="Playing")
        playing.device_state.name = "Playing"
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
    def __init__(self, mock_atv):
        self._atv = mock_atv

    async def execute(self, device, operation):
        result = operation(self._atv)
        if inspect.isawaitable(result):
            return await result
        return result


class FakeMcp:
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
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def recipe_file(tmp_path):
    """Provide a temp recipe file and patch the env var."""
    path = str(tmp_path / "test-recipes.json")
    with patch.dict(os.environ, {"MCP_PYATV_RECIPES_PATH": path}):
        yield path


def _make_recipe(**kwargs):
    defaults = {
        "name": "test-recipe",
        "description": "A test recipe",
        "steps": [
            {"action": "launch_app", "app": "Netflix"},
            {"action": "wait", "seconds": 1},
            {"action": "navigate", "direction": "select"},
        ],
        "app": "Netflix",
        "confidence": 0.8,
    }
    defaults.update(kwargs)
    return Recipe(**defaults)


# ---------------------------------------------------------------------------
# Storage tests
# ---------------------------------------------------------------------------

class TestRecipeStorage:

    @pytest.mark.asyncio
    async def test_save_and_load_recipe(self, recipe_file):
        recipe = _make_recipe()
        await save_recipe_storage(recipe)

        loaded = await load_recipes()
        assert "test-recipe" in loaded
        r = loaded["test-recipe"]
        assert r.name == "test-recipe"
        assert r.description == "A test recipe"
        assert len(r.steps) == 3
        assert r.app == "Netflix"

    @pytest.mark.asyncio
    async def test_confidence_decay(self, recipe_file):
        two_weeks_ago = (datetime.now(timezone.utc) - timedelta(weeks=2)).isoformat()
        recipe = _make_recipe(confidence=0.8, last_used=two_weeks_ago)
        await save_recipe_storage(recipe)

        loaded = await load_recipes()
        r = loaded["test-recipe"]
        # 2 weeks * 0.05 = 0.1 decay, so 0.8 - 0.1 = 0.7
        assert abs(r.confidence - 0.7) < 0.02

    @pytest.mark.asyncio
    async def test_delete_recipe(self, recipe_file):
        recipe = _make_recipe()
        await save_recipe_storage(recipe)

        deleted = await delete_recipe_storage("test-recipe")
        assert deleted is True

        loaded = await load_recipes()
        assert "test-recipe" not in loaded

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, recipe_file):
        deleted = await delete_recipe_storage("nonexistent")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_load_legacy_recipe_without_new_fields(self, recipe_file):
        """Old recipes without new fields load with defaults."""
        # Write a v1 recipe manually
        data = {
            "version": 1,
            "recipes": {
                "old_recipe": {
                    "name": "old_recipe",
                    "description": "Legacy",
                    "steps": [{"action": "launch_app", "app": "X"}],
                    "confidence": 0.8,
                    "success_count": 3,
                    "fail_count": 0,
                }
            }
        }
        with open(recipe_file, "w") as f:
            json.dump(data, f)

        recipes = await load_recipes()
        assert "old_recipe" in recipes
        assert recipes["old_recipe"].starting_screen is None
        assert recipes["old_recipe"].ending_screen is None
        assert recipes["old_recipe"].is_entry_point is False


# ---------------------------------------------------------------------------
# Tool tests
# ---------------------------------------------------------------------------

class TestListRecipes:

    @pytest.fixture
    def setup(self, recipe_file):
        fake_mcp = FakeMcp()
        register_recipe_tools(fake_mcp, pymobiledevice3_path=None)
        mock_atv = MockAtv()
        mock_conn = MockConn(mock_atv)
        ctx = _make_ctx(mock_conn)
        return fake_mcp, ctx, recipe_file

    @pytest.mark.asyncio
    async def test_list_recipes_filtered(self, setup):
        fake_mcp, ctx, recipe_file = setup
        list_fn = fake_mcp.tools["list_recipes"]

        await save_recipe_storage(_make_recipe(name="netflix-nav", app="Netflix"))
        await save_recipe_storage(_make_recipe(name="youtube-nav", app="YouTube"))

        result = await list_fn(app="Netflix", device=None, ctx=ctx)
        assert len(result) == 1
        assert result[0]["name"] == "netflix-nav"

    @pytest.mark.asyncio
    async def test_list_includes_screen_fields(self, setup):
        """list_recipes includes starting_screen, ending_screen, is_entry_point."""
        fake_mcp, ctx, _ = setup
        # Save a recipe with screen fields
        recipe = Recipe(
            name="test_screens",
            description="Test",
            steps=[{"action": "launch_app", "app": "X"}],
            starting_screen="Start screen",
            ending_screen="End screen",
            is_entry_point=True,
        )
        await save_recipe_storage(recipe)

        list_fn = fake_mcp.tools["list_recipes"]
        results = await list_fn(ctx=ctx)
        assert results[0]["starting_screen"] == "Start screen"
        assert results[0]["ending_screen"] == "End screen"
        assert results[0]["is_entry_point"] is True

    @pytest.mark.asyncio
    async def test_list_recipes_sorted(self, setup):
        fake_mcp, ctx, recipe_file = setup
        list_fn = fake_mcp.tools["list_recipes"]

        await save_recipe_storage(_make_recipe(name="low", confidence=0.3, app="Netflix"))
        await save_recipe_storage(_make_recipe(name="high", confidence=0.9, app="Netflix"))
        await save_recipe_storage(_make_recipe(name="mid", confidence=0.6, app="Netflix"))

        result = await list_fn(app=None, device=None, ctx=ctx)
        confidences = [r["confidence"] for r in result]
        assert confidences == sorted(confidences, reverse=True)


class TestRunRecipe:

    @pytest.fixture
    def setup(self, recipe_file):
        fake_mcp = FakeMcp()
        register_recipe_tools(fake_mcp, pymobiledevice3_path=None)
        mock_atv = MockAtv()
        mock_conn = MockConn(mock_atv)
        ctx = _make_ctx(mock_conn)
        return fake_mcp, mock_atv, ctx, recipe_file

    @pytest.mark.asyncio
    async def test_run_recipe_not_found(self, setup):
        fake_mcp, _, ctx, _ = setup
        run_fn = fake_mcp.tools["run_recipe"]

        result = await run_fn(name="nonexistent", device=None, ctx=ctx)
        assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_run_recipe_executes_steps(self, setup):
        fake_mcp, mock_atv, ctx, _ = setup
        run_fn = fake_mcp.tools["run_recipe"]

        recipe = _make_recipe(
            steps=[
                {"action": "launch_app", "app": "TestApp"},
                {"action": "navigate", "direction": "down"},
                {"action": "navigate", "direction": "select"},
            ]
        )
        await save_recipe_storage(recipe)

        with patch("mcp_pyatv.tools.batch.asyncio.sleep", new=AsyncMock()):
            result = await run_fn(name="test-recipe", device=None, ctx=ctx)

        assert "Navigated" in result


class TestSaveRecipeTool:

    @pytest.fixture
    def setup(self, recipe_file):
        fake_mcp = FakeMcp()
        register_recipe_tools(fake_mcp, pymobiledevice3_path=None)
        mock_atv = MockAtv()
        mock_conn = MockConn(mock_atv)
        ctx = _make_ctx(mock_conn)
        return fake_mcp, ctx, recipe_file

    @pytest.mark.asyncio
    async def test_save_recipe_valid(self, setup):
        fake_mcp, ctx, _ = setup
        save_fn = fake_mcp.tools["save_recipe"]

        result = await save_fn(
            name="my-recipe",
            description="Test",
            steps=[
                {"action": "launch_app", "app": "TestApp"},
                {"action": "navigate", "direction": "down"},
            ],
            device=None,
            ctx=ctx,
        )
        assert "saved" in result.lower()
        assert "0.6" in result

    @pytest.mark.asyncio
    async def test_save_recipe_verified(self, setup):
        fake_mcp, ctx, _ = setup
        save_fn = fake_mcp.tools["save_recipe"]

        result = await save_fn(
            name="my-recipe",
            description="Test",
            steps=[
                {"action": "launch_app", "app": "TestApp"},
                {"action": "navigate", "direction": "down"},
            ],
            verified_with_screenshot=True,
            device=None,
            ctx=ctx,
        )
        assert "0.8" in result

    @pytest.mark.asyncio
    async def test_save_recipe_invalid_action(self, setup):
        fake_mcp, ctx, _ = setup
        save_fn = fake_mcp.tools["save_recipe"]

        result = await save_fn(
            name="bad-recipe",
            description="Bad",
            steps=[
                {"action": "launch_app", "app": "TestApp"},
                {"action": "teleport"},
            ],
            device=None,
            ctx=ctx,
        )
        assert "Invalid action" in result

    @pytest.mark.asyncio
    async def test_save_recipe_must_start_with_launch_or_have_starting_screen(self, setup):
        """Recipe without launch_app and without starting_screen is rejected."""
        fake_mcp, ctx, _ = setup
        save_fn = fake_mcp.tools["save_recipe"]

        result = await save_fn(
            name="bad-start",
            description="Starts with navigate down",
            steps=[{"action": "navigate", "direction": "down"}],
            device=None,
            ctx=ctx,
        )
        assert "starting_screen" in result.lower()

    @pytest.mark.asyncio
    async def test_save_continuation_recipe_with_starting_screen(self, setup):
        """Continuation recipe (no launch_app) with starting_screen succeeds."""
        fake_mcp, ctx, _ = setup
        save_fn = fake_mcp.tools["save_recipe"]
        result = await save_fn(
            name="netflix_to_movies",
            description="Navigate from Netflix home to movies",
            steps=[
                {"action": "navigate", "direction": "right"},
                {"action": "navigate", "direction": "right"},
                {"action": "navigate", "direction": "select"},
            ],
            starting_screen="Netflix home screen with top row selected",
            ending_screen="Netflix movies section",
            device=None,
            ctx=ctx,
        )
        assert "saved" in result.lower()

    @pytest.mark.asyncio
    async def test_save_continuation_without_starting_screen_fails(self, setup):
        """Continuation recipe without starting_screen is rejected."""
        fake_mcp, ctx, _ = setup
        save_fn = fake_mcp.tools["save_recipe"]
        result = await save_fn(
            name="bad_continuation",
            description="No starting screen",
            steps=[
                {"action": "navigate", "direction": "down"},
            ],
            device=None,
            ctx=ctx,
        )
        assert "starting_screen" in result.lower()

    @pytest.mark.asyncio
    async def test_save_entry_point_auto_detected(self, setup):
        """Recipe starting with launch_app auto-sets is_entry_point."""
        fake_mcp, ctx, recipe_file = setup
        save_fn = fake_mcp.tools["save_recipe"]
        await save_fn(
            name="auto_entry",
            description="Auto entry point",
            steps=[{"action": "launch_app", "app": "Netflix"}],
            device=None,
            ctx=ctx,
        )
        # Load and verify
        recipes = await load_recipes()
        assert recipes["auto_entry"].is_entry_point is True


class TestConfirmRecipeRun:

    @pytest.fixture
    def setup(self, recipe_file):
        fake_mcp = FakeMcp()
        register_recipe_tools(fake_mcp, pymobiledevice3_path=None)
        mock_atv = MockAtv()
        mock_conn = MockConn(mock_atv)
        ctx = _make_ctx(mock_conn)
        return fake_mcp, ctx, recipe_file

    @pytest.mark.asyncio
    async def test_confirm_success(self, setup):
        fake_mcp, ctx, _ = setup
        confirm_fn = fake_mcp.tools["confirm_recipe_run"]

        recipe = _make_recipe(confidence=0.7, success_count=2, fail_count=0)
        await save_recipe_storage(recipe)

        result = await confirm_fn(name="test-recipe", success=True, device=None, ctx=ctx)
        assert "succeeded" in result

        loaded = await load_recipes()
        r = loaded["test-recipe"]
        assert r.success_count == 3
        assert r.confidence >= 0.74

    @pytest.mark.asyncio
    async def test_confirm_failure(self, setup):
        fake_mcp, ctx, _ = setup
        confirm_fn = fake_mcp.tools["confirm_recipe_run"]

        recipe = _make_recipe(confidence=0.7, success_count=2, fail_count=0)
        await save_recipe_storage(recipe)

        result = await confirm_fn(name="test-recipe", success=False, device=None, ctx=ctx)
        assert "failed" in result

        loaded = await load_recipes()
        r = loaded["test-recipe"]
        assert r.fail_count == 1
        assert r.confidence <= 0.51

    @pytest.mark.asyncio
    async def test_confirm_failure_deprecates(self, setup):
        fake_mcp, ctx, _ = setup
        confirm_fn = fake_mcp.tools["confirm_recipe_run"]

        recipe = _make_recipe(confidence=0.15, fail_count=5)
        await save_recipe_storage(recipe)

        result = await confirm_fn(name="test-recipe", success=False, device=None, ctx=ctx)
        assert "DEPRECATED" in result

        loaded = await load_recipes()
        r = loaded["test-recipe"]
        assert r.deprecated is True
        assert r.confidence < 0.1


class TestDeleteRecipeTool:

    @pytest.fixture
    def setup(self, recipe_file):
        fake_mcp = FakeMcp()
        register_recipe_tools(fake_mcp, pymobiledevice3_path=None)
        ctx = _make_ctx(MockConn(MockAtv()))
        return fake_mcp, ctx, recipe_file

    @pytest.mark.asyncio
    async def test_delete_existing(self, setup):
        fake_mcp, ctx, _ = setup
        delete_fn = fake_mcp.tools["delete_recipe"]

        await save_recipe_storage(_make_recipe())
        result = await delete_fn(name="test-recipe", ctx=ctx)
        assert "deleted" in result.lower()

    @pytest.mark.asyncio
    async def test_delete_not_found(self, setup):
        fake_mcp, ctx, _ = setup
        delete_fn = fake_mcp.tools["delete_recipe"]

        result = await delete_fn(name="nonexistent", ctx=ctx)
        assert "not found" in result.lower()
