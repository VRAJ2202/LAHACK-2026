"""
SpecMem CLI — automatic error capture + memory-powered debugging.

Usage:
    specmem run "python app.py"       # Run command, auto-capture errors
    specmem fix "python app.py"       # Re-run after editing, track fix via git diff
    specmem debug "query" -p PROJECT  # Manual debug query
    specmem check "fix" -p PROJECT    # Check if fix failed before
    specmem remember -p PROJECT       # Manually save a bug memory
    specmem memories -p PROJECT       # List stored memories
    specmem episodes -p PROJECT       # List auto-captured episodes
"""

import os
import json
import subprocess
import requests
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown
from rich.syntax import Syntax

app = typer.Typer(help="SpecMem — Memory-Powered Debugging CLI")
console = Console()

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
DEFAULT_PROJECT = os.getenv("SPECMEM_PROJECT", "")


def _post(path: str, data: dict) -> dict:
    r = requests.post(f"{BACKEND_URL}{path}", json=data, timeout=60)
    r.raise_for_status()
    return r.json()


def _get(path: str, params: dict | None = None) -> dict | list:
    r = requests.get(f"{BACKEND_URL}{path}", params=params or {}, timeout=10)
    r.raise_for_status()
    return r.json()


def _get_project_id(project_id: str | None) -> str:
    """Resolve project ID from flag, env var, or git remote."""
    if project_id:
        return project_id
    if DEFAULT_PROJECT:
        return DEFAULT_PROJECT
    # Try to infer from git
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return os.path.basename(result.stdout.strip())
    except Exception:
        pass
    return "default-project"


def _get_git_diff() -> str:
    """Get the current git diff (staged + unstaged)."""
    try:
        # Unstaged changes
        result = subprocess.run(
            ["git", "diff"],
            capture_output=True, text=True, timeout=10,
        )
        diff = result.stdout.strip()

        # Also get staged changes
        result2 = subprocess.run(
            ["git", "diff", "--cached"],
            capture_output=True, text=True, timeout=10,
        )
        staged = result2.stdout.strip()

        combined = diff
        if staged:
            combined = combined + "\n" + staged if combined else staged
        return combined
    except Exception:
        return ""


def _parse_error_locally(stderr: str, command: str) -> dict:
    """Parse error using the backend error_parser logic (imported or inline)."""
    import re
    lines = stderr.strip().splitlines()
    error_type = ""
    error_message = ""
    file_paths: list[str] = []
    module = ""

    for line in reversed(lines):
        line = line.strip()
        match = re.match(r"^(\w*(?:Error|Exception|Warning|Exit))\s*:\s*(.+)$", line)
        if match:
            error_type = match.group(1)
            error_message = match.group(2).strip()
            break
        match2 = re.match(r"^(\w*(?:Error|Exception))\s*$", line)
        if match2:
            error_type = match2.group(1)
            error_message = error_type
            break

    if not error_type:
        for line in reversed(lines):
            if line.strip():
                error_message = line.strip()
                error_type = "RuntimeError"
                break

    for line in lines:
        m = re.search(r'File "([^"]+)"', line)
        if m:
            fpath = m.group(1)
            if "site-packages" not in fpath and "/lib/python" not in fpath:
                if fpath not in file_paths:
                    file_paths.append(fpath)

    if file_paths:
        parts = file_paths[0].replace("\\", "/").split("/")
        module = parts[-2] if len(parts) >= 2 else parts[0].replace(".py", "")

    if not file_paths and command:
        m = re.search(r"[\w/\\]+\.py", command)
        if m:
            file_paths.append(m.group(0))

    return {
        "error_type": error_type,
        "error_message": error_message,
        "stack_trace": stderr.strip(),
        "file_paths": file_paths,
        "module": module,
    }


# ══════════════════════════════════════════════════════════════
# specmem run — AUTOMATIC ERROR CAPTURE
# ══════════════════════════════════════════════════════════════

