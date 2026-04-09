import asyncio
import logging
import os
import tempfile
from datetime import datetime, timezone

from fastmcp import Context
from fastmcp.utilities.types import Image

_LOGGER = logging.getLogger(__name__)

_SCREENSHOT_TIMEOUT = 30
_DEFAULT_WIDTH = 1920


async def _capture_screenshot(pymobiledevice3_path: str, width: int = _DEFAULT_WIDTH):
    """Capture a screenshot via pymobiledevice3 CLI.

    Returns an Image on success, or an error string on failure.
    """
    tmp_path = None
    jpg_path = None
    try:
        # Create temp file for raw screenshot
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix="atv_ss_")
        os.close(tmp_fd)
        jpg_path = tmp_path + ".jpg"

        # Take screenshot via pymobiledevice3 CLI
        cmd = [
            pymobiledevice3_path, "developer", "dvt", "screenshot",
            tmp_path, "--tunnel", "",
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=_SCREENSHOT_TIMEOUT
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return "Screenshot timed out. Ensure the tunnel daemon is running: sudo pymobiledevice3 remote tunneld"

        if proc.returncode != 0:
            return _interpret_error(stderr.decode("utf-8", errors="replace").strip())

        if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
            return "Screenshot command succeeded but produced no output."

        # Resize with sips (macOS built-in) to reduce size for MCP transport
        resize_proc = await asyncio.create_subprocess_exec(
            "sips",
            "--resampleWidth", str(width),
            "--setProperty", "format", "jpeg",
            "--setProperty", "formatOptions", "85",
            tmp_path,
            "--out", jpg_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await resize_proc.communicate()

        # Use resized JPEG if available, otherwise fall back to raw PNG
        if resize_proc.returncode == 0 and os.path.exists(jpg_path):
            image_path = jpg_path
            fmt = "jpeg"
        else:
            image_path = tmp_path
            fmt = "png"

        with open(image_path, "rb") as f:
            image_data = f.read()

        return Image(data=image_data, format=fmt)

    finally:
        for path in [tmp_path, jpg_path]:
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass


def register_developer_tools(mcp, pymobiledevice3_path: str = "pymobiledevice3"):

    @mcp.tool()
    async def take_screenshot(
        device: str | None = None,
        width: int = _DEFAULT_WIDTH,
        ctx: Context = None,
    ):
        """See what is on the Apple TV screen right now. Returns an image you can analyze to read text, find items in menus/lists, or verify navigation. Takes ~5s. Use now_playing instead if you just need playback info."""
        return await _capture_screenshot(pymobiledevice3_path, width)


def _interpret_error(error_msg: str) -> str:
    lower = error_msg.lower()

    if "tunnel" in lower or "unable to connect" in lower or "connection refused" in lower:
        return (
            "Tunnel not available. Start it first:\n"
            "  sudo pymobiledevice3 remote tunneld\n\n"
            f"Error: {error_msg}"
        )

    if "developer mode" in lower or "developer disk" in lower:
        return (
            "Developer Mode is not enabled on the Apple TV. "
            "Enable it in Settings > Developer.\n\n"
            f"Error: {error_msg}"
        )

    if "no devices" in lower or "not connected" in lower:
        return (
            "No Apple TV found. Ensure the device is on the same network "
            "and the tunnel daemon is running.\n\n"
            f"Error: {error_msg}"
        )

    return f"Screenshot failed: {error_msg}"
