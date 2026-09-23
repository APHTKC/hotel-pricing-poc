import json
from pathlib import Path

from services.deduplication import deduplicate_observations


SOURCE = Path("data/rates.jsonl")


def main() -> None:
    if not SOURCE.exists():
        print(f"No rate history found at {SOURCE}")
        return
    rows = [
        json.loads(line)
        for line in SOURCE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    unique = deduplicate_observations(rows, keep="latest")
    if len(unique) == len(rows):
        print(f"Rate history already unique: {len(rows)} observations")
        return
    temporary = SOURCE.with_suffix(".jsonl.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in unique:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    temporary.replace(SOURCE)
    print(f"Deduplicated rate history: {len(rows)} -> {len(unique)} observations")


if __name__ == "__main__":
    main()
