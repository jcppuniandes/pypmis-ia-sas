import os
import pathlib


def pytest_ignore_collect(collection_path, config):
    """Skip files that Windows Defender has quarantined."""
    try:
        collection_path.stat()
    except OSError:
        return True
    return None
