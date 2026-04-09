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

    screen_state_checked = False

    def mark_screen_state_checked():
        nonlocal screen_state_checked
        screen_state_checked = True

    def is_screen_state_checked():
        return screen_state_checked

    try:
        yield {
            "get_connections": get_connections,
            "get_storage": get_storage,
            "mark_screen_state_checked": mark_screen_state_checked,
            "is_screen_state_checked": is_screen_state_checked,
        }
    finally:
        if connections:
            await connections.close_all()


mcp = FastMCP(
    "mcp-pyatv",
    instructions=(
        "You control Apple TV via a virtual Siri Remote. "
        "navigate(up/down/left/right/select/menu/home) works in every app. "
        "select=click, menu=back, home=home screen.\n\n"
        "FOR EVERY TASK, follow steps 1-4 in order:\n"
        "1. get_screen_state — returns device state AND available_recipes. "
        "If asleep/screensaver, navigate('select') to wake.\n"
        "2. Check available_recipes in the response. If a recipe matches your task: "
        "run_recipe → screenshot → confirm_recipe_run → done.\n"
        "3. If no recipe matches: screenshot → navigate → screenshot → repeat.\n"
        "4. After successful multi-step navigation (3+ steps): save_recipe with "
        "starting_screen and ending_screen descriptions. Keep segments 3-8 steps.\n\n"
        "SCREENSHOT RULES:\n"
        "- Take one before ANY navigation to see where you are.\n"
        "- After launch_app, ALWAYS screenshot — app may resume anywhere.\n"
        "- NEVER take two screenshots in a row without acting between them.\n"
        "- COUNT items on screen: 'I see 4 items: 1=X 2=Y 3=Z 4=W. "
        "Focus is on item 1, target is 3, so 2 downs.' Find the highlight.\n"
        "- Batch only actions you can confirm from the CURRENT screenshot "
        "using execute_sequence. Do not guess layouts.\n\n"
        "NO SCREENSHOT NEEDED:\n"
        "- launch_app('name') alone (just opening an app)\n"
        "- play, pause, stop, volume, skip commands\n"
        "- now_playing (faster than screenshot for playback info)\n"
        "- navigate('menu') to go back, navigate('home')\n\n"
        "NEVER: navigate without seeing the screen first. "
        "Assume menu positions. Skip list_recipes. "
        "Make individual calls when execute_sequence works."
    ),
    lifespan=app_lifespan,
)

register_all_tools(mcp)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
