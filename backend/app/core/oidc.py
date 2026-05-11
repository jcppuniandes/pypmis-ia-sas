"""OIDC token validation.

Two-layer surface so unit tests can exercise the rules engine without a
live identity provider:

- ``OIDCValidator.validate_claims`` runs the pure-Python issuer / audience
  / expiry checks on a decoded claims dict. Tests cover this directly.
- ``OIDCValidator.decode_and_validate`` performs the JWKS fetch, JWT
  signature verification (via authlib), then delegates to
  ``validate_claims``. authlib is imported lazily so the module itself
  loads cleanly even on hosts where authlib is not yet installed.
"""

from __future__ import annotations

import time
from functools import lru_cache
from typing import Any


class OIDCValidationError(Exception):
    """Raised when an OIDC id_token fails any validation check."""


class OIDCValidator:
    def __init__(self, issuer: str, client_id: str, jwks_timeout: int = 5) -> None:
        self.issuer = issuer
        self.client_id = client_id
        self.jwks_timeout = jwks_timeout

    def validate_claims(self, claims: dict[str, Any]) -> None:
        if claims.get("iss") != self.issuer:
            raise OIDCValidationError(f"Invalid issuer: expected {self.issuer}, got {claims.get('iss')!r}")

        audience = claims.get("aud", "")
        if isinstance(audience, list):
            if self.client_id not in audience:
                raise OIDCValidationError("Invalid audience: client_id not present in 'aud' list")
        elif audience != self.client_id:
            raise OIDCValidationError(f"Invalid audience: expected {self.client_id}, got {audience!r}")

        exp = claims.get("exp", 0)
        try:
            exp_value = float(exp)
        except (TypeError, ValueError) as err:
            raise OIDCValidationError("Token has malformed 'exp' claim") from err
        if exp_value < time.time():
            raise OIDCValidationError("Token expired")

    def fetch_jwks(self) -> dict[str, Any]:
        import httpx

        jwks_url = f"{self.issuer.rstrip('/')}/.well-known/jwks.json"
        response = httpx.get(jwks_url, timeout=self.jwks_timeout)
        response.raise_for_status()
        return response.json()

    def decode_and_validate(self, token: str) -> dict[str, Any]:
        try:
            from authlib.jose import JsonWebKey, jwt
            from authlib.jose.errors import JoseError
        except ImportError as exc:
            raise OIDCValidationError("authlib is not installed; cannot verify OIDC tokens") from exc

        jwks = self.fetch_jwks()
        key_set = JsonWebKey.import_key_set(jwks)
        try:
            claims = jwt.decode(token, key_set)
        except JoseError as exc:
            raise OIDCValidationError(f"JWT decode failed: {exc}") from exc
        self.validate_claims(dict(claims))
        return dict(claims)


@lru_cache(maxsize=4)
def get_oidc_validator(issuer: str, client_id: str) -> OIDCValidator:
    return OIDCValidator(issuer=issuer, client_id=client_id)
