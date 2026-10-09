import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any


class TokenError(ValueError):
    pass


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    iterations = 120_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt, expected = password_hash.split("$", 3)
        iterations = int(iterations_raw)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations)
    return hmac.compare_digest(digest.hex(), expected)


def create_access_token(
    claims: dict[str, Any],
    secret_key: str,
    expires_delta: timedelta,
) -> tuple[str, int]:
    expires_at = datetime.now(UTC) + expires_delta
    payload = {**claims, "exp": int(expires_at.timestamp())}
    header = {"alg": "HS256", "typ": "JWT"}
    encoded_header = _base64url_json(header)
    encoded_payload = _base64url_json(payload)
    signature = _sign(f"{encoded_header}.{encoded_payload}", secret_key)
    return f"{encoded_header}.{encoded_payload}.{signature}", int(expires_delta.total_seconds())


def decode_access_token(token: str, secret_key: str) -> dict[str, Any]:
    try:
        encoded_header, encoded_payload, signature = token.split(".", 2)
    except ValueError as exc:
        raise TokenError("Malformed token") from exc
    expected_signature = _sign(f"{encoded_header}.{encoded_payload}", secret_key)
    if not hmac.compare_digest(signature, expected_signature):
        raise TokenError("Invalid token signature")
    payload = _base64url_decode_json(encoded_payload)
    expires_at = int(payload.get("exp", 0))
    if expires_at <= int(datetime.now(UTC).timestamp()):
        raise TokenError("Token expired")
    return payload


def _sign(value: str, secret_key: str) -> str:
    digest = hmac.new(secret_key.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).digest()
    return _base64url_encode(digest)


def _base64url_json(value: dict[str, Any]) -> str:
    return _base64url_encode(json.dumps(value, separators=(",", ":")).encode("utf-8"))


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _base64url_decode_json(value: str) -> dict[str, Any]:
    padded = value + "=" * (-len(value) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(decoded)
    except (ValueError, json.JSONDecodeError) as exc:
        raise TokenError("Invalid token payload") from exc
    if not isinstance(payload, dict):
        raise TokenError("Invalid token claims")
    return payload
