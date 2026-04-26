"""
SpecMem Agent Loop — autonomous observe → think → act → evaluate cycle.

Usage (via CLI):
    specmem agent "python app.py" --project-id my-project

The agent will:
1. Run the command and capture any error
2. Query SpecMem memory for similar past bugs
3. Ask Gemini to generate a concrete code fix
4. Apply the fix automatically to the file
5. Re-run and evaluate — repeat until success or max iterations
"""

import os
import re
import subprocess
import time
from pathlib import Path

import requests
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.markdown import Markdown
from rich.syntax import Syntax

console = Console()

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
MAX_ITERATIONS = int(os.getenv("SPECMEM_MAX_ITER", "5"))


# ── Subprocess helpers ────────────────────────────────────────

def run_command(command: str) -> tuple[bool, str, str]:
    """Run a shell command. Returns (success, stdout, stderr)."""
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=120,
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out after 120s"


# ── Error parsing ─────────────────────────────────────────────

def parse_error(stderr: str) -> dict:
    """Extract structured error info from Python traceback."""
    error_type = ""
    error_message = ""
    file_paths: list[str] = []

    for line in stderr.splitlines():
        # File mentions
        file_match = re.search(r'File "([^"]+)"', line)
        if file_match:
            fp = file_match.group(1)
            if "site-packages" not in fp and "/lib/python" not in fp and not fp.startswith("<"):
                if fp not in file_paths:
                    file_paths.append(fp)

        # Error type + message
        err_match = re.match(r"^(\w*(?:Error|Exception|Warning|Exit))\s*:\s*(.+)$", line.strip())
        if err_match:
            error_type = err_match.group(1)
            error_message = err_match.group(2).strip()

    if not error_type:
        for line in reversed(stderr.splitlines()):
            if line.strip():
                error_message = line.strip()[:200]
                error_type = "RuntimeError"
                break

    return {
        "error_type": error_type or "UnknownError",
        "error_message": error_message or stderr.strip()[:200],
        "file_paths": file_paths,
        "raw": stderr.strip(),
    }


# ── SpecMem backend calls ─────────────────────────────────────

def query_memory(project_id: str, query: str, file_path: str | None = None) -> dict:
    """Ask SpecMem backend for a debug suggestion."""
    try:
        r = requests.post(
            f"{BACKEND_URL}/debug",
            json={"project_id": project_id, "query": query, "file_path": file_path},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"answer": f"[Memory unavailable: {e}]", "similar_bugs": [], "failed_fix_warning": None}


def save_episode_result(project_id: str, error_info: dict, fix_applied: str, success: bool) -> None:
    """Save outcome back to SpecMem memory so the agent learns."""
    try:
        payload = {
            "project_id": project_id,
            "bug_title": f"[Agent] {error_info['error_type']}: {error_info['error_message'][:60]}",
            "description": error_info["error_message"],
            "file_path": error_info["file_paths"][0] if error_info["file_paths"] else "unknown",
            "module": Path(error_info["file_paths"][0]).stem if error_info["file_paths"] else "unknown",
            "root_cause": error_info["error_type"],
            "final_fix": fix_applied[:500] if success else "",
            "failed_fixes": [] if success else [fix_applied[:500]],
            "tags": ["agent", error_info["error_type"].lower(), "auto-fix"],
        }
        requests.post(f"{BACKEND_URL}/memory", json=payload, timeout=10)
    except Exception:
        pass  # non-blocking — learning is best-effort


