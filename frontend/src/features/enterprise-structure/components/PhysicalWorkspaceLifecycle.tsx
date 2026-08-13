import {
  AlertTriangle,
  CheckCircle2,
  Eye,
  LoaderCircle,
  LockKeyhole,
  PlayCircle,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError } from "../../../api/client";
import { enterpriseStructureApi } from "../api";
import type {
  PhysicalWorkspaceInitialization,
  PhysicalWorkspaceListItem,
  PhysicalWorkspaceOverview,
  ProjectWorkspaceChecklistItem,
} from "../types";

const stateLabels: Record<string, string> = {
  NOT_STARTED: "No iniciada",
  INITIALIZING: "Inicializando",
  BLOCKED: "Bloqueada",
  READY_FOR_ACTIVATION: "Lista para activar",
  ACTIVATED: "Activada",
  FAILED: "Fallida",
  READY: "Preparado",
  PLANNED: "Planificado",
};

function messageFrom(error: unknown) {
  if (!(error instanceof ApiError))
    return error instanceof Error ? error.message : "No fue posible completar la acción.";
  try {
    const body = JSON.parse(error.message) as { detail?: string | { code?: string; message?: string } };
    if (typeof body.detail === "string") return body.detail;
    if (body.detail?.code === "PHYSICAL_WORKSPACE_VERSION_CONFLICT")
      return "El workspace cambió. Actualice la vista antes de volver a ejecutar la acción.";
    return body.detail?.message || error.message;
  } catch {
    return error.message;
  }
}

function StateBadge({ state }: { state: string }) {
  return <span className={`workspaceLifecycleState ${state.toLowerCase()}`}>{stateLabels[state] || state}</span>;
}

