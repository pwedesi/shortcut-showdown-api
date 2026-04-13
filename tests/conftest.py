"""Shared pytest fixtures."""

from __future__ import annotations

import asyncio

import pytest

from app.core.game_room_manager import game_room_manager
from app.core.lobby_manager import lobby_manager


@pytest.fixture(autouse=True)
def clear_lobbies_after_test() -> None:
    """Isolate in-memory lobby and game room state between tests."""
    yield

    async def _reset() -> None:
        await lobby_manager.reset()
        await game_room_manager.reset()

    asyncio.run(_reset())
