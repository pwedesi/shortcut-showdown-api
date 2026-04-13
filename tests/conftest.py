"""Shared pytest fixtures."""

from __future__ import annotations

import asyncio

import pytest

from app.core.lobby_manager import lobby_manager


@pytest.fixture(autouse=True)
def clear_lobbies_after_test() -> None:
    """Isolate in-memory lobby state between tests."""
    yield
    asyncio.run(lobby_manager.reset())
