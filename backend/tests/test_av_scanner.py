from unittest.mock import MagicMock, patch

import pytest

from app.services.document_scanner import ScanResult, ScanStatus, scan_bytes

CLEAN_BYTES = b"This is a perfectly clean file."
FAKE_MALWARE_MARKER = b"<<simulated-malicious-payload-marker>>"


def test_local_mode_always_returns_clean() -> None:
    result = scan_bytes(CLEAN_BYTES, scan_mode="local")
    assert isinstance(result, ScanResult)
    assert result.status is ScanStatus.CLEAN


def test_clamav_mode_clean_response() -> None:
    with patch("app.services.document_scanner._get_clamd_client") as factory:
        client = MagicMock()
        client.instream.return_value = {"stream": ("OK", None)}
        factory.return_value = client

        result = scan_bytes(CLEAN_BYTES, scan_mode="clamav")

    assert result.status is ScanStatus.CLEAN


def test_clamav_mode_found_response_marks_infected() -> None:
    with patch("app.services.document_scanner._get_clamd_client") as factory:
        client = MagicMock()
        client.instream.return_value = {"stream": ("FOUND", "Sim-Test-Signature")}
        factory.return_value = client

        result = scan_bytes(FAKE_MALWARE_MARKER, scan_mode="clamav")

    assert result.status is ScanStatus.INFECTED
    assert "Sim-Test" in result.threat_name


def test_clamav_mode_unknown_status_marks_error() -> None:
    with patch("app.services.document_scanner._get_clamd_client") as factory:
        client = MagicMock()
        client.instream.return_value = {"stream": ("STRANGE", None)}
        factory.return_value = client

        result = scan_bytes(CLEAN_BYTES, scan_mode="clamav")

    assert result.status is ScanStatus.ERROR
    assert "STRANGE" in result.detail


def test_clamav_unreachable_raises_connection_error() -> None:
    with patch("app.services.document_scanner._get_clamd_client") as factory:
        factory.side_effect = ConnectionError("clamd unavailable")

        with pytest.raises(ConnectionError, match="clamd unavailable"):
            scan_bytes(CLEAN_BYTES, scan_mode="clamav")
