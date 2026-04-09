# mcp-pyatv Development Status — 2026-04-08

## What was done today

### Bug Fixes (connection stability)
- **Auto-reconnect on BlockedStateError/ConnectionLostError**: `ConnectionManager.execute()` catches dead connections and reconnects automatically
- **Startup retry with protocol probe**: `_connect()` probes Companion/MRP availability after connecting, retries with re-scan and backoff if protocol not established. HomePod/AirPlay-only devices skip the probe
- **NotSupportedError handling**: Separate catch in `execute()` that evicts stale connection before reconnecting
- **Connection heartbeat**: Background asyncio task every 30s probes connections, reconnects dead ones. Configurable via `MCP_PYATV_HEARTBEAT_INTERVAL` (0 to disable)
- **Reconnect lock**: `asyncio.Lock` prevents duplicate connections between heartbeat and execute()

### New Features

#### Screenshot support (Developer Mode required)
- `take_screenshot` tool via pymobiledevice3 CLI subprocess
- Captures 3840x2160 PNG, resizes to 1920px JPEG (~300KB) via macOS `sips`
- Optional — only registers if pymobiledevice3 is on PATH
- Requires: Developer Mode on Apple TV + `sudo pymobiledevice3 remote tunneld` running

#### Batch execution
- `execute_sequence(steps)` — run up to 30 actions in one MCP call
- `repeat_command(direction, count, delay_ms)` — press a button N times
- Shared `run_steps()` and `build_action_map()` helpers for reuse

#### Screen state detection
- `get_screen_state()` — returns attention (awake/screensaver/asleep), device_state, current app, keyboard focus, AND available recipes in one call
- Uses Companion protocol's `fetch_attention_state()` for screensaver detection

#### Navigation recipes (segmented)
- `save_recipe` / `run_recipe` / `list_recipes` / `confirm_recipe_run` / `delete_recipe`
- Recipes are SEGMENTS: each goes from one screen to another
- Entry-point recipes start with `launch_app`, continuation recipes have `starting_screen` description
- Confidence system: 0.8 initial (screenshot-verified), 0.6 (user-confirmed), +0.05 per success, -0.2 per failure, -0.05/week decay
- Stored in `~/.mcp-pyatv-recipes.json`
- `get_screen_state` includes available recipes in response so Claude can't skip them

#### Enforced workflow
- `navigate`, `launch_app`, `execute_sequence`, `repeat_command`, `run_recipe` all require `get_screen_state` to be called first, otherwise return ERROR
- Server instructions rewritten as single linear flow (1414 chars, down from 3775)

### Tool return fixes
- 6 tools in remote.py (play, pause, etc.) now return confirmation strings instead of None
- Fixes Claude Desktop interpreting `content: []` as error

### Improved tool docstrings
- `navigate`: "Works everywhere: home screen, inside apps (Netflix, YouTube, Settings...)"
- `take_screenshot`: "See what is on the Apple TV screen right now"
- `launch_app`: "Fast (~1s). No screenshot needed."
- `now_playing`: "Faster than a screenshot for checking what is playing"

## File inventory

### New files
- `src/mcp_pyatv/tools/developer.py` — take_screenshot + _capture_screenshot helper
- `src/mcp_pyatv/tools/batch.py` — execute_sequence, repeat_command, run_steps, build_action_map
- `src/mcp_pyatv/recipes.py` — Recipe dataclass, JSON storage, confidence decay
- `src/mcp_pyatv/tools/recipes.py` — 5 recipe tools
- `tests/test_batch.py` — 10 batch tests
- `tests/test_recipes.py` — 18 recipe tests
- `CLAUDE.md` — project documentation
- `STATUS.md` — this file

### Modified files
- `src/mcp_pyatv/connection.py` — heartbeat, reconnect lock, probe+retry, _force_reconnect, execute() with NotSupportedError
- `src/mcp_pyatv/server.py` — rewritten instructions, lifespan with screen_state_checked flag
- `src/mcp_pyatv/tools/__init__.py` — conditional developer tools, batch tools, recipe tools registration
- `src/mcp_pyatv/tools/apps.py` — improved docstring, screen_state gate
- `src/mcp_pyatv/tools/remote.py` — return strings instead of None, improved navigate docstring, screen_state gate
- `src/mcp_pyatv/tools/now_playing.py` — get_screen_state with recipes, improved now_playing docstring
- `tests/conftest.py` — DeadAtv mock
- `tests/test_connection.py` — heartbeat tests, close_all fix

## Test count
59 tests, all passing

## Known issues / next steps
- Claude (Sonnet) sometimes ignores instructions despite enforcement — the screen_state gate helps but behavior still varies
- Haiku is too weak for visual navigation — Sonnet is the minimum recommended model
- Screenshots take ~5s each — main bottleneck for navigation speed
- pymobiledevice3 can't detect Apple TV via Bonjour on tvOS 26.x — requires `bonjour remotepairing-manual-pairing` workaround
- Accessibility tree (`pymobiledevice3 developer accessibility list-items`) fails on tvOS 26.x with "connection terminated abruptly"
- Claude Desktop config points to local source: `uv run --directory /path/to/mcp-pyatv mcp-pyatv`
- PyPI version is 0.2.0 — needs bump to 0.3.0 when ready to publish

## Setup requirements for full features
1. pyatv pairing (for control) — `scan_devices` + `start_pairing`/`finish_pairing`
2. Developer Mode on Apple TV (for screenshots) — Settings > Developer
3. pymobiledevice3 pairing — `pymobiledevice3 remote pair`
4. Tunnel daemon running — `sudo pymobiledevice3 remote tunneld --no-usb --no-usbmux --no-mobdev2 --wifi`
