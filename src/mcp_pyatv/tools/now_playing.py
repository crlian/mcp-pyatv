import base64

from fastmcp import Context

from ..util import format_playing
from ..recipes import load_recipes as _load_recipes


def register_now_playing_tools(mcp):
    @mcp.tool()
    async def get_screen_state(device: str | None = None, ctx: Context = None) -> dict:
        """Get the full state of the Apple TV AND available recipes. Call this FIRST — it returns device state plus saved recipes so you can decide whether to use a recipe or navigate manually. If screensaver or asleep, wake with navigate('select')."""
        conn = await ctx.lifespan_context["get_connections"]()

        async def _op(atv):
            result = {}

            # Attention state (screensaver/awake/asleep)
            try:
                from pyatv.const import Protocol
                companion = atv.power._interfaces.get(Protocol.Companion)
                if companion and hasattr(companion, 'api'):
                    state = await companion.api.fetch_attention_state()
                    result["attention"] = state.name.lower()
                else:
                    result["attention"] = "unknown"
            except Exception:
                result["attention"] = "unknown"

            # Power
            try:
                result["power"] = atv.power.power_state.name.lower()
            except Exception:
                result["power"] = "unknown"

            # Now playing
            try:
                playing = await atv.metadata.playing()
                result["device_state"] = playing.device_state.name.lower()
                result["title"] = playing.title
                result["media_type"] = str(playing.media_type) if playing.media_type else None
            except Exception:
                result["device_state"] = "unknown"

            # Current app
            try:
                app = atv.metadata.app
                if app:
                    result["app_id"] = app.identifier
                    result["app_name"] = app.name
            except Exception:
                pass

            # Keyboard focus
            try:
                result["keyboard_focused"] = atv.keyboard.text_focus_state.name.lower() == "focused"
            except Exception:
                result["keyboard_focused"] = False

            return result

        state = await conn.execute(device, _op)

        # Mark that screen state was checked this session
        ctx.lifespan_context["mark_screen_state_checked"]()

        # Include available recipes so Claude sees them without a separate call
        try:
            recipes = await _load_recipes()
            if recipes:
                state["available_recipes"] = [
                    {
                        "name": r.name,
                        "description": r.description,
                        "app": r.app,
                        "confidence": round(r.confidence, 2),
                        "starting_screen": r.starting_screen,
                        "is_entry_point": r.is_entry_point,
                    }
                    for r in recipes.values()
                    if not r.deprecated and r.confidence >= 0.3
                ]
        except Exception:
            pass

        return state

    @mcp.tool()
    async def now_playing(device: str | None = None, ctx: Context = None) -> dict:
        """Get current playback info: title, artist, album, app name, play state, and position. Faster than a screenshot for checking what is playing."""
        conn = await ctx.lifespan_context["get_connections"]()

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

    @mcp.tool()
    async def get_artwork(
        device: str | None = None, width: int = 512, ctx: Context = None
    ) -> str:
        """Get the artwork for what is currently playing. Returns base64-encoded image data."""
        conn = await ctx.lifespan_context["get_connections"]()
        artwork = await conn.execute(device, lambda atv: atv.metadata.artwork(width=width))
        if artwork and artwork.bytes:
            return base64.b64encode(artwork.bytes).decode("utf-8")
        return "No artwork available"
