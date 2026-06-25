from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from oblak import api
from oblak.config import clear_token, get_server_url, save_token

app = typer.Typer(help="Oblak — serverless Python execution platform")
console = Console()


@app.command()
def login(
    server: str = typer.Option("http://localhost:8000", help="Server URL"),
) -> None:
    """Log in and save credentials locally."""
    username = typer.prompt("Username")
    password = typer.prompt("Password", hide_input=True)

    token = api.login(username, password, server)
    save_token(token, server)
    console.print(f"[green]Logged in as {username}[/green]")


@app.command()
def logout() -> None:
    """Remove saved credentials."""
    clear_token()
    console.print("Logged out.")


@app.command()
def whoami() -> None:
    """Show currently logged-in user."""
    user = api.me()
    console.print(f"[bold]{user['username']}[/bold]  (id={user['id']}, admin={user['is_admin']})")
    console.print(f"API key: {user['api_key']}")


@app.command()
def deploy(
    file: Path = typer.Argument(..., help="Python file to deploy"),
    requirements: Path | None = typer.Option(None, "--requirements", "-r", help="requirements.txt"),
    name: str | None = typer.Option(None, "--name", "-n", help="Function name (default: filename)"),
) -> None:
    """Deploy a Python function to Oblak."""
    if not file.exists():
        typer.echo(f"File not found: {file}", err=True)
        raise typer.Exit(1)
    if not file.suffix == ".py":
        typer.echo("Only .py files are supported.", err=True)
        raise typer.Exit(1)
    if requirements and not requirements.exists():
        typer.echo(f"Requirements file not found: {requirements}", err=True)
        raise typer.Exit(1)

    function_name = name or file.stem
    console.print(f"Deploying [bold]{function_name}[/bold]...")

    func = api.deploy(file, requirements, function_name)
    console.print(f"[green]Deployed![/green] id={func['id']}  status={func['status']}")


@app.command(name="list")
def list_cmd() -> None:
    """List all deployed functions."""
    functions = api.list_functions()
    if not functions:
        console.print("No functions deployed yet.")
        return

    table = Table("ID", "Name", "Status", "Invoke URL", "Created")
    for f in functions:
        table.add_row(
            str(f["id"]),
            f["name"],
            f["status"],
            f.get("invoke_url") or "—",
            f["created_at"][:19],
        )
    console.print(table)


@app.command()
def status(function_id: int = typer.Argument(..., help="Function ID")) -> None:
    """Show status of a deployed function."""
    func = api.get_function(function_id)
    console.print(f"[bold]ID:[/bold]         {func['id']}")
    console.print(f"[bold]Name:[/bold]       {func['name']}")
    console.print(f"[bold]Status:[/bold]     {func['status']}")
    console.print(f"[bold]Invoke URL:[/bold] {func.get('invoke_url') or '—'}")
    console.print(f"[bold]Created:[/bold]    {func['created_at'][:19]}")


@app.command()
def analysis(function_id: int = typer.Argument(..., help="Function ID")) -> None:
    """Show the code-analysis verdict (why a function was rejected/accepted)."""
    a = api.get_analysis(function_id)
    verdict = a.get("final_verdict")
    color = {"SAFE": "green", "REJECTED": "red", "PENDING": "yellow"}.get(verdict, "white")
    console.print(f"[bold]Verdict:[/bold] [{color}]{verdict}[/{color}]")
    if a.get("rejection_reason"):
        console.print(f"[bold]Reason:[/bold]  {a['rejection_reason']}")
    if a.get("bandit_score") is not None:
        console.print(f"[bold]Bandit HIGH nalaza:[/bold] {a['bandit_score']}")
    if a.get("llm_verdict"):
        console.print(f"[bold]LLM:[/bold]     {a['llm_verdict']}")


@app.command()
def invoke(function_id: int = typer.Argument(..., help="Function ID")) -> None:
    """Run a deployed function in a Firecracker microVM and show its output."""
    console.print(f"Invoking function [bold]{function_id}[/bold] in microVM...")
    result = api.invoke(function_id)
    console.print(
        f"[bold]exit_code:[/bold] {result['exit_code']}  "
        f"[bold]duration:[/bold] {result['duration_ms']}ms  "
        f"[bold]timed_out:[/bold] {result['timed_out']}"
    )
    if result.get("error"):
        console.print(f"[yellow]error:[/yellow] {result['error']}")
    if result.get("stdout"):
        console.print("[bold]stdout:[/bold]")
        console.print(result["stdout"], end="")
    if result.get("stderr"):
        console.print("[bold]stderr:[/bold]")
        console.print(result["stderr"], style="red", end="")
