"""Tests for keyboard token normalization in gameplay."""

from __future__ import annotations

from app.core.game_engine import GameEngine


def test_normalize_key_synonyms_match_expected_chords() -> None:
    left = GameEngine._normalize_keys(["Control", "c"])
    right = GameEngine._normalize_keys(["ctrl", "c"])
    assert left == right
    a = GameEngine._normalize_keys(["shift", "return"])
    b = GameEngine._normalize_keys(["enter", "shift"])
    assert a == b
    left2 = GameEngine._normalize_keys(["ShiftLeft", "enter"])
    right2 = GameEngine._normalize_keys(["shift", "numpadenter"])
    assert left2 == right2
    del_l = GameEngine._normalize_keys(["ctrl", "Del"])
    del_r = GameEngine._normalize_keys(["ctrl", "delete"])
    assert del_l == del_r