@app.command()
def run(
    command: str = typer.Argument(..., help='Command to run, e.g. "python app.py"'),
    project_id: str = typer.Option(None, "--project-id", "-p", help="Project ID (auto-detected from git)"),
):
    """Run a command and automatically capture errors into SpecMem memory."""
    pid = _get_project_id(project_id)
    console.print(f"[bold cyan]SpecMem[/bold cyan] running: [dim]{command}[/dim]")
    console.print(f"[dim]Project: {pid}[/dim]\n")

    # ── Execute the command ──
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        console.print("[red]Command timed out after 120s[/red]")
        raise typer.Exit(1)

    # ── Print stdout ──
    if result.stdout.strip():
        console.print(result.stdout)

    # ── Success path ──
    if result.returncode == 0:
        console.print(Panel(
            "[green]Command succeeded — no errors detected.[/green]",
            title="✅ Success",
        ))
        return

    # ── Error path ──
    stderr = result.stderr.strip()
    if stderr:
        console.print(Syntax(stderr, "pytb", theme="monokai", line_numbers=False))

    console.print(f"\n[red]Exit code: {result.returncode}[/red]")
    console.print("[bold yellow]Error detected — capturing into SpecMem...[/bold yellow]\n")

    # ── Parse the error ──
    parsed = _parse_error_locally(stderr, command)

    console.print(f"[bold]Error type:[/bold] {parsed['error_type']}")
    console.print(f"[bold]Message:[/bold]   {parsed['error_message']}")
    console.print(f"[bold]Files:[/bold]     {', '.join(parsed['file_paths']) or 'unknown'}")
    console.print(f"[bold]Module:[/bold]    {parsed['module'] or 'unknown'}")

    # ── Store episode via API ──
    try:
        # Use extract endpoint to auto-create memory from the error
        raw_text = (
            f"Command: {command}\n"
            f"Error: {parsed['error_type']}: {parsed['error_message']}\n"
            f"Files: {', '.join(parsed['file_paths'])}\n"
            f"Stack trace:\n{parsed['stack_trace'][:1000]}"
        )

        ep_data = {
            "project_id": pid,
            "command": command,
            "error_message": parsed["error_message"],
            "stack_trace": parsed["stack_trace"],
            "error_type": parsed["error_type"],
            "file_paths": parsed["file_paths"],
            "module": parsed["module"],
        }

        # Store directly via internal endpoint
        ep_result = _post("/episodes/capture", ep_data)
        episode_id = ep_result.get("id", "")

        console.print(Panel(
            f"[green]Episode captured![/green]\n"
            f"ID: {episode_id[:12]}...\n"
            f"Status: open",
            title="📝 Stored in Memory",
        ))

        # ── Show AI suggestion ──
        if ep_result.get("ai_suggestion"):
            console.print(Panel(
                Markdown(ep_result["ai_suggestion"]),
                title="🧠 SpecMem Suggestion",
            ))

        if ep_result.get("similar_episodes"):
            console.print(f"\n[dim]Found {len(ep_result['similar_episodes'])} similar past issues[/dim]")
            for item in ep_result["similar_episodes"][:3]:
                title = item.get("bug_title", item.get("error_type", "Past issue"))
                status = item.get("status", "")
                console.print(f"  [dim]•[/dim] {title} [{status}]")

        console.print(
            f"\n[cyan]Next step:[/cyan] Fix the code, then run:\n"
            f"  [bold]specmem fix \"{command}\"[/bold]"
        )

    except requests.exceptions.ConnectionError:
        console.print("[red]Backend not running. Start it with: uvicorn specmem.backend.main:app --reload[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Failed to store episode: {e}[/red]")
        raise typer.Exit(1)


# ══════════════════════════════════════════════════════════════
# specmem fix — AUTOMATIC FIX TRACKING
# ══════════════════════════════════════════════════════════════

