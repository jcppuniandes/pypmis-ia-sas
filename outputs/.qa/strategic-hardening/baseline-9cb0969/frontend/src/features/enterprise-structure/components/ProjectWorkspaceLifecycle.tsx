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
import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../../../api/client";
import { enterpriseStructureApi } from "../api";
import type { ProjectWorkspaceInitialization, ProjectWorkspaceListItem, ProjectWorkspaceOverview } from "../types";

const stateLabels: Record<string, string> = {
  NOT_STARTED: "No iniciada",
  INITIALIZING: "Inicializando",
  BLOCKED: "Bloqueada",
  READY_FOR_ACTIVATION: "Lista para activar",
  ACTIVATED: "Activada",
  FAILED: "Fallida",
};

function messageFrom(error: unknown) {
  if (!(error instanceof ApiError))
    return error instanceof Error ? error.message : "No fue posible completar la acción.";
  try {
    const body = JSON.parse(error.message) as { detail?: string | { code?: string; message?: string } };
    if (typeof body.detail === "string") return body.detail;
    if (body.detail?.code === "PROJECT_WORKSPACE_VERSION_CONFLICT")
      return "El workspace cambió. Actualice la vista antes de volver a ejecutar la acción.";
    return body.detail?.message || error.message;
  } catch {
    return error.message;
  }
}

function StateBadge({ state }: { state: string }) {
  return <span className={`workspaceLifecycleState ${state.toLowerCase()}`}>{stateLabels[state] || state}</span>;
}

function WorkspaceDetail({ token, workspaceId, onBack }: { token: string; workspaceId: number; onBack?: () => void }) {
  const [overview, setOverview] = useState<ProjectWorkspaceOverview | null>(null);
  const [initialization, setInitialization] = useState<ProjectWorkspaceInitialization | null>(null);
  const [preview, setPreview] = useState<ProjectWorkspaceInitialization | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const [nextOverview, nextInitialization] = await Promise.all([
        enterpriseStructureApi.projectWorkspaceOverview(token, workspaceId),
        enterpriseStructureApi.projectWorkspaceInitialization(token, workspaceId),
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

  // The memoized loader synchronizes this view with the selected canonical workspace.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => void load(), [load]);

  async function run(action: "preview" | "start" | "validate" | "activate") {
    if (!initialization) return;
    setBusy(true);
    try {
      const result =
        action === "preview"
          ? await enterpriseStructureApi.previewProjectWorkspaceInitialization(token, workspaceId)
          : await enterpriseStructureApi.transitionProjectWorkspace(
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
        {busy ? <LoaderCircle className="spin" size={18} /> : null} {error || "Consultando Project Overview…"}
      </div>
    );
  }
  const visible = preview || initialization;
  return (
    <section className="projectLifecycleWorkspace">
      {onBack ? (
        <button className="ghost lifecycleBack" onClick={onBack} type="button">
          ← My Project Workspaces
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
            <span>PROJECT OVERVIEW</span>
            <h2>{overview.project_name}</h2>
            <small>
              {overview.project_number} · {overview.record_code}
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
            <span>Plantilla</span>
            <strong>
              {visible.template_code || overview.template
                ? `${visible.template_code || overview.template} · r${visible.template_revision ?? "—"}`
                : "Sin snapshot histórico"}
            </strong>
          </article>
        </div>

        <div className="projectOverviewGrid">
          <div>
            <span>Ubicación</span>
            <strong>{overview.parent_workspace}</strong>
          </div>
          <div>
            <span>Project Manager</span>
            <strong>{overview.project_manager || "Sin asignar"}</strong>
          </div>
          <div>
            <span>Moneda</span>
            <strong>{overview.currency || "Sin definir"}</strong>
          </div>
          <div>
            <span>Activación</span>
            <strong>
              {overview.activated_at
                ? new Date(overview.activated_at).toLocaleString("es-CO")
                : overview.status === "active"
                  ? "Activo (registro histórico)"
                  : "Pendiente"}
            </strong>
          </div>
        </div>

        <nav className="lifecycleActions" aria-label="Acciones de inicialización">
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
              <ShieldCheck size={15} /> Activate Project Workspace
            </button>
          ) : null}
          {initialization.state === "ACTIVATED" ? (
            <span className="activatedNotice">
              <CheckCircle2 size={16} /> Workspace operativo
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
        <div className="checklistRows">
          {visible.checklist.map((item) => (
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
          {!visible.checklist.length && initialization.state === "ACTIVATED" ? (
            <p className="projectRequestEmpty">No aplica: el workspace ya se encuentra activo.</p>
          ) : null}
        </div>
      </section>

      <section className="enterprisePanel lifecycleModules">
        <header>
          <div>
            <span>CONFIGURATION CONTAINERS</span>
            <h3>Módulos habilitados</h3>
          </div>
        </header>
        <div>
          {visible.modules.map((module) => (
            <article key={module.module_key}>
              <strong>{module.module_key}</strong>
              <StateBadge state={module.state} />
              <small>Contenedor {module.configuration_container}; sin configuración operativa profunda.</small>
            </article>
          ))}
          {!visible.modules.length ? <p>No hay módulos habilitados para esta plantilla.</p> : null}
        </div>
      </section>
    </section>
  );
}

export default function ProjectWorkspaceLifecycle({ token, workspaceId }: { token: string; workspaceId?: number }) {
  const [items, setItems] = useState<ProjectWorkspaceListItem[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(workspaceId ?? null);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (workspaceId) return;
    setBusy(true);
    try {
      setItems(await enterpriseStructureApi.projectWorkspaces(token, status));
      setError("");
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(false);
    }
  }, [status, token, workspaceId]);

  // The memoized loader synchronizes the inventory with the selected filter.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => void load(), [load]);

  if (selectedId) {
    return (
      <WorkspaceDetail
        onBack={
          workspaceId
            ? undefined
            : () => {
                setSelectedId(null);
                void load();
              }
        }
        token={token}
        workspaceId={selectedId}
      />
    );
  }
  return (
    <section className="projectWorkspaceInventory">
      {error ? <div className="enterpriseAlert error">{error}</div> : null}
      <div className="projectListToolbar">
        <div>
          <ShieldCheck size={18} />
          <strong>Workspaces materializados y su preparación operativa</strong>
        </div>
        <label>
          <span>Estado</span>
          <select onChange={(event) => setStatus(event.target.value)} value={status}>
            <option value="">Todos</option>
            <option value="pending">Pending</option>
            <option value="active">Active</option>
          </select>
        </label>
        <button disabled={busy} onClick={() => void load()} type="button">
          <RefreshCw size={14} /> Actualizar
        </button>
      </div>
      <div className="projectWorkspaceCards">
        {items.map((item) => (
          <article key={item.workspace_id}>
            <header>
              <div>
                <span>{item.project_number}</span>
                <h3>{item.project_name}</h3>
              </div>
              <StateBadge state={item.initialization_state} />
            </header>
            <dl>
              <div>
                <dt>Record Code</dt>
                <dd>{item.record_code}</dd>
              </div>
              <div>
                <dt>Workspace</dt>
                <dd>{item.workspace_status}</dd>
              </div>
              <div>
                <dt>Project Manager</dt>
                <dd>{item.project_manager || "Sin asignar"}</dd>
              </div>
              <div>
                <dt>Plantilla</dt>
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
          <div className="projectRequestEmpty">No hay Project Workspaces para el filtro seleccionado.</div>
        ) : null}
      </div>
    </section>
  );
}
