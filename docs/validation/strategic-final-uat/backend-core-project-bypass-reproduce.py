"""Demonstrate open CORE-revision Project authority defect in a fresh memory DB.

No runtime database is read or written. A successful reproducer proves a defect,
not business UAT acceptance. It deliberately does not modify product CORE logic.
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SEED_DEMO_DATA"] = "false"
os.environ["AUTO_CREATE_SCHEMA"] = "false"
sys.path.insert(0, str(ROOT / "backend"))
from app.main import app as _app  # noqa: E402,F401 -- registers model metadata only; no lifespan
from sqlalchemy import func, select  # noqa: E402
from app.domain.models import EnterpriseWorkspace  # noqa: E402
from app.modules.project_creation.models import ProjectCreationRequest  # noqa: E402
from app.modules.project_workspace_initialization.models import ProjectWorkspaceInitialization  # noqa: E402
from app.modules.enterprise_structure.schemas import (  # noqa: E402
    RevisionWorkspaceCreate, RevisionClassificationIn, RevisionApprovalRequest, RevisionPublishRequest,
)

spec = importlib.util.spec_from_file_location("isolated_revision_fixture", ROOT / "backend/tests/test_enterprise_structure_revisions.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
db, editor, published = fixture._seed()
try:
    draft = editor.create_revision(published.id)
    draft = editor.add_workspace(
        draft.id,
        RevisionWorkspaceCreate(
            name="Isolated Final UAT Project Authority Reproducer", workspace_type_code="project", parent_key="PF-ONE", status="active",
            applicable_classifications=[RevisionClassificationIn(category_set_code="strategic-objective", category_item_code="growth")],
        ),
        expected_version=draft.revision_version,
    )
    candidate = next(w for w in draft.workspaces if w.name.startswith("Isolated Final UAT"))
    validation = editor.validate_revision(draft.id)
    assert validation.valid, validation.errors
    approver = fixture._service_as(db, editor, "uat-core-approver@isolated.invalid")
    approver.approve_revision(draft.id, RevisionApprovalRequest(draft_hash=validation.draft_hash, diff_hash=validation.diff_hash))
    publisher = fixture._service_as(db, editor, "uat-core-publisher@isolated.invalid")
    successor = publisher.publish_revision(draft.id, RevisionPublishRequest(draft_hash=validation.draft_hash, diff_hash=validation.diff_hash))
    row = db.scalar(select(EnterpriseWorkspace).where(EnterpriseWorkspace.external_key == candidate.workspace_key))
    requests = db.scalar(select(func.count()).select_from(ProjectCreationRequest))
    initializations = db.scalar(select(func.count()).select_from(ProjectWorkspaceInitialization))
    result = {
        "defect_id": "BACKEND-S2-CORE-REVISION-PROJECT-AUTHORITY", "severity": "S2 CRITICAL", "status": "OPEN_REPRODUCED",
        "evidence_kind": "ISOLATED_SQLITE_IN_MEMORY_SERVICE_PATH", "operational_database_access": False,
        "actual": {"published_release_state": successor.state, "workspace_type_code": row.workspace_type_code, "workspace_status": row.status,
                   "project_creation_requests": requests, "project_workspace_initializations": initializations},
        "expected": "ADMIN CORE revisions preserve/adopt historical PROJECT identities; new live Projects must follow USER Project Creation, Initialization and Activation.",
        "reproduced": row.workspace_type_code == "project" and row.status == "active" and requests == 0 and initializations == 0,
        "scope_limit": "Service path after normal CORE validation, independent approver and publisher. HTTP RBAC not exercised; no claim of unauthorized anonymous access.",
        "source": ["backend/app/modules/enterprise_structure/revisions.py:add_workspace", "backend/app/modules/enterprise_structure/revisions.py:_materialize_snapshot"],
    }
    assert result["reproduced"]
    (Path(__file__).parent / "backend-core-project-bypass-evidence.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
finally:
    db.close()
