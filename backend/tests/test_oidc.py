import time

import pytest

from app.core.oidc import OIDCValidationError, OIDCValidator


MOCK_ISSUER = "https://accounts.example.com"
MOCK_CLIENT_ID = "pypmis-client"


def _claims(**overrides) -> dict:
    base = {
        "iss": MOCK_ISSUER,
        "aud": MOCK_CLIENT_ID,
        "exp": time.time() + 300,
        "sub": "user-123",
    }
    base.update(overrides)
    return base


def test_validate_claims_accepts_well_formed_token() -> None:
    OIDCValidator(MOCK_ISSUER, MOCK_CLIENT_ID).validate_claims(_claims())


def test_validate_claims_rejects_wrong_issuer() -> None:
    validator = OIDCValidator(MOCK_ISSUER, MOCK_CLIENT_ID)
    with pytest.raises(OIDCValidationError, match="issuer"):
        validator.validate_claims(_claims(iss="https://evil.example.com"))


def test_validate_claims_rejects_wrong_audience_string() -> None:
    validator = OIDCValidator(MOCK_ISSUER, MOCK_CLIENT_ID)
    with pytest.raises(OIDCValidationError, match="audience"):
        validator.validate_claims(_claims(aud="some-other-client"))


def test_validate_claims_accepts_audience_list_with_client_id() -> None:
    OIDCValidator(MOCK_ISSUER, MOCK_CLIENT_ID).validate_claims(
        _claims(aud=["other-client", MOCK_CLIENT_ID])
    )


def test_validate_claims_rejects_audience_list_without_client_id() -> None:
    validator = OIDCValidator(MOCK_ISSUER, MOCK_CLIENT_ID)
    with pytest.raises(OIDCValidationError, match="audience"):
        validator.validate_claims(_claims(aud=["one", "two"]))


def test_validate_claims_rejects_expired_token() -> None:
    validator = OIDCValidator(MOCK_ISSUER, MOCK_CLIENT_ID)
    with pytest.raises(OIDCValidationError, match="expired"):
        validator.validate_claims(_claims(exp=time.time() - 1))


def test_validate_claims_rejects_malformed_exp() -> None:
    validator = OIDCValidator(MOCK_ISSUER, MOCK_CLIENT_ID)
    with pytest.raises(OIDCValidationError, match="exp"):
        validator.validate_claims(_claims(exp="not-a-number"))
