import asyncio

import pyatv
from fastmcp import Context
from pyatv.const import Protocol

_active_pairing = None
_active_config = None
_active_protocol = None

PROTOCOL_MAP = {
    "airplay": Protocol.AirPlay,
    "companion": Protocol.Companion,
    "raop": Protocol.RAOP,
}

# Pairing order: Companion first (remote control), then AirPlay (video), then RAOP (audio)
PAIRING_ORDER = ["companion", "airplay", "raop"]


def _get_unpaired_protocols(config):
    """Return list of protocol names that still need pairing."""
    from pyatv.const import PairingRequirement

    unpaired = []
    for name in PAIRING_ORDER:
        proto = PROTOCOL_MAP[name]
        for service in config.services:
            if service.protocol == proto:
                if service.pairing == PairingRequirement.Mandatory and service.credentials is None:
                    unpaired.append(name)
    return unpaired


def register_pairing_tools(mcp):
    @mcp.tool()
    async def start_pairing(
        device: str, protocol: str | None = None, ctx: Context = None
    ) -> dict:
        """Start pairing with a device. If protocol is not specified, automatically picks the next unpaired protocol. After calling this, a PIN will appear on the device screen. Ask the user for the PIN, then call finish_pairing."""
        global _active_pairing, _active_config, _active_protocol

        if _active_pairing:
            await _active_pairing.close()
            _active_pairing = None

        conn = await ctx.lifespan_context["get_connections"]()
        storage = await ctx.lifespan_context["get_storage"]()

        configs = await conn.scan()
        config = None
        for c in configs:
            if c.name.lower() == device.lower() or c.identifier == device:
                config = c
                break

        if not config:
            names = [c.name for c in configs]
            return {
                "error": f"Device '{device}' not found. Available: {', '.join(names)}"
            }

        # Auto-detect next unpaired protocol if not specified
        if protocol is None:
            unpaired = _get_unpaired_protocols(config)
            if not unpaired:
                return {
                    "status": "fully_paired",
                    "device": config.name,
                    "message": f"{config.name} is already fully paired on all protocols.",
                }
            protocol = unpaired[0]

        proto = PROTOCOL_MAP.get(protocol.lower())
        if not proto:
            return {
                "error": f"Unknown protocol '{protocol}'. Use: {', '.join(PROTOCOL_MAP.keys())}"
            }

        loop = asyncio.get_running_loop()
        handler = await pyatv.pair(
            config, proto, loop, storage=storage
        )
        await handler.begin()

        _active_pairing = handler
        _active_config = config
        _active_protocol = protocol

        if handler.device_provides_pin:
            return {
                "status": "awaiting_pin",
                "device": config.name,
                "protocol": protocol,
                "instructions": f"A 4-digit PIN is now displayed on {config.name}. Please provide the PIN to complete pairing.",
            }
        else:
            return {
                "status": "awaiting_pin",
                "device": config.name,
                "protocol": protocol,
                "instructions": f"Enter PIN 0000 on {config.name}, then call finish_pairing with pin=0000.",
            }

    @mcp.tool()
    async def finish_pairing(pin: int, ctx: Context = None) -> dict:
        """Complete pairing by providing the PIN displayed on the device. Call start_pairing first."""
        global _active_pairing, _active_config, _active_protocol

        if not _active_pairing:
            return {"error": "No active pairing session. Call start_pairing first."}

        handler = _active_pairing
        config = _active_config
        paired_protocol = _active_protocol

        handler.pin(pin)
        await handler.finish()

        success = handler.has_paired
        protocol_name = handler.service.protocol.name

        await handler.close()
        _active_pairing = None
        _active_config = None
        _active_protocol = None

        if success:
            storage = await ctx.lifespan_context["get_storage"]()
            await storage.save()

            # Re-scan to check remaining unpaired protocols
            conn = await ctx.lifespan_context["get_connections"]()
            configs = await conn.scan()
            updated_config = None
            for c in configs:
                if c.name.lower() == config.name.lower():
                    updated_config = c
                    break

            remaining = _get_unpaired_protocols(updated_config) if updated_config else []

            result = {
                "success": True,
                "device": config.name,
                "protocol": protocol_name,
                "message": f"Successfully paired with {config.name} via {protocol_name}. Credentials saved.",
            }

            if remaining:
                result["remaining_protocols"] = remaining
                result["hint"] = (
                    f"There are still {len(remaining)} protocol(s) to pair: {', '.join(remaining)}. "
                    f"Call start_pairing again for '{config.name}' to pair the next one. "
                    f"Full pairing enables all features (remote control, video streaming, audio)."
                )
            else:
                result["hint"] = f"{config.name} is now fully paired on all protocols."

            return result
        else:
            return {
                "success": False,
                "message": "Pairing failed. The PIN may have been incorrect. Try again with start_pairing.",
            }
