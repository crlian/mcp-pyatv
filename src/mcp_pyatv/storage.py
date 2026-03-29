import asyncio
import os

from pyatv.storage.file_storage import FileStorage

DEFAULT_STORAGE_PATH = os.path.expanduser("~/.pyatv.conf")

_storage: FileStorage | None = None


async def get_storage() -> FileStorage:
    global _storage
    if _storage is None:
        path = os.environ.get("MCP_PYATV_STORAGE_PATH", DEFAULT_STORAGE_PATH)
        loop = asyncio.get_running_loop()
        _storage = FileStorage(path, loop)
        await _storage.load()
    return _storage
