from fastmcp import Context


def register_app_tools(mcp):
    @mcp.tool()
    async def list_apps(device: str | None = None, ctx: Context = None) -> list[dict]:
        """List all installed apps on the device."""
        conn = await ctx.lifespan_context["get_connections"]()
        apps = await conn.execute(device, lambda atv: atv.apps.app_list())
        return [{"name": app.name, "bundle_id": app.identifier} for app in apps]

    @mcp.tool()
    async def launch_app(app: str, device: str | None = None, ctx: Context = None) -> str:
        """Launch an app by name or bundle ID on the device."""
        conn = await ctx.lifespan_context["get_connections"]()

        async def _op(atv):
            apps = await atv.apps.app_list()
            target = None
            for a in apps:
                if a.identifier == app or a.name.lower() == app.lower():
                    target = a
                    break
            if target:
                await atv.apps.launch_app(target.identifier)
                return f"Launched {target.name}"
            # Try launching directly as bundle ID
            await atv.apps.launch_app(app)
            return f"Launched {app}"

        return await conn.execute(device, _op)
