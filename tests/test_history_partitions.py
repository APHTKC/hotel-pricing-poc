import json
from pathlib import Path

from scripts.build_static_data import MAX_HISTORY_SHARD_BYTES


def test_published_history_index_preserves_rows_and_bounds_each_response():
    data_root = Path("public/data")
    index = json.loads((data_root / "rates/index.json").read_text(encoding="utf-8"))
    expected_rows = 0
    loaded_rows = 0
    paths = []

    for month in index["months"]:
        for hotel in month["hotels"]:
            expected_rows += hotel["observations"]
            paths.extend(
                [hotel["path"]]
                if "path" in hotel
                else [partition["path"] for partition in hotel["partitions"]]
            )

    assert paths
    for relative in paths:
        path = data_root / relative
        assert path.stat().st_size <= MAX_HISTORY_SHARD_BYTES
        loaded_rows += len(json.loads(path.read_text(encoding="utf-8"))["rates"])

    assert loaded_rows == expected_rows
    assert any("partitions" in hotel for month in index["months"] for hotel in month["hotels"])
