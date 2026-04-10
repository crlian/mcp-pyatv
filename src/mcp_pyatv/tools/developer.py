import asyncio
import io
import logging
import os
import tempfile

from fastmcp import Context
from fastmcp.utilities.types import Image

_LOGGER = logging.getLogger(__name__)

_SCREENSHOT_TIMEOUT = 30
_DEFAULT_WIDTH = 1920

# Try to import pymobiledevice3 Python API for fast screenshots
_HAS_PMD3_API = False
try:
    from pymobiledevice3.tunneld.api import get_tunneld_devices, TUNNELD_DEFAULT_ADDRESS
    from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
    from pymobiledevice3.services.dvt.instruments.screenshot import Screenshot as DVTScreenshot
    _HAS_PMD3_API = True
except ImportError:
    pass

# Try Pillow for fast in-process resize
_HAS_PILLOW = False
try:
    from PIL import Image as PILImage
    _HAS_PILLOW = True
except ImportError:
    pass


def _resize_png_to_jpeg(png_data: bytes, width: int = _DEFAULT_WIDTH) -> tuple[bytes, str]:
    """Resize PNG screenshot to JPEG. Returns (image_bytes, format_string)."""
    if _HAS_PILLOW:
        img = PILImage.open(io.BytesIO(png_data))
        ratio = width / img.width
        new_height = int(img.height * ratio)
        img = img.resize((width, new_height), PILImage.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue(), "jpeg"
    # No Pillow — return raw PNG
    return png_data, "png"


async def _capture_screenshot_api(width: int = _DEFAULT_WIDTH):
    """Capture screenshot via pymobiledevice3 Python API (fast path)."""
    import time
    t_start = time.monotonic()

    try:
        devices = await get_tunneld_devices(TUNNELD_DEFAULT_ADDRESS)
    except Exception as e:
        return f"Cannot connect to tunnel daemon: {e}. Start it with: sudo pymobiledevice3 remote tunneld"

    if not devices:
        return "No tunneled devices found. Start the tunnel: sudo pymobiledevice3 remote tunneld"

    t_tunnel = time.monotonic()
    _LOGGER.info("screenshot: tunnel discovery %.2fs", t_tunnel - t_start)

    service_provider = devices[0]
    try:
        async with DvtProvider(service_provider) as dvt:
            t_dvt = time.monotonic()
            _LOGGER.info("screenshot: DVT connect %.2fs", t_dvt - t_tunnel)

            async with DVTScreenshot(dvt) as screenshot:
                png_data = await asyncio.wait_for(
                    screenshot.get_screenshot(),
                    timeout=_SCREENSHOT_TIMEOUT,
                )
                t_capture = time.monotonic()
                _LOGGER.info("screenshot: capture %.2fs (%d bytes PNG)", t_capture - t_dvt, len(png_data))
    except asyncio.TimeoutError:
        return "Screenshot timed out. Ensure the tunnel daemon is running."
    except Exception as e:
        return _interpret_error(str(e))

    image_data, fmt = _resize_png_to_jpeg(png_data, width)
    t_end = time.monotonic()
    _LOGGER.info("screenshot: resize %.2fs (%d bytes %s) | TOTAL %.2fs", t_end - t_capture, len(image_data), fmt, t_end - t_start)

    return Image(data=image_data, format=fmt)


async def _capture_screenshot_cli(pymobiledevice3_path: str, width: int = _DEFAULT_WIDTH):
    """Capture screenshot via pymobiledevice3 CLI subprocess (fallback)."""
    tmp_path = None
    jpg_path = None
    try:
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix="atv_ss_")
        os.close(tmp_fd)
        jpg_path = tmp_path + ".jpg"

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

        # Read raw PNG
        with open(tmp_path, "rb") as f:
            png_data = f.read()

        # Resize
        if _HAS_PILLOW:
            image_data, fmt = _resize_png_to_jpeg(png_data, width)
        else:
            # Fallback to sips (macOS only)
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

            if resize_proc.returncode == 0 and os.path.exists(jpg_path):
                with open(jpg_path, "rb") as f:
                    image_data = f.read()
                fmt = "jpeg"
            else:
                image_data = png_data
                fmt = "png"

        return Image(data=image_data, format=fmt)

    finally:
        for path in [tmp_path, jpg_path]:
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass


async def _capture_screenshot(pymobiledevice3_path: str, width: int = _DEFAULT_WIDTH):
    """Capture screenshot — uses Python API if available, falls back to CLI."""
    if _HAS_PMD3_API:
        return await _capture_screenshot_api(width)
    return await _capture_screenshot_cli(pymobiledevice3_path, width)


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
