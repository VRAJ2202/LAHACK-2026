"""
E-commerce order analytics — intentionally buggy for SpecMem demo.

Bug: divides by zero when no completed orders exist.
Same root cause as app.py but different domain — SpecMem should recognize the pattern.
"""

import json


def load_orders(filepath: str) -> list[dict]:
    with open(filepath, "r") as f:
        return json.load(f)


def get_completed_orders(orders: list[dict]) -> list[dict]:
    return [o for o in orders if o.get("status") == "completed"]


def calculate_average_order_value(orders: list[dict]) -> float:
    total = sum(o["amount"] for o in orders)
    # return total / len(orders)   # ❌ BUG LINE: ZeroDivisionError when orders list is empty (same pattern as app.py)

    # ── Fix 1 (CORRECT — SpecMem already knows this fix from app.py) ──
    # SpecMem remembers: guard clause before division worked in app.py
    # Same pattern applied here: check for empty list, return 0.0
    if not orders:
        return 0.0
    total = sum(o["amount"] for o in orders)
    return total / len(orders)


def main():
    orders = load_orders("orders.json")
    completed = get_completed_orders(orders)
    avg = calculate_average_order_value(completed)
    print(f"Completed orders: {len(completed)}")
    print(f"Average order value: ${avg:.2f}")


if __name__ == "__main__":
    main()