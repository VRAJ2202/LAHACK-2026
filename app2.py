"""
E-commerce order analytics — intentionally buggy for SpecMem demo.

Bug: crashes with ZeroDivisionError when no completed orders exist.
"""

import json


def load_orders(filepath: str) -> list[dict]:
    with open(filepath, "r") as f:
        return json.load(f)


def get_completed_orders(orders: list[dict]) -> list[dict]:
    return [o for o in orders if o.get("status") == "completed"]


def calculate_average_order_value(orders: list[dict]) -> float:
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
