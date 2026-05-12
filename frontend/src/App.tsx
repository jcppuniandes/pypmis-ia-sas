import { useEffect, useMemo, useState, type ChangeEvent, type FormEvent, type ReactNode } from "react";
import { Building2, FileUp, GitBranch } from "lucide-react";
import { Navigate, Route, Routes } from "react-router-dom";
import { dashboard as dashboardApi } from "./api/dashboard";
import { projects as projectsApi } from "./api/projects";
import ProductLogo from "./components/ProductLogo";
import { useAuthStore } from "./store/auth";
import { useProjectStore } from "./store/project";
import type { Dashboard, Project } from "./types";
import LoginView from "./views/LoginView";

function RequireAuth({ children }: { children: ReactNode }) {
  const { token } = useAuthStore();
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

type ControlFlowView = "dashboard" | "baseline" | "progress" | "costs" | "decisions" | "evidence" | "work-packages";

function AppShell() {
  const { token, user, logout } = useAuthStore();
  const { dashboard, selectedProjectId, setDashboard, setSelectedProject } = useProjectStore();
  const [projectList, setProjectList] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [projectDraft, setProjectDraft] = useState({
    code: "",
    name: "",
    phase: "Planning",
    currency: "USD",
    start_date: "",
    finish_date: "",
  });
  const [projectAction, setProjectAction] = useState(false);
  const [projectMessage, setProjectMessage] = useState<string | null>(null);
  const [projectError, setProjectError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [activeControlView, setActiveControlView] = useState<ControlFlowView>("dashboard");

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

  async function refreshDashboard(projectId: number) {
    const nextDashboard = await dashboardApi.get(token, projectId);
    setDashboard(nextDashboard);
  }

  async function handleProjectCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setProjectAction(true);
    setProjectError(null);
    setProjectMessage(null);
    try {
      const created = await projectsApi.create(token, {
        code: projectDraft.code.trim(),
        name: projectDraft.name.trim(),
        phase: projectDraft.phase,
        currency: projectDraft.currency.trim().toUpperCase() || "USD",
        start_date: projectDraft.start_date || null,
        finish_date: projectDraft.finish_date || null,
      });
      setProjectList((current) =>
        current.some((projectItem) => projectItem.id === created.id)
          ? current.map((projectItem) => (projectItem.id === created.id ? created : projectItem))
          : [...current, created],
      );
      setSelectedProject(created.id);
      setProjectDraft({
        code: "",
        name: "",
        phase: "Planning",
        currency: created.currency || "USD",
        start_date: "",
        finish_date: "",
      });
      setProjectMessage(`Project ${created.code} created and selected.`);
    } catch (err) {
      setProjectError(err instanceof Error ? err.message : "Could not create project");
    } finally {
      setProjectAction(false);
    }
  }

  async function handleScheduleUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || !selectedProjectId) return;
    setUploading(true);
    setUploadError(null);
    setUploadMessage(null);
    try {
      await projectsApi.uploadSchedule(token, selectedProjectId, file);
      await refreshDashboard(selectedProjectId);
      setUploadMessage(`${file.name} uploaded. Data Quality Gate refreshed.`);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Could not upload schedule");
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  }

  function handleControlFlowNavigate(view: ControlFlowView) {
    setActiveControlView(view);
    document.getElementById("control-flow-content")?.scrollIntoView?.({ block: "start", behavior: "smooth" });
  }

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
  const currentMembership = dashboard.project_team.find((member) => member.user.id === user?.id)?.membership;
  const canConfigure = Boolean(currentMembership?.can_configure);
  const canUploadSchedule = currentMembership?.role === "Planner" || currentMembership?.role === "Control Manager";
  const activeImport = dashboard.schedule_import;
  const controlFlowItems: Array<{ key: ControlFlowView; label: string; count: string | number }> = [
    { key: "dashboard", label: "Dashboard", count: `${kpi.spi.toFixed(2)} SPI` },
    { key: "baseline", label: "Baseline", count: dashboard.schedule_activity_count },
    { key: "progress", label: "Progress", count: dashboard.latest_progress_records.length },
    { key: "costs", label: "Costs", count: dashboard.cost_sheet.length },
    { key: "decisions", label: "Decisions", count: dashboard.changes.length },
    {
      key: "evidence",
      label: "Evidence",
      count: `${dashboard.document_control_summary.controlled_document_score.toFixed(0)}%`,
    },
  ];

  return (
    <main>
      <header className="topbar">
        <div className="brandBlock">
          <ProductLogo compact />
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

      <section className="projectWorkspace" aria-label="Project workspace and control flow">
        <aside className="projectWorkspaceRail">
          <form className="adminPanel" onSubmit={handleProjectCreate}>
            <div className="panelHeader">
              <h2>
                <Building2 size={18} /> Project Shell
              </h2>
              <span>{projectList.length} projects</span>
            </div>
            <div className="formColumns">
              <label>
                <span>Code</span>
                <input
                  disabled={!canConfigure || projectAction}
                  onChange={(event) => setProjectDraft((current) => ({ ...current, code: event.target.value }))}
                  placeholder="PRJ-001"
                  required
                  value={projectDraft.code}
                />
              </label>
              <label>
                <span>Phase</span>
                <select
                  disabled={!canConfigure || projectAction}
                  onChange={(event) => setProjectDraft((current) => ({ ...current, phase: event.target.value }))}
                  value={projectDraft.phase}
                >
                  <option value="Planning">Planning</option>
                  <option value="Execution">Execution</option>
                  <option value="Closeout">Closeout</option>
                </select>
              </label>
            </div>
            <label>
              <span>Name</span>
              <input
                disabled={!canConfigure || projectAction}
                onChange={(event) => setProjectDraft((current) => ({ ...current, name: event.target.value }))}
                placeholder="Project control shell name"
                required
                value={projectDraft.name}
              />
            </label>
            <div className="formColumns">
              <label>
                <span>Currency</span>
                <input
                  disabled={!canConfigure || projectAction}
                  maxLength={3}
                  onChange={(event) =>
                    setProjectDraft((current) => ({ ...current, currency: event.target.value.toUpperCase() }))
                  }
                  value={projectDraft.currency}
                />
              </label>
              <label>
                <span>Start</span>
                <input
                  disabled={!canConfigure || projectAction}
                  onChange={(event) => setProjectDraft((current) => ({ ...current, start_date: event.target.value }))}
                  type="date"
                  value={projectDraft.start_date}
                />
              </label>
              <label>
                <span>Finish</span>
                <input
                  disabled={!canConfigure || projectAction}
                  onChange={(event) => setProjectDraft((current) => ({ ...current, finish_date: event.target.value }))}
                  type="date"
                  value={projectDraft.finish_date}
                />
              </label>
            </div>
            <button className="workflowAction primary" disabled={!canConfigure || projectAction} type="submit">
              {projectAction ? "Creating..." : "Create Project Shell"}
            </button>
            {projectMessage && <div className="uploadMessage success">{projectMessage}</div>}
            {projectError && <div className="uploadMessage error">{projectError}</div>}
          </form>

          <aside className="navigatorRail" aria-label="Control Flow">
            <div className="navigatorHeader">
              <strong>Control Flow</strong>
              <span>Essential views</span>
            </div>
            {controlFlowItems.map((item) => (
              <button
                aria-current={activeControlView === item.key ? "page" : undefined}
                className={activeControlView === item.key ? "navigatorItem active" : "navigatorItem"}
                key={item.key}
                onClick={() => handleControlFlowNavigate(item.key)}
                type="button"
              >
                <span>{item.label}</span>
                <strong>{item.count}</strong>
              </button>
            ))}
            <div className="navigatorDivider">
              <span>Advanced</span>
            </div>
            <button
              aria-current={activeControlView === "work-packages" ? "page" : undefined}
              className={activeControlView === "work-packages" ? "navigatorItem active" : "navigatorItem"}
              onClick={() => handleControlFlowNavigate("work-packages")}
              type="button"
            >
              <span>Work Packages</span>
              <strong>{dashboard.awp_summary.total_packages}</strong>
            </button>
          </aside>
        </aside>

        <section className="projectDashboardArea" aria-label="Control dashboard">
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

          <section className="flowBand" aria-label="Project control process flow">
            <div className="flowTrack">
              {[
                ["Project Shell", "Create"],
                ["Team Roles", currentMembership?.role ?? "Membership"],
                ["XML/XER Intake", activeImport ? "Loaded" : "Open"],
                ["Data Quality Gate", `${activeImport?.quality_score.toFixed(0) ?? "0"}%`],
                ["Control Accounts", dashboard.control_accounts.length],
                ["AWP Packages", dashboard.awp_summary.total_packages],
                ["Control Core", `${kpi.spi.toFixed(2)} SPI`],
              ].map(([label, value], index, items) => (
                <div className="flowStepWrap" key={label}>
                  <div className="flowStep">
                    <strong>{label}</strong>
                    <span>{value}</span>
                  </div>
                  {index < items.length - 1 && <div className="flowArrow">/</div>}
                </div>
              ))}
            </div>
          </section>

          <section aria-live="polite" className="viewPanel workspaceSection" id="control-flow-content">
          {activeControlView === "dashboard" && (
            <>
              <div className="panelHeader">
                <h2>Control Dashboard</h2>
                <span>
                  {project.code} / {project.phase}
                </span>
              </div>
              <div className="awpSummary">
                <article>
                  <span>PV</span>
                  <strong>{currency(kpi.pv, project.currency)}</strong>
                  <small>Planned value</small>
                </article>
                <article>
                  <span>EV</span>
                  <strong>{currency(kpi.ev, project.currency)}</strong>
                  <small>Earned value</small>
                </article>
                <article className={kpi.cpi < 0.95 ? "risk" : ""}>
                  <span>CPI</span>
                  <strong>{kpi.cpi.toFixed(3)}</strong>
                  <small>Cost performance</small>
                </article>
                <article className={kpi.spi < 0.95 ? "risk" : ""}>
                  <span>SPI</span>
                  <strong>{kpi.spi.toFixed(3)}</strong>
                  <small>Schedule performance</small>
                </article>
              </div>
              <div className="viewSplit">
                <div className="panel">
                  <div className="panelHeader compactHeader">
                    <h2>Control Core Status</h2>
                    <span>{dashboard.control_accounts.length} accounts</span>
                  </div>
                  <div className="workList">
                    <article>
                      <strong>{activeImport ? "Baseline loaded" : "Baseline pending"}</strong>
                      <span>
                        {activeImport
                          ? `${activeImport.baseline_name} / quality ${activeImport.quality_score.toFixed(0)}%`
                          : "Upload XML/XER to start the baseline and control workflow."}
                      </span>
                      <small>
                        {dashboard.schedule_activity_count} activities / {dashboard.schedule_findings.length} findings
                      </small>
                    </article>
                    <article>
                      <strong>AWP readiness {dashboard.awp_summary.readiness_score.toFixed(1)}%</strong>
                      <span>
                        {dashboard.awp_summary.ready_for_release} ready / {dashboard.awp_summary.blocked_packages} blocked
                      </span>
                      <small>{dashboard.awp_summary.total_packages} work packages</small>
                    </article>
                  </div>
                </div>
                <div className="panel">
                  <div className="panelHeader compactHeader">
                    <h2>Control Flow Snapshot</h2>
                    <span>Live project controls</span>
                  </div>
                  <div className="loopList">
                    {(dashboard.flow ?? []).length ? (
                      dashboard.flow.map((item) => (
                        <div key={item.name}>
                          <strong>{item.name}</strong>
                          <span>
                            {item.state} / {item.purpose}
                          </span>
                        </div>
                      ))
                    ) : (
                      <>
                        <div>
                          <strong>Baseline</strong>
                          <span>{dashboard.schedule_activity_count} activities loaded</span>
                        </div>
                        <div>
                          <strong>Progress</strong>
                          <span>{dashboard.latest_progress_records.length} records captured</span>
                        </div>
                        <div>
                          <strong>Costs</strong>
                          <span>{dashboard.cost_sheet.length} cost lines available</span>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              </div>
            </>
          )}
          {activeControlView === "baseline" && (
            <>
              <div className="panelHeader">
                <h2>Baseline Control</h2>
                <span>
                  {dashboard.schedule_activity_count} activities / {dashboard.schedule_relationship_count} links
                </span>
              </div>
              <div className="gateFacts">
                <div>
                  <span>Current Baseline</span>
                  <strong>{activeImport?.baseline_name ?? "Pending upload"}</strong>
                </div>
                <div>
                  <span>Data Quality Gate</span>
                  <strong>
                    {activeImport ? `${activeImport.quality_score.toFixed(0)}% / ${activeImport.status}` : "Open"}
                  </strong>
                </div>
                <div>
                  <span>Data Date</span>
                  <strong>{activeImport?.data_date ?? "Pending"}</strong>
                </div>
                <div>
                  <span>Baseline Versions</span>
                  <strong>{dashboard.baseline_versions.length}</strong>
                </div>
              </div>
              <div className="viewSplit">
                <div className="panel">
                  <div className="panelHeader compactHeader">
                    <h2>Baseline Versions</h2>
                    <span>{dashboard.baseline_versions.length} records</span>
                  </div>
                  <div className="workList">
                    {dashboard.baseline_versions.length ? (
                      dashboard.baseline_versions.map((baseline) => (
                        <article key={baseline.id}>
                          <strong>
                            BL-{baseline.version_no.toString().padStart(2, "0")} / {statusLabel(baseline.status)}
                          </strong>
                          <span>{baseline.name}</span>
                          <small>
                            {baseline.data_date ?? "No data date"} / Quality {baseline.quality_score.toFixed(0)}%
                          </small>
                        </article>
                      ))
                    ) : (
                      <article>
                        <strong>No baseline versions yet</strong>
                        <span>Upload XML/XER to create the first controlled schedule baseline.</span>
                      </article>
                    )}
                  </div>
                </div>
                <div className="panel">
                  <div className="panelHeader compactHeader">
                    <h2>Quality Findings</h2>
                    <span>{dashboard.schedule_findings.length} records</span>
                  </div>
                  <div className="qualityList">
                    {dashboard.schedule_findings.length ? (
                      dashboard.schedule_findings.map((finding) => (
                        <article key={finding.id}>
                          <div>
                            <strong>{finding.check_code}</strong>
                            <span className={`qualityStatus ${finding.severity.toLowerCase()}`}>
                              {statusLabel(finding.severity)}
                            </span>
                          </div>
                          <p>{finding.message}</p>
                          <small>{finding.item_count} items</small>
                        </article>
                      ))
                    ) : (
                      <article>
                        <div>
                          <strong>No findings</strong>
                          <span className="qualityStatus pass">Pass</span>
                        </div>
                        <p>The active schedule has no stored QA findings.</p>
                      </article>
                    )}
                  </div>
                </div>
              </div>
            </>
          )}
          {activeControlView === "progress" && (
            <>
              <div className="panelHeader">
                <h2>Progress Control</h2>
                <span>{dashboard.latest_progress_records.length} records</span>
              </div>
              <div className="workList">
                {dashboard.latest_progress_records.length ? (
                  dashboard.latest_progress_records.map((record) => (
                    <article key={record.id}>
                      <strong>{controlAccountLabel(dashboard, record.control_account_id)}</strong>
                      <span>{record.physical_percent.toFixed(1)}% physical progress</span>
                      <small>
                        {record.quantity_installed} installed / {record.labor_hours} hours /{" "}
                        {record.reported_on ?? "No report date"}
                      </small>
                    </article>
                  ))
                ) : (
                  <article>
                    <strong>No progress captured</strong>
                    <span>Progress records will appear here after field updates are captured.</span>
                  </article>
                )}
              </div>
            </>
          )}
          {activeControlView === "costs" && (
            <>
              <div className="panelHeader">
                <h2>Cost Control</h2>
                <span>{dashboard.cost_sheet.length} cost lines</span>
              </div>
              <table>
                <thead>
                  <tr>
                    <th>Control Account</th>
                    <th>CBS</th>
                    <th>BAC</th>
                    <th>EV</th>
                    <th>AC</th>
                    <th>CPI</th>
                  </tr>
                </thead>
                <tbody>
                  {dashboard.cost_sheet.map((line) => (
                    <tr key={line.control_account_id}>
                      <td>
                        <strong>{line.control_account_code}</strong>
                        <span>{line.control_account_name}</span>
                      </td>
                      <td>{line.cbs_code || "CBS pending"}</td>
                      <td>{currency(line.bac, project.currency)}</td>
                      <td>{currency(line.earned_value, project.currency)}</td>
                      <td>{currency(line.actual_cost, project.currency)}</td>
                      <td>{line.cpi.toFixed(3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!dashboard.cost_sheet.length && (
                <div className="workspaceEmpty">
                  <strong>No cost lines yet</strong>
                  <p>Cost data will appear after CBS and control account mapping are loaded.</p>
                </div>
              )}
            </>
          )}
          {activeControlView === "decisions" && (
            <>
              <div className="panelHeader">
                <h2>Decision Register</h2>
                <span>{dashboard.changes.length} changes</span>
              </div>
              <div className="workList">
                {dashboard.changes.length ? (
                  dashboard.changes.map((change) => (
                    <article key={change.id}>
                      <strong>{change.title}</strong>
                      <span>{change.deviation}</span>
                      <small>
                        {currency(change.cost_impact, project.currency)} / {change.schedule_impact_days} days /{" "}
                        {statusLabel(change.status)}
                      </small>
                    </article>
                  ))
                ) : (
                  <article>
                    <strong>No decisions pending</strong>
                    <span>Change and deviation decisions will be listed here.</span>
                  </article>
                )}
              </div>
            </>
          )}
          {activeControlView === "evidence" && (
            <>
              <div className="panelHeader">
                <h2>Evidence Register</h2>
                <span>{dashboard.document_control_summary.controlled_document_score.toFixed(0)}% controlled</span>
              </div>
              <div className="awpSummary">
                <article>
                  <span>Documents</span>
                  <strong>{dashboard.document_control_summary.total_documents ?? 0}</strong>
                  <small>{dashboard.document_control_summary.current_documents ?? 0} current</small>
                </article>
                <article className={dashboard.document_control_summary.overdue_reviews ? "risk" : ""}>
                  <span>Reviews</span>
                  <strong>{dashboard.document_control_summary.outstanding_reviews ?? 0}</strong>
                  <small>{dashboard.document_control_summary.overdue_reviews ?? 0} overdue</small>
                </article>
                <article>
                  <span>Transmittals</span>
                  <strong>{dashboard.document_control_summary.transmittals_sent ?? 0}</strong>
                  <small>{dashboard.document_control_summary.open_mail ?? 0} open mail</small>
                </article>
                <article>
                  <span>Attachments</span>
                  <strong>{dashboard.document_attachments.length}</strong>
                  <small>Evidence files</small>
                </article>
              </div>
              <div className="workList">
                {dashboard.documents.length ? (
                  dashboard.documents.slice(0, 12).map((document) => (
                    <article key={document.id}>
                      <strong>
                        {document.document_number} / Rev {document.revision}
                      </strong>
                      <span>{document.title}</span>
                      <small>
                        {document.doc_type} / {statusLabel(document.review_status)} / {document.file_name}
                      </small>
                    </article>
                  ))
                ) : (
                  <article>
                    <strong>No evidence documents yet</strong>
                    <span>Controlled documents and attachments will appear here.</span>
                  </article>
                )}
              </div>
            </>
          )}
          {activeControlView === "work-packages" && (
            <>
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
            </>
          )}
          </section>

          <section className="scheduleGate" aria-label="Schedule Intake">
            <div className="gateHeader">
              <div className="gateIntro">
                <GitBranch size={20} />
                <div>
                  <strong>Schedule Intake</strong>
                  <span>Upload the source XML/XER to open the Data Quality Gate and baseline workflow.</span>
                </div>
              </div>
              <label className={uploading ? "uploadButton disabled" : "uploadButton"}>
                <FileUp size={18} />
                <span>{uploading ? "Uploading..." : "Schedule XML or XER"}</span>
                <input
                  aria-label="Schedule XML or XER"
                  accept=".xml,.xer"
                  disabled={!canUploadSchedule || uploading}
                  onChange={handleScheduleUpload}
                  type="file"
                />
              </label>
            </div>
            <div className="gateFacts">
              <div>
                <span>Current Baseline</span>
                <strong>{activeImport?.baseline_name ?? "Pending upload"}</strong>
              </div>
              <div>
                <span>Data Quality Gate</span>
                <strong>
                  {activeImport ? `${activeImport.quality_score.toFixed(0)}% / ${activeImport.status}` : "Open"}
                </strong>
              </div>
              <div>
                <span>Data Date</span>
                <strong>{activeImport?.data_date ?? "Pending"}</strong>
              </div>
              <div>
                <span>Activities</span>
                <strong>{dashboard.schedule_activity_count}</strong>
              </div>
              <div>
                <span>Findings</span>
                <strong>{dashboard.schedule_findings.length}</strong>
              </div>
            </div>
            <p>
              The approved baseline feeds control accounts, AWP packages, progress capture, cost loading and Control
              Core decisions.
            </p>
            {uploadMessage && <div className="uploadMessage success">{uploadMessage}</div>}
            {uploadError && <div className="uploadMessage error">{uploadError}</div>}
            {!canUploadSchedule && (
              <div className="uploadMessage error">Only Planner or Control Manager roles can upload baselines.</div>
            )}
          </section>
        </section>
      </section>
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
