from contextlib import asynccontextmanager

from fastmcp import FastMCP

from .connection import ConnectionManager
from .storage import get_storage
from .tools import register_all_tools


@asynccontextmanager
async def app_lifespan(server):
    # Storage and connections are created lazily on first tool call
    # to avoid timeout during MCP initialization
    state = {"storage": None, "connections": None}

    async def get_connections():
        if state["connections"] is None:
            storage = await get_storage()
            state["storage"] = storage
            state["connections"] = ConnectionManager(storage)
        return state["connections"]

    async def get_stor():
        if state["storage"] is None:
            state["storage"] = await get_storage()
        return state["storage"]

    try:
        yield {"get_connections": get_connections, "get_storage": get_stor}
    finally:
        if state["connections"]:
            await state["connections"].close_all()


mcp = FastMCP(
    "mcp-pyatv",
    instructions=(
        "Control Apple TV, HomePod, and AirPlay devices on your local network. "
        "Use scan_devices to discover devices, start_pairing/finish_pairing to pair, "
        "then use playback, navigation, volume, and app tools to control them."
    ),
    lifespan=app_lifespan,
)

register_all_tools(mcp)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
