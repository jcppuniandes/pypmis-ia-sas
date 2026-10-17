"""Safety and data isolation contracts for the shared test-only SQLite reset."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from tests.sqlite_isolation import owned_database_path, reset_owned_sqlite_database


def test_module_reset_removes_prior_rows_without_changing_engine_identity(tmp_path: Path) -> None:
    target = tmp_path / "module.sqlite"
    engine = create_engine(f"sqlite:///{target.as_posix()}")
    original_identity = id(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE module_fixture (id INTEGER PRIMARY KEY, code TEXT)"))
        connection.execute(text("INSERT INTO module_fixture VALUES (1, 'prior-module')"))
    reset_owned_sqlite_database(engine, target, tmp_path)
    assert id(engine) == original_identity
    with engine.begin() as connection:
        assert connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).all() == []
        connection.execute(text("CREATE TABLE module_fixture (id INTEGER PRIMARY KEY, code TEXT)"))
        connection.execute(text("INSERT INTO module_fixture VALUES (1, 'fresh-module')"))
        assert connection.execute(text("SELECT code FROM module_fixture")).scalar_one() == "fresh-module"
    engine.dispose()


@pytest.mark.parametrize("name", ["../external.sqlite", ".", "not-a-database.txt"])
def test_owned_path_refuses_scope_escape_or_non_database_target(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError):
        owned_database_path(tmp_path / name, tmp_path)


def test_reset_refuses_a_different_database_without_deleting_either(tmp_path: Path) -> None:
    target = tmp_path / "target.sqlite"
    other = tmp_path / "other.sqlite"
    target.touch()
    engine = create_engine(f"sqlite:///{other.as_posix()}")
    with pytest.raises(ValueError, match="different from"):
        reset_owned_sqlite_database(engine, target, tmp_path)
    assert target.exists()
    engine.dispose()


def test_reset_refuses_an_external_database_without_deletion(tmp_path: Path) -> None:
    owned_root = tmp_path / "owned"
    owned_root.mkdir()
    external = tmp_path / "external.sqlite"
    external.touch()
    engine = create_engine(f"sqlite:///{external.as_posix()}")
    with pytest.raises(ValueError, match="inside"):
        reset_owned_sqlite_database(engine, external, owned_root)
    assert external.exists()
    engine.dispose()


def test_reset_refuses_memory_database(tmp_path: Path) -> None:
    engine = create_engine("sqlite:///:memory:")
    with pytest.raises(ValueError, match="file-backed"):
        reset_owned_sqlite_database(engine, tmp_path / "owned.sqlite", tmp_path)
    engine.dispose()


def test_reset_removes_owned_sqlite_sidecars_only(tmp_path: Path) -> None:
    target = tmp_path / "owned.sqlite"
    unrelated = tmp_path / "retain.txt"
    unrelated.touch()
    for suffix in ("", "-wal", "-shm", "-journal"):
        Path(f"{target}{suffix}").touch()
    engine = create_engine(f"sqlite:///{target.as_posix()}")
    reset_owned_sqlite_database(engine, target, tmp_path)
    assert unrelated.exists()
    assert all(not Path(f"{target}{suffix}").exists() for suffix in ("", "-wal", "-shm", "-journal"))


def test_sidecar_scope_escape_is_rejected_before_deleting_the_database(tmp_path: Path) -> None:
    owned_root = tmp_path / "owned"
    owned_root.mkdir()
    target = owned_root / "owned.sqlite"
    external = tmp_path / "external.sqlite"
    target.touch()
    external.touch()
    try:
        Path(f"{target}-wal").symlink_to(external)
    except OSError:
        pytest.skip("The platform does not permit creating the temporary test symlink")
    engine = create_engine(f"sqlite:///{target.as_posix()}")
    with pytest.raises(ValueError, match="sidecar escapes"):
        reset_owned_sqlite_database(engine, target, owned_root)
    assert target.exists()
    assert external.exists()
    engine.dispose()
