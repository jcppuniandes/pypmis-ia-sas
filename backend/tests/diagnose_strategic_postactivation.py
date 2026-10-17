"""Read-only captured/live source diagnosis; never refreshes or changes UAT records."""

import hashlib
import json
import traceback
from pathlib import Path

from sqlalchemy import event, select, text

from app.database.session import SessionLocal
from app.domain.models import EnterpriseWorkspace
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.investment_decision.models import InvestmentDecision
from app.modules.investment_decision.service import InvestmentDecisionService
from app.modules.investment_gate_preparation.models import InvestmentGatePreparation
from app.modules.investment_gate_preparation.service import InvestmentGatePreparationService
from app.modules.portfolio_analysis.schemas import AnalysisFiltersIn
from app.modules.portfolio_analysis.service import PortfolioAnalysisService
from app.modules.portfolio_budget.models import PortfolioBudgetScenario
from app.modules.portfolio_budget.service import PortfolioBudgetService
from app.modules.portfolio_convergence.models import PortfolioScenarioConvergence
from app.modules.portfolio_convergence.service import PortfolioConvergenceService
from app.modules.portfolio_evaluation.models import PortfolioProjectEvaluation
from app.modules.portfolio_evaluation.service import PortfolioEvaluationService
from app.modules.portfolio_resource.models import PortfolioResourceScenario
from app.modules.portfolio_resource.service import PortfolioResourceService


