"""
SpecMem CLI — developer interface for the memory system.
"""

import os
import json
import requests
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown

app = typer.Typer(help="SpecMem — Memory-Powered Debugging CLI")
console = Console()

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


def _post(path: str, data: dict) -> dict:
    r = requests.post(f"{BACKEND_URL}{path}", json=data, timeout=30)
    r.raise_for_status()
    return r.json()


def _get(path: str, params: dict | None = None) -> dict | list:
    r = requests.get(f"{BACKEND_URL}{path}", params=params or {}, timeout=10)
    r.raise_for_status()
    return r.json()


@app.command()
def remember(
    project_id: str = typer.Option(..., "--project-id", "-p", help="Project identifier"),
):
    """Interactively save a new bug memory."""
    console.print("[bold cyan]SpecMem — Save Bug Memory[/bold cyan]")
    bug_title = typer.prompt("Bug title")
    description = typer.prompt("Description")
    file_path = typer.prompt("File path")
    module = typer.prompt("Module")
    root_cause = typer.prompt("Root cause")
    final_fix = typer.prompt("Final fix")
    failed_raw = typer.prompt("Failed fixes (comma-separated)", default="")
    tags_raw = typer.prompt("Tags (comma-separated)", default="")

    payload = {
        "project_id": project_id,
        "bug_title": bug_title,
        "description": description,
        "file_path": file_path,
        "module": module,
        "root_cause": root_cause,
        "final_fix": final_fix,
        "failed_fixes": [f.strip() for f in failed_raw.split(",") if f.strip()],
        "tags": [t.strip() for t in tags_raw.split(",") if t.strip()],
    }

    try:
        result = _post("/memory", payload)
        console.print(Panel(
            f"[green]Memory saved![/green]\nID: {result.get('id', '')[:8]}...\nTitle: {result.get('bug_title')}",
            title="Success",
        ))
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def debug(
    query: str = typer.Argument(..., help="Bug description or query"),
    project_id: str = typer.Option(..., "--project-id", "-p"),
    module: str = typer.Option(None, "--module", "-m"),
    file_path: str = typer.Option(None, "--file", "-f"),
):
    """Debug a bug using SpecMem's memory."""
    console.print(f"[bold cyan]Querying memory for:[/bold cyan] {query}")
    try:
        result = _post("/debug", {
            "project_id": project_id,
            "query": query,
            "module": module,
            "file_path": file_path,
        })

        console.print(Panel(Markdown(result.get("answer", "")), title="🧠 SpecMem Answer"))

        if result.get("failed_fix_warning"):
            console.print(Panel(
                f"[yellow]{result['failed_fix_warning']}[/yellow]",
                title="⚠️  Failed Fix Warning",
            ))

        if result.get("token_savings"):
            ts = result["token_savings"]
            console.print(
                f"\n[dim]Token savings: {ts['before_tokens']} → {ts['after_tokens']} "
                f"({ts['savings_percent']}% saved)[/dim]"
            )

        if result.get("similar_bugs"):
            table = Table(title="Similar Past Bugs", show_lines=True)
            table.add_column("Title", style="bold")
            table.add_column("Module")
            table.add_column("Root Cause")
            table.add_column("Final Fix")
            for bug in result["similar_bugs"]:
                table.add_row(
                    bug.get("bug_title", ""),
                    bug.get("module", ""),
                    bug.get("root_cause", ""),
                    bug.get("final_fix", ""),
                )
            console.print(table)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def check(
    proposed_fix: str = typer.Argument(..., help="The fix you plan to apply"),
    project_id: str = typer.Option(..., "--project-id", "-p"),
    module: str = typer.Option(None, "--module", "-m"),
):
    """Check if a proposed fix has failed before."""
    try:
        result = _post("/check", {
            "project_id": project_id,
            "proposed_fix": proposed_fix,
            "module": module,
        })
        if result.get("warning"):
            console.print(Panel(
                f"[yellow]{result['warning']}[/yellow]\n\n"
                + json.dumps(result.get("matched_failed_fix", {}), indent=2, default=str),
                title="⚠️  Warning",
            ))
        else:
            console.print("[green]No matching failed fix — safe to try.[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def memories(
    project_id: str = typer.Option(..., "--project-id", "-p"),
    limit: int = typer.Option(20, "--limit", "-n"),
):
    """List recent bug memories for a project."""
    try:
        results = _get("/memory", {"project_id": project_id, "limit": limit})
        if not results:
            console.print("[dim]No memories found.[/dim]")
            return
        table = Table(title=f"Bug Memories — {project_id}", show_lines=True)
        table.add_column("Title", style="bold")
        table.add_column("Module")
        table.add_column("File")
        table.add_column("Tags")
        for mem in results:
            table.add_row(
                mem.get("bug_title", ""),
                mem.get("module", ""),
                mem.get("file_path", ""),
                ", ".join(mem.get("tags", [])),
            )
        console.print(table)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
