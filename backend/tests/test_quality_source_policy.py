"""Quality package references bind technical context, not assessment provenance."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.modules.quality.schemas import ReferenceIn
from app.modules.quality.sources import QualitySourceMixin


class PackageHarness(QualitySourceMixin):
    tenant_id = 2

    def __init__(self):
        self.package = SimpleNamespace(
            id=7,
            version=3,
            package_type="IWP",
            package_code="IWP-7",
            status="DRAFT",
            name="Inspection package",
            description="Technical scope",
            cwa_id=4,
            owner_user_id=12,
            responsible_role="supervisor",
        )
        self.db = SimpleNamespace(scalar=lambda _statement: None)

    def _get(self, _model, _workspace, _identity):
        return self.package

    @staticmethod
    def _error(status, code):
        raise HTTPException(status, detail={"code": code})


def test_public_minimal_package_reference_accepts_current_semantic_hash():
    service = PackageHarness()
    saved = service.resolve_reference(9, ReferenceIn(target_kind="IWP", target_id=7))
    minimal = ReferenceIn(target_kind="IWP", target_id=7, source_hash=saved["source_hash"])
    assert service.resolve_reference(9, minimal) == saved


def test_assessment_version_does_not_invalidate_quality_package_context():
    service = PackageHarness()
    saved = service.resolve_reference(9, ReferenceIn(target_kind="IWP", target_id=7))
    service.package.version += 1
    service.package.status = "RELEASED"
    assert service.resolve_reference(9, saved) == saved


@pytest.mark.parametrize("change", [{"name": "Different scope"}, {"status": "SUPERSEDED"}])
def test_real_package_context_change_or_supersession_fails_closed(change):
    service = PackageHarness()
    saved = service.resolve_reference(9, ReferenceIn(target_kind="IWP", target_id=7))
    for field, value in change.items():
        setattr(service.package, field, value)
    with pytest.raises(HTTPException) as error:
        service.resolve_reference(9, saved)
    assert error.value.status_code == 409
