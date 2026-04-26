"""
SpecMem LLM service — Gemini debugging agent with token savings.
Works with both manual bug memories and automatic debug episodes.
"""

import json

from specmem.backend.retrieval_service import (
    get_client,
    retrieve_similar_bugs,
    retrieve_similar_episodes,
    detect_failed_fix,
)
from specmem.backend.memory_service import save_token_log, list_bug_memories, list_episodes


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
    similar_episodes: list[dict],
    failed_match: dict | None,
    confidence: float,
) -> str:
    lines = [
        "You are SpecMem, a memory-powered debugging assistant.",
        "You have access to the project's past bug history and debugging episodes.",
        "",
        f"## Current Bug / Query\n{query}",
        "",
    ]

    if similar_bugs:
        lines.append("## Similar Past Bugs (from manual memory)")
        for i, bug in enumerate(similar_bugs, 1):
            lines.append(f"\n### Bug {i}: {bug.get('bug_title', 'Unknown')}")
            lines.append(f"- File: {bug.get('file_path', 'N/A')} | Module: {bug.get('module', 'N/A')}")
            lines.append(f"- Description: {bug.get('description', '')}")
            lines.append(f"- Root cause: {bug.get('root_cause', '')}")
            lines.append(f"- Final fix: {bug.get('final_fix', '')}")
            if bug.get("failed_fixes"):
                lines.append(f"- FAILED approaches: {', '.join(str(f) for f in bug['failed_fixes'])}")

    if similar_episodes:
        lines.append("\n## Similar Past Debugging Episodes (auto-captured)")
        for i, ep in enumerate(similar_episodes, 1):
            lines.append(f"\n### Episode {i}: {ep.get('error_type', 'Error')} — {ep.get('error_message', '')[:80]}")
            lines.append(f"- Command: {ep.get('command', 'N/A')}")
            lines.append(f"- Files: {', '.join(ep.get('file_paths', []))}")
            lines.append(f"- Status: {ep.get('status', 'unknown')}")
            if ep.get("failed_fixes"):
                lines.append(f"- FAILED fix attempts: {len(ep['failed_fixes'])}")
                for j, ff in enumerate(ep["failed_fixes"][:3], 1):
                    diff_preview = ff.get("diff", "")[:200]
                    lines.append(f"  Attempt {j}: {diff_preview}")
            if ep.get("successful_fix"):
                diff_preview = ep["successful_fix"].get("diff", "")[:300]
                lines.append(f"- SUCCESSFUL fix: {diff_preview}")

    if failed_match:
        pct = int(confidence * 100)
        example_ff = failed_match.get("failed_fixes", ["unknown"])[-1]
        if isinstance(example_ff, dict):
            example_ff = example_ff.get("diff", "unknown")[:100]
        lines.append(
            f"\n## WARNING — Previously Failed Fix ({pct}% similarity match)\n"
            f"This approach is {pct}% similar to a fix that already failed in "
            f"**'{failed_match.get('bug_title', 'a past bug')}'**.\n"
            f"Example of what failed: \"{example_ff}\"\n"
            "DO NOT recommend this approach."
        )

    lines += [
        "",
        "## Your Task",
        "1. Summarize what this bug likely is based on memory.",
        "2. Explicitly warn about failed approaches.",
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
    similar_bugs, bug_mode = retrieve_similar_bugs(
        project_id=project_id, query=query, module=module,
        file_path=file_path, limit=5,
    )

    similar_episodes, ep_mode = retrieve_similar_episodes(
        project_id=project_id, query=query, limit=5,
    )

    failed_match, confidence = detect_failed_fix(
        project_id=project_id, proposed_fix=query, module=module,
    )

    prompt = build_debug_prompt(query, similar_bugs, similar_episodes, failed_match, confidence)

    # Token savings: before = full project dump, after = focused prompt
    all_memories = list_bug_memories(project_id, limit=100)
    all_episodes = list_episodes(project_id, limit=100)
    raw_context = f"Project: {project_id}\nQuery: {query}\n" + "\n".join(
        " | ".join(str(v) for v in m.values()) for m in all_memories + all_episodes
    )
    token_savings = calculate_token_savings(raw_context, prompt)

    try:
        response = get_client().models.generate_content(
            model="gemini-2.5-flash", contents=prompt,
        )
        answer = response.text
    except Exception as e:
        answer = (
            f"[Gemini unavailable: {e}]\n\nTop matches from memory:\n"
            + "\n".join(
                f"- {b.get('bug_title', b.get('error_type', 'Unknown'))}: "
                f"{b.get('final_fix', b.get('error_message', 'No fix recorded'))}"
                for b in (similar_bugs + similar_episodes)[:5]
            )
        )

    try:
        save_token_log(
            project_id=project_id, query=query,
            before_tokens=token_savings["before_tokens"],
            after_tokens=token_savings["after_tokens"],
        )
    except Exception:
        pass

    failed_fix_warning_str: str | None = None
    if failed_match and confidence > 0:
        pct = int(confidence * 100)
        example_ff = failed_match.get("failed_fixes", ["unknown"])[-1]
        if isinstance(example_ff, dict):
            example_ff = example_ff.get("diff", "unknown")[:100]
        failed_fix_warning_str = (
            f"This fix is {pct}% similar to a previously failed fix in "
            f"'{failed_match.get('bug_title', 'a past bug')}'. Avoid: \"{example_ff}\""
        )

    return {
        "answer": answer,
        "similar_bugs": similar_bugs + similar_episodes,
        "failed_fix_warning": failed_fix_warning_str,
        "failed_fix_confidence": confidence if failed_match else None,
        "retrieval_mode": f"bugs:{bug_mode}, episodes:{ep_mode}",
        "token_savings": token_savings,
    }


def generate_episode_suggestion(
    project_id: str,
    error_message: str,
    stack_trace: str,
    file_paths: list[str],
) -> tuple[str, list[dict]]:
    """Generate AI debugging suggestion for an auto-captured error.
    Returns (suggestion_text, similar_items)."""

    query = f"{error_message}\n{stack_trace[:500]}"

    similar_bugs, _ = retrieve_similar_bugs(
        project_id=project_id, query=query, limit=3,
    )
    similar_episodes, _ = retrieve_similar_episodes(
        project_id=project_id, query=query, limit=3,
    )

    all_similar = similar_bugs + similar_episodes

    prompt = build_debug_prompt(
        query=f"Error: {error_message}\nFiles: {', '.join(file_paths)}\n\nStack trace:\n{stack_trace[:800]}",
        similar_bugs=similar_bugs,
        similar_episodes=similar_episodes,
        failed_match=None,
        confidence=0,
    )

    try:
        response = get_client().models.generate_content(
            model="gemini-2.5-flash", contents=prompt,
        )
        return response.text, all_similar
    except Exception as e:
        fallback = f"[Gemini unavailable: {e}]\n\nBased on memory:\n"
        for item in all_similar[:3]:
            title = item.get("bug_title", item.get("error_type", "Past issue"))
            fix = item.get("final_fix", item.get("successful_fix", "No fix recorded"))
            if isinstance(fix, dict):
                fix = fix.get("diff", "")[:100]
            fallback += f"- {title}: {fix}\n"
        return fallback, all_similar


def extract_bug_memory(project_id: str, raw_text: str) -> dict:
    """Use Gemini to extract structured bug memory fields from raw text."""
    prompt = f"""You are a bug memory extractor. Extract structured information from the text below and return ONLY a valid JSON object — no markdown, no explanation.

Text:
{raw_text}

Return this exact JSON structure:
{{
  "project_id": "{project_id}",
  "bug_title": "short descriptive title",
  "description": "what the bug is",
  "file_path": "file path if mentioned, else empty string",
  "module": "module or component if mentioned, else empty string",
  "failed_fixes": ["list of approaches that did not work"],
  "root_cause": "root cause if mentioned, else empty string",
  "final_fix": "the solution if mentioned, else empty string",
  "tags": ["relevant", "tags"]
}}"""

    response = get_client().models.generate_content(
        model="gemini-2.5-flash", contents=prompt,
    )
    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)
