import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ClipboardList,
  Eye,
  FolderTree,
  LoaderCircle,
  PlayCircle,
  Plus,
  RotateCcw,
  Send,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../../api/client";
import { enterpriseStructureApi } from "../api";
import type {
  ProjectCreationOptions,
  ProjectCreationRequest,
  ProjectGovernanceModel,
  ProjectRequestPayload,
  ProjectRequestPreview,
  ProjectWorkspaceOverview,
} from "../types";
import ProjectWorkspaceLifecycle from "./ProjectWorkspaceLifecycle";

export type ProjectCreationView = "create" | "requests" | "review" | "workspaces" | "overview";

type Props = {
  token: string;
  view: ProjectCreationView;
  initialParentId?: number;
  projectWorkspaceId?: number;
  onBack: () => void;
  onCreated?: () => void;
};

const emptyPayload: ProjectRequestPayload = {
  governance_model: null,
  source_context_type: null,
  source_context_id: null,
  source_external_key: null,
  idempotency_key: null,
  source_snapshot: {},
  parent_workspace_id: 0,
  project_template_config_id: 0,
  project_name: "",
  description: "",
  project_manager_user_id: 0,
  planned_start: null,
  planned_finish: null,
  currency_code: "COP",
  estimated_budget: null,
  project_type: null,
  project_phase: null,
  priority: null,
  country: "CO",
  region: null,
  strategic_objective_codes: [],
};

const governanceLabels: Record<ProjectGovernanceModel, string> = {
  CAPITAL_OWNER: "Capital Owner",
  CONTRACTOR_DELIVERY: "Contractor Delivery",
  DIRECT_INTERNAL: "Direct Internal",
};

const sourceLabels: Record<string, string> = {
  STRATEGIC_GATE_DECISION: "Strategic Gate Decision",
  CONTRACT_AWARD: "Contract Award",
  DIRECT_AUTHORIZATION: "Direct Authorization",
};

const stateLabels: Record<string, string> = {
  draft: "Borrador",
  submitted: "Enviada",
  under_review: "En revisión",
  returned: "Devuelta",
  rejected: "Rechazada",
  approved: "Aprobada",
  materializing: "Creando",
  created: "Creada",
  failed: "Fallida",
  cancelled: "Cancelada",
};

function errorMessage(error: unknown) {
  if (!(error instanceof ApiError))
    return error instanceof Error ? error.message : "No fue posible completar la acción.";
  try {
    const payload = JSON.parse(error.message) as {
      detail?: string | { code?: string; issues?: string[]; message?: string };
    };
    if (typeof payload.detail === "string") return payload.detail;
    if (payload.detail?.code === "REQUEST_VERSION_CONFLICT")
      return "La solicitud cambió desde que la abrió. Actualice la lista y vuelva a intentar.";
    return payload.detail?.message || payload.detail?.issues?.join(" · ") || error.message;
  } catch {
    return error.message;
  }
}