function ChecklistGroup({ title, items }: { title: string; items: ProjectWorkspaceChecklistItem[] }) {
  return (
    <section className="physicalChecklistGroup">
      <h4>{title}</h4>
      <div className="checklistRows">
        {items.map((item) => (
          <article className={item.status.toLowerCase()} key={item.code}>
            <span className="checkStatus">
              {item.status === "PASS" ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
            </span>
            <div>
              <strong>{item.code}</strong>
              <p>{item.message}</p>
            </div>
            {item.blocking ? (
              <span className="blockingFlag">
                <LockKeyhole size={12} /> Blocking
              </span>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}

function WorkspaceDetail({ token, workspaceId, onBack }: { token: string; workspaceId: number; onBack?: () => void }) {
  const [overview, setOverview] = useState<PhysicalWorkspaceOverview | null>(null);
  const [initialization, setInitialization] = useState<PhysicalWorkspaceInitialization | null>(null);
  const [preview, setPreview] = useState<PhysicalWorkspaceInitialization | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const [nextOverview, nextInitialization] = await Promise.all([
        enterpriseStructureApi.physicalWorkspaceOverview(token, workspaceId),
        enterpriseStructureApi.physicalWorkspaceInitialization(token, workspaceId),
      ]);
      setOverview(nextOverview);
      setInitialization(nextInitialization);
      setError("");
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(false);
    }
  }, [token, workspaceId]);

  // The memoized loader synchronizes both lifecycle contracts with the canonical workspace.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => void load(), [load]);

  async function run(action: "preview" | "start" | "validate" | "activate") {
    if (!initialization) return;
    setBusy(true);
    try {
      const result =
        action === "preview"
          ? await enterpriseStructureApi.previewPhysicalWorkspaceInitialization(token, workspaceId)
          : await enterpriseStructureApi.transitionPhysicalWorkspace(
              token,
              workspaceId,
              initialization.revision_version,
              action
            );
      if (action === "preview") setPreview(result);
      else {
        setInitialization(result);
        setPreview(null);
        await load();
      }
      setError("");
    } catch (caught) {
      const message = messageFrom(caught);
      await load();
      setError(message);
    } finally {
      setBusy(false);
    }
  }

  if (!overview || !initialization) {
    return (
      <div className="projectRequestEmpty">
        {busy ? <LoaderCircle className="spin" size={18} /> : null} {error || "Consultando Physical Workspace…"}
      </div>
    );
  }
  const visible = preview || initialization;
  return (
    <section className="projectLifecycleWorkspace physicalLifecycleWorkspace">
      {onBack ? (
        <button className="ghost lifecycleBack" onClick={onBack} type="button">
          ← My Physical Workspaces
        </button>
      ) : null}
      {error ? (
        <div className="enterpriseAlert error" role="alert">
          <AlertTriangle size={16} /> {error}
        </div>
      ) : null}
      <section className="projectOverviewCard lifecycleOverview">
        <header>
          <div>
            <span>{overview.workspace_type_code.toUpperCase()} OVERVIEW</span>
            <h2>{overview.workspace_name}</h2>
            <small>
              {overview.business_number} · {overview.record_code}
            </small>
          </div>
          <div className="lifecycleStateStack">
            <strong className={`workspaceStatus ${overview.status}`}>{overview.status}</strong>
            <StateBadge state={initialization.state} />
          </div>
        </header>
        <div className="initializationProgress" aria-label={`Inicialización ${visible.progress_percent}%`}>
          <span style={{ width: `${visible.progress_percent}%` }} />
        </div>
        <div className="lifecycleMetrics">
          <article>
            <span>Avance</span>
            <strong>{visible.progress_percent}%</strong>
          </article>
          <article>
            <span>Bloqueos</span>
            <strong>{visible.blocker_count}</strong>
          </article>
          <article>
            <span>Advertencias</span>
            <strong>{visible.warning_count}</strong>
          </article>
          <article>
            <span>Plantilla exacta</span>
            <strong>
              {visible.template_code} · r{visible.template_revision ?? "—"}
            </strong>
          </article>
        </div>
        <div className="projectOverviewGrid">
          <div>
            <span>Parent</span>
            <strong>{overview.parent_workspace}</strong>
          </div>
          <div>
            <span>Responsible</span>
            <strong>{overview.responsible || "Sin asignar"}</strong>
          </div>
          <div>
            <span>External Key</span>
            <strong>{visible.external_key}</strong>
          </div>
          <div>
            <span>Activación</span>
            <strong>
              {overview.activated_at ? new Date(overview.activated_at).toLocaleString("es-CO") : "Pendiente"}
            </strong>
          </div>
        </div>
        <nav className="lifecycleActions" aria-label="Acciones de inicialización física">
          {initialization.state !== "ACTIVATED" ? (
            <button className="ghost" disabled={busy} onClick={() => void run("preview")} type="button">
              <Eye size={15} /> Initialization Preview
            </button>
          ) : null}
          {overview.can_initialize && ["NOT_STARTED", "BLOCKED", "FAILED"].includes(initialization.state) ? (
            <button disabled={busy} onClick={() => void run("start")} type="button">
              <PlayCircle size={15} /> {initialization.state === "NOT_STARTED" ? "Start Initialization" : "Reintentar"}
            </button>
          ) : null}
          {overview.can_initialize &&
          initialization.persisted &&
          ["INITIALIZING", "BLOCKED", "FAILED"].includes(initialization.state) ? (
            <button className="ghost" disabled={busy} onClick={() => void run("validate")} type="button">
              <RefreshCw size={15} /> Validar
            </button>
          ) : null}
          {overview.can_activate && initialization.state === "READY_FOR_ACTIVATION" ? (
            <button className="activate" disabled={busy} onClick={() => void run("activate")} type="button">
              <ShieldCheck size={15} /> Activate Physical Workspace
            </button>
          ) : null}
          {initialization.state === "ACTIVATED" ? (
            <span className="activatedNotice">
              <CheckCircle2 size={16} /> Workspace físico operativo
            </span>
          ) : null}
        </nav>
      </section>

      <section className="enterprisePanel lifecycleChecklist">
        <header>
          <div>
            <span>CONTROL DE PREPARACIÓN</span>
            <h3>{preview ? "Initialization Preview" : "Initialization Checklist"}</h3>
          </div>
          {preview ? (
            <button className="ghost" onClick={() => setPreview(null)} type="button">
              Cerrar preview
            </button>
          ) : null}
        </header>
        <ChecklistGroup items={visible.common_checklist} title="Checklist común" />
        <ChecklistGroup items={visible.type_specific_checklist} title={`Checklist ${visible.workspace_type_code}`} />
      </section>

      <section className="enterprisePanel lifecycleModules">
        <header>
          <div>
            <span>MODULE READINESS</span>
            <h3>Preparación de módulos</h3>
          </div>
        </header>
        <div>
          {visible.modules.map((module) => (
            <article key={module.module_key}>
              <strong>{module.module_key}</strong>
              <StateBadge state={module.state} />
              <small>
                {module.planned
                  ? "Módulo futuro marcado PLANNED; no se creó persistencia operativa."
                  : "Configuración base validada; sin operación profunda en Gate 06C."}
              </small>
            </article>
          ))}
        </div>
      </section>
    </section>
  );
}

export default function PhysicalWorkspaceLifecycle({ token, workspaceId }: { token: string; workspaceId?: number }) {
  const [items, setItems] = useState<PhysicalWorkspaceListItem[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(workspaceId ?? null);
  const [filters, setFilters] = useState({ workspace_type: "", workspace_status: "", initialization_status: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const query = useMemo(() => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => value && params.set(key, value));
    return params.toString();
  }, [filters]);
  const load = useCallback(async () => {
    if (workspaceId) return;
    setBusy(true);
    try {
      setItems(await enterpriseStructureApi.physicalWorkspaces(token, query));
      setError("");
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(false);
    }
  }, [query, token, workspaceId]);
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => void load(), [load]);
  if (selectedId) {
    return (
      <WorkspaceDetail
        onBack={workspaceId ? undefined : () => setSelectedId(null)}
        token={token}
        workspaceId={selectedId}
      />
    );
  }
  return (
    <section className="projectWorkspaceInventory physicalWorkspaceInventory">
      {error ? <div className="enterpriseAlert error">{error}</div> : null}
      <div className="projectListToolbar physicalLifecycleFilters">
        <div>
          <ShieldCheck size={18} />
          <strong>Physical Workspaces y preparación operativa</strong>
        </div>
        <select
          aria-label="Workspace Type"
          onChange={(event) => setFilters({ ...filters, workspace_type: event.target.value })}
          value={filters.workspace_type}
        >
          <option value="">Todos los tipos</option>
          <option value="property">Property</option>
          <option value="facility">Facility</option>
          <option value="warehouse">Warehouse</option>
        </select>
        <select
          aria-label="Workspace Status"
          onChange={(event) => setFilters({ ...filters, workspace_status: event.target.value })}
          value={filters.workspace_status}
        >
          <option value="">Todos los estados</option>
          <option value="pending">Pending</option>
          <option value="active">Active</option>
        </select>
        <select
          aria-label="Initialization Status"
          onChange={(event) => setFilters({ ...filters, initialization_status: event.target.value })}
          value={filters.initialization_status}
        >
          <option value="">Toda preparación</option>
          {Object.entries(stateLabels)
            .filter(([key]) => !["READY", "PLANNED"].includes(key))
            .map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
        </select>
        <button disabled={busy} onClick={() => void load()} type="button">
          <RefreshCw size={14} /> Actualizar
        </button>
      </div>
      <div className="projectWorkspaceCards">
        {items.map((item) => (
          <article key={item.workspace_id}>
            <header>
              <div>
                <span>
                  {item.workspace_type_code.toUpperCase()} · {item.business_number}
                </span>
                <h3>{item.workspace_name}</h3>
              </div>
              <StateBadge state={item.initialization_state} />
            </header>
            <dl>
              <div>
                <dt>Record Code</dt>
                <dd>{item.record_code}</dd>
              </div>
              <div>
                <dt>Parent</dt>
                <dd>{item.parent}</dd>
              </div>
              <div>
                <dt>Responsible</dt>
                <dd>{item.responsible || "Sin asignar"}</dd>
              </div>
              <div>
                <dt>Template</dt>
                <dd>{item.template_code || "Sin snapshot"}</dd>
              </div>
            </dl>
            <footer>
              <span>
                {item.blocker_count} bloqueo(s) · {item.warning_count} advertencia(s)
              </span>
              <button onClick={() => setSelectedId(item.workspace_id)} type="button">
                <Eye size={14} /> Abrir
              </button>
            </footer>
          </article>
        ))}
        {!busy && !items.length ? (
          <div className="projectRequestEmpty">No hay Physical Workspaces para el filtro seleccionado.</div>
        ) : null}
      </div>
    </section>
  );
}
