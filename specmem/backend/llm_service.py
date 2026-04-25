"""
SpecMem LLM service — Gemini debugging agent with token savings.
"""

from google import genai

from specmem.backend.config import GEMINI_API_KEY
from specmem.backend.retrieval_service import get_client, retrieve_similar_bugs, detect_failed_fix
from specmem.backend.memory_service import save_token_log


def count_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def calculate_token_savings(raw_context: str, specmem_context: str) -> dict:
    before = count_tokens(raw_context)
    after = count_tokens(specmem_context)
    savings_pct = round((1 - after / max(before, 1)) * 100, 2)
    return {
        "before_tokens": before,
        "after_tokens": after,
        "savings_percent": savings_pct,
    }


def build_debug_prompt(
    query: str,
    similar_bugs: list[dict],
    failed_warning: dict | None,
) -> str:
    lines = [
        "You are SpecMem, a memory-powered debugging assistant.",
        "You have access to the project's past bug history.",
        "",
        f"## Current Bug / Query\n{query}",
        "",
    ]

    if similar_bugs:
        lines.append("## Similar Past Bugs (from memory)")
        for i, bug in enumerate(similar_bugs, 1):
            lines.append(f"\n### Bug {i}: {bug.get('bug_title', 'Unknown')}")
            lines.append(f"- File: {bug.get('file_path', 'N/A')} | Module: {bug.get('module', 'N/A')}")
            lines.append(f"- Description: {bug.get('description', '')}")
            lines.append(f"- Root cause: {bug.get('root_cause', '')}")
            lines.append(f"- Final fix: {bug.get('final_fix', '')}")
            if bug.get("failed_fixes"):
                lines.append(f"- FAILED approaches: {', '.join(bug['failed_fixes'])}")

    if failed_warning:
        lines.append("\n## WARNING — Previously Failed Fix")
        lines.append(f"The suggested approach matches a known failed fix in: **{failed_warning.get('bug_title', 'a past bug')}**")
        lines.append(f"Failed fixes tried: {', '.join(failed_warning.get('failed_fixes', []))}")
        lines.append("DO NOT recommend these approaches.")

    lines += [
        "",
        "## Your Task",
        "1. Summarize what this bug likely is based on memory.",
        "2. Warn about any failed approaches explicitly.",
        "3. Recommend the best fix based on past experience.",
        "4. Mention which files/modules are likely involved.",
        "5. Be concise and actionable.",
    ]

    return "\n".join(lines)


def generate_debug_response(
    project_id: str,
    query: str,
    module: str | None = None,
    file_path: str | None = None,
) -> dict:
    similar_bugs = retrieve_similar_bugs(
        project_id=project_id,
        query=query,
        module=module,
        file_path=file_path,
        limit=5,
    )

    failed_warning = detect_failed_fix(
        project_id=project_id,
        proposed_fix=query,
        module=module,
    )

    prompt = build_debug_prompt(query, similar_bugs, failed_warning)

    # "before" = naive approach: dump ALL project memories unfiltered into context
    from specmem.backend.memory_service import list_bug_memories
    all_memories = list_bug_memories(project_id, limit=100)
    raw_context = f"Project: {project_id}\nQuery: {query}\n" + "\n".join(
        " | ".join(str(v) for v in m.values()) for m in all_memories
    )
    token_savings = calculate_token_savings(raw_context, prompt)

    try:
        response = get_client().models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        answer = response.text
    except Exception as e:
        answer = f"[Gemini unavailable: {e}]\n\nBased on memory, here are the most relevant past bugs:\n"
        for bug in similar_bugs:
            answer += f"\n- {bug.get('bug_title')}: {bug.get('final_fix', 'No fix recorded')}"

    try:
        save_token_log(
            project_id=project_id,
            query=query,
            before_tokens=token_savings["before_tokens"],
            after_tokens=token_savings["after_tokens"],
        )
    except Exception:
        pass

    failed_fix_warning_str = None
    if failed_warning:
        failed_fix_warning_str = (
            f"Warning: This approach was already tried and failed in '{failed_warning.get('bug_title', 'a past bug')}'. "
            f"Failed fixes: {', '.join(failed_warning.get('failed_fixes', []))}"
        )

    return {
        "answer": answer,
        "similar_bugs": similar_bugs,
        "failed_fix_warning": failed_fix_warning_str,
        "token_savings": token_savings,
    }
