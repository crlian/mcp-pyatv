import asyncio
import logging

from fastmcp import Context
from fastmcp.utilities.types import Image
from pyatv.const import InputAction

from ..util import format_playing

_LOGGER = logging.getLogger(__name__)

INPUT_ACTION_MAP = {
    "single_tap": InputAction.SingleTap,
    "double_tap": InputAction.DoubleTap,
    "hold": InputAction.Hold,
}

DIRECTION_NAMES = {"up", "down", "left", "right", "select", "menu", "home", "top_menu"}

_MAX_STEPS = 30
_MAX_REPEAT = 20
_MAX_WAIT = 30


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------

async def _handle_navigate(conn, device, step):
    direction = step.get("direction")
    if not direction or direction not in DIRECTION_NAMES:
        raise ValueError(
            f"navigate requires 'direction' in {sorted(DIRECTION_NAMES)}, got: {direction}"
        )
    # "action" key is the step type (e.g. "navigate"), so use "input_action" for tap type
    tap_action = step.get("input_action", "single_tap")
    input_action = INPUT_ACTION_MAP.get(tap_action)
    if input_action is None:
        raise ValueError(f"Unknown input_action: {tap_action}. Use: {', '.join(INPUT_ACTION_MAP)}")

    async def _op(atv):
        method = getattr(atv.remote_control, direction)
        await method(action=input_action)
        return f"Navigated: {direction} ({tap_action})"

    return await conn.execute(device, _op)


async def _handle_wait(conn, device, step):
    seconds = step.get("seconds", 1)
    seconds = min(float(seconds), _MAX_WAIT)
    await asyncio.sleep(seconds)
    return f"Waited {seconds}s"


async def _handle_launch_app(conn, device, step):
    app = step.get("app")
    if not app:
        raise ValueError("launch_app requires 'app'")

    async def _op(atv):
        apps = await atv.apps.app_list()
        for a in apps:
            if a.identifier == app or a.name.lower() == app.lower():
                await atv.apps.launch_app(a.identifier)
                return f"Launched {a.name}"
        await atv.apps.launch_app(app)
        return f"Launched {app}"

    return await conn.execute(device, _op)


async def _handle_set_volume(conn, device, step):
    level = step.get("level")
    if level is None:
        raise ValueError("set_volume requires 'level'")

    await conn.execute(device, lambda atv: atv.audio.set_volume(float(level)))
    return f"Volume set to {level}"


async def _handle_volume_up(conn, device, step):
    await conn.execute(device, lambda atv: atv.audio.volume_up())
    return "Volume up"


async def _handle_volume_down(conn, device, step):
    await conn.execute(device, lambda atv: atv.audio.volume_down())
    return "Volume down"


async def _handle_play(conn, device, step):
    await conn.execute(device, lambda atv: atv.remote_control.play())
    return "Playing"


async def _handle_pause(conn, device, step):
    await conn.execute(device, lambda atv: atv.remote_control.pause())
    return "Paused"


async def _handle_play_pause(conn, device, step):
    await conn.execute(device, lambda atv: atv.remote_control.play_pause())
    return "Toggled play/pause"


async def _handle_stop(conn, device, step):
    await conn.execute(device, lambda atv: atv.remote_control.stop())
    return "Stopped"


async def _handle_next_track(conn, device, step):
    await conn.execute(device, lambda atv: atv.remote_control.next())
    return "Skipped to next"


async def _handle_previous_track(conn, device, step):
    await conn.execute(device, lambda atv: atv.remote_control.previous())
    return "Skipped to previous"


async def _handle_set_text(conn, device, step):
    text = step.get("text")
    if text is None:
        raise ValueError("set_text requires 'text'")
    await conn.execute(device, lambda atv: atv.keyboard.set_text(text))
    return f"Text set: {text}"


async def _handle_clear_text(conn, device, step):
    await conn.execute(device, lambda atv: atv.keyboard.clear_text())
    return "Text cleared"


async def _handle_turn_on(conn, device, step):
    await conn.execute(device, lambda atv: atv.power.turn_on())
    return "Turned on"


async def _handle_turn_off(conn, device, step):
    await conn.execute(device, lambda atv: atv.power.turn_off())
    return "Turned off"


async def _handle_now_playing(conn, device, step):
    async def _op(atv):
        playing = await atv.metadata.playing()
        result = format_playing(playing)
        try:
            app = atv.metadata.app
            if app:
                result["app_id"] = app.identifier
                result["app_name"] = app.name
        except Exception:
            pass
        return result

    return await conn.execute(device, _op)


_ACTION_MAP = {
    "navigate": _handle_navigate,
    "wait": _handle_wait,
    "launch_app": _handle_launch_app,
    "set_volume": _handle_set_volume,
    "volume_up": _handle_volume_up,
    "volume_down": _handle_volume_down,
    "play": _handle_play,
    "pause": _handle_pause,
    "play_pause": _handle_play_pause,
    "stop": _handle_stop,
    "next_track": _handle_next_track,
    "previous_track": _handle_previous_track,
    "set_text": _handle_set_text,
    "clear_text": _handle_clear_text,
    "turn_on": _handle_turn_on,
    "turn_off": _handle_turn_off,
    "now_playing": _handle_now_playing,
}


