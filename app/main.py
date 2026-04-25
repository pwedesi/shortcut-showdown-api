from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.game_rooms import router as game_rooms_router
from app.api.lobbies import router as lobbies_router
from app.api.players import router as players_router
from app.api.ws import router as ws_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="Shortcut Showdown API",
    description="Shortcut Showdown API",
)

# Browsers preflight with OPTIONS; without CORS, /lobbies returns 405 and POST never runs
_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(lobbies_router)
app.include_router(game_rooms_router)
app.include_router(players_router)
app.include_router(ws_router)


@app.get("/")
def read_root() -> dict[str, str]:
    return {
        "status": "success",
        "message": "Shortcut Showdown API is running.",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )
