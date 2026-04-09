import logging
from datetime import datetime, timezone

from fastmcp import Context
from fastmcp.utilities.types import Image

from ..recipes import (
    Recipe,
    load_recipes as _load_recipes,
    save_recipe as _save_recipe,
    delete_recipe as _delete_recipe,
)
from .batch import build_action_map, run_steps

_LOGGER = logging.getLogger(__name__)


def register_recipe_tools(mcp, pymobiledevice3_path: str | None = None):

    action_map = build_action_map(pymobiledevice3_path)

    @mcp.tool()
    async def list_recipes(
        app: str | None = None,
        device: str | None = None,
        ctx: Context = None,
    ) -> list[dict]:
        """List saved navigation recipes. ALWAYS call this before navigating to check for existing recipes."""
        recipes = await _load_recipes()
        results = []
        for r in recipes.values():
            if app:
                app_lower = app.lower()
                matches = (
                    (r.app and app_lower in r.app.lower())
                    or (r.expected_app and app_lower in r.expected_app.lower())
                )
                if not matches:
                    continue
            results.append({
                "name": r.name,
                "description": r.description,
                "app": r.app,
                "confidence": round(r.confidence, 2),
                "success_count": r.success_count,
                "fail_count": r.fail_count,
                "last_used": r.last_used,
                "deprecated": r.deprecated,
                "starting_screen": r.starting_screen,
                "ending_screen": r.ending_screen,
                "is_entry_point": r.is_entry_point,
            })
        results.sort(key=lambda x: x["confidence"], reverse=True)
        return results

    @mcp.tool()
    async def run_recipe(
        name: str,
        device: str | None = None,
        ctx: Context = None,
    ):
        """Execute a saved navigation recipe. Replays stored steps then verifies the result."""
        if not ctx.lifespan_context["is_screen_state_checked"]():
            return "ERROR: You must call get_screen_state first."

        recipes = await _load_recipes()
        recipe = recipes.get(name)
        if recipe is None:
            return f"Recipe '{name}' not found. Use list_recipes() to see available recipes."

        warning = ""
        if recipe.confidence < 0.3:
            warning = (
                f"WARNING: Recipe '{name}' has low confidence ({recipe.confidence:.2f}). "
                "It may not work correctly. "
            )

        conn = await ctx.lifespan_context["get_connections"]()
        results, screenshot_image = await run_steps(recipe.steps, conn, device, action_map)

        # Update last_used
        recipe.last_used = datetime.now(timezone.utc).isoformat()

        # Verification path
        if pymobiledevice3_path:
            # Developer mode: take screenshot for visual verification
            from .developer import _capture_screenshot

            screenshot = await _capture_screenshot(pymobiledevice3_path)
            await _save_recipe(recipe)

            summary = warning + "; ".join(
                r.get("result", r.get("error", ""))
                if isinstance(r.get("result"), str)
                else str(r.get("result", r.get("error", "")))
                for r in results
            )
            if isinstance(screenshot, Image):
                if recipe.ending_screen:
                    summary += f" | Expected ending screen: {recipe.ending_screen}"
                summary += " | Verify the screenshot and call confirm_recipe_run()."
                return [
                    summary,
                    screenshot,
                ]
            # Screenshot failed — fall through to non-screenshot path
            summary += f" | Screenshot failed: {screenshot}"

        # Non-developer mode: auto-verify via screen state
        has_error = any("error" in r for r in results)
        if not has_error and (recipe.expected_app or recipe.expected_state):
            try:
                async def _get_state(atv):
                    state = {}
                    try:
                        app_info = atv.metadata.app
                        if app_info:
                            state["app_id"] = app_info.identifier
                            state["app_name"] = app_info.name
                    except Exception:
                        pass
                    try:
                        playing = await atv.metadata.playing()
                        state["device_state"] = playing.device_state.name.lower()
                    except Exception:
                        pass
                    return state

                screen = await conn.execute(device, _get_state)
                matched = True
                if recipe.expected_app:
                    current_app = (screen.get("app_name") or "").lower()
                    current_id = (screen.get("app_id") or "").lower()
                    if (recipe.expected_app.lower() not in current_app
                            and recipe.expected_app.lower() not in current_id):
                        matched = False
                if recipe.expected_state:
                    current_state = (screen.get("device_state") or "").lower()
                    if recipe.expected_state.lower() != current_state:
                        matched = False

                if matched:
                    recipe.confidence = min(1.0, recipe.confidence + 0.05)
                    recipe.success_count += 1
                    recipe.last_verified = datetime.now(timezone.utc).isoformat()
                else:
                    recipe.confidence = max(0.0, recipe.confidence - 0.2)
                    recipe.fail_count += 1
                    if recipe.confidence < 0.1:
                        recipe.deprecated = True
            except Exception as e:
                _LOGGER.warning("Auto-verify failed: %s", e)

        await _save_recipe(recipe)

        summary = warning + "; ".join(
            r.get("result", r.get("error", ""))
            if isinstance(r.get("result"), str)
            else str(r.get("result", r.get("error", "")))
            for r in results
        )
        return summary

    @mcp.tool()
    async def save_recipe(
        name: str,
        description: str,
        steps: list[dict],
        app: str | None = None,
        expected_app: str | None = None,
        expected_state: str | None = None,
        starting_screen: str | None = None,
        ending_screen: str | None = None,
        is_entry_point: bool = False,
        verified_with_screenshot: bool = False,
        device: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Save a segmented navigation recipe. Recipes are SEGMENTS that go from one known screen to another.

Entry-point recipes start with launch_app or navigate(home) — is_entry_point is auto-detected.
Continuation recipes must provide starting_screen describing the expected screen before these steps run.
Always provide ending_screen describing what the screen looks like after the steps complete.
Keep segments short (3-8 steps), one segment per screen transition."""
        if steps:
            first = steps[0]
            first_action = first.get("action")
            first_is_launch = first_action == "launch_app"
            first_is_home = first_action == "navigate" and first.get("direction") == "home"

            # Auto-detect entry point from first step
            if first_is_launch or first_is_home:
                is_entry_point = True

            if is_entry_point and not first_is_launch and not first_is_home:
                return "Entry point recipes must start with launch_app or navigate(home)."

            if not is_entry_point and not starting_screen:
                return (
                    "Continuation recipes must provide starting_screen describing what the screen "
                    "looks like before these steps run. Or start with launch_app for an entry point recipe."
                )

        # Validate steps
        for i, step in enumerate(steps):
            act = step.get("action")
            if not act or act not in action_map:
                return f"Invalid action '{act}' in step {i}. Valid actions: {', '.join(sorted(action_map.keys()))}"

        confidence = 0.8 if verified_with_screenshot else 0.6
        recipe = Recipe(
            name=name,
            description=description,
            steps=steps,
            app=app,
            expected_app=expected_app,
            expected_state=expected_state,
            starting_screen=starting_screen,
            ending_screen=ending_screen,
            is_entry_point=is_entry_point,
            confidence=confidence,
            last_used=datetime.now(timezone.utc).isoformat(),
        )
        await _save_recipe(recipe)
        return f"Recipe '{name}' saved with confidence {confidence}."

    @mcp.tool()
    async def confirm_recipe_run(
        name: str,
        success: bool,
        device: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Confirm whether a recipe run succeeded after visual verification via screenshot."""
        recipes = await _load_recipes()
        recipe = recipes.get(name)
        if recipe is None:
            return f"Recipe '{name}' not found."

        if success:
            recipe.confidence = min(1.0, recipe.confidence + 0.05)
            recipe.success_count += 1
            recipe.last_verified = datetime.now(timezone.utc).isoformat()
        else:
            recipe.confidence = max(0.0, recipe.confidence - 0.2)
            recipe.fail_count += 1
            if recipe.confidence < 0.1:
                recipe.deprecated = True

        await _save_recipe(recipe)
        status = "succeeded" if success else "failed"
        return (
            f"Recipe '{name}' marked as {status}. "
            f"Confidence: {recipe.confidence:.2f}, "
            f"Success: {recipe.success_count}, Fail: {recipe.fail_count}"
            + (", DEPRECATED" if recipe.deprecated else "")
        )

    @mcp.tool()
    async def delete_recipe(
        name: str,
        ctx: Context = None,
    ) -> str:
        """Delete a saved navigation recipe."""
        deleted = await _delete_recipe(name)
        if deleted:
            return f"Recipe '{name}' deleted."
        return f"Recipe '{name}' not found."