function RequestList({
  requests,
  review,
  busyId,
  onAction,
}: {
  requests: ProjectCreationRequest[];
  review: boolean;
  busyId: number | null;
  onAction: (
    request: ProjectCreationRequest,
    action: "submit" | "cancel" | "start-review" | "return" | "reject" | "approve" | "materialize"
  ) => void;
}) {
  if (!requests.length) {
    return <div className="projectRequestEmpty">No hay solicitudes para esta vista.</div>;
  }
  return (
    <div className="projectRequestList">
      {requests.map((request) => (
        <article className="projectRequestCard" key={request.id}>
          <header>
            <div>
              <span>{request.request_number}</span>
              <h3>{request.project_name}</h3>
            </div>
            <span className={`requestState ${request.state}`}>{stateLabels[request.state] || request.state}</span>
          </header>
          <dl>
            <div>
              <dt>Ubicación</dt>
              <dd>{request.parent_name}</dd>
            </div>
            <div>
              <dt>Modelo de gobierno</dt>
              <dd>{request.governance_model ? governanceLabels[request.governance_model] : "Legacy"}</dd>
            </div>
            <div>
              <dt>Fuente</dt>
              <dd>{request.source_context_type ? sourceLabels[request.source_context_type] : "No clasificada"}</dd>
            </div>
            <div>
              <dt>Plantilla</dt>
              <dd>{request.template_name}</dd>
            </div>
            <div>
              <dt>Project Manager</dt>
              <dd>{request.project_manager_name}</dd>
            </div>
            <div>
              <dt>Versión</dt>
              <dd>{request.revision_version}</dd>
            </div>
          </dl>
          {request.decision_reason ? <p className="requestDecision">Decisión: {request.decision_reason}</p> : null}
          {request.materialized_project_number ? (
            <p className="requestCreatedNumber">
              <CheckCircle2 size={14} /> {request.materialized_project_number} · {request.materialized_record_code}
            </p>
          ) : null}
          <footer>
            {!review && request.state === "draft" ? (
              <button disabled={busyId === request.id} onClick={() => onAction(request, "submit")} type="button">
                <Send size={14} /> Enviar
              </button>
            ) : null}
            {!review && ["draft", "submitted", "returned"].includes(request.state) ? (
              <button
                className="ghost"
                disabled={busyId === request.id}
                onClick={() => onAction(request, "cancel")}
                type="button"
              >
                <XCircle size={14} /> Cancelar
              </button>
            ) : null}
            {review && request.state === "submitted" ? (
              <button disabled={busyId === request.id} onClick={() => onAction(request, "start-review")} type="button">
                <PlayCircle size={14} /> Iniciar revisión
              </button>
            ) : null}
            {review && request.state === "under_review" ? (
              <>
                <button disabled={busyId === request.id} onClick={() => onAction(request, "approve")} type="button">
                  <ShieldCheck size={14} /> Aprobar
                </button>
                <button
                  className="ghost"
                  disabled={busyId === request.id}
                  onClick={() => onAction(request, "return")}
                  type="button"
                >
                  <RotateCcw size={14} /> Devolver
                </button>
                <button
                  className="danger"
                  disabled={busyId === request.id}
                  onClick={() => onAction(request, "reject")}
                  type="button"
                >
                  <XCircle size={14} /> Rechazar
                </button>
              </>
            ) : null}
            {review && ["approved", "failed"].includes(request.state) ? (
              <button disabled={busyId === request.id} onClick={() => onAction(request, "materialize")} type="button">
                <FolderTree size={14} /> Crear Project Workspace
              </button>
            ) : null}
          </footer>
        </article>
      ))}
    </div>
  );
}

export function ProjectOverview({ token, workspaceId }: { token: string; workspaceId: number }) {
  const [overview, setOverview] = useState<ProjectWorkspaceOverview | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    enterpriseStructureApi
      .projectWorkspaceOverview(token, workspaceId)
      .then(setOverview)
      .catch((caught) => setError(errorMessage(caught)));
  }, [token, workspaceId]);
  if (error) return <div className="enterpriseAlert error">{error}</div>;
  if (!overview) return <div className="projectRequestEmpty">Consultando Project Overview…</div>;
  return (
    <section className="projectOverviewCard">
      <header>
        <div>
          <span>PROJECT OVERVIEW</span>
          <h2>{overview.project_name}</h2>
        </div>
        <strong>{overview.status}</strong>
      </header>
      <div className="projectOverviewGrid">
        <div>
          <span>Project Number</span>
          <strong>{overview.project_number}</strong>
        </div>
        <div>
          <span>Record Code</span>
          <strong>{overview.record_code}</strong>
        </div>
        <div>
          <span>Ubicación</span>
          <strong>{overview.parent_workspace}</strong>
        </div>
        <div>
          <span>Project Manager</span>
          <strong>{overview.project_manager}</strong>
        </div>
        <div>
          <span>Plantilla</span>
          <strong>{overview.template}</strong>
        </div>
        <div>
          <span>Modelo de gobierno</span>
          <strong>{overview.governance_label}</strong>
        </div>
        <div>
          <span>Fuente de creación</span>
          <strong>{overview.creation_source ? sourceLabels[overview.creation_source] : "Legacy"}</strong>
        </div>
        <div>
          <span>Referencia fuente</span>
          <strong>{overview.source_reference || "Sin referencia"}</strong>
        </div>
        <div>
          <span>Readiness de activación</span>
          <strong>{overview.activation_readiness}</strong>
        </div>
        <div>
          <span>Presupuesto</span>
          <strong>
            {overview.estimated_budget || "Sin definir"} {overview.currency}
          </strong>
        </div>
      </div>
      <section>
        <h3>Objetivos estratégicos</h3>
        <div className="projectTagRow">
          {overview.strategic_objectives.map((item) => (
            <span key={item}>{item}</span>
          ))}
        </div>
      </section>
      <section>
        <h3>Módulos habilitados</h3>
        <div className="projectTagRow">
          {overview.enabled_modules.map((item) => (
            <span key={item}>{item}</span>
          ))}
        </div>
      </section>
    </section>
  );
}

