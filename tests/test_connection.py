import asyncio

import pytest

from mcp_pyatv.connection import ConnectionManager


class FakeAtv:
    """Minimal fake AppleTV that tracks whether its close tasks were awaited."""

    def __init__(self):
        self.task_was_awaited = False

    def close(self):
        async def _close():
            self.task_was_awaited = True

        return {asyncio.create_task(_close())}


@pytest.mark.asyncio
async def test_close_all_awaits_tasks():
    conn = ConnectionManager(storage=None)
    fake = FakeAtv()
    conn._connections["fake-id"] = fake

    await conn.close_all()

    assert fake.task_was_awaited, "close_all() did not await the tasks returned by atv.close()"
    assert conn._connections == {}
    assert conn._configs == {}
