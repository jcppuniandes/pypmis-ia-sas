import { ArrowLeft, Building2, Clock3, ExternalLink, Search, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { workspaceContextApi, type MyWorkspaceFilters } from "./api";
import type { MyWorkspace, RecentWorkspace } from "./types";
import "./workspaceContext.css";

const initialFilters: MyWorkspaceFilters = {
  name: "",
  workspace_type: "",
  status: "",
  responsible: "",
  parent: "",
  business_number: "",
};

export default function MyWorkspacesPanel({ onBack, token }: { onBack: () => void; token: string }) {
  const navigate = useNavigate();
  const [filters, setFilters] = useState(initialFilters);
  const [workspaces, setWorkspaces] = useState<MyWorkspace[]>([]);
  const [recent, setRecent] = useState<RecentWorkspace[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const timer = window.setTimeout(() => {
      setLoading(true);
      workspaceContextApi
        .list(token, filters)
        .then((result) => {
          if (!active) return;
          setWorkspaces(result);
          setError("");
        })
        .catch((caught: unknown) => active && setError(caught instanceof Error ? caught.message : "Query failed"))
        .finally(() => active && setLoading(false));
    }, 200);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [filters, token]);

  useEffect(() => {
    let active = true;
    workspaceContextApi
      .recent(token)
      .then((result) => active && setRecent(result))
      .catch(() => active && setRecent([]));
    return () => {
      active = false;
    };
  }, [token]);

  function setFilter(key: keyof MyWorkspaceFilters, value: string) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  return (
    <section className="enterpriseWorkspace myWorkspacesPage">
      <button className="workspaceDirectoryBack" onClick={onBack} type="button">
        <ArrowLeft size={16} /> Enterprise Explorer
      </button>
      <CompactModuleHeader
        description="Vista transversal autorizada de Workspaces operativos y en ciclo de preparación."
        eyebrow="USER MODE · ENTERPRISE EXPLORER"
        metrics={[
          { label: "Results", value: workspaces.length },
          { label: "Recent", value: recent.length },
          { label: "Active", value: workspaces.filter((item) => item.status === "ACTIVE").length },
        ]}
        title="My Workspaces"
        tone="user"
      />

      <section className="myWorkspacesFilters" aria-label="My Workspaces filters">
        <label>
          <span>Name</span>
          <input value={filters.name} onChange={(event) => setFilter("name", event.target.value)} />
        </label>
        <label>
          <span>Workspace Type</span>
          <select value={filters.workspace_type} onChange={(event) => setFilter("workspace_type", event.target.value)}>
            <option value="">All</option>
            <option value="PROJECT">Project</option>
            <option value="PROPERTY">Property</option>
            <option value="FACILITY">Facility</option>
            <option value="WAREHOUSE">Warehouse</option>
          </select>
        </label>
        <label>
          <span>Status</span>
          <select value={filters.status} onChange={(event) => setFilter("status", event.target.value)}>
            <option value="">All</option>
            <option value="ACTIVE">Active</option>
            <option value="PENDING">Pending</option>
            <option value="ARCHIVED">Archived</option>
          </select>
        </label>
        <label>
          <span>Responsible</span>
          <input value={filters.responsible} onChange={(event) => setFilter("responsible", event.target.value)} />
        </label>
        <label>
          <span>Parent</span>
          <input value={filters.parent} onChange={(event) => setFilter("parent", event.target.value)} />
        </label>
        <label>
          <span>Business Number</span>
          <input
            value={filters.business_number}
            onChange={(event) => setFilter("business_number", event.target.value)}
          />
        </label>
      </section>

      {recent.length ? (
        <section className="recentWorkspaces" aria-label="Recent Workspaces">
          <header>
            <Clock3 size={17} /> <strong>Recent Workspaces</strong>
          </header>
          <div>
            {recent.map((item) => (
              <button key={item.workspace_id} onClick={() => navigate(item.last_route)} type="button">
                <strong>{item.workspace_name}</strong>
                <span>
                  {item.workspace_type} · {item.business_number}
                </span>
              </button>
            ))}
          </div>
        </section>
      ) : null}

      {error ? (
        <div className="enterpriseAlert error" role="alert">
          {error}
        </div>
      ) : null}
      <section className="myWorkspacesResults" aria-busy={loading}>
        <header>
          <Search size={17} />
          <strong>{loading ? "Loading…" : `${workspaces.length} Workspace(s)`}</strong>
        </header>
        <div className="myWorkspaceCards">
          {workspaces.map((workspace) => {
            const route =
              workspace.status === "PENDING" ? `/workspaces/${workspace.workspace_id}/overview` : workspace.last_route;
            return (
              <article key={workspace.workspace_id}>
                <div className="myWorkspaceCardTitle">
                  <Building2 size={18} />
                  <div>
                    <span>{workspace.workspace_type}</span>
                    <h3>{workspace.workspace_name}</h3>
                  </div>
                  <b data-status={workspace.status}>{workspace.status}</b>
                </div>
                <dl>
                  <div>
                    <dt>Business Number</dt>
                    <dd>{workspace.business_number}</dd>
                  </div>
                  <div>
                    <dt>Record Code</dt>
                    <dd>{workspace.record_code}</dd>
                  </div>
                  <div>
                    <dt>Responsible</dt>
                    <dd>
                      <UserRound size={13} /> {workspace.responsible || "Not assigned"}
                    </dd>
                  </div>
                  <div>
                    <dt>Parent</dt>
                    <dd>{workspace.parent || "Root"}</dd>
                  </div>
                </dl>
                <button onClick={() => navigate(route)} type="button">
                  <ExternalLink size={14} /> {workspace.status === "PENDING" ? "Open Overview" : "Open Workspace"}
                </button>
              </article>
            );
          })}
          {!loading && !workspaces.length ? (
            <p className="myWorkspacesEmpty">No authorized Workspaces match the filters.</p>
          ) : null}
        </div>
      </section>
    </section>
  );
}
