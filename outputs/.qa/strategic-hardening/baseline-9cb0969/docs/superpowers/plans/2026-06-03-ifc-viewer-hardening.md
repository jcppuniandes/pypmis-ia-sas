# Robust IFC Viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the BIM module from a basic IFC geometry renderer into a production-grade IFC coordination viewer connected to quantity takeoff, WBS, CBS, FBS and AWP traceability.

**Architecture:** Split BIM into two explicit data lanes: `BIM Model Coordination` for IFC source/geometry, and `Quantity Takeoff` for controlled quantity lines. Store IFC source files independently from synchronous quantity extraction, add a BIM model registry, and let the frontend load cached viewer artifacts when available, falling back to source IFC geometry.

**Tech Stack:** Existing React/Vite/Three.js/web-ifc frontend, FastAPI/SQLAlchemy backend, Docker Compose, Vitest, backend pytest, Playwright/Chrome verification. Engine decision starts with current `web-ifc` + Three.js, with a formal spike for That Open Components/Fragments and xeokit before adding a larger dependency.

---

## Market Decision

Current app state:
- `frontend/src/components/BimIfcModelViewer.tsx` already renders real IFC geometry with `web-ifc` and Three.js.
- IFC upload is still tied to `QuantityTakeoffService.import_file()`.
- Large or complex IFCs can fail quantity extraction before becoming a durable coordination model.
- The viewer does not yet expose model tree, element properties, element selection, class/storey filters, isolate/hide, clipping or cached geometry.

Recommended market alignment:
- Keep the current `web-ifc` path as the safe baseline because the repo already uses it.
- Run a short engine spike before adopting a new viewer stack:
  - That Open Components/Fragments: best fit if we want cached fragment models and a modern IFC/Three ecosystem.
  - xeokit: strong BIM viewer performance, but check license/commercial fit before embedding in a proprietary SaaS.
  - Plain web-ifc + Three.js: lowest dependency risk, but more engineering work for tree, properties, filters and performance.

Decision rule:
- If That Open Components can load the pilot IFC, expose properties/tree, and cache a fragment/binary artifact without license friction, adopt it as the production viewer engine.
- If not, continue hardening the existing `web-ifc` viewer and add only the missing UX and backend registry features.

Useful references:
- That Open docs: https://docs.thatopen.com/
- web-ifc repository: https://github.com/ThatOpen/engine_web-ifc
- xeokit SDK: https://xeokit.github.io/xeokit-sdk/

---

## File Structure

Create:
- `backend/alembic/versions/20260603_0020_bim_model_registry.py`  
  Migration for persisted BIM coordination models.
- `backend/app/services/bim_models.py`  
  Backend service for IFC source storage, model metadata, fragment artifact storage and deletion.
- `backend/tests/test_bim_model_registry.py`  
  Backend tests for upload/list/download/delete and multi-tenant isolation.
- `frontend/src/api/bimModels.ts`  
  Frontend API client for model registry endpoints.
- `frontend/src/components/bim/BimModelViewer.tsx`  
  Main viewer shell that owns model lifecycle and rendering state.
- `frontend/src/components/bim/BimModelToolbar.tsx`  
  Fit/top/iso/section/isolate/reset controls.
- `frontend/src/components/bim/BimModelTree.tsx`  
  Tree by Project > Site > Building > Storey > IFC class.
- `frontend/src/components/bim/BimElementProperties.tsx`  
  Selected element details and quantity/WBS/CBS/FBS trace.
- `frontend/src/components/bim/useIfcGeometry.ts`  
  Existing `web-ifc` geometry loading refactored into a reusable hook.
- `frontend/src/components/bim/useIfcSelection.ts`  
  Raycast selection, highlight and selected element state.
- `frontend/tests/BimModelViewer.test.tsx`  
  Unit/integration tests for viewer shell, states and model metadata.
- `frontend/tests/bim-model-registry.test.tsx`  
  API/UI tests for upload, clear model and reload behavior.
- `frontend/e2e/bim-viewer.spec.ts`  
  Browser E2E for nonblank canvas, persisted model and model controls.
