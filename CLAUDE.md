# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

mcp-pyatv is an MCP (Model Context Protocol) server that bridges Claude and other MCP clients to Apple TV, HomePod, and AirPlay devices on a local network. It wraps the [pyatv](https://pyatv.dev) Python library and exposes device control as 32 MCP tools via [FastMCP](https://github.com/jlowin/FastMCP) 2.0+.

## Build & Run

```bash
# Install from source (editable)
pip install -e .

# Run the server
mcp-pyatv
# or
python -m mcp_pyatv.server

# Run via uvx (no install)
uvx mcp-pyatv
```

Build system is **hatchling** (configured in `pyproject.toml`). No linter/formatter configuration exists. No automated tests exist yet (tests/ is empty).

**Python**: 3.11, 3.12, 3.13 supported. 3.14 is **not** supported (asyncio issues in upstream pyatv).

## Architecture

### Server Lifecycle (`server.py`)

FastMCP server with **lazy initialization**: storage and connections are created on first tool call (not at startup) to avoid timeouts during MCP handshake. The lifespan context exposes two lazy getters:
- `ctx.lifespan_context["get_connections"]()` → `ConnectionManager`
- `ctx.lifespan_context["get_storage"]()` → `FileStorage`

### Connection Management (`connection.py`)

`ConnectionManager` wraps pyatv's scan/connect/pair APIs and maintains two caches:
- `_connections`: device identifier → connected AppleTV instance
- `_configs`: device identifier → device config metadata

**Device resolution** (`conn.get(device)`): if `device=None`, auto-selects when exactly 1 device exists. Otherwise matches by name (case-insensitive) or identifier. Scans the network if device not in cache.

### Storage (`storage.py`)

Wraps `pyatv.storage.FileStorage` for credential persistence at `~/.pyatv.conf` (configurable via `MCP_PYATV_STORAGE_PATH` env var). This file is shared with the `atvremote` CLI tool.

### Tools (`tools/`)

9 modules, 32 tools total:

| Module | Tools | Notes |
|--------|-------|-------|
| `discovery.py` | `scan_devices`, `device_info` | Network scanning |
| `pairing.py` | `start_pairing`, `finish_pairing` | Stateful pairing flow with global state |
| `remote.py` | 13 tools (play, pause, navigate, seek, etc.) | Largest module |
| `power.py` | `turn_on`, `turn_off`, `power_state` | |
| `audio.py` | `get_volume`, `set_volume`, `volume_up`, `volume_down` | |
| `apps.py` | `list_apps`, `launch_app` | Match by name or bundle_id |
| `keyboard.py` | `set_text`, `get_text`, `clear_text` | |
| `now_playing.py` | `now_playing`, `get_artwork` | Artwork is base64-encoded |
| `stream.py` | `play_url`, `stream_file` | AirPlay streaming |

All tools are registered in `tools/__init__.py` via `register_all_tools(mcp)`.

### Tool Implementation Pattern

Every tool follows this structure:

```python
@mcp.tool()
async def tool_name(param: type, device: str | None = None, ctx: Context = None) -> return_type:
    """Docstring becomes the MCP tool description."""
    conn = await ctx.lifespan_context["get_connections"]()
    atv = await conn.get(device)
    result = await atv.some_interface.method(param)
    return result
```

Key conventions:
- Optional `device` parameter (None = auto-select single device)
- `ctx: Context` for FastMCP dependency injection
- All operations are async
- Return types: str, dict, list, or float

### Pairing State Machine (`tools/pairing.py`)

Pairing is stateful with module-level globals (`_active_pairing`, `_active_config`, `_active_protocol`). Protocol order: Companion → AirPlay → RAOP. After completing one protocol, the tool checks for remaining unpaired protocols. Only one pairing session at a time.

### Utilities (`util.py`)

- `format_device(config)` / `format_playing(playing)` — structured output formatters
- `parse_shuffle(state)` / `parse_repeat(state)` — string-to-pyatv enum converters

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `MCP_PYATV_STORAGE_PATH` | `~/.pyatv.conf` | Credential storage location |
| `MCP_PYATV_HEARTBEAT_INTERVAL` | `30` | Heartbeat probe interval in seconds (0 to disable) |

## Known Limitations

- `play_url` broken on tvOS 26.x (upstream pyatv issue)
- Some apps ignore `stop` command
- `get_artwork` depends on app support
- Shuffle/repeat require active music queue
- Devices must be on same network as the server
