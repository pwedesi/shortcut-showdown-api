"""Helpers for the Shortcut Showdown WebSocket message envelope."""

from __future__ import annotations

from typing import Any

PROTOCOL_VERSION = 1
_RESERVED_KEYS = frozenset({"v", "type", "event", "payload"})


def build_message(
    message_type: str,
    payload: dict[str, Any] | None = None,
    **legacy_fields: Any,
) -> dict[str, Any]:
    """Build a versioned protocol message with compatibility aliases."""
    body = dict(payload or {})
    message = {
        "v": PROTOCOL_VERSION,
        "type": message_type,
        "event": message_type,
        "payload": body,
    }
    for key, value in body.items():
        if key not in _RESERVED_KEYS:
            message[key] = value
    message.update(legacy_fields)
    return message


def build_error(code: str, message: str | None = None, **details: Any) -> dict[str, Any]:
    """Build a typed error message for client-visible socket failures."""
    payload: dict[str, Any] = {"code": code, "message": message or code}
    payload.update(details)
    return build_message("error", payload)


def parse_inbound_message(message: Any) -> tuple[str | None, dict[str, Any], Any | None]:
    """Normalize inbound JSON into a message type and payload dict."""
    if not isinstance(message, dict):
        return None, {}, None

    message_type = message.get("type") or message.get("event")
    raw_payload = message.get("payload")
    if isinstance(raw_payload, dict):
        payload = dict(raw_payload)
    else:
        payload = dict(message)

    if message_type is not None:
        payload.setdefault("type", message_type)
        payload.setdefault("event", message_type)

    version = message.get("v")
    if version is not None:
        payload.setdefault("v", version)

    return (str(message_type) if message_type is not None else None, payload, version)