- `docs/29-ifc-viewer-engine-decision.md`  
  Formal decision record: current web-ifc vs That Open vs xeokit.

Modify:
- `backend/app/domain/models.py`  
  Add `BimModel` SQLAlchemy model.
- `backend/app/domain/schemas.py`  
  Add `BimModelOut`, `BimModelCreateOut`, `BimModelArtifactOut`.
- `backend/app/api/v1/routers/projects.py`  
  Add BIM model endpoints under project membership security.
- `backend/app/api/v1/router.py` if shared router exports require registration.
- `frontend/src/App.tsx`  
  Replace direct `BimIfcModelViewer` wiring with `BimModelViewer`, and keep one quantity table below it.
- `frontend/src/types/index.ts`  
  Add `BimModel` and viewer metadata types.
- `frontend/src/styles.css`  
  Full-width viewer layout, tree/properties panel, selected element styling and responsive behavior.
- `frontend/package.json`  
  Add viewer dependency only after Task 2 engine decision. Do not add a new BIM library before the decision record is completed.

---

## Acceptance Criteria

- IFC model upload for coordination is independent from quantity extraction.
- A large IFC can be registered and viewed even when quantity takeoff is pending or fails.
- The viewer shows real IFC geometry, not symbolic quantity blocks.
- The viewer remains available after reload because the IFC source/artifact is stored.
- The BIM module has one main viewer and one controlled quantity table.
- The viewer exposes model identity: file name, size, schema, units, project/site/building/storey count, element count.
- Clicking an element shows: GlobalId, IFC class, constructive label, type/family/name, storey, system/zone/assembly when available.
- Selecting an element highlights it and links to matching quantity lines by `element_guid` or `element_id`.
- Tree/filter controls can isolate by storey and IFC class.
- Browser E2E verifies the canvas is nonblank on desktop and mobile widths.
- Tests and build pass.

---

### Task 1: Engine Decision Spike

**Files:**
- Create: `docs/29-ifc-viewer-engine-decision.md`
- Modify: none
- Test: manual/browser spike notes in the decision doc

- [ ] **Step 1: Record current viewer baseline**

Create `docs/29-ifc-viewer-engine-decision.md` with:

```markdown
# IFC Viewer Engine Decision

## Current Baseline

The current app uses `web-ifc` plus `three` in `frontend/src/components/BimIfcModelViewer.tsx`.

Observed strengths:
- No new viewer dependency.
- Real IFC mesh rendering works for stored IFC runs.
- Fits current Vite/React build.

Observed gaps:
- No model tree.
- No element property panel.
- No object selection.
- No persisted optimized viewer artifact.
- IFC coordination upload is still coupled to quantity extraction.

## Candidate Engines

| Engine | Strength | Risk | Decision |
|---|---|---|---|
| web-ifc + Three.js | Already installed and working | More custom code for tree/properties/performance | Keep as baseline |
| That Open Components/Fragments | BIM-oriented viewer ecosystem, fragments/cache path | New dependency and API learning curve | Spike first |
| xeokit | Mature BIM viewer performance and model tree concepts | License/commercial fit must be confirmed | Evaluate, do not adopt until license is clear |

## Decision

Default implementation path: keep `web-ifc` as fallback and introduce a model registry first. Adopt That Open only if the spike proves stable with the pilot IFC and the license is acceptable for SaaS use.
```

- [ ] **Step 2: Run current build**

Run:

```powershell
npm.cmd run build
```

Expected:

```text
tsc && vite build
✓ built
```

- [ ] **Step 3: Commit decision doc**

Run:

```powershell
git add docs/29-ifc-viewer-engine-decision.md
git commit -m "docs: record ifc viewer engine decision"
```

---

### Task 2: Backend BIM Model Registry

**Files:**
- Create: `backend/alembic/versions/20260603_0020_bim_model_registry.py`
- Create: `backend/app/services/bim_models.py`
- Create: `backend/tests/test_bim_model_registry.py`
- Modify: `backend/app/domain/models.py`
- Modify: `backend/app/domain/schemas.py`
- Modify: `backend/app/api/v1/routers/projects.py`