def normalize(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return json.loads(json.dumps(value, default=str))


def fingerprint(value):
    return hashlib.sha256(json.dumps(normalize(value), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def differences(before, after, path="$", result=None):
    result = [] if result is None else result
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after)):
            if key not in before or key not in after:
                result.append({"path": f"{path}.{key}", "before": before.get(key), "after": after.get(key)})
            else:
                differences(before[key], after[key], f"{path}.{key}", result)
    elif before != after:
        result.append({"path": path, "before": before, "after": after})
    return result


def main():
    root = Path("/artifacts")
    chain_file = root / "fresh-capital-owner-chain.json"
    chain_hash = hashlib.sha256(chain_file.read_bytes()).hexdigest()
    chain = json.loads(chain_file.read_text())
    setup = chain["setup"]
    assert (setup["tenant_id"], setup["project_id"], setup["portfolio_id"]) == (1, 4, 3)
    target = root / "diagnosis-postactivation"
    target.mkdir(exist_ok=True)
    destination = target / "captured-live-source-diagnosis-v2.json"
    assert not destination.exists(), "Preserve the existing diagnostic attempt"
    result = {
        "scope": "READ_ONLY_NO_REFRESH_NO_COMMANDS",
        "identity": {key: setup[key] for key in ("tenant_id", "tenant_slug", "project_id", "portfolio_id")},
        "sql_mutations": [],
        "captures": {},
    }

    with SessionLocal() as db:
        db.autoflush = False
        engine = db.get_bind()
        assert engine.dialect.name == "postgresql"
        assert engine.url.database == "strategic_fresh_uat"

        def reject_write(_connection, _cursor, statement, _params, _context, _many):
            command = statement.lstrip().split(None, 1)[0].upper()
            if command not in {"SELECT", "SHOW", "SET", "COMMIT", "ROLLBACK", "SAVEPOINT", "RELEASE"}:
                result["sql_mutations"].append(statement)
                raise RuntimeError("Read-only diagnosis rejected SQL mutation")

        def reject_flush(session, _context, _instances):
            if session.new or session.dirty or session.deleted:
                raise RuntimeError("Read-only diagnosis rejected ORM flush")

        event.listen(engine, "before_cursor_execute", reject_write)
        event.listen(db, "before_flush", reject_flush)
        db.execute(text("SET TRANSACTION READ ONLY"))
        context = require_enterprise_permission(
            db, 1, setup["actor_id"], "investment_gate_preparation.read", bootstrap=False
        )
        gate = InvestmentGatePreparationService(db, 1, setup["actor_id"], context)
        convergence_service = PortfolioConvergenceService(db, 1, setup["actor_id"], context)
        preparation = db.scalar(
            select(InvestmentGatePreparation).where(
                InvestmentGatePreparation.tenant_id == 1, InvestmentGatePreparation.portfolio_workspace_id == 3
            )
        )
        convergence = db.scalar(
            select(PortfolioScenarioConvergence).where(
                PortfolioScenarioConvergence.id == preparation.source_convergence_id,
                PortfolioScenarioConvergence.tenant_id == 1,
            )
        )
        decision = db.scalar(
            select(InvestmentDecision).where(
                InvestmentDecision.tenant_id == 1, InvestmentDecision.investment_gate_preparation_id == preparation.id
            )
        )
        project = db.get(EnterpriseWorkspace, 4)
        assert project.tenant_id == 1 and project.status == "active"

        def row(record):
            return normalize({column.name: getattr(record, column.name) for column in record.__table__.columns})

        selected = {"project": project, "gate": preparation, "decision": decision, "convergence": convergence}
        before = {name: row(record) for name, record in selected.items()}
        result["persisted_before"] = before
        result["captured_gate07i_contract"] = preparation.source_snapshot_json["gate07i_contract"]
        result["captured_convergence_source"] = convergence.source_snapshot_json
        result["captured_budget_scenarios"] = [
            row(item)
            for item in db.scalars(select(PortfolioBudgetScenario).where(PortfolioBudgetScenario.tenant_id == 1))
        ]
        result["captured_resource_scenarios"] = [
            row(item)
            for item in db.scalars(select(PortfolioResourceScenario).where(PortfolioResourceScenario.tenant_id == 1))
        ]

        def capture(name, fn):
            try:
                value = normalize(fn())
                result["captures"][name] = {"success": True, "value": value}
                return value
            except Exception as error:
                result["captures"][name] = {
                    "success": False,
                    "exception": type(error).__name__,
                    "detail": normalize(getattr(error, "detail", str(error))),
                    "traceback": traceback.format_exc(),
                }
                # A rejected SELECT FOR UPDATE or other SQL error must not
                # poison subsequent independent read-only captures.
                db.rollback()
                db.execute(text("SET TRANSACTION READ ONLY"))
                return None

        capture("gate07i_live_contract", lambda: gate._gate07i_contract(3))
        capture(
            "fid_current_guard",
            lambda: InvestmentDecisionService(db, 1, setup["actor_id"], context)._assert_preparation_current(
                preparation
            ),
        )
        capture(
            "portfolio_evaluation_queue",
            lambda: [
                normalize(item)
                for item in PortfolioEvaluationService(db, 1, setup["actor_id"], context).evaluation_queue(3)
            ],
        )
        captured_evaluations = [
            row(item)
            for item in db.scalars(
                select(PortfolioProjectEvaluation).where(
                    PortfolioProjectEvaluation.tenant_id == 1, PortfolioProjectEvaluation.portfolio_workspace_id == 3
                )
            )
        ]
        result["captured_evaluations"] = captured_evaluations
        capture("convergence_readiness", lambda: convergence_service.readiness(3))
        live = capture(
            "convergence_live_source",
            lambda: convergence_service._source_snapshot(
                3,
                required_budget=convergence.required_budget_branch,
                required_resource=convergence.required_resource_branch,
                configuration_hash=convergence_service._current_configuration_hash(3),
                require_ready=False,
            ),
        )
        capture(
            "analysis_current_dataset",
            lambda: PortfolioAnalysisService(db, 1, setup["actor_id"], context)._build_dataset(3, AnalysisFiltersIn())[
                0
            ],
        )
        capture(
            "budget_recommendation_contract",
            lambda: PortfolioBudgetService(db, 1, setup["actor_id"], context).recommendation_contract(3),
        )
        capture(
            "resource_recommendation_contract",
            lambda: PortfolioResourceService(db, 1, setup["actor_id"], context).recommendation_contract(3),
        )
        if live is not None:
            result["convergence_captured_live_diff"] = differences(normalize(convergence.source_snapshot_json), live)
        db.rollback()
        db.execute(text("SET TRANSACTION READ ONLY"))
        after = {name: row(db.get(type(record), record.id)) for name, record in selected.items()}
        result["persisted_after_hashes"] = {name: fingerprint(value) for name, value in after.items()}
        result["persisted_before_hashes"] = {name: fingerprint(value) for name, value in before.items()}
        result["selected_business_rows_preserved"] = before == after
        result["pending_orm_objects_not_persisted"] = len(db.new) + len(db.dirty) + len(db.deleted)
        db.rollback()
        event.remove(db, "before_flush", reject_flush)
        event.remove(engine, "before_cursor_execute", reject_write)

    result["backend_manifest_preserved"] = hashlib.sha256(chain_file.read_bytes()).hexdigest() == chain_hash
    assert result["selected_business_rows_preserved"] and result["backend_manifest_preserved"]
    destination.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "artifact": str(destination),
                "business_preserved": result["selected_business_rows_preserved"],
                "manifest_preserved": result["backend_manifest_preserved"],
                "captures": {name: value["success"] for name, value in result["captures"].items()},
                "changed_paths": [entry["path"] for entry in result.get("convergence_captured_live_diff", [])],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
