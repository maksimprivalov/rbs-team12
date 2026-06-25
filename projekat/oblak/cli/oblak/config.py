import json
from pathlib import Path

# CONFIG_DIR = Path.home() / ".oblak"
CONFIG_DIR = Path(__file__).parent.parent / "config"
CONFIG_FILE = CONFIG_DIR / "config.json"


def save_token(token: str, server_url: str) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps({"token": token, "server_url": server_url}))
    CONFIG_FILE.chmod(0o600)


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    return json.loads(CONFIG_FILE.read_text())


def get_token() -> str | None:
    return load_config().get("token")


def get_server_url() -> str:
    return load_config().get("server_url", "http://localhost:8000")


def clear_token() -> None:
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()
