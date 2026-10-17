"""Reset only the disposable SQLite database owned by the pytest invocation.

Several acceptance modules deliberately share data inside a module. A module
boundary, rather than a transaction around every test, preserves those workflows
without leaking their actors, policy revisions or workspace fixtures to peers.
This helper never resets an explicitly supplied PostgreSQL or external database.
"""

from pathlib import Path

from sqlalchemy.engine import Engine


def owned_database_path(database_path: Path, runtime_root: Path) -> Path:
    """Fail closed before any deletion if a test path escapes its runtime tree."""
    candidate = database_path.resolve()
    root = runtime_root.resolve()
    if candidate == root or not candidate.is_relative_to(root):
        raise ValueError("The pytest SQLite database must be a file inside PYPMIS_PYTEST_RUNTIME_DIR")
    if candidate.suffix.lower() not in {".sqlite", ".sqlite3", ".db"}:
        raise ValueError("The pytest SQLite database must have an explicit database-file extension")
    return candidate


def reset_owned_sqlite_database(engine: Engine, database_path: Path, runtime_root: Path) -> None:
    """Close pooled connections, then discard only verified test-owned files."""
    target = owned_database_path(database_path, runtime_root)
    if engine.dialect.name != "sqlite" or not engine.url.database or engine.url.database == ":memory:":
        raise ValueError("Only the invocation-owned file-backed SQLite engine may be reset")
    if Path(engine.url.database).resolve() != target:
        raise ValueError("Refusing to reset a database different from the application's test engine")
    candidates = [Path(f"{target}{suffix}") for suffix in ("", "-wal", "-shm", "-journal")]
    # Preflight all final targets before deleting any file, including symlinks.
    for candidate in candidates:
        if not candidate.resolve().is_relative_to(runtime_root.resolve()):
            raise ValueError("A pytest SQLite sidecar escapes its owned runtime tree")
    engine.dispose()
    for candidate in candidates:
        candidate.unlink(missing_ok=True)
