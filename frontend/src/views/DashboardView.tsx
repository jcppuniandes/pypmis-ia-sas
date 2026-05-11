import React from "react";
import { Activity, Bot, ClipboardCheck, FileText, Gauge, GitBranch, ShieldCheck } from "lucide-react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { AppShellCtx } from "../components/AppShellCtx";
import StatusLight from "../components/StatusLight";
import { currency, neutralScheduleText, statusLabel } from "../components/utils";

export default function DashboardView({ ctx }: { ctx: AppShellCtx }) {
  const {
    activeView,
    dashboard,
    project,
    kpi,
    redAlerts,
    chartData,
    accountLabel,
  } = ctx;
  return (
    <>
      <section
        className={
          activeView === "control-dashboard" ? "kpiGrid workspaceSection" : "kpiGrid workspaceSection hidden"
        }
      >
        <article className="metric">
          <div>
            <Gauge size={18} />
            <span>SPI</span>
          </div>
          <strong>{kpi.spi.toFixed(3)}</strong>
          <small>Schedule performance</small>
          <StatusLight value={kpi.spi} />
        </article>
        <article className="metric">
          <div>
            <ShieldCheck size={18} />
            <span>CPI</span>
          </div>
          <strong>{kpi.cpi.toFixed(3)}</strong>
          <small>Cost performance</small>
          <StatusLight value={kpi.cpi} />
        </article>
        <article className="metric">
          <div>
            <Activity size={18} />
            <span>VAC</span>
          </div>
          <strong>{currency(kpi.vac, project.currency)}</strong>
          <small>Variance at completion</small>
        </article>
        <article className="metric">
          <div>
            <GitBranch size={18} />
            <span>EAC</span>
          </div>
          <strong>{currency(kpi.eac, project.currency)}</strong>
          <small>Estimate at completion</small>
        </article>
      </section>

      <section
        className={
          activeView === "control-dashboard" ? "mainGrid workspaceSection" : "mainGrid workspaceSection hidden"
        }
        id="control-dashboard"
      >
        <div className="panel wide">
          <div className="panelHeader">
            <h2>S-Curve Control View</h2>
            <span>PV / EV / AC</span>
          </div>
          <ResponsiveContainer width="100%" height={270}>
            <AreaChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#d8dee5" />
              <XAxis dataKey="period" />
              <YAxis tickFormatter={(value) => `$${Number(value) / 1000000}M`} />
              <Tooltip formatter={(value) => currency(Number(value), project.currency)} />
              <Area type="monotone" dataKey="PV" stroke="#52616f" fill="#dce3ea" strokeWidth={2} />
              <Area type="monotone" dataKey="EV" stroke="#0f8b8d" fill="#bde7e5" strokeWidth={2} />
              <Area type="monotone" dataKey="AC" stroke="#c85a3a" fill="#f2c5b8" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <h2>Control Core Loop</h2>
            <ClipboardCheck size={18} />
          </div>
          <div className="loopList">
            {dashboard.loop.map((item) => (
              <div key={item.step}>
                <strong>{item.step}</strong>
                <span>{item.description}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <h2>Early Warnings</h2>
            <span>{redAlerts} critical</span>
          </div>
          <div className="stack">
            {dashboard.alerts.map((alert) => (
              <article className={`alert ${alert.severity}`} key={alert.id}>
                <strong>{alert.rule}</strong>
                <span>{alert.message}</span>
                <small>{alert.recommendation}</small>
              </article>
            ))}
          </div>
        </div>

        <div className="panel wide">
          <div className="panelHeader">
            <h2>EAC Forecast Scenarios</h2>
            <span>{dashboard.forecast_scenarios.length} scenarios</span>
          </div>
          <div className="scenarioGrid">
            {dashboard.forecast_scenarios.map((scenario) => (
              <article className={`scenarioCard ${scenario.completion_risk}`} key={scenario.id}>
                <div>
                  <strong>{scenario.name}</strong>
                  <span>{scenario.method}</span>
                </div>
                <div className="scenarioNumbers">
                  <span>
                    EAC <strong>{currency(scenario.eac, project.currency)}</strong>
                  </span>
                  <span>
                    VAC <strong>{currency(scenario.vac, project.currency)}</strong>
                  </span>
                  <span>
                    CPI/SPI{" "}
                    <strong>
                      {scenario.cpi_factor.toFixed(3)} / {scenario.spi_factor.toFixed(3)}
                    </strong>
                  </span>
                </div>
                <small>
                  {statusLabel(scenario.completion_risk)} risk / {scenario.period_label}
                </small>
              </article>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <h2>Productivity</h2>
            <span>{dashboard.productivity_summary.low_productivity_accounts} low accounts</span>
          </div>
          <div className="productivityCard">
            <strong>{dashboard.productivity_summary.productivity_index.toFixed(3)}</strong>
            <span>Productivity index</span>
            <small>
              {dashboard.productivity_summary.total_quantity.toLocaleString()} qty /{" "}
              {dashboard.productivity_summary.total_labor_hours.toLocaleString()} labor hours
            </small>
          </div>
        </div>

        <div className="panel wide">
          <div className="panelHeader">
            <h2>Control Accounts</h2>
            <span>{dashboard.control_accounts.length} mapped from schedule</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>Account</th>
                <th>Owner</th>
                <th>Discipline</th>
                <th>PV</th>
                <th>EV</th>
                <th>AC</th>
                <th>SPI</th>
                <th>CPI</th>
              </tr>
            </thead>
            <tbody>
              {dashboard.control_accounts.map((account) => {
                const accountKpi = dashboard.account_kpis.find((item) => item.control_account_id === account.id);
                return (
                  <tr key={account.id}>
                    <td>
                      <strong>{account.code}</strong>
                      <span>{account.name}</span>
                    </td>
                    <td>{account.responsible}</td>
                    <td>{account.discipline}</td>
                    <td>{currency(accountKpi?.pv ?? 0, project.currency)}</td>
                    <td>{currency(accountKpi?.ev ?? 0, project.currency)}</td>
                    <td>{currency(accountKpi?.ac ?? 0, project.currency)}</td>
                    <td>{accountKpi?.spi.toFixed(3)}</td>
                    <td>{accountKpi?.cpi.toFixed(3)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="panel wide">
          <div className="panelHeader">
            <h2>Schedule QA & Baseline</h2>
            <span>
              {dashboard.schedule_findings.length} findings / {dashboard.baseline_versions.length} baselines
            </span>
          </div>
          <div className="contractGrid">
            <div>
              <strong>Validation Findings</strong>
              <div className="workList">
                {dashboard.schedule_findings.length ? (
                  dashboard.schedule_findings.slice(0, 5).map((finding) => (
                    <article key={finding.id}>
                      <strong>
                        {finding.check_code} / {statusLabel(finding.severity)}
                      </strong>
                      <span>{finding.message}</span>
                      <small>
                        {finding.item_count} items / weight {finding.weight}
                      </small>
                    </article>
                  ))
                ) : (
                  <article>
                    <strong>No findings</strong>
                    <span>The active schedule has no stored QA findings.</span>
                  </article>
                )}
              </div>
            </div>
            <div>
              <strong>Baseline Versions</strong>
              <div className="workList">
                {dashboard.baseline_versions.length ? (
                  dashboard.baseline_versions.map((baseline) => (
                    <article key={baseline.id}>
                      <strong>
                        BL-{baseline.version_no.toString().padStart(2, "0")} / {statusLabel(baseline.status)}
                      </strong>
                      <span>{neutralScheduleText(baseline.name)}</span>
                      <small>
                        {baseline.data_date ?? "No data date"} / Quality {baseline.quality_score.toFixed(0)}%
                      </small>
                    </article>
                  ))
                ) : (
                  <article>
                    <strong>No baseline versions</strong>
                    <span>Load a source schedule to create the first baseline version.</span>
                  </article>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="panel wide">
          <div className="panelHeader">
            <h2>BP Engine / uDesigner</h2>
            <span>{dashboard.process_templates.length} persistent templates</span>
          </div>
          <div className="designerSummary">
            <div>
              <strong>
                {dashboard.process_templates.reduce((total, template) => total + template.step_templates.length, 0)}
              </strong>
              <span>configured steps</span>
            </div>
            <div>
              <strong>
                {dashboard.process_templates.reduce((total, template) => total + template.transitions.length, 0)}
              </strong>
              <span>workflow transitions</span>
            </div>
            <div>
              <strong>
                {
                  dashboard.process_templates.filter((template) => template.status.toLowerCase() === "active")
                    .length
                }
              </strong>
              <span>active BP definitions</span>
            </div>
          </div>
          <div className="templateGrid">
            {dashboard.process_templates.map((template) => (
              <article key={template.code}>
                <div>
                  <strong>{template.name}</strong>
                  <span>
                    {template.code} / {template.category} / v{template.version_no}
                  </span>
                </div>
                <p>{template.description || "Business process controlled by the configurable workflow engine."}</p>
                <small>Form: {template.form_schema.join(", ")}</small>
                <small>Workflow: {template.workflow_steps.join(" -> ")}</small>
                <small>
                  Transitions:{" "}
                  {template.transitions
                    .map(
                      (transition) =>
                        `${transition.label || statusLabel(transition.action)}: ${transition.from_step} -> ${transition.to_step}`
                    )
                    .join(" / ") || "Pending"}
                </small>
                <small>Roles: {template.roles.join(", ")}</small>
                <span className="templateStatus">{template.status}</span>
              </article>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <h2>Project Team & Roles</h2>
            <span>{dashboard.project_team.length} users</span>
          </div>
          <div className="teamList">
            {dashboard.project_team.map((member) => (
              <article key={member.membership.id}>
                <strong>{member.user.full_name}</strong>
                <span>{member.membership.role}</span>
                <small>{member.user.title}</small>
              </article>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <h2>Audit Trail</h2>
            <span>{dashboard.audit_logs.length} recent</span>
          </div>
          <div className="auditList">
            {dashboard.audit_logs.length ? (
              dashboard.audit_logs.map((log) => (
                <article key={log.id}>
                  <strong>{statusLabel(log.action.replace("workflow.", ""))}</strong>
                  <span>
                    {log.actor} / {log.entity_type} #{log.entity_id ?? "-"}
                  </span>
                  <small>{new Date(log.created_at).toLocaleString()}</small>
                </article>
              ))
            ) : (
              <article>
                <strong>No workflow actions yet</strong>
                <span>Route a BP to create an audit entry.</span>
              </article>
            )}
          </div>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <h2>Decision Layer</h2>
            <Bot size={18} />
          </div>
          <p className="aiBrief">{dashboard.ai_brief}</p>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <h2>Changes & Claims</h2>
            <FileText size={18} />
          </div>
          <div className="workList">
            {[...dashboard.changes, ...dashboard.claims].map((item) => (
              <article key={`${item.title}-${item.id}`}>
                <strong>{item.title}</strong>
                <span>{item.status}</span>
              </article>
            ))}
          </div>
        </div>

        <div className="panel wide">
          <div className="panelHeader">
            <h2>Contract Administration</h2>
            <span>
              {dashboard.contracts.length} contracts / {dashboard.purchase_orders.length} POs /{" "}
              {dashboard.payment_certificates.length} actas / {dashboard.warehouse_receipts.length} almacen
            </span>
          </div>
          <div className="contractGrid">
            <div>
              <strong>Contracts</strong>
              <div className="workList">
                {dashboard.contracts.map((contract) => (
                  <article key={contract.id}>
                    <strong>
                      {contract.code} / {contract.counterparty}
                    </strong>
                    <span>{contract.title}</span>
                    <small>
                      {currency(contract.value, project.currency)} /{" "}
                      {contract.control_account_id
                        ? accountLabel(contract.control_account_id)
                        : "No control account"}{" "}
                      / {statusLabel(contract.status)}
                    </small>
                  </article>
                ))}
              </div>
            </div>
            <div>
              <strong>Purchase Orders</strong>
              <div className="workList">
                {dashboard.purchase_orders.map((order) => (
                  <article key={order.id}>
                    <strong>
                      {order.po_number} / {currency(order.committed_amount, project.currency)}
                    </strong>
                    <span>{order.description}</span>
                    <small>
                      {order.control_account_id ? accountLabel(order.control_account_id) : "No control account"} /{" "}
                      {statusLabel(order.status)}
                    </small>
                  </article>
                ))}
              </div>
            </div>
            <div>
              <strong>Payment Certificates</strong>
              <div className="workList">
                {dashboard.payment_certificates.map((certificate) => (
                  <article key={certificate.id}>
                    <strong>
                      {certificate.certificate_no} / {currency(certificate.certified_amount, project.currency)}
                    </strong>
                    <span>{certificate.period_label || "No period"}</span>
                    <small>
                      {certificate.control_account_id
                        ? accountLabel(certificate.control_account_id)
                        : "No control account"}{" "}
                      / {statusLabel(certificate.status)}
                    </small>
                  </article>
                ))}
              </div>
            </div>
            <div>
              <strong>Warehouse Receipts</strong>
              <div className="workList">
                {dashboard.warehouse_receipts.map((receipt) => (
                  <article key={receipt.id}>
                    <strong>
                      {receipt.receipt_no} / {currency(receipt.received_value, project.currency)}
                    </strong>
                    <span>{receipt.description || "Warehouse receipt"}</span>
                    <small>
                      {receipt.control_account_id ? accountLabel(receipt.control_account_id) : "No control account"}{" "}
                      / {statusLabel(receipt.status)}
                    </small>
                  </article>
                ))}
              </div>
            </div>
            <div>
              <strong>Communications</strong>
              <div className="workList">
                {dashboard.communications.map((communication) => (
                  <article key={communication.id}>
                    <strong>
                      {statusLabel(communication.communication_type)} / {communication.sent_on}
                    </strong>
                    <span>{communication.subject}</span>
                    <small>{communication.reference || "No reference"}</small>
                  </article>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="panel wide">
          <div className="panelHeader">
            <h2>Document Control Register</h2>
            <span>{dashboard.documents.length} controlled records</span>
          </div>
          <div className="documentGrid">
            {dashboard.documents.map((document) => (
              <article key={document.id}>
                <strong>
                  {document.document_number} Rev {document.revision}
                </strong>
                <span>{document.title}</span>
                <small>
                  {statusLabel(document.review_status)} / {document.uri}
                </small>
              </article>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}