- [ ] **Step 1: Write failing backend tests**

Create `backend/tests/test_bim_model_registry.py`:

```python
from io import BytesIO


def test_upload_bim_model_registers_ifc_without_quantity_takeoff(client, auth_headers, project):
    response = client.post(
        f"/api/v1/projects/{project.id}/bim-models",
        headers=auth_headers,
        files={"file": ("wellness.ifc", BytesIO(b"ISO-10303-21;\\nEND-ISO-10303-21;"), "application/octet-stream")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_file_name"] == "wellness.ifc"
    assert payload["source_type"] == "ifc"
    assert payload["status"] == "uploaded"
    assert payload["source_size_bytes"] > 0


def test_bim_model_source_download_requires_project_membership(client, auth_headers, other_project, project):
    upload = client.post(
        f"/api/v1/projects/{project.id}/bim-models",
        headers=auth_headers,
        files={"file": ("model.ifc", BytesIO(b"ISO-10303-21;"), "application/octet-stream")},
    )
    assert upload.status_code == 200

    model_id = upload.json()["id"]
    response = client.get(f"/api/v1/projects/{other_project.id}/bim-models/{model_id}/source", headers=auth_headers)

    assert response.status_code in {403, 404}
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
docker compose exec -T api pytest backend/tests/test_bim_model_registry.py
```

Expected:

```text
FAILED ... 404 Not Found
```

- [ ] **Step 3: Add `BimModel` domain model**

In `backend/app/domain/models.py`, add:

```python
class BimModel(Base, TenantProjectMixin, TimestampMixin):
    __tablename__ = "bim_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_file_name: Mapped[str] = mapped_column(String(255), default="")
    source_type: Mapped[str] = mapped_column(String(30), default="ifc")
    source_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    source_storage_path: Mapped[str] = mapped_column(String(500), default="")
    viewer_artifact_path: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(40), default="uploaded")
    schema: Mapped[str] = mapped_column(String(40), default="")
    units: Mapped[str] = mapped_column(String(80), default="")
    element_count: Mapped[int] = mapped_column(Integer, default=0)
    storey_count: Mapped[int] = mapped_column(Integer, default=0)
    model_identity: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), nullable=True)
```

- [ ] **Step 4: Add migration**

Create `backend/alembic/versions/20260603_0020_bim_model_registry.py`:

```python
"""bim model registry

Revision ID: 20260603_0020
Revises: 20260520_0019
Create Date: 2026-06-03
"""

from alembic import op
import sqlalchemy as sa


revision = "20260603_0020"
down_revision = "20260520_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bim_models",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("source_file_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("source_type", sa.String(length=30), nullable=False, server_default="ifc"),
        sa.Column("source_size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_storage_path", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("viewer_artifact_path", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="uploaded"),
        sa.Column("schema", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("units", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("element_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("storey_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("model_identity", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user_accounts.id"]),
    )
    op.create_index("ix_bim_models_tenant_project", "bim_models", ["tenant_id", "project_id"])


def downgrade() -> None:
    op.drop_index("ix_bim_models_tenant_project", table_name="bim_models")
    op.drop_table("bim_models")
```

- [ ] **Step 5: Add schemas**

In `backend/app/domain/schemas.py`, add:

```python
class BimModelOut(BaseModel):
    id: int
    project_id: int
    source_file_name: str
    source_type: str
    source_size_bytes: int
    status: str
    schema: str
    units: str
    element_count: int
    storey_count: int
    model_identity: dict
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
```

- [ ] **Step 6: Implement service**

Create `backend/app/services/bim_models.py` with storage helpers equivalent to `QuantityTakeoffService._persist_ifc_source()`, but under `bim-models/tenant-{tenant_id}/project-{project_id}/model-{model_id}/`.

Required methods:

