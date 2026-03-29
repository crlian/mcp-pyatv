from fastmcp import Context


def register_power_tools(mcp):
    @mcp.tool()
    async def turn_on(device: str | None = None, ctx: Context = None) -> str:
        """Turn on a device or wake it from sleep."""
        conn = await ctx.lifespan_context["get_connections"]()
        atv = await conn.get(device)
        await atv.power.turn_on()
        return "Device turned on"

    @mcp.tool()
    async def turn_off(device: str | None = None, ctx: Context = None) -> str:
        """Turn off a device or put it to sleep."""
        conn = await ctx.lifespan_context["get_connections"]()
        atv = await conn.get(device)
        await atv.power.turn_off()
        return "Device turned off"

    @mcp.tool()
    async def power_state(device: str | None = None, ctx: Context = None) -> str:
        """Get the current power state of the device."""
        conn = await ctx.lifespan_context["get_connections"]()
        atv = await conn.get(device)
        state = atv.power.power_state
        return state.name
