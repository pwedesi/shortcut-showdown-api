"""Default shortcut dataset for the Shortcut Showdown game.

Prompts intentionally omit key hints; `expectedKeys` remains internal.
"""

from __future__ import annotations

from typing import Any, Dict, List


DEFAULT_CHALLENGES: List[Dict[str, Any]] = [
    {"prompt": "Copy selected text", "expectedKeys": ["ctrl", "c"]},
    {"prompt": "Paste", "expectedKeys": ["ctrl", "v"]},
    {"prompt": "Save file", "expectedKeys": ["ctrl", "s"]},
    {"prompt": "Open new tab", "expectedKeys": ["ctrl", "t"]},
    {"prompt": "Close window", "expectedKeys": ["alt", "f4"]},
    {"prompt": "Undo", "expectedKeys": ["ctrl", "z"]},
    {"prompt": "Redo", "expectedKeys": ["ctrl", "y"]},
    {"prompt": "Find", "expectedKeys": ["ctrl", "f"]},
    {"prompt": "Replace", "expectedKeys": ["ctrl", "h"]},
    {"prompt": "Select all", "expectedKeys": ["ctrl", "a"]},
    {"prompt": "Toggle fullscreen", "expectedKeys": ["f11"]},
    {"prompt": "New window", "expectedKeys": ["ctrl", "n"]},
]


def get_default_dataset() -> List[Dict[str, Any]]:
    """Return a shallow copy of the default dataset for extension or testing."""
    return [dict(item) for item in DEFAULT_CHALLENGES]
