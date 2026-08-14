import { Archive, ArrowLeft, Building2, Clock3, FileText, Home, UserRound, Workflow } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, Navigate, useLocation, useNavigate, useParams } from "react-router-dom";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import IdeaLifecycleWorkspace from "../idea-demand/IdeaLifecycleWorkspace";
import { workspaceContextApi } from "./api";
import { WorkspaceContextProvider, useActiveWorkspaceContext } from "./WorkspaceContextProvider";
import "./workspaceContext.css";

function WorkspaceSwitcher({ currentId, token }: { currentId: number; token: string }) {
  const navigate = useNavigate();
  const [workspaces, setWorkspaces] = useState<Awaited<ReturnType<typeof workspaceContextApi.list>>>([]);

  useEffect(() => {
    let active = true;
    workspaceContextApi
      .list(token)
      .then((items) => active && setWorkspaces(items.filter((item) => ["ACTIVE", "ARCHIVED"].includes(item.status))))
      .catch(() => active && setWorkspaces([]));
    return () => {
      active = false;
    };
  }, [token]);

  return (
    <label className="workspaceSwitcher">
      <span>Switch Workspace</span>
      <select
        aria-label="Switch Workspace"
        onChange={(event) => {
          const target = workspaces.find((item) => item.workspace_id === Number(event.target.value));
          if (target) navigate(target.last_route || `/workspaces/${target.workspace_id}/home`);
        }}
        value={currentId}
      >
        {!workspaces.some((item) => item.workspace_id === currentId) ? (
          <option value={currentId}>Current</option>
        ) : null}
        {workspaces.map((item) => (
          <option key={item.workspace_id} value={item.workspace_id}>
            {item.workspace_name} · {item.workspace_type}
          </option>
        ))}
      </select>
    </label>
  );
}