export default function ProjectCreationWorkspace({
  token,
  view,
  initialParentId,
  projectWorkspaceId,
  onBack,
  onCreated,
}: Props) {
  const [options, setOptions] = useState<ProjectCreationOptions | null>(null);
  const [payload, setPayload] = useState<ProjectRequestPayload>({ ...emptyPayload });
  const [request, setRequest] = useState<ProjectCreationRequest | null>(null);
  const [preview, setPreview] = useState<ProjectRequestPreview | null>(null);
  const [requests, setRequests] = useState<ProjectCreationRequest[]>([]);
  const [busy, setBusy] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const review = view === "review";

  useEffect(() => {
    if (view !== "create") return;
    enterpriseStructureApi
      .projectCreationOptions(token, initialParentId)
      .then((result) => {
        setOptions(result);
        const preferred =
          result.allowed_governance_models.find((item) => item.code === "DIRECT_INTERNAL") ??
          result.allowed_governance_models[0];
        setPayload((current) => ({
          ...current,
          governance_model: preferred?.code ?? null,
          source_context_type: preferred?.source_context_type ?? null,
          parent_workspace_id: initialParentId || result.locations[0]?.id || 0,
          project_template_config_id: result.templates[0]?.id || 0,
          project_manager_user_id: result.managers[0]?.id || 0,
        }));
      })
      .catch((caught) => setError(errorMessage(caught)));
  }, [token, initialParentId, view]);

  async function loadRequests() {
    setBusy(true);
    try {
      setRequests(await enterpriseStructureApi.projectRequests(token, review));
      setError("");
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (view === "requests" || view === "review") void loadRequests();
    // loadRequests is intentionally tied to view/token.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, view]);

  const selectedLocation = useMemo(
    () => options?.locations.find((item) => item.id === payload.parent_workspace_id),
    [options, payload.parent_workspace_id]
  );

  async function changeParent(parentId: number) {
    setPayload((current) => ({ ...current, parent_workspace_id: parentId, project_template_config_id: 0 }));
    setPreview(null);
    try {
      const scoped = await enterpriseStructureApi.projectCreationOptions(token, parentId);
      setOptions((current) =>
        current ? { ...current, templates: scoped.templates, blocked_reason: scoped.blocked_reason } : scoped
      );
      setPayload((current) => ({ ...current, project_template_config_id: scoped.templates[0]?.id || 0 }));
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function createDraft(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      if (payload.governance_model === "CAPITAL_OWNER") {
        throw new Error("Capital Owner se inicia desde Strategic Project Planning Entry para conservar Gate 07D.");
      }
      await enterpriseStructureApi.previewProjectSource(token, payload);
      const created = await enterpriseStructureApi.createProjectFromSource(token, payload);
      setRequest(created);
      setPreview(await enterpriseStructureApi.projectRequestPreview(token, created.id));
      setError("");
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  function selectGovernance(model: ProjectGovernanceModel) {
    const selected = options?.allowed_governance_models.find((item) => item.code === model);
    setRequest(null);
    setPreview(null);
    setPayload((current) => ({
      ...current,
      governance_model: model,
      source_context_type: selected?.source_context_type ?? null,
      source_context_id: null,
      source_external_key: null,
      idempotency_key: null,
      source_snapshot: {},
      strategic_objective_codes: [],
    }));
  }

  function updateSourceSnapshot(key: string, value: string | boolean | null) {
    setPayload((current) => ({
      ...current,
      source_snapshot: { ...current.source_snapshot, [key]: value },
      ...(key === "contract_number" || key === "authorization_reference"
        ? { source_external_key: String(value || ""), idempotency_key: String(value || "") }
        : {}),
    }));
  }

  async function submitDraft() {
    if (!request) return;
    setBusy(true);
    try {
      const updated = await enterpriseStructureApi.transitionProjectRequest(token, request, "submit");
      setRequest(updated);
      setError("");
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function act(
    item: ProjectCreationRequest,
    action: "submit" | "cancel" | "start-review" | "return" | "reject" | "approve" | "materialize"
  ) {
    setBusyId(item.id);
    try {
      if (action === "materialize") {
        await enterpriseStructureApi.materializeProjectRequest(token, item.id);
        onCreated?.();
      } else {
        const reason = ["return", "reject"].includes(action)
          ? window.prompt(action === "return" ? "Motivo de devolución" : "Motivo de rechazo")?.trim()
          : undefined;
        if (["return", "reject"].includes(action) && !reason) return;
        await enterpriseStructureApi.transitionProjectRequest(token, item, action, reason);
      }
      await loadRequests();
      setError("");
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="projectCreationWorkspace">
      <header className="projectCreationHeader">
        <button className="ghost" onClick={onBack} type="button">
          <ArrowLeft size={16} /> Enterprise Explorer
        </button>
        <div>
          <span>USER MODE · ENTERPRISE STRATEGY MANAGER</span>
          <h2>
            {view === "create"
              ? "Create Project"
              : view === "requests"
                ? "My Project Requests"
                : view === "review"
                  ? "Project Review Queue"
                  : view === "workspaces"
                    ? "My Project Workspaces"
                    : "Project Overview"}
          </h2>
        </div>
        <span className="governedBadge">
          <ShieldCheck size={15} /> Proceso gobernado
        </span>
      </header>

      {error ? (
        <div className="enterpriseAlert error" role="alert">
          <AlertTriangle size={16} /> {error}
        </div>
      ) : null}

      {view === "overview" && projectWorkspaceId ? (
        <ProjectWorkspaceLifecycle token={token} workspaceId={projectWorkspaceId} />
      ) : null}

      {view === "workspaces" ? <ProjectWorkspaceLifecycle token={token} /> : null}

      {view === "requests" || view === "review" ? (
        <section className="projectRequestPanel">
          <div className="projectListToolbar">
            <div>
              <ClipboardList size={18} />
              <strong>{review ? "Solicitudes pendientes de control" : "Solicitudes creadas por usted"}</strong>
            </div>
            <button disabled={busy} onClick={() => void loadRequests()} type="button">
              {busy ? <LoaderCircle className="spin" size={14} /> : <RotateCcw size={14} />} Actualizar
            </button>
          </div>
          <RequestList
            busyId={busyId}
            onAction={(item, action) => void act(item, action)}
            requests={requests}
            review={review}
          />
        </section>
      ) : null}

      {view === "create" && options ? (
        options.blocked_reason ? (
          <section className="projectBlockedState">
            <AlertTriangle size={28} />
            <h3>No hay una Project Template publicada y aplicable</h3>
            <p>
              Un administrador debe publicar una plantilla compatible antes de crear solicitudes. Las plantillas DRAFT
              no son elegibles.
            </p>
          </section>
        ) : request ? (
          <section className="projectPreviewPanel">
            <header>
              <div>
                <span>SOLICITUD CREADA</span>
                <h3>
                  {request.request_number} · {request.project_name}
                </h3>
              </div>
              <span className={`requestState ${request.state}`}>{stateLabels[request.state]}</span>
            </header>
            {preview ? (
              <>
                <div className="previewNotice">
                  <Eye size={17} />
                  <span>{preview.notice}. Esta vista no consume numeración ni crea un Project Workspace.</span>
                </div>
                <div className="projectPreviewGrid">
                  <div>
                    <span>Project Number estimado</span>
                    <strong>{preview.projected_project_number}</strong>
                  </div>
                  <div>
                    <span>Record Code estimado</span>
                    <strong>{preview.projected_record_code}</strong>
                  </div>
                  <div>
                    <span>Estado inicial</span>
                    <strong>{preview.initial_workspace_status}</strong>
                  </div>
                  <div>
                    <span>Módulos</span>
                    <strong>{preview.enabled_modules.join(", ") || "Ninguno"}</strong>
                  </div>
                </div>
              </>
            ) : null}
            <footer>
              {request.state === "draft" ? (
                <button disabled={busy} onClick={() => void submitDraft()} type="button">
                  <Send size={15} /> Enviar a revisión
                </button>
              ) : null}
              {request.state === "submitted" ? (
                <p>
                  <CheckCircle2 size={16} /> Solicitud enviada. Puede seguirla en My Project Requests.
                </p>
              ) : null}
            </footer>
          </section>
        ) : (
          <form className="projectIntakeForm" onSubmit={createDraft}>
            <section className="projectIntakeSection governanceModelPicker">
              <header>
                <span>1</span>
                <div>
                  <h3>Modelo de gobierno del proyecto</h3>
                  <p>Define el origen, los campos y el readiness; es independiente del tipo de proyecto.</p>
                </div>
              </header>
              <div className="governanceModelOptions" role="radiogroup" aria-label="Modelo de gobierno">
                {options.allowed_governance_models.map((model) => (
                  <label className={payload.governance_model === model.code ? "selected" : ""} key={model.code}>
                    <input
                      checked={payload.governance_model === model.code}
                      name="governance-model"
                      onChange={() => selectGovernance(model.code)}
                      type="radio"
                    />
                    <span>
                      <strong>{model.label}</strong>
                      <small>{sourceLabels[model.source_context_type]}</small>
                    </span>
                  </label>
                ))}
              </div>
              {payload.governance_model === "CAPITAL_OWNER" ? (
                <div className="governanceRouteNotice" role="status">
                  <ShieldCheck size={18} />
                  <span>
                    Esta ruta se crea desde <strong>Strategic Project Planning Entry</strong>; allí se conserva la
                    decisión Gate 07D, el Portfolio objetivo y sus hashes de readiness.
                  </span>
                </div>
              ) : null}
            </section>

            <section className="projectIntakeSection locationPicker">
              <header>
                <span>2</span>
                <div>
                  <h3>Ubicación empresarial</h3>
                  <p>Seleccione un Portfolio o Program permitido por la composición publicada.</p>
                </div>
              </header>
              <div className="projectLocationTree" role="radiogroup" aria-label="Ubicación del proyecto">
                {options.locations.map((location) => (
                  <label
                    className={payload.parent_workspace_id === location.id ? "selected" : ""}
                    key={location.id}
                    style={{ paddingLeft: `${14 + Math.max(0, location.path.length - 2) * 16}px` }}
                  >
                    <input
                      checked={payload.parent_workspace_id === location.id}
                      name="parent"
                      onChange={() => void changeParent(location.id)}
                      type="radio"
                    />
                    <FolderTree size={16} />
                    <span>
                      <strong>{location.name}</strong>
                      <small>
                        {location.path.join(" / ")} · {location.record_code}
                      </small>
                    </span>
                  </label>
                ))}
              </div>
              {selectedLocation ? (
                <p className="selectedPath">Ruta seleccionada: {selectedLocation.path.join(" / ")}</p>
              ) : null}
            </section>

            <section className="projectIntakeSection">
              <header>
                <span>3</span>
                <div>
                  <h3>Identidad y gobierno</h3>
                  <p>La solicitud es independiente del Project Workspace que se creará al final.</p>
                </div>
              </header>
              <div className="projectFormGrid">
                <label className="wide">
                  Nombre del proyecto
                  <input
                    required
                    value={payload.project_name}
                    onChange={(event) => setPayload({ ...payload, project_name: event.target.value })}
                  />
                </label>
                <label>
                  Project Template
                  <select
                    required
                    value={payload.project_template_config_id || ""}
                    onChange={(event) =>
                      setPayload({ ...payload, project_template_config_id: Number(event.target.value) })
                    }
                  >
                    <option value="">Seleccione…</option>
                    {options.templates.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name} · {item.code}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Project Manager
                  <select
                    required
                    value={payload.project_manager_user_id || ""}
                    onChange={(event) =>
                      setPayload({ ...payload, project_manager_user_id: Number(event.target.value) })
                    }
                  >
                    <option value="">Seleccione…</option>
                    {options.managers.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name} · {item.email}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="wide">
                  Descripción
                  <textarea
                    rows={3}
                    value={payload.description}
                    onChange={(event) => setPayload({ ...payload, description: event.target.value })}
                  />
                </label>
                <label>
                  Inicio planeado
                  <input
                    type="date"
                    value={payload.planned_start || ""}
                    onChange={(event) => setPayload({ ...payload, planned_start: event.target.value || null })}
                  />
                </label>
                <label>
                  Fin planeado
                  <input
                    type="date"
                    value={payload.planned_finish || ""}
                    onChange={(event) => setPayload({ ...payload, planned_finish: event.target.value || null })}
                  />
                </label>
                <label>
                  Moneda
                  <input
                    maxLength={8}
                    required
                    value={payload.currency_code}
                    onChange={(event) => setPayload({ ...payload, currency_code: event.target.value.toUpperCase() })}
                  />
                </label>
                <label>
                  Presupuesto estimado
                  <input
                    min="0"
                    step="0.01"
                    type="number"
                    value={payload.estimated_budget || ""}
                    onChange={(event) => setPayload({ ...payload, estimated_budget: event.target.value || null })}
                  />
                </label>
                <label>
                  País
                  <input
                    value={payload.country || ""}
                    onChange={(event) => setPayload({ ...payload, country: event.target.value || null })}
                  />
                </label>
                <label>
                  Región
                  <select
                    value={payload.region || ""}
                    onChange={(event) => setPayload({ ...payload, region: event.target.value || null })}
                  >
                    <option value="">Sin definir</option>
                    {(options.classifications.region || []).map((item) => (
                      <option key={item.code} value={item.code}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            </section>

            {payload.governance_model === "CONTRACTOR_DELIVERY" ? (
              <section className="projectIntakeSection sourceContextPanel">
                <header>
                  <span>4</span>
                  <div>
                    <h3>Contrato adjudicado</h3>
                    <p>Captura la fuente contractual controlada sin crear un segundo registro de Project.</p>
                  </div>
                </header>
                <div className="projectFormGrid">
                  <label>
                    Cliente
                    <input
                      required
                      value={String(payload.source_snapshot.client ?? "")}
                      onChange={(event) => updateSourceSnapshot("client", event.target.value)}
                    />
                  </label>
                  <label>
                    Número de contrato
                    <input
                      required
                      value={String(payload.source_snapshot.contract_number ?? "")}
                      onChange={(event) => updateSourceSnapshot("contract_number", event.target.value)}
                    />
                  </label>
                  <label className="wide">
                    Alcance contractual
                    <textarea
                      required
                      rows={3}
                      value={String(payload.source_snapshot.contractual_scope ?? "")}
                      onChange={(event) => updateSourceSnapshot("contractual_scope", event.target.value)}
                    />
                  </label>
                  <label>
                    Valor contractual
                    <input
                      min="0"
                      step="0.01"
                      type="number"
                      value={String(payload.source_snapshot.contract_value ?? "")}
                      onChange={(event) => updateSourceSnapshot("contract_value", event.target.value || null)}
                    />
                  </label>
                  <label className="projectBooleanField">
                    <input
                      checked={Boolean(payload.source_snapshot.mobilization_authorized)}
                      onChange={(event) => updateSourceSnapshot("mobilization_authorized", event.target.checked)}
                      type="checkbox"
                    />
                    Movilización autorizada
                  </label>
                </div>
              </section>
            ) : null}

            {payload.governance_model === "DIRECT_INTERNAL" ? (
              <section className="projectIntakeSection sourceContextPanel">
                <header>
                  <span>4</span>
                  <div>
                    <h3>Autorización interna directa</h3>
                    <p>Registra el patrocinador y la autorización sin exigir contrato ni decisión estratégica.</p>
                  </div>
                </header>
                <div className="projectFormGrid">
                  <label>
                    Referencia de autorización
                    <input
                      required
                      value={String(payload.source_snapshot.authorization_reference ?? "")}
                      onChange={(event) => updateSourceSnapshot("authorization_reference", event.target.value)}
                    />
                  </label>
                  <label>
                    Patrocinador
                    <input
                      required
                      value={String(payload.source_snapshot.sponsor ?? "")}
                      onChange={(event) => updateSourceSnapshot("sponsor", event.target.value)}
                    />
                  </label>
                  <label className="wide">
                    Propósito de negocio
                    <textarea
                      rows={3}
                      value={String(payload.source_snapshot.business_purpose ?? "")}
                      onChange={(event) => updateSourceSnapshot("business_purpose", event.target.value)}
                    />
                  </label>
                  <label className="projectBooleanField">
                    <input
                      checked={Boolean(payload.source_snapshot.authorization_approved)}
                      onChange={(event) => updateSourceSnapshot("authorization_approved", event.target.checked)}
                      type="checkbox"
                    />
                    Autorización aprobada
                  </label>
                </div>
              </section>
            ) : null}

            <section className="projectIntakeSection">
              <header>
                <span>{payload.governance_model === "CAPITAL_OWNER" ? "4" : "5"}</span>
                <div>
                  <h3>Alineación estratégica</h3>
                  <p>
                    {payload.governance_model === "CAPITAL_OWNER"
                      ? "Obligatoria y heredada de la decisión estratégica."
                      : "Opcional para esta ruta de gobierno."}
                  </p>
                </div>
              </header>
              <div className="objectivePicker">
                {options.strategic_objectives.map((objective) => (
                  <label key={objective.code}>
                    <input
                      checked={payload.strategic_objective_codes.includes(objective.code)}
                      onChange={(event) =>
                        setPayload({
                          ...payload,
                          strategic_objective_codes: event.target.checked
                            ? [...payload.strategic_objective_codes, objective.code]
                            : payload.strategic_objective_codes.filter((code) => code !== objective.code),
                        })
                      }
                      type="checkbox"
                    />
                    <span>
                      {objective.label}
                      <small>{objective.code}</small>
                    </span>
                  </label>
                ))}
              </div>
            </section>

            <footer className="projectFormActions">
              <p>
                <ShieldCheck size={16} /> Guardar crea una solicitud DRAFT. No crea el proyecto ni reserva Project
                Number.
              </p>
              <button
                disabled={
                  busy ||
                  !payload.governance_model ||
                  payload.governance_model === "CAPITAL_OWNER" ||
                  (payload.governance_model === "CONTRACTOR_DELIVERY" &&
                    (!payload.source_snapshot.client ||
                      !payload.source_snapshot.contract_number ||
                      !payload.source_snapshot.contractual_scope)) ||
                  (payload.governance_model === "DIRECT_INTERNAL" &&
                    (!payload.source_snapshot.authorization_reference || !payload.source_snapshot.sponsor))
                }
                type="submit"
              >
                {busy ? <LoaderCircle className="spin" size={15} /> : <Plus size={15} />} Guardar solicitud y
                previsualizar
              </button>
            </footer>
          </form>
        )
      ) : view === "create" && !error ? (
        <div className="projectRequestEmpty">Consultando configuración publicada…</div>
      ) : null}
    </section>
  );
}
