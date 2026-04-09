from fastmcp import Context
from pyatv.const import InputAction

from ..util import parse_repeat, parse_shuffle

INPUT_ACTION_MAP = {
    "single_tap": InputAction.SingleTap,
    "double_tap": InputAction.DoubleTap,
    "hold": InputAction.Hold,
}

DIRECTION_NAMES = {"up", "down", "left", "right", "select", "menu", "home", "top_menu"}


def register_remote_tools(mcp):
    @mcp.tool()
    async def play(device: str | None = None, ctx: Context = None) -> str:
        """Start or resume playback."""
        conn = await ctx.lifespan_context["get_connections"]()
        await conn.execute(device, lambda atv: atv.remote_control.play())
        return "Playing"

    @mcp.tool()
    async def pause(device: str | None = None, ctx: Context = None) -> str:
        """Pause playback."""
        conn = await ctx.lifespan_context["get_connections"]()
        await conn.execute(device, lambda atv: atv.remote_control.pause())
        return "Paused"

    @mcp.tool()
    async def play_pause(device: str | None = None, ctx: Context = None) -> str:
        """Toggle play/pause."""
        conn = await ctx.lifespan_context["get_connections"]()
        await conn.execute(device, lambda atv: atv.remote_control.play_pause())
        return "Toggled play/pause"

    @mcp.tool()
    async def stop(device: str | None = None, ctx: Context = None) -> str:
        """Stop playback."""
        conn = await ctx.lifespan_context["get_connections"]()
        await conn.execute(device, lambda atv: atv.remote_control.stop())
        return "Stopped"

    @mcp.tool()
    async def next_track(device: str | None = None, ctx: Context = None) -> str:
        """Skip to next track or chapter."""
        conn = await ctx.lifespan_context["get_connections"]()
        await conn.execute(device, lambda atv: atv.remote_control.next())
        return "Skipped to next"

    @mcp.tool()
    async def previous_track(device: str | None = None, ctx: Context = None) -> str:
        """Skip to previous track or chapter."""
        conn = await ctx.lifespan_context["get_connections"]()
        await conn.execute(device, lambda atv: atv.remote_control.previous())
        return "Skipped to previous"

    @mcp.tool()
    async def skip_forward(
        device: str | None = None, seconds: float = 15, ctx: Context = None
    ) -> str:
        """Skip forward by a number of seconds."""
        conn = await ctx.lifespan_context["get_connections"]()
        await conn.execute(device, lambda atv: atv.remote_control.skip_forward(seconds))
        return f"Skipped forward {seconds}s"

    @mcp.tool()
    async def skip_backward(
        device: str | None = None, seconds: float = 15, ctx: Context = None
    ) -> str:
        """Skip backward by a number of seconds."""
        conn = await ctx.lifespan_context["get_connections"]()
        await conn.execute(device, lambda atv: atv.remote_control.skip_backward(seconds))
        return f"Skipped backward {seconds}s"

    @mcp.tool()
    async def set_position(
        position: int, device: str | None = None, ctx: Context = None
    ) -> str:
        """Seek to a specific position in seconds."""
        conn = await ctx.lifespan_context["get_connections"]()
        await conn.execute(device, lambda atv: atv.remote_control.set_position(position))
        return f"Position set to {position}s"

    @mcp.tool()
    async def set_shuffle(
        state: str, device: str | None = None, ctx: Context = None
    ) -> str:
        """Set shuffle mode. State: 'off', 'songs', or 'albums'."""
        shuffle = parse_shuffle(state)
        conn = await ctx.lifespan_context["get_connections"]()
        await conn.execute(device, lambda atv: atv.remote_control.set_shuffle(shuffle))
        return f"Shuffle set to {state}"

    @mcp.tool()
    async def set_repeat(
        state: str, device: str | None = None, ctx: Context = None
    ) -> str:
        """Set repeat mode. State: 'off', 'track', or 'all'."""
        repeat = parse_repeat(state)
        conn = await ctx.lifespan_context["get_connections"]()
        await conn.execute(device, lambda atv: atv.remote_control.set_repeat(repeat))
        return f"Repeat set to {state}"

    @mcp.tool()
    async def navigate(
        direction: str,
        action: str = "single_tap",
        device: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Press a button on the virtual Siri Remote. Works everywhere: home screen, inside apps (Netflix, YouTube, Settings, etc.). Directions: up, down, left, right = move focus. select = confirm/click. menu = go back. home = home screen. top_menu = top-level menu. Actions: single_tap (default), double_tap, hold."""
        if not ctx.lifespan_context["is_screen_state_checked"]():
            return "ERROR: You must call get_screen_state first before navigating. This checks if the device is awake and shows available recipes."

        if direction not in DIRECTION_NAMES:
            return f"Unknown direction: {direction}. Use: {', '.join(sorted(DIRECTION_NAMES))}"

        input_action = INPUT_ACTION_MAP.get(action)
        if input_action is None:
            return f"Unknown action: {action}. Use: {', '.join(INPUT_ACTION_MAP)}"

        conn = await ctx.lifespan_context["get_connections"]()

        async def _op(atv):
            method = getattr(atv.remote_control, direction)
            await method(action=input_action)
            return f"Navigated: {direction} ({action})"

        return await conn.execute(device, _op)
