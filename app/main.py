from fastapi import FastAPI

from app.api.ws import router as ws_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="Shortcut Showdown API",
    description="Shortcut Showdown API",
)

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