```python
class BimModelService:
    def __init__(self, db: Session): ...
    def create_ifc_model(self, tenant_id: int, project_id: int, user_id: int, filename: str, content: bytes) -> BimModel: ...
    @classmethod
    def source_path(cls, model: BimModel) -> Path | None: ...
    def delete_model(self, tenant_id: int, project_id: int, model_id: int) -> None: ...
```

- [ ] **Step 7: Add endpoints**

In `backend/app/api/v1/routers/projects.py`, add:

```python
@router.get("/projects/{project_id}/bim-models", response_model=list[BimModelOut])
def list_bim_models(...): ...

@router.post("/projects/{project_id}/bim-models", response_model=BimModelOut)
async def upload_bim_model(...): ...

@router.get("/projects/{project_id}/bim-models/{model_id}/source")
def get_bim_model_source(...): ...

@router.delete("/projects/{project_id}/bim-models/{model_id}")
def delete_bim_model(...): ...
```

Security:
- Use `_require_project()`.
- Use `_require_membership()`.
- Upload requires `membership.can_capture_cost or membership.can_configure`.
- Source download requires membership only.

- [ ] **Step 8: Run backend tests**

Run:

```powershell
docker compose exec -T api pytest backend/tests/test_bim_model_registry.py
```

Expected:

```text
2 passed
```

---

### Task 3: Frontend API and State

**Files:**
- Create: `frontend/src/api/bimModels.ts`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/App.tsx`
- Test: `frontend/tests/bim-model-registry.test.tsx`

- [ ] **Step 1: Add frontend type**

In `frontend/src/types/index.ts`, add:

```ts
export type BimModel = {
  id: number;
  project_id: number;
  source_file_name: string;
  source_type: "ifc";
  source_size_bytes: number;
  status: string;
  schema: string;
  units: string;
  element_count: number;
  storey_count: number;
  model_identity: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};
```

- [ ] **Step 2: Add API client**

Create `frontend/src/api/bimModels.ts`:

```ts
import { apiFetch, apiFetchFile } from "./client";
import type { BimModel } from "../types";

export const bimModels = {
  list: (token: string, projectId: number) =>
    apiFetch<BimModel[]>(`/api/v1/projects/${projectId}/bim-models`, { token }),
  upload: (token: string, projectId: number, file: File) => {
    const body = new FormData();
    body.append("file", file);
    return apiFetch<BimModel>(`/api/v1/projects/${projectId}/bim-models`, { token, method: "POST", body });
  },
  source: (token: string, projectId: number, modelId: number) =>
    apiFetchFile(`/api/v1/projects/${projectId}/bim-models/${modelId}/source`, { token }),
  remove: (token: string, projectId: number, modelId: number) =>
    apiFetch<{ status: string }>(`/api/v1/projects/${projectId}/bim-models/${modelId}`, {
      token,
      method: "DELETE",
    }),
};
```

- [ ] **Step 3: Write failing UI test**

Create `frontend/tests/bim-model-registry.test.tsx` with expectations:

```tsx
it("registers an IFC coordination model without requiring quantity lines", async () => {
  // mock bimModels.upload to return a BimModel
  // click BIM module
  // upload wellness.ifc
  // expect Modelo IFC heading and file name
  // expect Quantity Lines still allows no lines
});
```

- [ ] **Step 4: Wire `App.tsx`**

Add state:

```ts
const [bimModelsList, setBimModelsList] = useState<BimModel[]>([]);
const latestBimModel = bimModelsList[0];
```

Load `bimModels.list(token, projectId)` beside `quantityTakeoffRuns`.

Change IFC upload behavior:
- IFC coordination upload calls `bimModels.upload()`.
- Excel/CSV quantity upload continues using `projectsApi.loadQuantityTakeoff()`.
- The BIM module shows `latestBimModel` even when `latestQuantityTakeoff` is absent.

- [ ] **Step 5: Run frontend tests**

Run:

```powershell
npm.cmd test -- bim-model-registry.test.tsx AppFlow.test.tsx
```

Expected:

```text
passed
```

---

### Task 4: Viewer Refactor and Core Controls

**Files:**
- Create: `frontend/src/components/bim/BimModelViewer.tsx`
- Create: `frontend/src/components/bim/BimModelToolbar.tsx`
- Create: `frontend/src/components/bim/useIfcGeometry.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/tests/BimModelViewer.test.tsx`

- [ ] **Step 1: Move existing geometry loader into hook**

Move the `web-ifc` loading logic from `frontend/src/components/BimIfcModelViewer.tsx` into:

```ts
export type IfcGeometryLoadResult = {
  productCount: number;
  meshCount: number;
  modelBox: THREE.Box3;
  focusBox: THREE.Box3;
  root: THREE.Group;
};

