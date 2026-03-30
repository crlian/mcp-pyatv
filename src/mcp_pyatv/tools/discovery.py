from fastmcp import Context

from ..util import format_device


def register_discovery_tools(mcp):
    @mcp.tool()
    async def scan_devices(timeout: float = 3.0, ctx: Context = None) -> list[dict]:
        """Scan the local network for Apple TV, HomePod, and AirPlay devices."""
        conn = await ctx.lifespan_context["get_connections"]()
        configs = await conn.scan(timeout)
        return [format_device(c) for c in configs]

    @mcp.tool()
    async def device_info(device: str, ctx: Context = None) -> dict:
        """Get detailed information about a specific device."""
        conn = await ctx.lifespan_context["get_connections"]()

        async def _op(atv):
            di = atv.device_info
            return {
                "model": str(di.model),
                "model_str": di.model_str,
                "raw_model": di.raw_model,
                "operating_system": str(di.operating_system),
                "version": str(di.version),
                "build_number": di.build_number,
                "mac": di.mac,
            }

        return await conn.execute(device, _op)
