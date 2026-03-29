from .discovery import register_discovery_tools
from .pairing import register_pairing_tools
from .remote import register_remote_tools
from .now_playing import register_now_playing_tools
from .apps import register_app_tools
from .power import register_power_tools
from .audio import register_audio_tools
from .stream import register_stream_tools
from .keyboard import register_keyboard_tools


def register_all_tools(mcp):
    register_discovery_tools(mcp)
    register_pairing_tools(mcp)
    register_remote_tools(mcp)
    register_now_playing_tools(mcp)
    register_app_tools(mcp)
    register_power_tools(mcp)
    register_audio_tools(mcp)
    register_stream_tools(mcp)
    register_keyboard_tools(mcp)
