from fastmcp import Context


def register_keyboard_tools(mcp):
    @mcp.tool()
    async def set_text(text: str, device: str | None = None, ctx: Context = None) -> str:
        """Type text into the focused text field on the device. Useful for search fields and login forms."""
        conn = await ctx.lifespan_context["get_connections"]()
        await conn.execute(device, lambda atv: atv.keyboard.text_set(text))
        return f"Text set to: {text}"

    @mcp.tool()
    async def clear_text(device: str | None = None, ctx: Context = None) -> str:
        """Clear text in the focused text field on the device."""
        conn = await ctx.lifespan_context["get_connections"]()
        await conn.execute(device, lambda atv: atv.keyboard.text_clear())
        return "Text cleared"

    @mcp.tool()
    async def get_text(device: str | None = None, ctx: Context = None) -> str:
        """Get the current text in the focused text field on the device."""
        conn = await ctx.lifespan_context["get_connections"]()
        text = await conn.execute(device, lambda atv: atv.keyboard.text_get())
        return text if text else ""
