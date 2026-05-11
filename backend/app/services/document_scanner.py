"""Document antivirus scanning.

Two scan modes are supported:

- ``local`` (default in dev): pass-through, returns CLEAN. Useful in
  laptop/CI environments where running ClamAV is unnecessary overhead.
- ``clamav``: stream the bytes to a clamd daemon over TCP and translate
  its response to a structured ScanResult. ``clamd`` is imported
  lazily so the module loads cleanly when the dependency is absent.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from typing import Any


class ScanStatus(str, Enum):
    CLEAN = "clean"
    INFECTED = "infected"
    ERROR = "error"


@dataclass
class ScanResult:
    status: ScanStatus
    threat_name: str = ""
    detail: str = ""


@lru_cache(maxsize=4)
def _get_clamd_client(host: str = "clamav", port: int = 3310, timeout: int = 30) -> Any:
    import clamd

    return clamd.ClamdNetworkSocket(host=host, port=port, timeout=timeout)


def scan_bytes(
    data: bytes,
    scan_mode: str = "local",
    host: str = "clamav",
    port: int = 3310,
    timeout: int = 30,
) -> ScanResult:
    """Scan ``data`` and return a structured result.

    Raises ``ConnectionError`` if ``scan_mode='clamav'`` and the daemon is
    unreachable, so callers can decide whether to fail-open or fail-closed.
    """

    if scan_mode != "clamav":
        return ScanResult(status=ScanStatus.CLEAN, detail="scan-mode=local; bytes passed through")

    client = _get_clamd_client(host, port, timeout)
    result = client.instream(io.BytesIO(data))
    status_str, threat = result.get("stream", ("ERROR", None))

    if status_str == "OK":
        return ScanResult(status=ScanStatus.CLEAN)
    if status_str == "FOUND":
        return ScanResult(status=ScanStatus.INFECTED, threat_name=threat or "Unknown")
    return ScanResult(status=ScanStatus.ERROR, detail=f"clamd returned {status_str!r}")
