import json
from pathlib import Path

from services.deduplication import deduplicate_observations
from storage.local_jsonl import jsonl_partition_paths


SOURCE = Path("data/rates")


def deduplicate_file(path: Path) -> tuple[int, int]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    unique = deduplicate_observations(rows, keep="latest")
    if len(unique) == len(rows):
        return len(rows), len(unique)
    temporary = path.with_suffix(".jsonl.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in unique:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    temporary.replace(path)
    return len(rows), len(unique)


def main() -> None:
    shards = jsonl_partition_paths(SOURCE)
    if not shards:
        print(f"No rate history found at {SOURCE}")
        return
    before = after = 0
    for shard in shards:
        shard_before, shard_after = deduplicate_file(shard)
        before += shard_before
        after += shard_after
    print(f"Deduplicated {len(shards)} rate shards: {before} -> {after} observations")


if __name__ == "__main__":
    main()
