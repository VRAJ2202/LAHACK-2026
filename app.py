"""
Demo app for SpecMem — intentionally buggy for demo purposes.

Bug: divides by zero when active user count is 0.
"""

import json


def load_users(filepath: str) -> list[dict]:
    with open(filepath, "r") as f:
        return json.load(f)


def calculate_average_age(users: list[dict]) -> float:
    total = sum(u["age"] for u in users)
    # return total / len(users)   # ❌ BUG LINE: ZeroDivisionError when users list is empty

    # ── Fix 1 (WRONG — still crashes) ──────────────────────
    # Attempted: convert len() to int, thinking it was a type issue
    # Result: still crashes — int(0) is still 0, division by zero remains
    # return total / int(len(users))

    # ── Fix 2 (WRONG — hides error, breaks downstream) ────
    # Attempted: wrap in try/except to catch the error
    # Result: returns None silently, causes TypeError downstream when formatting
    # try:
    #     return total / len(users)
    # except ZeroDivisionError:
    #     return None

    # ── Fix 3 (CORRECT — handles empty list properly) ──────
    # Attempted: add guard clause before division
    # Result: returns 0.0 for empty list, no crash, correct behavior
    if not users:
        return 0.0
    total = sum(u["age"] for u in users)
    return total / len(users)


def get_active_users(users: list[dict]) -> list[dict]:
    return [u for u in users if u.get("active")]


def main():
    users = load_users("users.json")
    active = get_active_users(users)
    avg_age = calculate_average_age(active)
    print(f"Active users: {len(active)}")
    print(f"Average age: {avg_age:.1f}")


if __name__ == "__main__":
    main()