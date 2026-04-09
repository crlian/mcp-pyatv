import os
import shutil

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

    # Optional: developer tools (screenshots) require pymobiledevice3
    _pmd3_paths = [
        shutil.which("pymobiledevice3"),
        os.path.expanduser("~/.local/bin/pymobiledevice3"),
    ]
    pmd3_path = next((p for p in _pmd3_paths if p and os.path.isfile(p)), None)
    if pmd3_path:
        from .developer import register_developer_tools
        register_developer_tools(mcp, pymobiledevice3_path=pmd3_path)

    # Batch tools are always registered; take_screenshot action inside
    # execute_sequence gracefully degrades if pymobiledevice3 is unavailable.
    from .batch import register_batch_tools
    register_batch_tools(mcp, pymobiledevice3_path=pmd3_path)

    # Recipe tools for saving and replaying navigation paths
    from .recipes import register_recipe_tools
    register_recipe_tools(mcp, pymobiledevice3_path=pmd3_path)
