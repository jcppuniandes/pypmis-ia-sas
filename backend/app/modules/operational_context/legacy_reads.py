"""Compatibility response for an absent legacy control cycle, never a snapshot."""

from app.core.time import utc_now
from app.domain.schemas import KPIOut


def no_legacy_control_cycle() -> KPIOut:
    """Preserve the old mandatory numeric response shape without calculating.

    id=0 and NOT_GENERATED explicitly identify an unavailable, non-persisted
    view. Existing clients can still open ADMIN before operational onboarding.
    A genuine calculation remains an explicit authorized POST command.
    """
    return KPIOut(
        id=0,
        control_account_id=None,
        period="NOT_GENERATED",
        pv=0,
        ev=0,
        ac=0,
        spi=0,
        cpi=0,
        sv=0,
        cv=0,
        bac=0,
        eac=0,
        etc=0,
        vac=0,
        created_at=utc_now(),
    )