@app.command()
def fix(
    command: str = typer.Argument(..., help='Command to re-run, e.g. "python app.py"'),
    project_id: str = typer.Option(None, "--project-id", "-p"),
):
    """Re-run command after editing code. Tracks fix via git diff."""
    pid = _get_project_id(project_id)

    # ── Get git diff (what the developer changed) ──
    diff = _get_git_diff()
    if not diff:
        console.print("[yellow]No git changes detected. Edit your code first, then run specmem fix.[/yellow]")
        console.print("[dim]Tip: make sure you're in a git repo and have uncommitted changes.[/dim]")

    if diff:
        console.print(Panel(
            Syntax(diff[:500] + ("\n..." if len(diff) > 500 else ""), "diff"),
            title="📋 Your Changes (git diff)",
        ))

    console.print(f"[bold cyan]SpecMem[/bold cyan] re-running: [dim]{command}[/dim]\n")

    # ── Re-run the command ──
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        console.print("[red]Command timed out[/red]")
        raise typer.Exit(1)

    if result.stdout.strip():
        console.print(result.stdout)

    # ── Success: fix worked! ──
    if result.returncode == 0:
        console.print(Panel(
            "[bold green]Fix worked! Error is resolved.[/bold green]",
            title="✅ Fix Successful",
        ))

        # Store successful fix
        try:
            fix_result = _post("/episodes/fix-result", {
                "project_id": pid,
                "command": command,
                "diff": diff or "(no git diff captured)",
                "success": True,
                "stderr": "",
            })
            console.print(f"[green]Successful fix stored in memory.[/green]")
            console.print(f"[dim]Future errors like this will get better suggestions.[/dim]")
        except Exception as e:
            console.print(f"[dim]Note: couldn't store fix result: {e}[/dim]")
        return

    # ── Still failing: fix didn't work ──
    stderr = result.stderr.strip()
    if stderr:
        console.print(Syntax(stderr, "pytb", theme="monokai", line_numbers=False))

    console.print(f"\n[red]Still failing (exit code: {result.returncode})[/red]")

    # Store failed fix
    try:
        fix_result = _post("/episodes/fix-result", {
            "project_id": pid,
            "command": command,
            "diff": diff or "(no git diff captured)",
            "success": False,
            "stderr": stderr[:2000],
        })

        console.print(Panel(
            "[yellow]Failed fix recorded in memory.[/yellow]\n"
            "SpecMem will warn about this approach in the future.",
            title="❌ Fix Failed",
        ))

        if fix_result.get("ai_suggestion"):
            console.print(Panel(
                Markdown(fix_result["ai_suggestion"]),
                title="🧠 Updated Suggestion",
            ))

        console.print(
            f"\n[cyan]Try again:[/cyan] Edit code, then:\n"
            f"  [bold]specmem fix \"{command}\"[/bold]"
        )
    except Exception as e:
        console.print(f"[dim]Note: couldn't store fix result: {e}[/dim]")


# ══════════════════════════════════════════════════════════════
# Existing commands (manual)
# ══════════════════════════════════════════════════════════════

