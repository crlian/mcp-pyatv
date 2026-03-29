import asyncio
from typing import Any

import pyatv
from pyatv.storage.file_storage import FileStorage


class ConnectionManager:
    def __init__(self, storage: FileStorage):
        self.storage = storage
        self._connections: dict[str, Any] = {}  # id -> AppleTV
        self._configs: dict[str, Any] = {}  # id -> BaseConfig

    async def scan(self, timeout: float = 3.0):
        loop = asyncio.get_running_loop()
        configs = await pyatv.scan(
            loop, timeout=int(timeout), storage=self.storage
        )
        for config in configs:
            self._configs[config.identifier] = config
        return configs

    async def get(self, device: str | None = None):
        if device is None:
            if len(self._connections) == 1:
                return list(self._connections.values())[0]
            configs = await self.scan()
            if len(configs) == 0:
                raise ValueError("No devices found on network")
            if len(configs) == 1:
                return await self._connect(configs[0])
            names = [c.name for c in configs]
            raise ValueError(
                f"Multiple devices found: {', '.join(names)}. Please specify which one."
            )

        for id_, atv in self._connections.items():
            config = self._configs.get(id_)
            if config and config.name.lower() == device.lower():
                return atv
            if id_ == device:
                return atv

        configs = await self.scan()
        for config in configs:
            if config.name.lower() == device.lower() or config.identifier == device:
                return await self._connect(config)

        names = [c.name for c in configs]
        raise ValueError(f"Device '{device}' not found. Available: {', '.join(names)}")

    async def _connect(self, config):
        if config.identifier in self._connections:
            return self._connections[config.identifier]
        loop = asyncio.get_running_loop()
        atv = await pyatv.connect(
            config, loop, storage=self.storage
        )
        self._connections[config.identifier] = atv
        self._configs[config.identifier] = config
        return atv

    async def close_all(self):
        for atv in self._connections.values():
            atv.close()
        self._connections.clear()
        self._configs.clear()
