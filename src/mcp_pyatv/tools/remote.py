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
        return await conn.execute(device, lambda atv: atv.remote_control.play())

    @mcp.tool()
    async def pause(device: str | None = None, ctx: Context = None) -> str:
        """Pause playback."""
        conn = await ctx.lifespan_context["get_connections"]()
        return await conn.execute(device, lambda atv: atv.remote_control.pause())

    @mcp.tool()
    async def play_pause(device: str | None = None, ctx: Context = None) -> str:
        """Toggle play/pause."""
        conn = await ctx.lifespan_context["get_connections"]()
        return await conn.execute(device, lambda atv: atv.remote_control.play_pause())

    @mcp.tool()
    async def stop(device: str | None = None, ctx: Context = None) -> str:
        """Stop playback."""
        conn = await ctx.lifespan_context["get_connections"]()
        return await conn.execute(device, lambda atv: atv.remote_control.stop())

    @mcp.tool()
    async def next_track(device: str | None = None, ctx: Context = None) -> str:
        """Skip to next track or chapter."""
        conn = await ctx.lifespan_context["get_connections"]()
        return await conn.execute(device, lambda atv: atv.remote_control.next())

    @mcp.tool()
    async def previous_track(device: str | None = None, ctx: Context = None) -> str:
        """Skip to previous track or chapter."""
        conn = await ctx.lifespan_context["get_connections"]()
        return await conn.execute(device, lambda atv: atv.remote_control.previous())

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
        """Navigate the device UI. Direction: 'up', 'down', 'left', 'right', 'select', 'menu', 'home', 'top_menu'. Action: 'single_tap', 'double_tap', 'hold'."""
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
