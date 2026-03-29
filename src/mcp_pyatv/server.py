from contextlib import asynccontextmanager

from fastmcp import FastMCP

from .connection import ConnectionManager
from .storage import get_storage
from .tools import register_all_tools


@asynccontextmanager
async def app_lifespan(server):
    # Storage and connections are created lazily on first tool call
    # to avoid timeout during MCP initialization
    connections = None

    async def get_connections():
        nonlocal connections
        if connections is None:
            storage = await get_storage()
            connections = ConnectionManager(storage)
        return connections

    try:
        yield {"get_connections": get_connections, "get_storage": get_storage}
    finally:
        if connections:
            await connections.close_all()


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
