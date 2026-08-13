"""register Gate 06A physical/geographic configuration contract

Revision ID: 20260812_0036
Revises: 20260812_0035
Create Date: 2026-08-12

Gate 06A deliberately reuses AdminConfiguration, AdminNumberSequence,
EnterpriseWorkspace and SecurityEvent. No parallel persistence table is needed;
this additive marker keeps the schema lineage explicit and reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "20260812_0036"
down_revision: str | None = "20260812_0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

