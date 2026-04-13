from fastapi import FastAPI

from app.core.config import load_settings

load_settings()

app = FastAPI(title="Shortcut Showdown API")


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Shortcut Showdown API"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
