import {
  AlertTriangle,
  ArrowLeft,
  Building2,
  CheckCircle2,
  ClipboardList,
  Eye,
  FolderTree,
  LoaderCircle,
  RotateCcw,
  Send,
  ShieldCheck,
  Warehouse,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../../api/client";
import { enterpriseStructureApi } from "../api";
import type {
  PhysicalWorkspaceCreationOptions,
  PhysicalWorkspaceCreationRequest,
  PhysicalWorkspaceOverview,
  PhysicalWorkspaceRequestPayload,
  PhysicalWorkspaceRequestPreview,
} from "../types";

export type PhysicalWorkspaceCreationView = "create" | "requests" | "review" | "overview";

type PhysicalType = "property" | "facility" | "warehouse";
type RequestAction =
  | "submit"
  | "cancel"
  | "start-review"
  | "return"
  | "reject"
  | "approve"
  | "materialize"
  | "edit"
  | "preview"
  | "open";

type Props = {
  token: string;
  view: PhysicalWorkspaceCreationView;
  initialType?: PhysicalType;
  initialParentId?: number;
  workspaceId?: number;
  onBack: () => void;
  onCreated?: () => void;
};

const labels: Record<string, string> = {
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

function emptyPayload(type: PhysicalType = "property"): PhysicalWorkspaceRequestPayload {
  return {
    workspace_type_code: type,
    parent_workspace_id: 0,
    template_config_id: 0,
    workspace_name: "",
    description: "",
    responsible_user_id: 0,
    attributes: {},
    classifications: [],
  };
}

function errorMessage(error: unknown) {
  if (!(error instanceof ApiError))
    return error instanceof Error ? error.message : "No fue posible completar la acción.";
  try {
    const payload = JSON.parse(error.message) as {
      detail?: string | { code?: string; issues?: string[]; message?: string };
    };
    if (typeof payload.detail === "string") return payload.detail;
    if (payload.detail?.code === "PHYSICAL_WORKSPACE_REQUEST_VERSION_CONFLICT")
      return "La solicitud cambió. Actualice la lista antes de continuar.";
    return payload.detail?.message || payload.detail?.issues?.join(" · ") || error.message;
  } catch {
    return error.message;
  }
}

function RequestCards({
  requests,
  review,
  busyId,
  onAction,
}: {
  requests: PhysicalWorkspaceCreationRequest[];
  review: boolean;
  busyId: number | null;
  onAction: (request: PhysicalWorkspaceCreationRequest, action: RequestAction) => void;
}) {
  if (!requests.length) return <div className="projectRequestEmpty">No hay solicitudes físicas para esta vista.</div>;
  return (
    <div className="projectRequestList physicalRequestList">
      {requests.map((request) => (
        <article className="projectRequestCard" key={request.id}>
          <header>
            <div>
              <span>
                {request.request_number} · {request.workspace_type_code.toUpperCase()}
              </span>
              <h3>{request.workspace_name}</h3>
            </div>
            <span className={`requestState ${request.state}`}>{labels[request.state] || request.state}</span>
          </header>
          <dl>
            <div>
              <dt>Parent</dt>
              <dd>{request.parent_name}</dd>
            </div>
            <div>
              <dt>Template</dt>
              <dd>{request.template_name}</dd>
            </div>
            <div>
              <dt>Responsible</dt>
              <dd>{request.responsible_name}</dd>
            </div>
            <div>
              <dt>Versión</dt>
              <dd>{request.revision_version}</dd>
            </div>
          </dl>
          {request.decision_reason ? <p className="requestDecision">Decisión: {request.decision_reason}</p> : null}
          {request.materialized_business_number ? (
            <p className="requestCreatedNumber">
              <CheckCircle2 size={14} /> {request.materialized_business_number} · {request.materialized_record_code}
            </p>
          ) : null}
          <footer>
            {!review && request.state === "draft" ? (
              <button disabled={busyId === request.id} onClick={() => onAction(request, "submit")} type="button">
                <Send size={14} /> Enviar
              </button>
            ) : null}
            {!review && request.state === "draft" ? (
              <button
                className="ghost"
                disabled={busyId === request.id}
                onClick={() => onAction(request, "preview")}
                type="button"
              >
                <Eye size={14} /> Preview
              </button>
            ) : null}
            {!review && request.state === "returned" ? (
              <button disabled={busyId === request.id} onClick={() => onAction(request, "edit")} type="button">
                <RotateCcw size={14} /> Editar y volver a borrador
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
            {!review && request.state === "created" && request.materialized_workspace_id ? (
              <button disabled={busyId === request.id} onClick={() => onAction(request, "open")} type="button">
                <FolderTree size={14} /> Abrir Workspace
              </button>
            ) : null}
            {review && request.state === "submitted" ? (
              <button disabled={busyId === request.id} onClick={() => onAction(request, "start-review")} type="button">
                <Eye size={14} /> Iniciar revisión
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
            {review && request.state === "approved" ? (
              <button disabled={busyId === request.id} onClick={() => onAction(request, "materialize")} type="button">
                <FolderTree size={14} /> Materializar Workspace
              </button>
            ) : null}
          </footer>
        </article>
      ))}
    </div>
  );
}

function PhysicalOverview({ token, workspaceId }: { token: string; workspaceId: number }) {
  const [data, setData] = useState<PhysicalWorkspaceOverview | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    enterpriseStructureApi
      .physicalWorkspaceOverview(token, workspaceId)
      .then(setData)
      .catch((caught) => setError(errorMessage(caught)));
  }, [token, workspaceId]);
  if (error) return <div className="enterpriseAlert error">{error}</div>;
  if (!data) return <div className="projectRequestEmpty">Consultando Physical Workspace Overview…</div>;
  return (
    <section className="projectOverviewCard physicalOverviewCard">
      <header>
        <div>
          <span>{data.workspace_type_code.toUpperCase()} OVERVIEW</span>
          <h2>{data.workspace_name}</h2>
        </div>
        <strong>{data.status}</strong>
      </header>
      <div className="projectOverviewGrid">
        <div>
          <span>Business Number</span>
          <strong>{data.business_number}</strong>
        </div>
        <div>
          <span>Record Code</span>
          <strong>{data.record_code}</strong>
        </div>
        <div>
          <span>Parent</span>
          <strong>{data.parent_workspace}</strong>
        </div>
        <div>
          <span>Responsible</span>
          <strong>{data.responsible}</strong>
        </div>
        <div>
          <span>Template</span>
          <strong>{data.template}</strong>
        </div>
        <div>
          <span>Creation Request</span>
          <strong>{data.creation_request_number}</strong>
        </div>
      </div>
      <section>
        <h3>Atributos gobernados</h3>
        <dl className="physicalAttributeSummary">
          {Object.entries(data.attributes).map(([key, value]) => (
            <div key={key}>
              <dt>{key.replace(/_/g, " ")}</dt>
              <dd>{String(value || "—")}</dd>
            </div>
          ))}
        </dl>
      </section>
      <section>
        <h3>Módulos habilitados</h3>
        <div className="projectTagRow">
          {data.enabled_modules.length ? (
            data.enabled_modules.map((item) => <span key={item}>{item}</span>)
          ) : (
            <span>Sin módulos operativos profundos</span>
          )}
        </div>
      </section>
    </section>
  );
}

export default function PhysicalWorkspaceCreationWorkspace({
  token,
  view,
  initialType = "property",
  initialParentId,
  workspaceId,
  onBack,
  onCreated,
}: Props) {
  const [options, setOptions] = useState<PhysicalWorkspaceCreationOptions | null>(null);
  const [payload, setPayload] = useState<PhysicalWorkspaceRequestPayload>(() => emptyPayload(initialType));
  const [request, setRequest] = useState<PhysicalWorkspaceCreationRequest | null>(null);
  const [preview, setPreview] = useState<PhysicalWorkspaceRequestPreview | null>(null);
  const [requests, setRequests] = useState<PhysicalWorkspaceCreationRequest[]>([]);
  const [busy, setBusy] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [previewMessage, setPreviewMessage] = useState("");
  const [selectedOverviewId, setSelectedOverviewId] = useState<number | null>(null);
  const [requestFilters, setRequestFilters] = useState({
    request_number: "",
    workspace_name: "",
    workspace_type: "",
    state: "",
    parent: "",
    template: "",
    requestor: "",
    created_date: "",
  });
  const review = view === "review";

  async function loadOptions(type: PhysicalType, parentId?: number) {
    const result = await enterpriseStructureApi.physicalCreationOptions(token, type, parentId);
    setOptions(result);
    setPayload((current) => ({
      ...current,
      workspace_type_code: type,
      parent_workspace_id: parentId || result.locations[0]?.id || 0,
      template_config_id: result.templates[0]?.id || 0,
      responsible_user_id: current.responsible_user_id || result.responsibles[0]?.id || 0,
      attributes: parentId ? current.attributes : {},
      classifications: parentId ? current.classifications : [],
    }));
  }

  useEffect(() => {
    if (view !== "create") return;
    const timer = window.setTimeout(() => {
      loadOptions(initialType, initialParentId).catch((caught) => setError(errorMessage(caught)));
    }, 0);
    // loadOptions is intentionally bound to the initial route context.
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, initialType, initialParentId, view]);

  async function loadRequests() {
    setBusy(true);
    try {
      setRequests(await enterpriseStructureApi.physicalWorkspaceRequests(token, review));
      setError("");
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!["requests", "review"].includes(view)) return;
    const timer = window.setTimeout(() => void loadRequests(), 0);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, view]);

  const selectedLocation = useMemo(
    () => options?.locations.find((item) => item.id === payload.parent_workspace_id),
    [options, payload.parent_workspace_id]
  );
  const visibleRequests = useMemo(
    () =>
      requests.filter((item) => {
        const contains = (value: string, filter: string) => value.toLowerCase().includes(filter.trim().toLowerCase());
        return (
          (!requestFilters.request_number || contains(item.request_number, requestFilters.request_number)) &&
          (!requestFilters.workspace_name || contains(item.workspace_name, requestFilters.workspace_name)) &&
          (!requestFilters.workspace_type || item.workspace_type_code === requestFilters.workspace_type) &&
          (!requestFilters.state || item.state === requestFilters.state) &&
          (!requestFilters.parent || contains(item.parent_name, requestFilters.parent)) &&
          (!requestFilters.template || contains(item.template_name, requestFilters.template)) &&
          (!requestFilters.requestor || contains(item.requestor_name, requestFilters.requestor)) &&
          (!requestFilters.created_date || item.created_at.slice(0, 10) === requestFilters.created_date)
        );
      }),
    [requestFilters, requests]
  );

  async function selectType(type: PhysicalType) {
    setRequest(null);
    setPreview(null);
    setPayload(emptyPayload(type));
    setError("");
    try {
      await loadOptions(type);
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function selectParent(parentId: number) {
    setPreview(null);
    try {
      await loadOptions(payload.workspace_type_code, parentId);
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function createDraft(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const created = await enterpriseStructureApi.createPhysicalWorkspaceRequest(token, payload);
      setRequest(created);
      setPreview(await enterpriseStructureApi.physicalWorkspaceRequestPreview(token, created.id));
      setError("");
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function submitDraft() {
    if (!request) return;
    setBusy(true);
    try {
      setRequest(await enterpriseStructureApi.transitionPhysicalWorkspaceRequest(token, request, "submit"));
      setError("");
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function act(item: PhysicalWorkspaceCreationRequest, action: RequestAction) {
    setBusyId(item.id);
    try {
      if (action === "open") {
        if (item.materialized_workspace_id) setSelectedOverviewId(item.materialized_workspace_id);
        return;
      } else if (action === "preview") {
        const result = await enterpriseStructureApi.physicalWorkspaceRequestPreview(token, item.id);
        setPreviewMessage(
          `${item.request_number}: ${result.projected_business_number} · ${result.projected_record_code} (no persistente)`
        );
      } else if (action === "edit") {
        const workspaceName = window.prompt("Nombre del Workspace", item.workspace_name)?.trim();
        if (!workspaceName) return;
        await enterpriseStructureApi.updatePhysicalWorkspaceRequest(token, item.id, item.revision_version, {
          workspace_type_code: item.workspace_type_code,
          parent_workspace_id: item.parent_workspace_id,
          template_config_id: item.template_config_id,
          workspace_name: workspaceName,
          description: item.description,
          responsible_user_id: item.responsible_user_id,
          attributes: item.attributes,
          classifications: item.classifications,
        });
      } else if (action === "materialize") {
        await enterpriseStructureApi.materializePhysicalWorkspaceRequest(token, item);
        onCreated?.();
      } else {
        const reason = ["return", "reject"].includes(action)
          ? window.prompt(action === "return" ? "Motivo de devolución" : "Motivo de rechazo")?.trim()
          : undefined;
        if (["return", "reject"].includes(action) && !reason) return;
        await enterpriseStructureApi.transitionPhysicalWorkspaceRequest(token, item, action, reason);
      }
      await loadRequests();
      setError("");
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusyId(null);
    }
  }

  const title =
    view === "create"
      ? "Create Physical Workspace"
      : view === "requests"
        ? "My Physical Workspace Requests"
        : view === "review"
          ? "Physical Workspace Review Queue"
          : "Physical Workspace Overview";

  return (
    <section className="projectCreationWorkspace physicalCreationWorkspace">
      <header className="projectCreationHeader">
        <button className="ghost" onClick={onBack} type="button">
          <ArrowLeft size={16} /> Enterprise Explorer
        </button>
        <div>
          <span>USER MODE · ENTERPRISE STRATEGY MANAGER</span>
          <h2>{title}</h2>
        </div>
        <span className="governedBadge">
          <ShieldCheck size={15} /> Gate 06B · Gobernado
        </span>
      </header>
      {error ? (
        <div className="enterpriseAlert error" role="alert">
          <AlertTriangle size={16} /> {error}
        </div>
      ) : null}
      {previewMessage ? (
        <div className="enterpriseAlert success" role="status">
          <Eye size={16} /> {previewMessage}
        </div>
      ) : null}
      {view === "overview" && workspaceId ? <PhysicalOverview token={token} workspaceId={workspaceId} /> : null}
      {selectedOverviewId ? <PhysicalOverview token={token} workspaceId={selectedOverviewId} /> : null}
      {["requests", "review"].includes(view) ? (
        <section className="projectRequestPanel">
          <div className="projectListToolbar">
            <div>
              <ClipboardList size={18} />
              <strong>{review ? "Solicitudes pendientes de control" : "Solicitudes físicas creadas por usted"}</strong>
            </div>
            <button disabled={busy} onClick={() => void loadRequests()} type="button">
              {busy ? <LoaderCircle className="spin" size={14} /> : <RotateCcw size={14} />} Actualizar
            </button>
          </div>
          <div className="physicalRequestFilters" aria-label="Filtros de solicitudes físicas">
            <input
              aria-label="Request Number"
              placeholder="Request Number"
              value={requestFilters.request_number}
              onChange={(event) => setRequestFilters({ ...requestFilters, request_number: event.target.value })}
            />
            <input
              aria-label="Workspace Name filter"
              placeholder="Workspace Name"
              value={requestFilters.workspace_name}
              onChange={(event) => setRequestFilters({ ...requestFilters, workspace_name: event.target.value })}
            />
            <select
              aria-label="Workspace Type filter"
              value={requestFilters.workspace_type}
              onChange={(event) => setRequestFilters({ ...requestFilters, workspace_type: event.target.value })}
            >
              <option value="">Todos los tipos</option>
              <option value="property">PROPERTY</option>
              <option value="facility">FACILITY</option>
              <option value="warehouse">WAREHOUSE</option>
            </select>
            <select
              aria-label="State filter"
              value={requestFilters.state}
              onChange={(event) => setRequestFilters({ ...requestFilters, state: event.target.value })}
            >
              <option value="">Todos los estados</option>
              {Object.entries(labels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
            <input
              aria-label="Parent filter"
              placeholder="Parent"
              value={requestFilters.parent}
              onChange={(event) => setRequestFilters({ ...requestFilters, parent: event.target.value })}
            />
            <input
              aria-label="Template filter"
              placeholder="Template"
              value={requestFilters.template}
              onChange={(event) => setRequestFilters({ ...requestFilters, template: event.target.value })}
            />
            <input
              aria-label="Requestor filter"
              placeholder="Requestor"
              value={requestFilters.requestor}
              onChange={(event) => setRequestFilters({ ...requestFilters, requestor: event.target.value })}
            />
            <input
              aria-label="Created Date filter"
              type="date"
              value={requestFilters.created_date}
              onChange={(event) => setRequestFilters({ ...requestFilters, created_date: event.target.value })}
            />
          </div>
          <RequestCards
            busyId={busyId}
            onAction={(item, action) => void act(item, action)}
            requests={visibleRequests}
            review={review}
          />
        </section>
      ) : null}
      {view === "create" && options ? (
        <>
          <section className="physicalTypePicker" aria-label="Workspace Type Picker">
            {options.workspace_types.map((type) => (
              <button
                className={payload.workspace_type_code === type.code ? "active" : ""}
                key={type.code}
                onClick={() => void selectType(type.code)}
                type="button"
              >
                {type.code === "warehouse" ? <Warehouse size={19} /> : <Building2 size={19} />}
                <span>
                  <strong>{type.name}</strong>
                  <small>{type.domain_description || "Operational Physical Workspace"}</small>
                </span>
              </button>
            ))}
          </section>
          {options.blocked_reason ? (
            <section className="projectBlockedState">
              <AlertTriangle size={28} />
              <h3>
                {options.blocked_reason === "PHYSICAL_CREATION_POLICY_NOT_PUBLISHED"
                  ? "No hay una Creation Policy publicada"
                  : "No hay un Physical Template publicado y aplicable"}
              </h3>
              <p>
                Gate 06A mantiene las configuraciones reales en DRAFT. Un administrador debe validarlas y publicarlas
                bajo Four-Eyes antes de admitir solicitudes; esta pantalla no las publica automáticamente.
              </p>
            </section>
          ) : request ? (
            <section className="projectPreviewPanel">
              <header>
                <div>
                  <span>SOLICITUD FÍSICA CREADA</span>
                  <h3>
                    {request.request_number} · {request.workspace_name}
                  </h3>
                </div>
                <span className={`requestState ${request.state}`}>{labels[request.state]}</span>
              </header>
              {preview ? (
                <>
                  <div className="previewNotice">
                    <Eye size={17} />
                    <span>Preview no persistente: no consume Business Number ni crea Workspace.</span>
                  </div>
                  <div className="projectPreviewGrid">
                    <div>
                      <span>Business Number proyectado</span>
                      <strong>{preview.projected_business_number}</strong>
                    </div>
                    <div>
                      <span>Record Code proyectado</span>
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
                ) : (
                  <p>
                    <CheckCircle2 size={16} /> Solicitud enviada.
                  </p>
                )}
              </footer>
            </section>
          ) : (
            <form className="projectIntakeForm physicalIntakeForm" onSubmit={createDraft}>
              <section className="projectIntakeSection locationPicker">
                <header>
                  <span>1</span>
                  <div>
                    <h3>Workspace Location / Parent</h3>
                    <p>Opciones calculadas por Composition Rules y Creation Policy publicadas.</p>
                  </div>
                </header>
                <div className="projectLocationTree" role="radiogroup" aria-label="Workspace Location Picker">
                  {options.locations.map((location) => (
                    <label className={payload.parent_workspace_id === location.id ? "selected" : ""} key={location.id}>
                      <input
                        checked={payload.parent_workspace_id === location.id}
                        name="physical-parent"
                        onChange={() => void selectParent(location.id)}
                        type="radio"
                      />
                      <FolderTree size={16} />
                      <span>
                        <strong>{location.name}</strong>
                        <small>
                          {location.path.join(" / ")} · {location.workspace_type_code.toUpperCase()} ·{" "}
                          {location.record_code}
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
                  <span>2</span>
                  <div>
                    <h3>Common Intake</h3>
                    <p>Un único formulario parametrizado por Workspace Type.</p>
                  </div>
                </header>
                <div className="projectFormGrid">
                  <label className="wide">
                    Workspace Name
                    <input
                      required
                      value={payload.workspace_name}
                      onChange={(event) => setPayload({ ...payload, workspace_name: event.target.value })}
                    />
                  </label>
                  <label>
                    Physical Template
                    <select
                      required
                      value={payload.template_config_id || ""}
                      onChange={(event) => setPayload({ ...payload, template_config_id: Number(event.target.value) })}
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
                    Responsible
                    <select
                      required
                      value={payload.responsible_user_id || ""}
                      onChange={(event) => setPayload({ ...payload, responsible_user_id: Number(event.target.value) })}
                    >
                      <option value="">Seleccione…</option>
                      {options.responsibles.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.name} · {item.email}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="wide">
                    Description
                    <textarea
                      rows={3}
                      value={payload.description}
                      onChange={(event) => setPayload({ ...payload, description: event.target.value })}
                    />
                  </label>
                  <label>
                    Business Number
                    <input disabled placeholder="Asignado en Materialization" />
                  </label>
                  <label>
                    Record Code
                    <input disabled placeholder="Calculado en Materialization" />
                  </label>
                </div>
              </section>
              <section className="projectIntakeSection">
                <header>
                  <span>3</span>
                  <div>
                    <h3>{payload.workspace_type_code.toUpperCase()} Dynamic Attributes</h3>
                    <p>Campos derivados de la configuración vigente del Workspace Type.</p>
                  </div>
                </header>
                <div className="projectFormGrid dynamicPhysicalAttributes">
                  {options.dynamic_attributes.map((attribute) => (
                    <label key={attribute.code}>
                      {attribute.label}
                      {attribute.input_type === "classification" ? (
                        <select
                          required={attribute.required}
                          value={String(payload.attributes[attribute.code] || "")}
                          onChange={(event) => {
                            const value = event.target.value;
                            setPayload({
                              ...payload,
                              attributes: { ...payload.attributes, [attribute.code]: value },
                              classifications: value
                                ? [
                                    {
                                      category_set_code: `${payload.workspace_type_code}-type`,
                                      category_item_code: value,
                                    },
                                  ]
                                : [],
                            });
                          }}
                        >
                          <option value="">Seleccione…</option>
                          {attribute.options.map((item) => (
                            <option key={item.code} value={item.code}>
                              {item.label}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <input
                          required={attribute.required}
                          step={attribute.input_type === "decimal" ? "any" : undefined}
                          type={
                            attribute.input_type === "decimal"
                              ? "number"
                              : attribute.input_type === "date"
                                ? "date"
                                : "text"
                          }
                          value={String(payload.attributes[attribute.code] || "")}
                          onChange={(event) =>
                            setPayload({
                              ...payload,
                              attributes: { ...payload.attributes, [attribute.code]: event.target.value },
                            })
                          }
                        />
                      )}
                    </label>
                  ))}
                </div>
              </section>
              <footer className="projectFormFooter">
                <div>
                  <ShieldCheck size={18} />
                  <span>
                    Submit revalida tenant, parent, Composition Rules, template, policy, atributos y clasificaciones.
                  </span>
                </div>
                <button
                  disabled={
                    busy || !payload.parent_workspace_id || !payload.template_config_id || !payload.responsible_user_id
                  }
                  type="submit"
                >
                  {busy ? <LoaderCircle className="spin" size={16} /> : <Eye size={16} />} Crear borrador y
                  previsualizar
                </button>
              </footer>
            </form>
          )}
        </>
      ) : null}
    </section>
  );
}
