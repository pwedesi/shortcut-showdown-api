from pathlib import Path

from dotenv import load_dotenv


def load_settings() -> None:
    """Load environment variables from a local `.env` if present."""
    env_path = Path(__file__).resolve().parents[2] / ".env"
    load_dotenv(env_path)
