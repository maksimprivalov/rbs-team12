from pathlib import Path

import httpx
import typer

from oblak.config import get_server_url, get_token


def _client(timeout: float = 30) -> httpx.Client:
    token = get_token()
    if not token:
        typer.echo("Not logged in. Run: oblak login", err=True)
        raise typer.Exit(1)
    return httpx.Client(
        base_url=get_server_url(),
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
    )


def _handle_error(resp: httpx.Response) -> None:
    if resp.is_error:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        typer.echo(f"Error {resp.status_code}: {detail}", err=True)
        raise typer.Exit(1)


def login(username: str, password: str, server_url: str) -> str:
    with httpx.Client(base_url=server_url, timeout=10) as client:
        resp = client.post("/auth/login", json={"username": username, "password": password})
    _handle_error(resp)
    return resp.json()["access_token"]


def me() -> dict:
    with _client() as client:
        resp = client.get("/auth/me")
    _handle_error(resp)
    return resp.json()


def deploy(code_path: Path, requirements_path: Path | None, name: str) -> dict:
    with _client() as client:
        files: dict = {"file": (code_path.name, code_path.read_bytes(), "text/x-python")}
        if requirements_path:
            files["requirements"] = ("requirements.txt", requirements_path.read_bytes(), "text/plain")
        resp = client.post("/functions/upload", params={"name": name}, files=files)
    _handle_error(resp)
    return resp.json()


def list_functions() -> list[dict]:
    with _client() as client:
        resp = client.get("/functions/")
    _handle_error(resp)
    return resp.json()


def get_function(function_id: int) -> dict:
    with _client() as client:
        resp = client.get(f"/functions/{function_id}")
    _handle_error(resp)
    return resp.json()


def get_analysis(function_id: int) -> dict:
    with _client() as client:
        resp = client.get(f"/functions/{function_id}/analysis")
    if resp.status_code == 202:
        return {"final_verdict": "PENDING", "rejection_reason": None}
    _handle_error(resp)
    return resp.json()


def invoke(function_id: int) -> dict:
    # Izvršavanje u microVM-u može da potraje (boot + kod + timeout), pa duži timeout
    with _client(timeout=120) as client:
        resp = client.post(f"/invoke/{function_id}")
    _handle_error(resp)
    return resp.json()