export async function loadIfcGeometry(params: {
  bytes: Uint8Array;
  scene: THREE.Scene;
  disposed: () => boolean;
}): Promise<IfcGeometryLoadResult> {
  // existing OpenModel, LoadAllGeometry, mesh creation and bounds calculation
}
```

- [ ] **Step 2: Add toolbar**

Create toolbar buttons:
- `Fit`
- `Top`
- `Iso`
- `Reset selection`

All buttons must have `aria-label` values:
- `Fit IFC model`
- `Top IFC view`
- `Iso IFC view`
- `Reset IFC selection`

- [ ] **Step 3: Add full-width layout**

Update CSS:

```css
.ifcViewerShell {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 12px;
  width: 100%;
}

.ifcViewerCanvasWrap {
  min-height: 620px;
  width: 100%;
}

.ifcViewerCanvasWrap canvas {
  display: block;
  width: 100%;
  height: 100%;
}

@media (max-width: 980px) {
  .ifcViewerShell {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 4: Run tests and build**

Run:

```powershell
npm.cmd test -- BimModelViewer.test.tsx
npm.cmd run build
```

Expected:

```text
passed
✓ built
```

---

### Task 5: Element Selection and Properties

**Files:**
- Create: `frontend/src/components/bim/useIfcSelection.ts`
- Create: `frontend/src/components/bim/BimElementProperties.tsx`
- Modify: `frontend/src/components/bim/BimModelViewer.tsx`
- Test: `frontend/tests/BimModelViewer.test.tsx`

- [ ] **Step 1: Preserve mesh metadata**

When creating meshes, assign:

```ts
mesh.userData = {
  expressId: flatMesh.expressID,
  ifcClass: "",
  globalId: "",
};
```

- [ ] **Step 2: Add raycast selection**

Create `useIfcSelection.ts`:

```ts
export type SelectedIfcElement = {
  expressId: number;
  globalId: string;
  ifcClass: string;
  name: string;
  typeName: string;
  storey: string;
};
```

The hook returns:
- `selectedElement`
- `onPointerClick`
- `clearSelection`

- [ ] **Step 3: Add properties panel**

Panel labels:
- `Elemento seleccionado`
- `GlobalId`
- `Clase IFC`
- `Tipo`
- `Nivel`
- `Trazabilidad de cantidades`

If no element is selected, show:

```text
Selecciona un elemento del modelo para ver propiedades y trazabilidad.
```

- [ ] **Step 4: Link selected element to quantity lines**

In `BimElementProperties.tsx`, match:

```ts
const matchingLines = quantityLines.filter(
  (line) => line.element_guid === selected.globalId || line.element_id === String(selected.expressId),
);
```

Show WBS/CBS/FBS/package for matching lines.

- [ ] **Step 5: Verify tests**

Run:

```powershell
npm.cmd test -- BimModelViewer.test.tsx BimScopeValidationPanel.test.tsx
```

Expected:

```text
passed
```

---

### Task 6: Model Tree and Filters

**Files:**
- Create: `frontend/src/components/bim/BimModelTree.tsx`
- Modify: `frontend/src/components/bim/BimModelViewer.tsx`
- Test: `frontend/tests/BimModelViewer.test.tsx`

- [ ] **Step 1: Build tree structure**

Tree type:

```ts
export type BimTreeNode = {
  id: string;
  label: string;
  kind: "project" | "site" | "building" | "storey" | "ifc_class";
  count: number;
  children: BimTreeNode[];
};
```

Tree grouping:

```text
Project
  Site
    Building
      Storey
        IFC Class
```

- [ ] **Step 2: Add isolate by tree node**

Clicking a storey or IFC class updates visible meshes:

```ts
mesh.visible = selectedFilter ? mesh.userData.storey === selectedFilter || mesh.userData.ifcClass === selectedFilter : true;
```

- [ ] **Step 3: Add reset filter**

Add button:

```tsx
<button aria-label="Reset IFC filters" type="button">Reset filters</button>
```

- [ ] **Step 4: Verify**

Run:

```powershell
npm.cmd test -- BimModelViewer.test.tsx
```

Expected:

```text
passed
```

---

### Task 7: Browser E2E Visual Verification

**Files:**
- Create: `frontend/e2e/bim-viewer.spec.ts`
- Modify: none

- [ ] **Step 1: Add E2E test**

Create `frontend/e2e/bim-viewer.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

test("renders a nonblank IFC viewer and keeps quantity table below it", async ({ page }) => {
  await page.goto("/login");
  await page.fill("#email", "admin");
  await page.fill("#password", "1234");
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/app/);

  await page.locator('button:has-text("Cantidades BIM")').first().click({ force: true });
  await expect(page.getByRole("region", { name: /modelo ifc/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: /quantity lines/i })).toBeVisible();

  const canvas = page.getByTestId("ifc-geometry-viewer-canvas");
  await expect(canvas).toBeVisible();
});
```

- [ ] **Step 2: Run E2E**

Run:

```powershell
npm.cmd run test:e2e -- bim-viewer.spec.ts
```

Expected:

```text
1 passed
```

---

### Task 8: Production Hardening

**Files:**
- Modify: `frontend/src/components/bim/BimModelViewer.tsx`
- Modify: `backend/app/services/bim_models.py`
- Modify: `backend/tests/test_bim_model_registry.py`
- Modify: `docs/29-ifc-viewer-engine-decision.md`

- [ ] **Step 1: Add clear errors**

Viewer error messages:

```text
No se pudo cargar la geometria IFC. El modelo quedó registrado, pero necesita revisión técnica del archivo fuente.
```

Upload error messages:

```text
El modelo IFC no se pudo registrar. Revisa tamaño, permisos o disponibilidad del servicio.
```

- [ ] **Step 2: Add delete model**

Backend delete removes:
- Source IFC file.
- Viewer artifact file if present.
- `BimModel` row.

Frontend button:

```tsx
<button aria-label="Clear loaded BIM model" type="button">Limpiar modelo</button>
```

- [ ] **Step 3: Add observability fields**

Update `BimModel.model_identity` with:

```json
{
  "source": "ifc",
  "upload_size_mb": 0,
  "viewer_engine": "web-ifc",
  "first_render_ms": 0,
  "rendered_meshes": 0
}
```

- [ ] **Step 4: Run final verification**

Run:

```powershell
docker compose exec -T api pytest backend/tests/test_bim_model_registry.py backend/tests/test_quantity_takeoff.py
npm.cmd test -- BimModelViewer.test.tsx bim-model-registry.test.tsx AppFlow.test.tsx
npm.cmd run build
```

Expected:

```text
passed
✓ built
```

---

## Execution Notes

Recommended order:
1. Backend registry first. This fixes the core product problem: a BIM model must survive even when quantity extraction is not ready.
2. Frontend registry integration. Users should see the loaded model as the primary BIM object.
3. Viewer refactor. Keep current `web-ifc` as fallback while improving layout and controls.
4. Selection/properties/tree. This creates market-level utility.
5. Engine upgrade. Add That Open/Fragments only after the decision spike confirms it beats the current path.

Do not:
- Reintroduce symbolic block previews.
- Add a second quantity table.
- Couple model upload to synchronous quantity extraction.
- Hide failed quantity extraction as if the model upload failed.

Definition of done:
- The app has one IFC viewer, one quantity table and a clear model identity.
- The user can answer: “What model is this?”, “What element did I select?”, “What WBS/CBS/FBS does it support?”, and “Can I reload the project and still see it?”
