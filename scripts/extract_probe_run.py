import argparse
import json
import os
from pathlib import Path


def extract_probe_run(source: Path, target: Path, run_id: str) -> int:
    """Move one probe run out of publishable history without reformatting JSONL."""
    source = source.resolve()
    target = target.resolve()
    if not target.name.endswith("-local-probe.jsonl"):
        raise ValueError("Probe target must end with -local-probe.jsonl")
    if source == target:
        raise ValueError("Source and target must differ")

    selected: list[bytes] = []
    retained: list[bytes] = []
    for line in source.read_bytes().splitlines(keepends=True):
        if not line.strip():
            retained.append(line)
            continue
        payload = json.loads(line)
        (selected if payload.get("run_id") == run_id else retained).append(line)
    if not selected:
        raise ValueError(f"Run id not found: {run_id}")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"".join(selected))
    temporary = source.with_suffix(source.suffix + ".tmp")
    temporary.write_bytes(b"".join(retained))
    os.replace(temporary, source)
    return len(selected)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    parser.add_argument("target", type=Path)
    parser.add_argument("--source", type=Path, default=Path("data/rates.jsonl"))
    args = parser.parse_args()
    moved = extract_probe_run(args.source, args.target, args.run_id)
    print(f"Moved {moved} probe observations to {args.target}")


if __name__ == "__main__":
    main()
