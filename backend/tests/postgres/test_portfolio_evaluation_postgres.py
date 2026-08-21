"""Real PostgreSQL concurrency checks for Gate 07E idempotency."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from tests.test_portfolio_evaluation_gate07e import _portfolio, _project, _ratings, _workspace_context

from app.database.session import SessionLocal, engine
from app.main import app
from app.modules.portfolio_evaluation.schemas import EvaluationUpdateIn
from app.modules.portfolio_evaluation.service import PortfolioEvaluationService

pytestmark = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="PostgreSQL concurrency required")


@pytest.fixture(scope="module", autouse=True)
def _started_application():
    with TestClient(app):
        yield


def _context():
    tenant_id, actor_id, parent = _workspace_context()
    with SessionLocal() as db:
        portfolio = _portfolio(db, tenant_id, actor_id, parent, "Gate 07E PostgreSQL Concurrency")
        project, _membership = _project(db, tenant_id, actor_id, parent, portfolio)
        db.commit()
        return tenant_id, actor_id, portfolio.id, project.id


def test_concurrent_start_with_same_key_creates_one_evaluation() -> None:
    tenant_id, actor_id, portfolio_id, project_id = _context()
    barrier = Barrier(2)
    key = f"postgres-start-{uuid4()}"

    def start_once() -> int:
        with SessionLocal() as db:
            barrier.wait(timeout=15)
            return (
                PortfolioEvaluationService(db, tenant_id, actor_id).start_evaluation(portfolio_id, project_id, key).id
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        identifiers = list(executor.map(lambda _value: start_once(), range(2)))
    assert len(set(identifiers)) == 1


def test_concurrent_complete_with_same_key_is_idempotent() -> None:
    tenant_id, actor_id, portfolio_id, project_id = _context()
    with SessionLocal() as db:
        service = PortfolioEvaluationService(db, tenant_id, actor_id)
        started = service.start_evaluation(portfolio_id, project_id, f"postgres-prepare-{uuid4()}")
        updated = service.update_evaluation(
            started.id,
            started.revision_version,
            EvaluationUpdateIn(ratings=_ratings(4), comments="PostgreSQL concurrency evidence."),
        )
        evaluation_id = updated.id
        expected_version = updated.revision_version
    barrier = Barrier(2)
    key = f"postgres-complete-{uuid4()}"

    def complete_once() -> tuple[int, str]:
        with SessionLocal() as db:
            barrier.wait(timeout=15)
            result = PortfolioEvaluationService(db, tenant_id, actor_id).complete_evaluation(
                evaluation_id, expected_version, key
            )
            return result.id, result.status

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _value: complete_once(), range(2)))
    assert results == [(evaluation_id, "COMPLETED"), (evaluation_id, "COMPLETED")]