@app.command()
def debug(
    query: str = typer.Argument(..., help="Bug description or query"),
    project_id: str = typer.Option(None, "--project-id", "-p"),
    module: str = typer.Option(None, "--module", "-m"),
    file_path: str = typer.Option(None, "--file", "-f"),
):
    """Debug a bug using SpecMem's memory."""
    pid = _get_project_id(project_id)
    console.print(f"[bold cyan]Querying memory for:[/bold cyan] {query}")
    try:
        result = _post("/debug", {
            "project_id": pid, "query": query,
            "module": module, "file_path": file_path,
        })
        console.print(Panel(Markdown(result.get("answer", "")), title="🧠 SpecMem Answer"))
        if result.get("failed_fix_warning"):
            console.print(Panel(f"[yellow]{result['failed_fix_warning']}[/yellow]", title="⚠️  Warning"))
        if result.get("token_savings"):
            ts = result["token_savings"]
            console.print(f"\n[dim]Tokens: {ts['before_tokens']} → {ts['after_tokens']} ({ts['savings_percent']}% saved)[/dim]")
        if result.get("similar_bugs"):
            table = Table(title="Similar Past Issues", show_lines=True)
            table.add_column("Title", style="bold")
            table.add_column("Module")
            table.add_column("Fix / Status")
            for bug in result["similar_bugs"][:5]:
                title = bug.get("bug_title", bug.get("error_type", ""))
                mod = bug.get("module", "")
                fix = bug.get("final_fix", bug.get("status", ""))
                table.add_row(title, mod, str(fix)[:60])
            console.print(table)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def check(
    proposed_fix: str = typer.Argument(..., help="The fix you plan to apply"),
    project_id: str = typer.Option(None, "--project-id", "-p"),
    module: str = typer.Option(None, "--module", "-m"),
):
    """Check if a proposed fix has failed before."""
    pid = _get_project_id(project_id)
    try:
        result = _post("/check", {
            "project_id": pid, "proposed_fix": proposed_fix, "module": module,
        })
        if result.get("warning"):
            console.print(Panel(f"[yellow]{result['warning']}[/yellow]", title="⚠️  Warning"))
        else:
            console.print("[green]No matching failed fix — safe to try.[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def remember(
    project_id: str = typer.Option(None, "--project-id", "-p"),
):
    """Interactively save a new bug memory (manual)."""
    pid = _get_project_id(project_id)
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
        "project_id": pid, "bug_title": bug_title, "description": description,
        "file_path": file_path, "module": module, "root_cause": root_cause,
        "final_fix": final_fix,
        "failed_fixes": [f.strip() for f in failed_raw.split(",") if f.strip()],
        "tags": [t.strip() for t in tags_raw.split(",") if t.strip()],
    }
    try:
        result = _post("/memory", payload)
        console.print(Panel(f"[green]Memory saved![/green]\nID: {result.get('id', '')[:12]}...", title="Success"))
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def memories(
    project_id: str = typer.Option(None, "--project-id", "-p"),
    limit: int = typer.Option(20, "--limit", "-n"),
):
    """List recent bug memories."""
    pid = _get_project_id(project_id)
    try:
        results = _get("/memory", {"project_id": pid, "limit": limit})
        if not results:
            console.print("[dim]No memories found.[/dim]")
            return
        table = Table(title=f"Bug Memories — {pid}", show_lines=True)
        table.add_column("Title", style="bold")
        table.add_column("Module")
        table.add_column("File")
        table.add_column("Tags")
        for mem in results:
            table.add_row(
                mem.get("bug_title", ""), mem.get("module", ""),
                mem.get("file_path", ""), ", ".join(mem.get("tags", [])),
            )
        console.print(table)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@app.command()
def episodes(
    project_id: str = typer.Option(None, "--project-id", "-p"),
    limit: int = typer.Option(20, "--limit", "-n"),
):
    """List auto-captured debugging episodes."""
    pid = _get_project_id(project_id)
    try:
        results = _get("/episodes", {"project_id": pid, "limit": limit})
        if not results:
            console.print("[dim]No episodes found.[/dim]")
            return
        table = Table(title=f"Debug Episodes — {pid}", show_lines=True)
        table.add_column("Error", style="bold")
        table.add_column("Command")
        table.add_column("Status")
        table.add_column("Fixes Tried")
        for ep in results:
            error = f"{ep.get('error_type', '')}: {ep.get('error_message', '')[:40]}"
            cmd = ep.get("command", "")[:30]
            status = ep.get("status", "")
            fixes = str(len(ep.get("failed_fixes", [])))
            if ep.get("successful_fix"):
                fixes += " + ✅"
            table.add_row(error, cmd, status, fixes)
        console.print(table)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


if __name__ == "__main__":
    app()
