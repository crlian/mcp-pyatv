from fastmcp import Context


def register_stream_tools(mcp):
    @mcp.tool()
    async def play_url(url: str, device: str | None = None, ctx: Context = None) -> str:
        """Play media from a URL on the device via AirPlay."""
        conn = await ctx.lifespan_context["get_connections"]()
        atv = await conn.get(device)
        await atv.stream.play_url(url)
        return f"Streaming {url}"

    @mcp.tool()
    async def stream_file(path: str, device: str | None = None, ctx: Context = None) -> str:
        """Stream a local audio file to the device."""
        conn = await ctx.lifespan_context["get_connections"]()
        atv = await conn.get(device)
        await atv.stream.stream_file(path)
        return f"Streaming {path}"
