from fastmcp import Context


def register_audio_tools(mcp):
    @mcp.tool()
    async def get_volume(device: str | None = None, ctx: Context = None) -> float:
        """Get the current volume level (0-100)."""
        conn = await ctx.lifespan_context["get_connections"]()
        atv = await conn.get(device)
        return atv.audio.volume

    @mcp.tool()
    async def set_volume(level: float, device: str | None = None, ctx: Context = None) -> str:
        """Set volume to a specific level (0-100)."""
        conn = await ctx.lifespan_context["get_connections"]()
        atv = await conn.get(device)
        await atv.audio.set_volume(level)
        return f"Volume set to {level}"

    @mcp.tool()
    async def volume_up(device: str | None = None, ctx: Context = None) -> str:
        """Increase volume."""
        conn = await ctx.lifespan_context["get_connections"]()
        atv = await conn.get(device)
        await atv.audio.volume_up()
        return "Volume increased"

    @mcp.tool()
    async def volume_down(device: str | None = None, ctx: Context = None) -> str:
        """Decrease volume."""
        conn = await ctx.lifespan_context["get_connections"]()
        atv = await conn.get(device)
        await atv.audio.volume_down()
        return "Volume decreased"
