import json
from pathlib import Path


SOURCE = Path("data/rates.jsonl")
TARGET = Path("public/data/rates.json")


def main() -> None:
    rows = []
    if SOURCE.exists():
        for line in SOURCE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    rows.sort(key=lambda row: row.get("queried_at", ""), reverse=True)
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(
        json.dumps({"generated_from": "data/rates.jsonl", "rates": rows}, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Published {len(rows)} observations to {TARGET}")


if __name__ == "__main__":
    main()
