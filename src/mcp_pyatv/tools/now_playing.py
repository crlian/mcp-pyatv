import base64

from fastmcp import Context

from ..util import format_playing


def register_now_playing_tools(mcp):
    @mcp.tool()
    async def now_playing(device: str | None = None, ctx: Context = None) -> dict:
        """Get information about what is currently playing on the device."""
        conn = await ctx.lifespan_context["get_connections"]()
        atv = await conn.get(device)
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

    @mcp.tool()
    async def get_artwork(
        device: str | None = None, width: int = 512, ctx: Context = None
    ) -> str:
        """Get the artwork for what is currently playing. Returns base64-encoded image data."""
        conn = await ctx.lifespan_context["get_connections"]()
        atv = await conn.get(device)
        artwork = await atv.metadata.artwork(width=width)
        if artwork and artwork.bytes:
            return base64.b64encode(artwork.bytes).decode("utf-8")
        return "No artwork available"
