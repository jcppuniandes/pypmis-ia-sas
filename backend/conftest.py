import os
import pathlib
import tempfile


def pytest_configure(config):
    """Keep pytest databases and temporary files in a disposable repository path."""
    configured = os.getenv("PYPMIS_PYTEST_BASETEMP", "").strip()
    default = pathlib.Path(__file__).resolve().parent / ".pytest_tmp" / f"run-{os.getpid()}"
    session_root = pathlib.Path(configured).expanduser() if configured else default
    if not session_root.is_absolute():
        session_root = pathlib.Path.cwd() / session_root
    session_root = session_root.resolve()
    if config.option.basetemp is None:
        pytest_temp = session_root / "pytest"
        config.option.basetemp = str(pytest_temp)
    else:
        pytest_temp = pathlib.Path(config.option.basetemp).resolve()
    runtime_temp = session_root / "runtime"
    pytest_temp.mkdir(parents=True, exist_ok=True)
    runtime_temp.mkdir(parents=True, exist_ok=True)
    # Pytest removes its configured basetemp the first time tmp_path is used.
    # Keep the live SQLite database and document storage in a sibling directory
    # so Windows does not attempt to unlink an open database handle.
    os.environ["PYPMIS_PYTEST_RUNTIME_DIR"] = str(runtime_temp)
    for variable in ("TMP", "TEMP", "TMPDIR"):
        os.environ[variable] = str(runtime_temp)
    tempfile.tempdir = str(runtime_temp)


def pytest_ignore_collect(collection_path, config):
    """Skip files that Windows Defender has quarantined."""
    try:
        collection_path.stat()
    except OSError:
        return True
    return None
