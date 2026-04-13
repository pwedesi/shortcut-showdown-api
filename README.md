# Shortcut Showdown API

Backend service for **Shortcut Showdown**, built with [FastAPI](https://fastapi.tiangolo.com/). It exposes a simple health check and a WebSocket endpoint for real-time messaging during gameplay.

## Features

- **REST** — `GET /` returns a JSON status payload confirming the API is up.
- **WebSockets** — `WS /ws` accepts connections, assigns a `player_id`, and echoes text messages with structured JSON events (`connect`, `message`).

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
