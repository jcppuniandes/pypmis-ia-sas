import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { dashboard as dashboardApi } from "./api/dashboard";
import { projects as projectsApi } from "./api/projects";
import { useAuthStore } from "./store/auth";
import { useProjectStore } from "./store/project";
import type { Dashboard, Project } from "./types";
import LoginView from "./views/LoginView";

function RequireAuth({ children }: { children: ReactNode }) {
  const { token } = useAuthStore();
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function AppShell() {
  const { token, user, logout } = useAuthStore();
  const { dashboard, selectedProjectId, setDashboard, setSelectedProject } = useProjectStore();
  const [projectList, setProjectList] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadProjects() {
      setLoading(true);
      setError(null);
      try {
        const records = await projectsApi.list(token);
        if (cancelled) return;
        setProjectList(records);
        const nextProjectId = selectedProjectId ?? records[0]?.id ?? null;
        if (nextProjectId) {
          setSelectedProject(nextProjectId);
        } else {
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load projects");
          setLoading(false);
        }
      }
    }
    loadProjects();
    return () => {
      cancelled = true;
    };
  }, [token, selectedProjectId, setSelectedProject]);

  useEffect(() => {
    if (!selectedProjectId) return;
    const projectId = selectedProjectId;
    let cancelled = false;
    async function loadDashboard() {
      setLoading(true);
      setError(null);
      try {
        const nextDashboard = await dashboardApi.get(token, projectId);
        if (!cancelled) {
          setDashboard(nextDashboard);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load dashboard");
          setLoading(false);
        }
      }
    }
    loadDashboard();
    return () => {
      cancelled = true;
    };
  }, [token, selectedProjectId, setDashboard]);

  const constraintsByPackage = useMemo(() => {
    return (dashboard?.work_package_constraints ?? []).reduce<Record<number, number>>((acc, constraint) => {
      if (constraint.status === "open" && constraint.blocking) {
        acc[constraint.work_package_id] = (acc[constraint.work_package_id] ?? 0) + 1;
      }
      return acc;
    }, {});
  }, [dashboard?.work_package_constraints]);

  if (loading && !dashboard) {
    return <div className="loading">Loading workspace...</div>;
  }

  if (error || !dashboard) {
    return (
      <main>
        <section className="panel workspaceEmpty">
          <h1>Workspace unavailable</h1>
          <p>{error ?? "No project dashboard is available."}</p>
        </section>
      </main>
    );
  }

  const project = dashboard.project;
  const kpi = dashboard.project_kpi;

  return (
    <main>
      <header className="topbar">
        <div className="brandBlock">
          <p className="eyebrow">Project Controls</p>
          <h1>{project.name}</h1>
          <p className="productStatement">
            {project.code} / {project.phase} / {project.currency}
          </p>
        </div>
        <div className="headerActions">
          <div className="contextSwitch">
            <label>
              <span>Project</span>
              <select
                onChange={(event) => setSelectedProject(Number(event.target.value))}
                value={selectedProjectId ?? project.id}
              >
                {projectList.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.code}
                  </option>
                ))}
              </select>
            </label>
            <strong>{user?.email ?? "Signed in"}</strong>
            <button className="quickNavButton" onClick={logout} type="button">
              Logout
            </button>
          </div>
        </div>
      </header>

      <section className="controlSummary">
        <div>
          <span>PV</span>
          <strong>{currency(kpi.pv, project.currency)}</strong>
        </div>
        <div>
          <span>EV</span>
          <strong>{currency(kpi.ev, project.currency)}</strong>
        </div>
        <div>
          <span>AC</span>
          <strong>{currency(kpi.ac, project.currency)}</strong>
        </div>
        <div>
          <span>SPI</span>
          <strong>{kpi.spi.toFixed(3)}</strong>
        </div>
        <div>
          <span>CPI</span>
          <strong>{kpi.cpi.toFixed(3)}</strong>
        </div>
        <div>
          <span>AWP Ready</span>
          <strong>{dashboard.awp_summary.readiness_score.toFixed(1)}%</strong>
        </div>
      </section>

      <div className="unifierFrame">
        <aside className="navigatorRail">
          <div className="navigatorHeader">
            <strong>Control Flow</strong>
            <span>Essential views</span>
          </div>
          {[
            ["Baseline", dashboard.schedule_activity_count],
            ["Progress", dashboard.latest_progress_records.length],
            ["Costs", dashboard.cost_sheet.length],
            ["Decisions", dashboard.changes.length],
            ["Evidence", `${dashboard.document_control_summary.controlled_document_score.toFixed(0)}%`],
          ].map(([label, count]) => (
            <div className="navigatorItem active" key={label}>
              <span>{label}</span>
              <strong>{count}</strong>
            </div>
          ))}
          <div className="navigatorDivider">
            <span>Advanced</span>
          </div>
          <div className="navigatorItem">
            <span>Work Packages</span>
            <strong>{dashboard.awp_summary.total_packages}</strong>
          </div>
        </aside>

        <section className="viewPanel workspaceSection">
          <div className="panelHeader">
            <h2>AWP Minimum Register</h2>
            <span>
              {dashboard.awp_summary.cwp_count} CWP / {dashboard.awp_summary.iwp_count} IWP /{" "}
              {dashboard.awp_summary.twp_count} TWP / {dashboard.awp_summary.top_count} TOP
            </span>
          </div>

          <div className="awpSummary">
            <article className={dashboard.awp_summary.blocking_constraints ? "risk" : ""}>
              <span>Open Constraints</span>
              <strong>{dashboard.awp_summary.open_constraints}</strong>
              <small>{dashboard.awp_summary.blocking_constraints} blocking</small>
            </article>
            <article className={dashboard.awp_summary.high_priority_constraints ? "risk" : ""}>
              <span>High Priority</span>
              <strong>{dashboard.awp_summary.high_priority_constraints}</strong>
              <small>Before release</small>
            </article>
            <article>
              <span>Closure Evidence</span>
              <strong>{dashboard.awp_summary.closure_evidence_count}</strong>
              <small>Closed constraints</small>
            </article>
            <article>
              <span>Ready Packages</span>
              <strong>{dashboard.awp_summary.ready_for_release}</strong>
              <small>{dashboard.awp_summary.blocked_packages} blocked</small>
            </article>
          </div>

          <div className="viewSplit">
            <div className="panel">
              <div className="panelHeader compactHeader">
                <h2>Master Packages</h2>
                <span>{dashboard.work_packages.length} records</span>
              </div>
              <div className="workList">
                {dashboard.work_packages.map((workPackage) => (
                  <article
                    className={constraintsByPackage[workPackage.id] ? "blockedPackage" : ""}
                    key={workPackage.id}
                  >
                    <strong>
                      {workPackage.package_type} / {workPackage.code}
                    </strong>
                    <span>{workPackage.title}</span>
                    <small>
                      {workPackage.path_of_construction || "No path defined"} /{" "}
                      {statusLabel(workPackage.readiness_status)}
                    </small>
                    <div className="packageFacts">
                      <span>{controlAccountLabel(dashboard, workPackage.control_account_id)}</span>
                      <span>Release {workPackage.release_required_on ?? workPackage.planned_start ?? "Pending"}</span>
                      <span>{constraintsByPackage[workPackage.id] ?? 0} blockers</span>
                    </div>
                  </article>
                ))}
              </div>
            </div>

            <div className="panel">
              <div className="panelHeader compactHeader">
                <h2>Constraint Register</h2>
                <span>{dashboard.work_package_constraints.length} records</span>
              </div>
              <div className="workList">
                {dashboard.work_package_constraints.map((constraint) => (
                  <article
                    className={constraint.status === "open" && constraint.blocking ? "blockedPackage" : undefined}
                    key={constraint.id}
                  >
                    <strong>
                      {statusLabel(constraint.priority)} / {packageLabel(dashboard, constraint.work_package_id)}
                    </strong>
                    <span>{constraint.description}</span>
                    <small>
                      {constraint.constraint_type} / Required {constraint.required_by ?? "Pending"} /{" "}
                      {statusLabel(constraint.status)}
                    </small>
                    <div className="packageFacts">
                      <span>{constraint.owner_role}</span>
                      <span>{constraint.evidence_ref || "Evidence pending"}</span>
                      <span>{constraint.closed_on ? `Closed ${constraint.closed_on}` : "Open"}</span>
                    </div>
                  </article>
                ))}
              </div>
            </div>
          </div>

          <div className="panel wide">
            <div className="panelHeader compactHeader">
              <h2>Control Accounts</h2>
              <span>{dashboard.control_accounts.length} mapped accounts</span>
            </div>
            <table>
              <thead>
                <tr>
                  <th>Account</th>
                  <th>Owner</th>
                  <th>CBS / Contract</th>
                  <th>Measurement</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {dashboard.control_accounts.map((account) => (
                  <tr key={account.id}>
                    <td>
                      <strong>{account.code}</strong>
                      <span>{account.name}</span>
                    </td>
                    <td>{account.responsible}</td>
                    <td>
                      <strong>{account.cbs_code || "CBS pending"}</strong>
                      <span>{account.contract_ref || "Contract pending"}</span>
                    </td>
                    <td>{account.measurement_rule || "Physical progress rule pending"}</td>
                    <td>
                      <strong>{statusLabel(account.lifecycle_status)}</strong>
                      <span>{account.risk_ref || "No risk ref"}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </main>
  );
}

function currency(value: number, code: string) {
  return new Intl.NumberFormat("en-US", {
    currency: code || "USD",
    maximumFractionDigits: 0,
    style: "currency",
  }).format(value || 0);
}

function statusLabel(value: string) {
  return value
    ? value
        .split("_")
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(" ")
    : "Pending";
}

function packageLabel(dashboard: Dashboard, packageId: number) {
  const workPackage = dashboard.work_packages.find((item) => item.id === packageId);
  return workPackage ? workPackage.code : `WP-${packageId}`;
}

function controlAccountLabel(dashboard: Dashboard, accountId: number | null) {
  if (!accountId) return "Area level";
  const account = dashboard.control_accounts.find((item) => item.id === accountId);
  return account ? account.code : `CA-${accountId}`;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/app" replace />} />
      <Route path="/login" element={<LoginView />} />
      <Route
        path="/app/*"
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      />
    </Routes>
  );
}