function WorkspaceOperationalContent({ token, workspaceId }: { token: string; workspaceId: number }) {
  const { context, home, loading, error } = useActiveWorkspaceContext();
  const location = useLocation();
  const navigate = useNavigate();
  const routeParts = location.pathname.replace(/\/+$/, "").split("/");
  const routeCode = routeParts[routeParts.length - 1] || "home";

  if (loading) return <section className="workspaceContextLoading">Loading Workspace Context…</section>;
  if (error || !context || !home) {
    return (
      <section className="workspaceContextError" role="alert">
        <strong>Workspace unavailable</strong>
        <span>{error || "The backend did not return an operational context."}</span>
        <Link to="/app">Return to Enterprise Explorer</Link>
      </section>
    );
  }

  const selected = context.navigator.find((item) => item.code === routeCode);
  if (!selected && routeCode !== String(workspaceId))
    return <Navigate replace to={`/workspaces/${workspaceId}/home`} />;
  const current = selected ?? context.navigator.find((item) => item.code === "home");

  async function selectRoute(route: string, state: string) {
    if (state !== "READY") return;
    await workspaceContextApi.updateLastRoute(token, workspaceId, route);
    navigate(route);
  }

  return (
    <main className="workspaceOperationalShell">
      <header className="workspaceHeader">
        <Link className="workspaceBack" to="/app">
          <ArrowLeft size={16} /> Enterprise Explorer
        </Link>
        <div>
          <span>{context.identity.workspace_type} Workspace</span>
          <h1>{context.identity.workspace_name}</h1>
        </div>
        <WorkspaceSwitcher currentId={workspaceId} token={token} />
        <dl>
          <div>
            <dt>Business Number</dt>
            <dd>{context.identity.business_number}</dd>
          </div>
          <div>
            <dt>Record Code</dt>
            <dd>{context.identity.record_code}</dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd>{context.identity.workspace_status}</dd>
          </div>
          <div>
            <dt>Responsible</dt>
            <dd>{context.responsible.name || "Not assigned"}</dd>
          </div>
        </dl>
      </header>

      <nav className="workspaceBreadcrumb" aria-label="Workspace Breadcrumb">
        {context.breadcrumb.map((item, index) => (
          <span key={item.workspace_id}>
            {index ? <b aria-hidden="true">›</b> : null}
            {item.navigable ? (
              <Link to={`/workspaces/${item.workspace_id}/home`}>{item.workspace_name}</Link>
            ) : (
              item.workspace_name
            )}
          </span>
        ))}
      </nav>

      <div className="workspaceOperationalGrid">
        <aside className="workspaceNavigator">
          <header>
            <Workflow size={17} />
            <strong>Workspace Navigator</strong>
          </header>
          {context.navigator.map((item) => (
            <button
              aria-current={current?.code === item.code ? "page" : undefined}
              className={current?.code === item.code ? "active" : ""}
              disabled={item.state !== "READY"}
              key={item.code}
              onClick={() => void selectRoute(item.route, item.state)}
              title={item.reason}
              type="button"
            >
              <span>{item.label}</span>
              <small>{item.state}</small>
            </button>
          ))}
        </aside>

        <section className="workspaceOperationalContent">
          <CompactModuleHeader
            description={
              current?.code === "home"
                ? "Landing común del contexto operacional activo."
                : "Contenido Workspace-scoped validado por backend."
            }
            eyebrow="USER MODE · ACTIVE WORKSPACE CONTEXT"
            metrics={[
              { label: "Type", value: context.identity.workspace_type },
              { label: "Status", value: context.identity.workspace_status },
              {
                label: "Modules",
                value: context.navigator.filter(
                  (item) => item.state === "READY" && !["home", "overview"].includes(item.code)
                ).length,
              },
            ]}
            title={current?.label ?? "Workspace Home"}
            tone="user"
          />

          {current?.code === "ideas" ? (
            <IdeaLifecycleWorkspace token={token} workspaceId={workspaceId} />
          ) : current?.code === "home" ? (
            <>
              <div className="workspaceHomeFacts">
                <article>
                  <Building2 size={19} />
                  <span>Key Information</span>
                  <strong>{context.identity.business_number}</strong>
                  <small>{context.template.code || "No template snapshot"}</small>
                </article>
                <article>
                  <Clock3 size={19} />
                  <span>Status</span>
                  <strong>{home.status}</strong>
                  <small>{context.allowed_actions.join(" · ")}</small>
                </article>
                <article>
                  <UserRound size={19} />
                  <span>Responsible</span>
                  <strong>{context.responsible.name || "Not assigned"}</strong>
                  <small>{context.responsible.email}</small>
                </article>
                <article>
                  <Archive size={19} />
                  <span>Workspace Context</span>
                  <strong>{context.etag.slice(0, 12)}</strong>
                  <small>Version {context.version}</small>
                </article>
              </div>
              <section className="workspaceHomeSection">
                <header>
                  <Home size={18} />
                  <h2>Enabled Modules</h2>
                </header>
                <div className="workspaceModuleChips">
                  {context.navigator
                    .filter((item) => item.state === "READY" && !["home", "overview"].includes(item.code))
                    .map((item) => (
                      <span key={item.code}>{item.label}</span>
                    ))}
                  {!context.enabled_modules.length ? (
                    <em>No operational module is enabled for this Workspace.</em>
                  ) : null}
                </div>
              </section>
              <section className="workspaceHomeSection planned">
                <header>
                  <Clock3 size={18} />
                  <h2>Planned Modules</h2>
                </header>
                <div className="workspaceModuleChips">
                  {context.navigator
                    .filter((item) => item.state === "PLANNED")
                    .map((item) => (
                      <span key={item.code}>{item.label} · PLANNED</span>
                    ))}
                  {!context.planned_modules.length ? <em>No planned modules.</em> : null}
                </div>
              </section>
              <div className="workspaceHomeEmptyGrid">
                <article>
                  <h3>Recent Activity</h3>
                  <p>Capability not configured yet.</p>
                </article>
                <article>
                  <h3>Recent Documents</h3>
                  <p>No documents returned.</p>
                </article>
                <article>
                  <h3>My Tasks</h3>
                  <p>No task engine enabled.</p>
                </article>
                <article>
                  <h3>Related Workspaces</h3>
                  <p>{home.related_workspaces.length} relationship(s).</p>
                </article>
              </div>
            </>
          ) : current?.state === "PLANNED" ? (
            <section className="workspacePlanned">
              <Clock3 size={32} />
              <h2>{current.label} is PLANNED</h2>
              <p>No operational Module Definition or records were created.</p>
            </section>
          ) : current?.read_only ? (
            <section className="workspaceCapabilityEmpty">
              <Archive size={32} />
              <h2>{current.label} · Read only</h2>
              <p>The archived Workspace keeps its operational context without exposing mutation actions.</p>
            </section>
          ) : context.identity.workspace_type === "PROJECT" &&
            ["scope", "schedule", "cost", "documents", "reports"].includes(current?.code ?? "") ? (
            <section className="workspaceBridge">
              <Workflow size={32} />
              <h2>{current?.label}</h2>
              <p>This Project capability reuses the existing Project Controls workspace.</p>
              <Link to="/app">Open current Project Controls</Link>
            </section>
          ) : (
            <section className="workspaceCapabilityEmpty">
              <FileText size={32} />
              <h2>{current?.label}</h2>
              <p>The route and data scope are ready. Deep operational capability is intentionally outside Gate 06D.</p>
            </section>
          )}
        </section>
      </div>
    </main>
  );
}

export default function WorkspaceOperationalPage({ token }: { token: string }) {
  const workspaceId = Number(useParams<{ workspaceId: string }>().workspaceId);
  const location = useLocation();
  if (!Number.isInteger(workspaceId) || workspaceId < 1) return <Navigate replace to="/app" />;
  return (
    <WorkspaceContextProvider key={workspaceId} route={location.pathname} token={token} workspaceId={workspaceId}>
      <WorkspaceOperationalContent token={token} workspaceId={workspaceId} />
    </WorkspaceContextProvider>
  );
}
