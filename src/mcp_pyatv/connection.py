import asyncio
import inspect
import logging
import os
from typing import Any

import pyatv
from pyatv.const import FeatureName, FeatureState, Protocol
from pyatv.exceptions import (
    BlockedStateError,
    ConnectionFailedError,
    ConnectionLostError,
    NotSupportedError,
)
from pyatv.storage.file_storage import FileStorage

_LOGGER = logging.getLogger(__name__)

_CONNECT_RETRIES = 3
_CONNECT_BACKOFF = [1.0, 2.0]  # seconds before attempt 2 and 3
_DEFAULT_HEARTBEAT_INTERVAL = 30


class ConnectionManager:
    def __init__(self, storage: FileStorage):
        self.storage = storage
        self._connections: dict[str, Any] = {}  # id -> AppleTV
        self._configs: dict[str, Any] = {}  # id -> BaseConfig
        self._reconnect_lock = asyncio.Lock()
        self._heartbeat_task: asyncio.Task | None = None
        self._heartbeat_interval: int = int(
            os.environ.get("MCP_PYATV_HEARTBEAT_INTERVAL", _DEFAULT_HEARTBEAT_INTERVAL)
        )

    async def scan(self, timeout: float = 3.0):
        loop = asyncio.get_running_loop()
        configs = await pyatv.scan(
            loop, timeout=int(timeout), storage=self.storage
        )
        for config in configs:
            self._configs[config.identifier] = config
        return configs

    async def get(self, device: str | None = None):
        _, atv = await self._get_with_id(device)
        return atv

    async def _get_with_id(self, device: str | None) -> tuple[str, Any]:
        if device is None:
            if len(self._connections) == 1:
                id_ = next(iter(self._connections))
                return id_, self._connections[id_]
            configs = await self.scan()
            if len(configs) == 0:
                raise ValueError("No devices found on network")
            if len(configs) == 1:
                atv = await self._connect(configs[0])
                return configs[0].identifier, atv
            names = [c.name for c in configs]
            raise ValueError(
                f"Multiple devices found: {', '.join(names)}. Please specify which one."
            )

        for id_, atv in self._connections.items():
            config = self._configs.get(id_)
            if config and config.name.lower() == device.lower():
                return id_, atv
            if id_ == device:
                return id_, atv

        configs = await self.scan()
        for config in configs:
            if config.name.lower() == device.lower() or config.identifier == device:
                atv = await self._connect(config)
                return config.identifier, atv

        names = [c.name for c in configs]
        raise ValueError(f"Device '{device}' not found. Available: {', '.join(names)}")

    async def _connect(self, config):
        if config.identifier in self._connections:
            return self._connections[config.identifier]

        # Only Apple TV devices advertise Companion or MRP protocols.
        # HomePod and AirPlay-only devices never have them — skip the probe for those.
        needs_probe = any(
            s.protocol in (Protocol.Companion, Protocol.MRP)
            for s in config.services
        )

        loop = asyncio.get_running_loop()
        for attempt in range(_CONNECT_RETRIES):
            if attempt > 0:
                delay = _CONNECT_BACKOFF[attempt - 1]
                _LOGGER.warning(
                    "Retrying connection to '%s' (attempt %d/%d) in %.1fs — "
                    "Companion/MRP protocol was not established on previous attempt",
                    config.name, attempt + 1, _CONNECT_RETRIES, delay,
                )
                await asyncio.sleep(delay)
                # Re-scan with a longer timeout so the Apple TV has time to wake up
                fresh_configs = await pyatv.scan(loop, timeout=5, storage=self.storage)
                for fc in fresh_configs:
                    if fc.identifier == config.identifier:
                        config = fc
                        self._configs[config.identifier] = fc
                        break
                else:
                    _LOGGER.warning(
                        "Device '%s' not found in re-scan, retrying with cached config",
                        config.name,
                    )

            atv = await pyatv.connect(config, loop, storage=self.storage)

            if not needs_probe:
                # HomePod / AirPlay-only: no remote_control expected, connection is valid
                self._connections[config.identifier] = atv
                self._configs[config.identifier] = config
                self._start_heartbeat()
                return atv

            # Apple TV: verify Companion/MRP actually established by probing a remote_control feature
            try:
                ok = atv.features.in_state(FeatureState.Available, FeatureName.Up)
            except Exception:
                ok = False

            if ok:
                _LOGGER.debug(
                    "Connected to '%s' with Companion/MRP available (attempt %d)",
                    config.name, attempt + 1,
                )
                self._connections[config.identifier] = atv
                self._configs[config.identifier] = config
                self._start_heartbeat()
                return atv

            # Partial connection — Companion/MRP missing. Close and retry.
            _LOGGER.warning(
                "Connected to '%s' but Companion/MRP protocol is missing "
                "(attempt %d/%d) — will retry",
                config.name, attempt + 1, _CONNECT_RETRIES,
            )
            try:
                tasks = atv.close()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
            except Exception:
                pass

        raise ConnectionFailedError(
            f"Could not establish a full connection to '{config.name}' after "
            f"{_CONNECT_RETRIES} attempts. "
            "Companion/MRP protocol was never available. "
            "Ensure the device is awake and paired."
        )

    async def _force_reconnect(self, identifier: str):
        stale = self._connections.pop(identifier, None)
        if stale is not None:
            try:
                tasks = stale.close()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
            except Exception:
                pass

        config = self._configs.get(identifier)
        if config is None:
            raise ValueError(
                f"No config cached for '{identifier}'; cannot reconnect. "
                "Try scan_devices first."
            )
        _LOGGER.info("Reconnecting to device '%s'", identifier)
        return await self._connect(config)

    async def execute(self, device: str | None, operation):
        """Get device, run operation(atv), auto-reconnect once on blocked/lost/unsupported."""
        identifier, atv = await self._get_with_id(device)
        try:
            result = operation(atv)
            if inspect.isawaitable(result):
                return await result
            return result
        except (BlockedStateError, ConnectionLostError) as exc:
            _LOGGER.warning(
                "Connection to '%s' lost (%s); reconnecting...", identifier, exc
            )
            async with self._reconnect_lock:
                atv = await self._force_reconnect(identifier)
            result = operation(atv)
            if inspect.isawaitable(result):
                return await result
            return result
        except NotSupportedError as exc:
            _LOGGER.warning(
                "Operation on '%s' raised NotSupportedError (%s); "
                "protocol may not have been established — forcing reconnect",
                identifier, exc,
            )
            async with self._reconnect_lock:
                self._connections.pop(identifier, None)
                atv = await self._force_reconnect(identifier)
            result = operation(atv)
            if inspect.isawaitable(result):
                return await result
            return result

    # ------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------

    def _start_heartbeat(self):
        """Start the heartbeat task if not already running and interval > 0."""
        if self._heartbeat_interval <= 0:
            return
        if self._heartbeat_task is not None and not self._heartbeat_task.done():
            return
        self._heartbeat_task = asyncio.get_running_loop().create_task(
            self._heartbeat_loop()
        )

    async def _heartbeat_loop(self):
        """Periodically probe connections and reconnect dead ones."""
        _LOGGER.debug("Heartbeat started (interval=%ds)", self._heartbeat_interval)
        try:
            while True:
                await asyncio.sleep(self._heartbeat_interval)

                if not self._connections:
                    continue

                # Snapshot keys to avoid dict-changed-during-iteration
                identifiers = list(self._connections.keys())

                for identifier in identifiers:
                    atv = self._connections.get(identifier)
                    if atv is None:
                        continue

                    config = self._configs.get(identifier)
                    needs_probe = config is not None and any(
                        s.protocol in (Protocol.Companion, Protocol.MRP)
                        for s in config.services
                    )

                    if not needs_probe:
                        continue

                    # Probe: check if Companion/MRP is still alive
                    alive = True
                    try:
                        ok = atv.features.in_state(
                            FeatureState.Available, FeatureName.Up
                        )
                        if not ok:
                            alive = False
                    except (BlockedStateError, ConnectionLostError, NotSupportedError):
                        alive = False
                    except Exception as exc:
                        _LOGGER.debug(
                            "Heartbeat: unexpected error probing '%s': %s",
                            identifier, exc,
                        )
                        continue

                    if alive:
                        continue

                    _LOGGER.warning(
                        "Heartbeat: connection to '%s' is dead; reconnecting...",
                        identifier,
                    )
                    try:
                        async with self._reconnect_lock:
                            await self._force_reconnect(identifier)
                        _LOGGER.info("Heartbeat: reconnected to '%s'", identifier)
                    except Exception as exc:
                        _LOGGER.warning(
                            "Heartbeat: failed to reconnect '%s' (%s); "
                            "removing from cache",
                            identifier, exc,
                        )
                        self._connections.pop(identifier, None)
        except asyncio.CancelledError:
            _LOGGER.debug("Heartbeat stopped")

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    async def close_all(self):
        # Cancel heartbeat first
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        tasks = set()
        for atv in self._connections.values():
            tasks.update(atv.close())
        self._connections.clear()
        # _configs intentionally retained to allow reconnection after restart
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
