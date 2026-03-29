# mcp-pyatv

MCP server for controlling Apple TV, HomePod, and AirPlay devices via [pyatv](https://github.com/postlund/pyatv).

![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![Python 3.11-3.13](https://img.shields.io/badge/Python-3.11--3.13-green.svg)

---

## What It Does

mcp-pyatv is an [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that bridges any MCP client to Apple TV, HomePod, and AirPlay devices on your local network. It wraps [pyatv](https://github.com/postlund/pyatv) -- the open-source Python library that implements the actual Apple TV and AirPlay protocols -- and exposes its functionality as MCP tools.

This lets you control your devices using natural language through Claude Desktop, Claude Code, Cursor, or any other MCP-compatible client.

**This project does not implement any device protocols.** All protocol-level communication is handled by pyatv. mcp-pyatv is purely the MCP bridge layer.

## Supported Devices

- **Apple TV** -- all generations, including tvOS 15+
- **HomePod / HomePod Mini**
- **AirPort Express**
- **Third-party AirPlay speakers**
- **macOS** (Music/iTunes)

## Quick Start

### Install

```bash
pip install mcp-pyatv
```

Or run directly without installing:

```bash
uvx mcp-pyatv
```

### Claude Desktop Configuration

Add this to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "apple-tv": {
      "command": "uvx",
      "args": ["mcp-pyatv"]
    }
  }
}
```

### Local Development

If you've cloned the repo and want to run from source:

```json
{
  "mcpServers": {
    "apple-tv": {
      "command": "/path/to/venv/bin/python",
      "args": ["-m", "mcp_pyatv.server"],
      "env": {
        "PYTHONPATH": "/path/to/mcp-pyatv/src"
      }
    }
  }
}
```

## First Use / Pairing

On first use, just say **"Pair my Apple TV"** to your MCP client. The server handles the rest:

1. It scans your network and discovers devices.
2. A PIN appears on your TV screen.
3. You tell the client the PIN.
4. Credentials are stored locally and persist across sessions.

You only need to pair once per device. HomePods do not require pairing.

## Available Tools

mcp-pyatv exposes 32 tools organized by category:

### Discovery

| Tool | Description |
|------|-------------|
| `scan_devices` | Scan the local network for Apple TV and AirPlay devices |
| `device_info` | Get detailed information about a specific device |

### Pairing

| Tool | Description |
|------|-------------|
| `start_pairing` | Begin the pairing process with a device |
| `finish_pairing` | Complete pairing by submitting the PIN shown on screen |

### Playback

| Tool | Description |
|------|-------------|
| `play` | Resume playback |
| `pause` | Pause playback |
| `play_pause` | Toggle play/pause |
| `stop` | Stop playback |
| `next_track` | Skip to next track |
| `previous_track` | Go to previous track |
| `skip_forward` | Skip forward by a number of seconds |
| `skip_backward` | Skip backward by a number of seconds |
| `set_position` | Seek to a specific position |
| `set_shuffle` | Set shuffle mode |
| `set_repeat` | Set repeat mode |

### Navigation

| Tool | Description |
|------|-------------|
| `navigate` | Send remote control commands -- supports `up`, `down`, `left`, `right`, `select`, `menu`, `home`, `top_menu` with `single_tap`, `double_tap`, or `hold` actions |

### Audio

| Tool | Description |
|------|-------------|
| `get_volume` | Get the current volume level |
| `set_volume` | Set volume to a specific level |
| `volume_up` | Increase volume |
| `volume_down` | Decrease volume |

### Apps

| Tool | Description |
|------|-------------|
| `list_apps` | List all installed apps |
| `launch_app` | Launch an app by name or bundle ID |

### Power

| Tool | Description |
|------|-------------|
| `turn_on` | Turn on the device |
| `turn_off` | Turn off / put the device to sleep |
| `power_state` | Check if the device is on or off |

### Keyboard

| Tool | Description |
|------|-------------|
| `set_text` | Type text into a text field (e.g., search boxes) |
| `get_text` | Get the current text field contents |
| `clear_text` | Clear the current text field |

### Streaming

| Tool | Description |
|------|-------------|
| `play_url` | Stream media from a URL to the device |
| `stream_file` | Stream a local file to the device |

### Media Info

| Tool | Description |
|------|-------------|
| `now_playing` | Get information about what's currently playing |
| `get_artwork` | Get the artwork for the currently playing media |

## Example Conversations

**Checking what's playing:**
> "What's playing on my Apple TV?"
>
> The server calls `scan_devices` to find your Apple TV, then `now_playing` to get the current track/show info.

**Launching an app:**
> "Open Netflix"
>
> The server calls `launch_app` with the Netflix bundle ID.

**Adjusting volume:**
> "Set the volume to 40"
>
> The server calls `set_volume` with level 40.

**Pairing a new device:**
> "Pair my Apple TV"
>
> The server calls `scan_devices`, then `start_pairing`. A PIN appears on your TV. You say "The PIN is 1234", and the server calls `finish_pairing` to complete the process.

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `MCP_PYATV_STORAGE_PATH` | Override the file path where pairing credentials are stored | `~/.pyatv.conf` |

The default credential file (`~/.pyatv.conf`) is shared with pyatv's `atvremote` CLI tool. If you've already paired devices using `atvremote`, mcp-pyatv will pick up those credentials automatically.

## Known Limitations

- **`play_url` broken on tvOS 26.x** -- upstream pyatv issue ([#2821](https://github.com/postlund/pyatv/issues/2821))
- **`stop` ignored by some apps** -- YouTube and certain other apps do not respond to the stop command
- **`get_artwork` depends on the app** -- not all apps expose artwork metadata
- **Same network required** -- your machine must be on the same WiFi network as your devices
- **`set_shuffle` / `set_repeat`** -- require an active music playback queue to work
- **Python 3.14** -- not currently supported due to asyncio compatibility issues in pyatv

## Built On

This project is built on **[pyatv](https://github.com/postlund/pyatv)** by [Pierre Stahl](https://github.com/postlund) -- the Python library that implements the Companion, AirPlay, RAOP, MRP, and DMAP protocols used by Apple devices. All protocol-level communication, device discovery, and pairing logic happens inside pyatv. mcp-pyatv provides only the MCP server layer on top.

For protocol details, bug reports related to device communication, or to contribute to the underlying library, visit:

- [pyatv GitHub](https://github.com/postlund/pyatv)
- [pyatv Documentation](https://pyatv.dev)

## License

MIT -- see [LICENSE](LICENSE) for details.