def capture_episode(project_id: str, command: str, error_info: dict) -> dict:
    """Capture the error as a debug episode via the backend."""
    try:
        r = requests.post(
            f"{BACKEND_URL}/episodes/capture",
            json={
                "project_id": project_id,
                "command": command,
                "error_message": error_info["error_message"],
                "stack_trace": error_info["raw"][:2000],
                "error_type": error_info["error_type"],
                "file_paths": error_info["file_paths"],
                "module": Path(error_info["file_paths"][0]).stem if error_info["file_paths"] else "",
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}


# ── Fix extraction + application ─────────────────────────────

def extract_code_block(text: str) -> str | None:
    """Pull the first ```python ... ``` block out of LLM response."""
    match = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    return match.group(1).strip() if match else None


def apply_fix_to_file(file_path: str, new_content: str) -> bool:
    """Overwrite file with new content. Backs up original first."""
    try:
        path = Path(file_path)
        if not path.exists():
            return False
        backup = path.with_suffix(path.suffix + ".specmem_bak")
        backup.write_text(path.read_text())
        path.write_text(new_content)
        return True
    except Exception as e:
        console.print(f"[red]Could not apply fix to {file_path}: {e}[/red]")
        return False


def restore_backup(file_path: str) -> None:
    """Restore .specmem_bak if fix made things worse."""
    try:
        path = Path(file_path)
        backup = path.with_suffix(path.suffix + ".specmem_bak")
        if backup.exists():
            path.write_text(backup.read_text())
    except Exception:
        pass


def build_fix_prompt(
    error_info: dict,
    file_path: str,
    file_content: str,
    memory_answer: str,
    attempt_history: list[str],
) -> str:
    """Build a prompt asking Gemini to return a complete fixed file."""
    history_section = ""
    if attempt_history:
        history_section = "\n## Previous Failed Attempts (DO NOT repeat these)\n"
        for i, attempt in enumerate(attempt_history[-3:], 1):
            history_section += f"\n### Attempt {i}:\n```python\n{attempt[:300]}\n```\n"

    return f"""You are an autonomous debugging agent.

## Error
Type: {error_info['error_type']}
Message: {error_info['error_message']}

## File to fix: {file_path}
```python
{file_content}
```

## SpecMem Memory Suggestion
{memory_answer}
{history_section}
## Your Task
Return the COMPLETE fixed Python file content inside a single ```python ... ``` block.
- Fix the error shown above
- Do NOT truncate — return the full file
- Do NOT add explanation outside the code block
- Apply only the minimal change needed
- Do NOT repeat any previously failed approach"""


def ask_gemini_for_fix(prompt: str) -> str | None:
    """Call Gemini directly to get a fix. Returns raw response text."""
    try:
        from google import genai
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            console.print("[red]GEMINI_API_KEY not set[/red]")
            return None
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return response.text
    except Exception as e:
        console.print(f"[dim]Gemini unavailable: {e}[/dim]")
        return None


# ── Main agent loop ───────────────────────────────────────────

def run_agent_loop(
    command: str,
    project_id: str,
    max_iterations: int = MAX_ITERATIONS,
    dry_run: bool = False,
) -> bool:
    """
    Core autonomous loop: observe → think → act → evaluate → repeat.

    Returns True if the command eventually succeeds, False otherwise.
    """
    console.print(Rule("[bold cyan]🤖 SpecMem Agent Starting[/bold cyan]"))
    console.print(f"[dim]Command:[/dim]  [bold]{command}[/bold]")
    console.print(f"[dim]Project:[/dim]  {project_id}")
    console.print(f"[dim]Max iter:[/dim] {max_iterations}")
    if dry_run:
        console.print("[yellow]DRY RUN — will suggest fixes but not apply them[/yellow]")
    console.print()

    attempt_history: list[str] = []
    error_info: dict = {}

    for step in range(1, max_iterations + 1):
        console.print(Rule(f"[yellow]Step {step} / {max_iterations}[/yellow]"))

        # ── OBSERVE ──────────────────────────────────────────
        console.print("[cyan]▶ Running command...[/cyan]")
        success, stdout, stderr = run_command(command)

        if stdout.strip():
            console.print(f"[dim]{stdout[:300]}[/dim]")

        if success:
            console.print(Panel(
                f"[bold green]✅ Command succeeded on step {step}![/bold green]\n\n"
                + (stdout.strip()[:500] if stdout.strip() else "(no output)"),
                title="🎉 Agent Success",
            ))
            # Save successful fix to memory
            if attempt_history and error_info:
                save_episode_result(project_id, error_info, attempt_history[-1], success=True)
            # Mark episode as resolved so Streamlit shows green
            try:
                import subprocess as _sp
                diff = _sp.run(
                    ["git", "diff"], capture_output=True, text=True, timeout=5,
                ).stdout.strip()
                requests.post(
                    f"{BACKEND_URL}/episodes/fix-result",
                    json={
                        "project_id": project_id,
                        "command": command,
                        "diff": diff or "(agent auto-fix)",
                        "success": True,
                        "stderr": "",
                    },
                    timeout=10,
                )
                console.print("[dim]Episode marked as resolved.[/dim]")
            except Exception:
                pass
            return True

        # ── THINK ────────────────────────────────────────────
        error_info = parse_error(stderr)

        console.print(Panel(
            f"[red]{error_info['error_type']}[/red]: {error_info['error_message']}\n"
            + (f"[dim]Files: {', '.join(error_info['file_paths'])}[/dim]" if error_info["file_paths"] else ""),
            title=f"🔍 Error (Step {step})",
        ))

        # Capture episode on first error
        if step == 1:
            ep = capture_episode(project_id, command, error_info)
            if ep.get("id"):
                console.print(f"[dim]Episode captured: {ep['id'][:12]}...[/dim]")

        # Query SpecMem memory
        target_file = error_info["file_paths"][-1] if error_info["file_paths"] else None
        query = f"{error_info['error_type']}: {error_info['error_message']}"
        console.print("[cyan]🧠 Querying SpecMem memory...[/cyan]")
        memory_result = query_memory(project_id, query, file_path=target_file)

        if memory_result.get("failed_fix_warning"):
            console.print(f"[yellow]⚠️  {memory_result['failed_fix_warning']}[/yellow]")

        if memory_result.get("similar_bugs"):
            count = len(memory_result["similar_bugs"])
            console.print(f"[dim]Found {count} similar past issues[/dim]")

        console.print(Panel(
            Markdown(memory_result.get("answer", "No suggestion available.")),
            title="🧠 Memory Suggestion",
        ))

        if dry_run:
            console.print("[dim]Dry-run mode — not applying fix.[/dim]")
            return False

        # ── ACT ──────────────────────────────────────────────
        if not target_file or not Path(target_file).exists():
            console.print(f"[yellow]Cannot auto-fix: file '{target_file}' not found locally.[/yellow]")
            console.print("[dim]Apply the fix manually and re-run.[/dim]")
            return False

        file_content = Path(target_file).read_text()
        fix_prompt = build_fix_prompt(
            error_info, target_file, file_content,
            memory_result.get("answer", ""),
            attempt_history,
        )

        console.print("[cyan]🔧 Asking Gemini to generate fix...[/cyan]")
        llm_response = ask_gemini_for_fix(fix_prompt)

        if not llm_response:
            console.print("[red]Could not get fix from Gemini. Stopping.[/red]")
            return False

        fixed_code = extract_code_block(llm_response)
        if not fixed_code:
            console.print("[yellow]Gemini didn't return a code block. Retrying...[/yellow]")
            attempt_history.append(f"(step {step}: no code block)")
            time.sleep(1)
            continue

        # Check for repeated fix
        if fixed_code in attempt_history:
            console.print("[yellow]Agent generated the same fix again — stopping to avoid loop.[/yellow]")
            break

        # Show diff preview
        if fixed_code != file_content:
            console.print(Panel(
                f"[green]Fix generated[/green] — applying to [bold]{target_file}[/bold]",
                title=f"🔧 Step {step} Fix",
            ))

        applied = apply_fix_to_file(target_file, fixed_code)
        if not applied:
            console.print("[red]Could not write fix to file.[/red]")
            return False

        attempt_history.append(fixed_code)

        # Save failed attempt to memory
        save_episode_result(project_id, error_info, fixed_code[:500], success=False)

        # ── EVALUATE (next iteration re-runs the command) ────
        console.print(f"[dim]Fix applied. Re-running...[/dim]\n")
        time.sleep(0.5)

    # ── Max iterations reached ────────────────────────────────
    console.print(Panel(
        f"[red]Agent could not fix the error in {max_iterations} attempts.[/red]\n\n"
        "All attempted fixes have been saved to SpecMem memory\n"
        "so future runs on similar errors will be smarter.",
        title="❌ Agent Stopped",
    ))

    # Restore original file
    if error_info.get("file_paths"):
        target = error_info["file_paths"][-1]
        console.print(f"[dim]Restoring original {target} from backup...[/dim]")
        restore_backup(target)

    return False
