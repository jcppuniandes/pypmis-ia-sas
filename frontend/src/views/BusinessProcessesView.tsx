import React from "react";
import { ArrowRight } from "lucide-react";
import type { AppShellCtx } from "../components/AppShellCtx";
import { neutralScheduleText } from "../components/utils";

export default function BusinessProcessesView({ ctx }: { ctx: AppShellCtx }) {
  const {
    activeView,
    dashboard,
    workflowInstance,
    workflowStatus,
    workflowActionButtons,
    workflowStages,
    bpRecords,
    selectedBpRecord,
    setSelectedBpRecordNo,
    routingAction,
    canRouteCurrentWorkflow,
    handleWorkflowAction,
  } = ctx;
  return (
    <section
      className={
        activeView === "business-processes"
          ? "workflowShell workspaceSection"
          : "workflowShell workspaceSection hidden"
      }
      id="workflow-record"
    >
      <aside className="processRail">
        <div className="railHeader">
          <span>Business Processes</span>
          <strong>Project Control</strong>
        </div>
        {[
          "Project",
          "Schedule Intake",
          "Work Packages",
          "Progress Update",
          "Cost Actuals",
          "Change Request",
          "Contract Notice",
          "Claim Impact",
          "Document Link",
          "Decision Action",
        ].map((item, index) => (
          <button className={index === 0 ? "railItem active" : "railItem"} key={item}>
            <span>{item}</span>
            <strong>
              {item === "Schedule Intake"
                ? workflowInstance
                  ? "Open"
                  : "Waiting"
                : item === "Work Packages"
                  ? `${dashboard.awp_summary.open_constraints} open`
                  : item === "Contract Notice"
                    ? `${dashboard.contract_notices.length} records`
                    : item === "Claim Impact"
                      ? `${dashboard.claim_impact_analyses.length} analyses`
                      : item === "Project"
                        ? "Active"
                        : "Ready"}
            </strong>
          </button>
        ))}
      </aside>

      <div className="workflowCanvas">
        <div className="workflowHeader">
          <div>
            <span>Workflow Routing</span>
            <h2>
              {workflowInstance
                ? neutralScheduleText(workflowInstance.title)
                : "Schedule upload triggers the control workflow"}
            </h2>
          </div>
          <div className="workflowMeta">
            <span>BP Status</span>
            <strong>{workflowInstance ? workflowStatus : "Waiting for schedule"}</strong>
          </div>
        </div>

        <div className="stageTrack">
          {workflowStages.map((stage, index) => (
            <React.Fragment key={stage.name}>
              <article className={`stageCard ${stage.tone}`}>
                <span>{stage.status}</span>
                <strong>{stage.name}</strong>
                <p>{stage.detail}</p>
                <small>Ball in Court: {stage.owner}</small>
              </article>
              {index < workflowStages.length - 1 && <ArrowRight className="stageArrow" size={18} />}
            </React.Fragment>
          ))}
        </div>

        <div className="recordRegistry">
          <div className="registryHeader">
            <h2>BP Records</h2>
            <span>{bpRecords.length} routed records</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>Record No.</th>
                <th>Business Process</th>
                <th>Title</th>
                <th>Current Step</th>
                <th>Ball in Court</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {bpRecords.map((record) => (
                <tr
                  className={selectedBpRecord?.record === record.record ? "selectedRecord" : ""}
                  key={record.record}
                >
                  <td>
                    <button
                      className="recordLink"
                      onClick={() => setSelectedBpRecordNo(record.record)}
                      type="button"
                    >
                      {record.record}
                    </button>
                  </td>
                  <td>{record.process}</td>
                  <td>{record.title}</td>
                  <td>{record.step}</td>
                  <td>{record.ballInCourt}</td>
                  <td>
                    <span className={`statusPill ${record.tone}`}>{record.status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {selectedBpRecord && (
          <div className="bpRecordDetail">
            <div>
              <span>Selected BP Record</span>
              <strong>
                {selectedBpRecord.record} / {selectedBpRecord.process}
              </strong>
            </div>
            <p>{selectedBpRecord.title}</p>
            <div className="detailFacts">
              <span>
                Current Step: <strong>{selectedBpRecord.step}</strong>
              </span>
              <span>
                Ball in Court: <strong>{selectedBpRecord.ballInCourt}</strong>
              </span>
              <span>
                Status: <strong>{selectedBpRecord.status}</strong>
              </span>
            </div>
          </div>
        )}
      </div>

      <aside className="routingPanel">
        <div>
          <span>Current Step</span>
          <strong>{workflowInstance?.current_step ?? "Schedule Upload Gate"}</strong>
          <p>
            {workflowInstance
              ? "Validate schedule variance, cost exposure and contractual notice before routing to approval."
              : "Upload a schedule XML or XER file to create the BP record and start routing."}
          </p>
        </div>
        <div>
          <span>Required Attachments</span>
          <strong>{dashboard.document_control_summary.controlled_document_score.toFixed(0)}% controlled</strong>
          <p>Controlled revisions, transmittals, reviews and project mail remain tied to BP records.</p>
        </div>
        <div>
          <span>Ball in Court</span>
          <strong>{workflowInstance?.ball_in_court ?? "Planner"}</strong>
          <p>
            {workflowInstance
              ? "The responsible role owns the next routed action in the control cycle."
              : "The planner must load the schedule before downstream controls can run."}
          </p>
        </div>
        <div>
          <span>Workflow Actions</span>
          <div className="actionStack">
            {workflowActionButtons.length ? (
              workflowActionButtons.map((item) => (
                <button
                  className={`workflowAction ${item.tone}`}
                  disabled={routingAction !== null || !canRouteCurrentWorkflow}
                  key={item.action}
                  onClick={() => handleWorkflowAction(item.action)}
                  type="button"
                >
                  {routingAction === item.action ? "Routing..." : item.label}
                </button>
              ))
            ) : (
              <strong>No pending action</strong>
            )}
          </div>
          <p>Each action updates the routed step, ball-in-court and audit trail.</p>
        </div>
      </aside>
    </section>
  );
}
