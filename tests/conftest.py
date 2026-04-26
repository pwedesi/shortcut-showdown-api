"""Shared pytest fixtures."""

from __future__ import annotations

import asyncio

import pytest

from app.core.config import get_settings
from app.core.connection_manager import connection_manager
from app.core.game_room_manager import game_room_manager
from app.core.lobby_manager import lobby_manager


@pytest.fixture(autouse=True)
def clear_lobbies_after_test(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset state; pin lobby cap to 2 so tests are independent of local `.env`."""
    get_settings.cache_clear()
    monkeypatch.setenv("LOBBY_MAX_PLAYERS", "2")
    get_settings()
    yield
    get_settings.cache_clear()

    async def _reset() -> None:
        await lobby_manager.reset()
        await game_room_manager.reset()
        await connection_manager.reset()

    asyncio.run(_reset())
