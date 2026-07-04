import type { AppShellCtx } from "../components/AppShellCtx";
import { currency, statusLabel, neutralScheduleText } from "../components/utils";

export default function ScheduleView({ ctx }: { ctx: AppShellCtx }) {
  const {
    activeView,
    dashboard,
    project,
    mappingSummary,
    captureAction,
    canApproveControlBaseline,
    accountLabel,
    handleControlBaselineApprove,
  } = ctx;
  return (
    <section
      className={activeView === "schedule" ? "viewPanel workspaceSection" : "viewPanel workspaceSection hidden"}
    >
      <div className="panelHeader">
        <h2>Planning Baseline</h2>
        <button
          className="linkButton"
          disabled={!canApproveControlBaseline || captureAction !== null}
          onClick={handleControlBaselineApprove}
          type="button"
        >
          {captureAction === "control-baseline-approve" ? "Approving..." : "Approve Control Baseline"}
        </button>
      </div>
      <div className="mappingSummary">
        <article>
          <span>Mapped Activities</span>
          <strong>
            {mappingSummary.mapped_activities}/{mappingSummary.total_schedule_activities}
          </strong>
          <small>{mappingSummary.mapping_score.toFixed(1)}% WBS to control account coverage</small>
        </article>
        <article>
          <span>Cost Loading</span>
          <strong>
            {mappingSummary.cost_loaded_activities}/{mappingSummary.total_schedule_activities}
          </strong>
          <small>{mappingSummary.cost_loading_score.toFixed(1)}% schedule activities with cost</small>
        </article>
        <article>
          <span>Control Accounts</span>
          <strong>{mappingSummary.control_account_count}</strong>
          <small>
            {currency(mappingSummary.total_bac, project.currency)} BAC / PV{" "}
            {currency(mappingSummary.total_planned_value, project.currency)}
          </small>
        </article>
        <article>
          <span>Baseline Status</span>
          <strong>{statusLabel(mappingSummary.baseline_status)}</strong>
          <small>
            {dashboard.schedule_activity_count} activities / {dashboard.schedule_relationship_count} relationships
          </small>
        </article>
      </div>
      <div className="viewSplit">
        <div className="workList">
          <article>
            <strong>
              {dashboard.schedule_import
                ? neutralScheduleText(dashboard.schedule_import.baseline_name)
                : "No baseline"}
            </strong>
            <span>
              {dashboard.schedule_import?.validation_summary ??
                "Upload a schedule XML or XER file to start the baseline workflow."}
            </span>
            <small>
              Quality {dashboard.schedule_import?.quality_score.toFixed(0) ?? "0"}% / Data date{" "}
              {dashboard.schedule_import?.data_date ?? "Pending"}
            </small>
          </article>
          {dashboard.baseline_versions.map((baseline) => (
            <article key={baseline.id}>
              <strong>
                BL-{baseline.version_no.toString().padStart(2, "0")} / {statusLabel(baseline.status)}
              </strong>
              <span>{neutralScheduleText(baseline.name)}</span>
              <small>
                {baseline.data_date ?? "No data date"} / Quality {baseline.quality_score.toFixed(0)}%
              </small>
            </article>
          ))}
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
                <small>
                  {finding.item_count} items / weight {finding.weight}
                </small>
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
      <div className="mappingTable">
        <div className="panelHeader compactHeader">
          <h2>WBS / CBS / Activity Mapping</h2>
          <span>{dashboard.control_account_mappings.length} linked activities</span>
        </div>
        <table>
          <thead>
            <tr>
              <th>WBS</th>
              <th>CBS</th>
              <th>Control Account</th>
              <th>Planned %</th>
              <th>BAC</th>
              <th>PV</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {dashboard.control_account_mappings.slice(0, 12).map((mapping) => (
              <tr key={mapping.id}>
                <td>
                  <strong>{mapping.wbs_code}</strong>
                  <span>{mapping.wbs_name}</span>
                </td>
                <td>{mapping.cbs_code}</td>
                <td>{mapping.control_account_id ? accountLabel(mapping.control_account_id) : "Unmapped"}</td>
                <td>{mapping.planned_percent.toFixed(1)}%</td>
                <td>{currency(mapping.planned_cost, project.currency)}</td>
                <td>{currency(mapping.planned_value, project.currency)}</td>
                <td>{statusLabel(mapping.status)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
