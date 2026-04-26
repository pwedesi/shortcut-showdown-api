"""Default shortcut dataset for the Shortcut Showdown game.

Prompts intentionally omit key hints; `expectedKeys` remains internal.

Challenges use **Windows-style** bindings (Ctrl / Shift / Alt and key names like
``arrowleft``). They avoid browser-chrome and OS-capture chords (e.g. new tab,
new window, save page, find, F11) that are often not cancelable in a web app.
Clients on other OSes should map to the same logical tokens (e.g. use ``ctrl``
for the primary modifier, not ``meta`` / Command, so objectives stay consistent).
"""

from __future__ import annotations

from typing import Any, Dict, List


DEFAULT_CHALLENGES: List[Dict[str, Any]] = [
    {"prompt": "Copy selected text", "expectedKeys": ["ctrl", "c"]},
    {"prompt": "Paste", "expectedKeys": ["ctrl", "v"]},
    {"prompt": "Cut", "expectedKeys": ["ctrl", "x"]},
    {"prompt": "Undo", "expectedKeys": ["ctrl", "z"]},
    {"prompt": "Redo", "expectedKeys": ["ctrl", "y"]},
    {"prompt": "Select all", "expectedKeys": ["ctrl", "a"]},
    {"prompt": "Bold", "expectedKeys": ["ctrl", "b"]},
    {"prompt": "Italic", "expectedKeys": ["ctrl", "i"]},
    {"prompt": "Move the caret one word left", "expectedKeys": ["ctrl", "arrowleft"]},
    {"prompt": "Move the caret one word right", "expectedKeys": ["ctrl", "arrowright"]},
    {"prompt": "Delete the previous word", "expectedKeys": ["ctrl", "backspace"]},
    {
        "prompt": "Go to the start of the line or the current text (editor / browser)",
        "expectedKeys": ["ctrl", "home"],
    },
    {
        "prompt": "Go to the end of the line or the current text (editor / browser)",
        "expectedKeys": ["ctrl", "end"],
    },
    {
        "prompt": "Redo (alternate shortcut, common in many apps)",
        "expectedKeys": ["ctrl", "shift", "z"],
    },
    {
        "prompt": "Delete the next word (after the caret)",
        "expectedKeys": ["ctrl", "delete"],
    },
    {
        "prompt": "Select from the caret to the start of the line",
        "expectedKeys": ["shift", "home"],
    },
    {
        "prompt": "Select from the caret to the end of the line",
        "expectedKeys": ["shift", "end"],
    },
    {
        "prompt": "Extend the selection by one word to the right",
        "expectedKeys": ["arrowright", "ctrl", "shift"],
    },
    {
        "prompt": "Extend the selection by one word to the left",
        "expectedKeys": ["arrowleft", "ctrl", "shift"],
    },
]


def get_default_dataset() -> List[Dict[str, Any]]:
    """Return a shallow copy of the default dataset for extension or testing."""
    return [dict(item) for item in DEFAULT_CHALLENGES]
