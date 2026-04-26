"""
SpecMem error parser — extracts structured info from stderr output.

Parses Python tracebacks, pytest output, and generic error messages
to extract error type, message, file paths, and module info.
"""

import re


def parse_error(stderr: str, command: str = "") -> dict:
    """Parse stderr output and return structured error info.

    Returns:
        {
            "error_type": "ZeroDivisionError",
            "error_message": "division by zero",
            "stack_trace": "full traceback...",
            "file_paths": ["app.py", "utils.py"],
            "module": "app",
        }
    """
    lines = stderr.strip().splitlines()

    error_type = ""
    error_message = ""
    file_paths: list[str] = []
    module = ""

    # --- Extract error type + message from last line ---
    # Pattern: "ErrorType: message" (standard Python traceback)
    for line in reversed(lines):
        line = line.strip()
        match = re.match(r"^(\w*(?:Error|Exception|Warning|Exit))\s*:\s*(.+)$", line)
        if match:
            error_type = match.group(1)
            error_message = match.group(2).strip()
            break
        # Bare error type with no message
        match2 = re.match(r"^(\w*(?:Error|Exception))\s*$", line)
        if match2:
            error_type = match2.group(1)
            error_message = error_type
            break

    # Fallback: if no Python error found, take last non-empty line
    if not error_type:
        for line in reversed(lines):
            if line.strip():
                error_message = line.strip()
                error_type = "RuntimeError"
                break

    # --- Extract file paths from traceback ---
    # Pattern: File "path/to/file.py", line N
    for line in lines:
        match = re.search(r'File "([^"]+)"', line)
        if match:
            fpath = match.group(1)
            # Skip stdlib / site-packages
            if "site-packages" not in fpath and "/lib/python" not in fpath:
                if fpath not in file_paths:
                    file_paths.append(fpath)

    # --- Extract module from first user file ---
    if file_paths:
        # Use the first user file as the module
        first_file = file_paths[0]
        # "src/auth/token.py" → "auth"
        parts = first_file.replace("\\", "/").split("/")
        if len(parts) >= 2:
            module = parts[-2]
        else:
            module = parts[0].replace(".py", "")

    # --- Fallback file path from command ---
    if not file_paths and command:
        match = re.search(r"[\w/\\]+\.py", command)
        if match:
            file_paths.append(match.group(0))

    return {
        "error_type": error_type,
        "error_message": error_message,
        "stack_trace": stderr.strip(),
        "file_paths": file_paths,
        "module": module,
    }


def build_error_signature(error_type: str, error_message: str, file_paths: list[str]) -> str:
    """Build a short signature for deduplication / quick display."""
    files_str = ", ".join(file_paths[:2]) if file_paths else "unknown"
    return f"{error_type}: {error_message[:80]} @ {files_str}"
