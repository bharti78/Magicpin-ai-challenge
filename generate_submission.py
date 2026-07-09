from __future__ import annotations

import json
from pathlib import Path

from composer import compose

ROOT = Path(__file__).parent
EXPANDED = ROOT / "expanded"
OUT = ROOT / "submission.jsonl"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def find_merchant(merchant_id: str) -> dict:
    matches = list((EXPANDED / "merchants").glob(f"{merchant_id}*.json"))
    if not matches:
        raise FileNotFoundError(f"Merchant not found: {merchant_id}")
    return load_json(matches[0])


def find_customer(customer_id: str) -> dict:
    matches = list((EXPANDED / "customers").glob(f"{customer_id}*.json"))
    if not matches:
        raise FileNotFoundError(f"Customer not found: {customer_id}")
    return load_json(matches[0])


def find_trigger(trigger_id: str) -> dict:
    matches = list((EXPANDED / "triggers").glob(f"{trigger_id}*.json"))
    if not matches:
        raise FileNotFoundError(f"Trigger not found: {trigger_id}")
    return load_json(matches[0])


def main() -> None:
    pairs = load_json(EXPANDED / "test_pairs.json")["pairs"]
    lines = []

    for pair in pairs:
        test_id = pair["test_id"]
        merchant = find_merchant(pair["merchant_id"])
        trigger = find_trigger(pair["trigger_id"])
        category = load_json(EXPANDED / "categories" / f"{merchant['category_slug']}.json")
        customer = find_customer(pair["customer_id"]) if pair.get("customer_id") else None

        result = compose(category, merchant, trigger, customer)
        row = {
            "test_id": test_id,
            "body": result["body"],
            "cta": result["cta"],
            "send_as": result["send_as"],
            "suppression_key": result["suppression_key"],
            "rationale": result["rationale"],
        }
        lines.append(row)
        print(f"{test_id}: {result['body'][:70]}...".encode("ascii", "replace").decode())

    with OUT.open("w", encoding="utf-8") as f:
        for row in lines:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"\nWrote {len(lines)} lines to {OUT}")


if __name__ == "__main__":
    main()
