import type { AppShellCtx } from "../components/AppShellCtx";
import { statusLabel } from "../components/utils";

export default function AwpView({ ctx }: { ctx: AppShellCtx }) {
  const {
    activeView,
    dashboard,
    setActiveView,
    constraintsByPackage,
    packageLabel,
    accountLabel,
    canManageAwp,
    captureAction,
    handleConstraintClose,
  } = ctx;
  return (
    <section
      className={activeView === "awp" ? "viewPanel workspaceSection" : "viewPanel workspaceSection hidden"}
    >
      <div className="panelHeader">
        <h2>Work Package Readiness</h2>
        <button className="linkButton" onClick={() => setActiveView("bp-entry-forms")} type="button">
          Open package forms
        </button>
      </div>
      <div className="awpSummary">
        <article>
          <span>Readiness Score</span>
          <strong>{dashboard.awp_summary.readiness_score.toFixed(1)}%</strong>
          <small>
            {dashboard.awp_summary.ready_for_release} ready / {dashboard.awp_summary.total_packages} packages
          </small>
        </article>
        <article>
          <span>CWP / IWP</span>
          <strong>
            {dashboard.awp_summary.cwp_count} / {dashboard.awp_summary.iwp_count}
          </strong>
          <small>Construction and installation work packages</small>
        </article>
        <article className={dashboard.awp_summary.blocking_constraints ? "risk" : ""}>
          <span>Open Constraints</span>
          <strong>{dashboard.awp_summary.open_constraints}</strong>
          <small>{dashboard.awp_summary.blocking_constraints} blocking constraints</small>
        </article>
        <article className={dashboard.awp_summary.blocked_packages ? "risk" : ""}>
          <span>Blocked Packages</span>
          <strong>{dashboard.awp_summary.blocked_packages}</strong>
          <small>Constraint review before field release</small>
        </article>
      </div>
      <div className="viewSplit">
        <div>
          <div className="subHeader">
            <strong>Path of Construction Packages</strong>
            <span>{dashboard.work_packages.length} records</span>
          </div>
          <div className="workList">
            {dashboard.work_packages.map((workPackage) => {
              const openBlocking = (constraintsByPackage[workPackage.id] ?? []).filter(
                (constraint) => constraint.status === "open" && constraint.blocking
              ).length;
              return (
                <article className={openBlocking ? "blockedPackage" : ""} key={workPackage.id}>
                  <strong>
                    {workPackage.package_type} / {workPackage.code}
                  </strong>
                  <span>{workPackage.title}</span>
                  <small>
                    {workPackage.path_of_construction || "No path defined"} /{" "}
                    {statusLabel(workPackage.readiness_status)}
                  </small>
                  <div className="packageFacts">
                    <span>
                      {workPackage.control_account_id
                        ? accountLabel(workPackage.control_account_id)
                        : "Area level"}
                    </span>
                    <span>
                      {workPackage.planned_start ?? "Pending"} to {workPackage.planned_finish ?? "Pending"}
                    </span>
                    <span>{workPackage.progress_percent.toFixed(1)}% progress</span>
                    <span>{openBlocking} blockers</span>
                  </div>
                </article>
              );
            })}
          </div>
        </div>
        <div>
          <div className="subHeader">
            <strong>Constraint Log</strong>
            <span>{dashboard.work_package_constraints.length} constraints</span>
          </div>
          <div className="workList">
            {dashboard.work_package_constraints.map((constraint) => (
              <article
                className={constraint.status === "open" && constraint.blocking ? "blockedPackage" : ""}
                key={constraint.id}
              >
                <strong>
                  {constraint.constraint_type} / {packageLabel(constraint.work_package_id)}
                </strong>
                <span>{constraint.description}</span>
                <small>
                  {constraint.owner_role} / Required {constraint.required_by ?? "Pending"} /{" "}
                  {statusLabel(constraint.status)}
                </small>
                {constraint.status === "open" && (
                  <button
                    className="linkButton compact"
                    disabled={!canManageAwp || captureAction === `awp-constraint-${constraint.id}`}
                    onClick={() => handleConstraintClose(constraint)}
                    type="button"
                  >
                    {captureAction === `awp-constraint-${constraint.id}` ? "Closing..." : "Close Constraint"}
                  </button>
                )}
              </article>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
