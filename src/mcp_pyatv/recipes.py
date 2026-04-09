import asyncio
import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

_LOGGER = logging.getLogger(__name__)
_DEFAULT_PATH = os.path.expanduser("~/.mcp-pyatv-recipes.json")
_lock = asyncio.Lock()


@dataclass
class Recipe:
    name: str
    description: str
    steps: list[dict]
    app: str | None = None
    expected_app: str | None = None
    expected_state: str | None = None
    starting_screen: str | None = None
    ending_screen: str | None = None
    is_entry_point: bool = False
    confidence: float = 0.6
    success_count: int = 0
    fail_count: int = 0
    last_used: str | None = None
    last_verified: str | None = None
    deprecated: bool = False


def _path():
    return os.environ.get("MCP_PYATV_RECIPES_PATH", _DEFAULT_PATH)


def _apply_decay(recipe: Recipe) -> Recipe:
    """Apply confidence decay based on time since last use."""
    if recipe.last_used:
        last = datetime.fromisoformat(recipe.last_used)
        weeks = (datetime.now(timezone.utc) - last).days / 7
        recipe.confidence = max(0.0, recipe.confidence - 0.05 * weeks)
        if recipe.confidence < 0.1:
            recipe.deprecated = True
    return recipe


async def load_recipes() -> dict[str, Recipe]:
    async with _lock:
        path = _path()
        if not os.path.exists(path):
            return {}
        try:
            with open(path) as f:
                data = json.load(f)
            recipes = {}
            for name, d in data.get("recipes", {}).items():
                r = Recipe(**{k: v for k, v in d.items() if k in Recipe.__dataclass_fields__})
                recipes[name] = _apply_decay(r)
            return recipes
        except (json.JSONDecodeError, Exception) as e:
            _LOGGER.warning("Failed to load recipes: %s", e)
            return {}


async def save_recipe(recipe: Recipe):
    async with _lock:
        path = _path()
        data = {"version": 2, "recipes": {}}
        if os.path.exists(path):
            try:
                with open(path) as f:
                    data = json.load(f)
            except Exception:
                pass
        data.setdefault("recipes", {})[recipe.name] = asdict(recipe)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)


async def delete_recipe(name: str) -> bool:
    async with _lock:
        path = _path()
        if not os.path.exists(path):
            return False
        try:
            with open(path) as f:
                data = json.load(f)
            if name in data.get("recipes", {}):
                del data["recipes"][name]
                with open(path, "w") as f:
                    json.dump(data, f, indent=2)
                return True
        except Exception:
            pass
        return False
