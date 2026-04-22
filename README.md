# Shortcut Showdown API

Backend service for **Shortcut Showdown**, built with [FastAPI](https://fastapi.tiangolo.com/). It exposes a simple health check and a WebSocket endpoint for real-time messaging during gameplay.

## Features

- **REST** — `GET /` returns a JSON status payload confirming the API is up.
- **Authoritative game sessions** — `GET /game-rooms/{room_id}` returns server-owned round state (`running`/`finished`), synchronized timer fields, per-player telemetry, and end-of-round resolution.
- **Authoritative player actions** — `POST /game-rooms/{room_id}/attempts` validates attempts server-side and updates room state deterministically.
- **Authoritative player identity** — `PATCH /players/{player_id}` stores a server-known callsign for an active WebSocket player, and lobby responses return resolved player identities instead of bare ids.
- **WebSockets** — `WS /ws` accepts connections, assigns a `player_id`, and echoes text messages with structured JSON events (`connect`, `message`).

Gameplay determinism notes:
- Challenge RNG is server-side and seeded by room id, so all players in a room receive the same objective sequence.
- Timeout/forfeit tie-breaking order is deterministic: highest objective index, then highest accuracy, then highest WPM, then lexicographically smallest player id.
- Bots/AI players are not implemented.

## Player Identity

Every connected client receives a stable `player_id` from `WS /ws`. After connecting, clients should set a display name with:

```http
PATCH /players/{player_id}
{
  "display_name": "OPERATOR_01"
}
```

Rules for `display_name`:
- Maximum length: 24 characters
- Allowed characters: letters, numbers, spaces, `_`, and `-`
- Leading and trailing whitespace is trimmed before validation and storage
- Duplicate display names are allowed
- Display names can be updated while a player is in a lobby

Validation errors use machine-readable `detail` values:
- `display_name_empty`
- `display_name_too_long`
- `display_name_invalid_characters`
- `player_not_found`

Lobby payloads return resolved player entries in join order:

```json
{
  "id": "lobby-id",
  "players": [
    {"player_id": "player-a", "display_name": "OPERATOR_01"},
    {"player_id": "player-b", "display_name": "MAVERICK"}
  ],
  "status": "waiting"
}
```

If a player has not set a display name yet, the API falls back to their `player_id` in lobby responses.

Configuration (host, port, environment) is driven by environment variables and an optional `.env` file. See `.env.example` for supported keys.

## Requirements

- Python 3.11+ (recommended; match your deployment target)
- Dependencies listed in `requirements.txt`

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # adjust HOST, PORT, ENVIRONMENT as needed
```

## Run locally

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Or:

```bash
python -m app.main
```

Interactive docs: `http://127.0.0.1:8000/docs` (when the server is running).

## Tests

```bash
pytest -q -o "addopts= "
```

## 👥 Team

<div align="center">

<table>
<tr>
<td align="center" width="50%" valign="top">
  <img src="https://github.com/hdmGOAT.png" width="88" height="88" alt="Hans Matthew Del Mundo" /><br />
  <strong>Hans Matthew Del Mundo</strong><br />
  <a href="https://github.com/hdmGOAT"><kbd>@hdmGOAT</kbd></a>
</td>
<td align="center" width="50%" valign="top">
  <img src="https://github.com/potakaaa.png" width="88" height="88" alt="Gerald Helbiro Jr." /><br />
  <strong>Gerald Helbiro Jr.</strong><br />
  <a href="https://github.com/potakaaa"><kbd>@potakaaa</kbd></a>
</td>
</tr>
<tr>
<td align="center" width="50%" valign="top">
  <img src="https://github.com/areeesss.png" width="88" height="88" alt="Vin Marcus Gerebise" /><br />
  <strong>Vin Marcus Gerebise</strong><br />
  <a href="https://github.com/areeesss"><kbd>@areeesss</kbd></a>
</td>
<td align="center" width="50%" valign="top">
  <img src="https://github.com/unripelo.png" width="88" height="88" alt="Ira Chloie Narisma" /><br />
  <strong>Ira Chloie Narisma</strong><br />
  <a href="https://github.com/unripelo"><kbd>@unripelo</kbd></a>
</td>
</tr>
</table>

</div>
