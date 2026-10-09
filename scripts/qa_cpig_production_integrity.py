from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FOLDERS = (ROOT / "backend" / "app", ROOT / "backend" / "alembic", ROOT / "frontend" / "src")
EXPECTED = "218e73926488aa0abcffdbe5009b26f30aaac8014e813c865c516c7a21483fc2"


def main() -> None:
    paths = sorted((p for folder in FOLDERS for p in folder.rglob("*") if p.is_file()), key=lambda p: p.relative_to(ROOT).as_posix())
    sha = hashlib.sha256()
    for path in paths:
        contents = path.read_bytes()
        sha.update(path.relative_to(ROOT).as_posix().encode("utf-8") + contents)
    print(f"file_count={len(paths)}")
    value = sha.hexdigest()
    print(f"production_tree_sha256={value}")
    if value != EXPECTED:
        raise SystemExit("Production tree changed after the reproducible anchor was captured")
    print("PRODUCTION_TREE_SINCE_ANCHOR=UNCHANGED")


if __name__ == "__main__":
    main()
