from fastmcp import Context

from ..util import parse_repeat, parse_shuffle


def register_remote_tools(mcp):
    @mcp.tool()
    async def play(device: str | None = None, ctx: Context = None) -> str:
        """Start or resume playback."""
        conn = await ctx.lifespan_context["get_connections"]()
        atv = await conn.get(device)
        await atv.remote_control.play()
        return "Playing"

    @mcp.tool()
    async def pause(device: str | None = None, ctx: Context = None) -> str:
        """Pause playback."""
        conn = await ctx.lifespan_context["get_connections"]()
        atv = await conn.get(device)
        await atv.remote_control.pause()
        return "Paused"

    @mcp.tool()
    async def play_pause(device: str | None = None, ctx: Context = None) -> str:
        """Toggle play/pause."""
        conn = await ctx.lifespan_context["get_connections"]()
        atv = await conn.get(device)
        await atv.remote_control.play_pause()
        return "Toggled play/pause"

    @mcp.tool()
    async def stop(device: str | None = None, ctx: Context = None) -> str:
        """Stop playback."""
        conn = await ctx.lifespan_context["get_connections"]()
        atv = await conn.get(device)
        await atv.remote_control.stop()
        return "Stopped"

    @mcp.tool()
    async def next_track(device: str | None = None, ctx: Context = None) -> str:
        """Skip to next track or chapter."""
        conn = await ctx.lifespan_context["get_connections"]()
        atv = await conn.get(device)
        await atv.remote_control.next()
        return "Skipped to next"

    @mcp.tool()
    async def previous_track(device: str | None = None, ctx: Context = None) -> str:
        """Skip to previous track or chapter."""
        conn = await ctx.lifespan_context["get_connections"]()
        atv = await conn.get(device)
        await atv.remote_control.previous()
        return "Skipped to previous"

    @mcp.tool()
    async def skip_forward(
        device: str | None = None, seconds: float = 15, ctx: Context = None
    ) -> str:
        """Skip forward by a number of seconds."""
        conn = await ctx.lifespan_context["get_connections"]()
        atv = await conn.get(device)
        await atv.remote_control.skip_forward(seconds)
        return f"Skipped forward {seconds}s"

    @mcp.tool()
    async def skip_backward(
        device: str | None = None, seconds: float = 15, ctx: Context = None
    ) -> str:
        """Skip backward by a number of seconds."""
        conn = await ctx.lifespan_context["get_connections"]()
        atv = await conn.get(device)
        await atv.remote_control.skip_backward(seconds)
        return f"Skipped backward {seconds}s"

    @mcp.tool()
    async def set_position(
        position: int, device: str | None = None, ctx: Context = None
    ) -> str:
        """Seek to a specific position in seconds."""
        conn = await ctx.lifespan_context["get_connections"]()
        atv = await conn.get(device)
        await atv.remote_control.set_position(position)
        return f"Position set to {position}s"

    @mcp.tool()
    async def set_shuffle(
        state: str, device: str | None = None, ctx: Context = None
    ) -> str:
        """Set shuffle mode. State: 'off', 'songs', or 'albums'."""
        conn = await ctx.lifespan_context["get_connections"]()
        atv = await conn.get(device)
        await atv.remote_control.set_shuffle(parse_shuffle(state))
        return f"Shuffle set to {state}"

    @mcp.tool()
    async def set_repeat(
        state: str, device: str | None = None, ctx: Context = None
    ) -> str:
        """Set repeat mode. State: 'off', 'track', or 'all'."""
        conn = await ctx.lifespan_context["get_connections"]()
        atv = await conn.get(device)
        await atv.remote_control.set_repeat(parse_repeat(state))
        return f"Repeat set to {state}"

    @mcp.tool()
    async def navigate(
        direction: str,
        action: str = "single_tap",
        device: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Navigate the device UI. Direction: 'up', 'down', 'left', 'right', 'select', 'menu', 'home', 'top_menu'. Action: 'single_tap', 'double_tap', 'hold'."""
        conn = await ctx.lifespan_context["get_connections"]()
        atv = await conn.get(device)
        rc = atv.remote_control

        action_map = {
            "single_tap": {
                "up": rc.up,
                "down": rc.down,
                "left": rc.left,
                "right": rc.right,
                "select": rc.select,
                "menu": rc.menu,
                "home": rc.home,
                "top_menu": rc.top_menu,
            },
        }

        if direction not in action_map.get("single_tap", {}):
            return f"Unknown direction: {direction}. Use: up, down, left, right, select, menu, home, top_menu"

        await action_map["single_tap"][direction]()
        return f"Navigated: {direction} ({action})"
