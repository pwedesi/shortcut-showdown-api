"""Shortcut challenge engine: dataset and sequence generator.

Provides a small dataset of shortcut challenges and a helper to generate
randomized sequences for a game room. Each challenge contains a `prompt`
and an `expectedKeys` list.
"""

from __future__ import annotations

from typing import Any, Dict, List
import random

from app.services.shortcut_dataset import get_default_dataset


def generate_shortcut_sequence(count: int = 10, rng: random.Random | None = None) -> List[Dict[str, Any]]:
    """Return a randomized sequence of shortcut challenges.

    - If `count` <= number of available unique challenges, a random sample
      without replacement is returned.
    - If `count` is larger, items are chosen with replacement so a sequence
      of the requested length is always produced.
    Each returned challenge is a shallow copy of the source with an added
    `index` field indicating its position in the sequence.
    """
    rng = rng or random
    if count <= 0:
        return []
    dataset = get_default_dataset()
    if count <= len(dataset):
        seq = rng.sample(dataset, count)
    else:
        seq = [rng.choice(dataset) for _ in range(count)]

    result: List[Dict[str, Any]] = []
    for idx, item in enumerate(seq):
        entry = dict(item)
        entry["index"] = idx
        result.append(entry)
    return result

def mask_challenge_for_player(challenge: Dict[str, Any]) -> Dict[str, Any]:
    """Return the public view of a challenge (remove internal answers)."""
    return {k: v for k, v in challenge.items() if k != "expectedKeys"}


def publicize_challenges(challenges: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return a list of challenges safe to send to clients."""
    return [mask_challenge_for_player(ch) for ch in challenges]
