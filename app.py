"""
Demo app for SpecMem — intentionally buggy for demo purposes.

Bug: divides by zero when user count is 0.
"""

import json


def load_users(filepath: str) -> list[dict]:
    with open(filepath, "r") as f:
        return json.load(f)


def calculate_average_age(users: list[dict]) -> float:
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