def build_action_map(pymobiledevice3_path: str | None = None) -> dict:
    """Return the full action dispatch dict, including take_screenshot."""

    async def _handle_take_screenshot(conn, device, step):
        if not pymobiledevice3_path:
            return "take_screenshot unavailable: pymobiledevice3 not found on this system."
        from .developer import _capture_screenshot

        return await _capture_screenshot(pymobiledevice3_path)

    return {**_ACTION_MAP, "take_screenshot": _handle_take_screenshot}


async def run_steps(steps: list[dict], conn, device, action_map: dict):
    """Execute a list of action steps and return (results_list, last_image_or_none).

    Stops on the first error. Each result is a dict with step, action, and
    result or error keys. If any step produces an Image, the last one is
    returned as the second element.
    """
    results = []
    screenshot_image = None

    for i, step in enumerate(steps):
        action = step.get("action")
        handler = action_map.get(action) if action else None
        if handler is None:
            results.append({"step": i, "action": action, "error": f"Unknown action: {action}"})
            break
        try:
            result = await handler(conn, device, step)
            if isinstance(result, Image):
                screenshot_image = result
                results.append({"step": i, "action": action, "result": "Screenshot captured"})
            elif isinstance(result, dict):
                results.append({"step": i, "action": action, "result": result})
            else:
                results.append({"step": i, "action": action, "result": str(result)})
        except Exception as exc:
            results.append({"step": i, "action": action, "error": str(exc)})
            break

    return results, screenshot_image


def register_batch_tools(mcp, pymobiledevice3_path: str | None = None):

    action_map = build_action_map(pymobiledevice3_path)

    @mcp.tool()
    async def execute_sequence(
        steps: list[dict],
        device: str | None = None,
        ctx: Context = None,
    ):
        """Run multiple actions in a single call to save round-trips. Each step is a dict with an 'action' key and flat parameters. Steps execute in order on the same device connection; execution stops on the first error and returns results so far. Max 30 steps.

Supported actions: navigate(direction, input_action?), wait(seconds?), launch_app(app), set_volume(level), volume_up, volume_down, play, pause, play_pause, stop, next_track, previous_track, set_text(text), clear_text, turn_on, turn_off, now_playing, take_screenshot.

Example: [{"action": "launch_app", "app": "Netflix"}, {"action": "wait", "seconds": 2}, {"action": "navigate", "direction": "select"}]"""
        if not ctx.lifespan_context["is_screen_state_checked"]():
            return "ERROR: You must call get_screen_state first before executing sequences."

        if not steps:
            return "No steps provided."
        if len(steps) > _MAX_STEPS:
            return f"Too many steps: {len(steps)} (max {_MAX_STEPS})."

        conn = await ctx.lifespan_context["get_connections"]()
        results, screenshot_image = await run_steps(steps, conn, device, action_map)

        # If the last step was a screenshot, return [summary, Image]
        if screenshot_image is not None and steps[-1].get("action") == "take_screenshot":
            summary = "; ".join(
                r.get("result", r.get("error", "")) if isinstance(r.get("result"), str) else r.get("action", "")
                for r in results
            )
            return [summary, screenshot_image]

        return results

    @mcp.tool()
    async def repeat_command(
        direction: str,
        count: int = 1,
        delay_ms: int = 300,
        action: str = "single_tap",
        device: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Press a remote button N times with a delay between each press. Useful for scrolling through menus and lists without multiple tool calls. Max count: 20.

Example: repeat_command('down', count=5) to scroll down 5 items."""
        if not ctx.lifespan_context["is_screen_state_checked"]():
            return "ERROR: You must call get_screen_state first."

        if direction not in DIRECTION_NAMES:
            return f"Unknown direction: {direction}. Use: {', '.join(sorted(DIRECTION_NAMES))}"
        if count > _MAX_REPEAT:
            return f"Count too high: {count} (max {_MAX_REPEAT})."
        if count < 1:
            return "Count must be at least 1."

        input_action = INPUT_ACTION_MAP.get(action)
        if input_action is None:
            return f"Unknown action: {action}. Use: {', '.join(INPUT_ACTION_MAP)}"

        conn = await ctx.lifespan_context["get_connections"]()
        delay_s = delay_ms / 1000.0

        for i in range(count):
            async def _op(atv):
                method = getattr(atv.remote_control, direction)
                await method(action=input_action)

            await conn.execute(device, _op)
            if i < count - 1:
                await asyncio.sleep(delay_s)

        return f"Pressed {direction} ({action}) {count} time(s) with {delay_ms}ms delay."
