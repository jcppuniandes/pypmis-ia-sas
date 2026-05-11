import type { AppShellCtx } from "../components/AppShellCtx";
import { currency, statusLabel } from "../components/utils";

export default function CostView({ ctx }: { ctx: AppShellCtx }) {
  const {
    activeView,
    dashboard,
    project,
    setActiveView,
    costManager,
    costDisabled,
    captureAction,
    accountLabel,
    fundingDraft,
    setFundingDraft,
    cashFlowDraft,
    setCashFlowDraft,
    handleFundingSubmit,
    handleCashFlowSubmit,
  } = ctx;
  return (
    <section
      className={activeView === "cost" ? "viewPanel workspaceSection" : "viewPanel workspaceSection hidden"}
    >
      <div className="panelHeader">
        <h2>Cost Manager</h2>
        <button className="linkButton" onClick={() => setActiveView("bp-entry-forms")} type="button">
          Open capture form
        </button>
      </div>
      <div className="costManagerSummary">
        <article className={costManager.cost_variance < 0 ? "risk" : ""}>
          <span>Cost Variance</span>
          <strong>{currency(costManager.cost_variance, project.currency)}</strong>
          <small>
            EV {currency(costManager.total_earned_value, project.currency)} / actas{" "}
            {currency(costManager.total_incurred_from_payment_certificates, project.currency)} / almacen{" "}
            {currency(costManager.total_incurred_from_warehouse_receipts, project.currency)}
          </small>
        </article>
        <article>
          <span>Funding Coverage</span>
          <strong>{costManager.funding_coverage_percent.toFixed(1)}%</strong>
          <small>
            {currency(costManager.total_funding, project.currency)} funding /{" "}
            {currency(costManager.total_bac, project.currency)} BAC
          </small>
        </article>
        <article className={costManager.cash_flow_variance < 0 ? "risk" : ""}>
          <span>Cash Flow Variance</span>
          <strong>{currency(costManager.cash_flow_variance, project.currency)}</strong>
          <small>Actual net vs planned net</small>
        </article>
        <article>
          <span>Committed Cost</span>
          <strong>{currency(costManager.total_committed_cost, project.currency)}</strong>
          <small>
            Contracts {currency(costManager.total_contract_commitments, project.currency)} / PO{" "}
            {currency(costManager.total_purchase_order_commitments, project.currency)}
          </small>
        </article>
        <article>
          <span>Forecast Outflow</span>
          <strong>{currency(costManager.forecast_outflow, project.currency)}</strong>
          <small>
            {dashboard.cash_flow.length} periods / {dashboard.funding_sources.length} funds
          </small>
        </article>
      </div>
      <div className="viewSplit">
        <div>
          <div className="subHeader">
            <strong>Cost Sheet</strong>
            <span>{dashboard.cost_sheet.length} control accounts</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>Control Account</th>
                <th>CBS</th>
                <th>BAC</th>
                <th>EV</th>
                <th>Actas</th>
                <th>Almacen</th>
                <th>Incurred</th>
                <th>Contract</th>
                <th>PO</th>
                <th>Committed</th>
                <th>CPI</th>
              </tr>
            </thead>
            <tbody>
              {dashboard.cost_sheet.map((line) => (
                <tr key={line.control_account_id}>
                  <td>{line.control_account_code}</td>
                  <td>{line.cbs_code || "Pending"}</td>
                  <td>{currency(line.bac, project.currency)}</td>
                  <td>{currency(line.earned_value, project.currency)}</td>
                  <td>{currency(line.incurred_payment_certificate_value, project.currency)}</td>
                  <td>{currency(line.incurred_warehouse_receipt_value, project.currency)}</td>
                  <td>{currency(line.actual_cost, project.currency)}</td>
                  <td>{currency(line.committed_contract_value, project.currency)}</td>
                  <td>{currency(line.committed_purchase_order_value, project.currency)}</td>
                  <td>{currency(line.committed_cost, project.currency)}</td>
                  <td>{line.cpi.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="subHeader spaced">
            <strong>Payment Certificates</strong>
            <span>{dashboard.payment_certificates.length} actas</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>Control Account</th>
                <th>Certificate</th>
                <th>Amount</th>
                <th>Certified On</th>
              </tr>
            </thead>
            <tbody>
              {dashboard.payment_certificates.map((certificate) => (
                <tr key={certificate.id}>
                  <td>
                    {certificate.control_account_id ? accountLabel(certificate.control_account_id) : "No account"}
                  </td>
                  <td>{certificate.certificate_no}</td>
                  <td>{currency(certificate.certified_amount, project.currency)}</td>
                  <td>{certificate.certified_on ?? "Open"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="subHeader spaced">
            <strong>Warehouse Receipts</strong>
            <span>{dashboard.warehouse_receipts.length} entradas</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>Control Account</th>
                <th>Receipt</th>
                <th>Value</th>
                <th>Received On</th>
              </tr>
            </thead>
            <tbody>
              {dashboard.warehouse_receipts.map((receipt) => (
                <tr key={receipt.id}>
                  <td>{receipt.control_account_id ? accountLabel(receipt.control_account_id) : "No account"}</td>
                  <td>{receipt.receipt_no}</td>
                  <td>{currency(receipt.received_value, project.currency)}</td>
                  <td>{receipt.received_on ?? "Open"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="subHeader spaced">
            <strong>Cost Evidence Records</strong>
            <span>{dashboard.latest_cost_records.length} recent</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>Control Account</th>
                <th>Source</th>
                <th>Amount</th>
                <th>Incurred On</th>
              </tr>
            </thead>
            <tbody>
              {dashboard.latest_cost_records.map((record) => (
                <tr key={record.id}>
                  <td>{accountLabel(record.control_account_id)}</td>
                  <td>{statusLabel(record.source)}</td>
                  <td>{currency(record.amount, project.currency)}</td>
                  <td>{record.incurred_on}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div>
          <div className="subHeader">
            <strong>Funding Sources</strong>
            <span>{currency(costManager.total_funding, project.currency)}</span>
          </div>
          <div className="workList compactList">
            {dashboard.funding_sources.map((funding) => (
              <article key={funding.id}>
                <strong>
                  {funding.code} / {currency(funding.amount, funding.currency)}
                </strong>
                <span>{funding.name}</span>
                <small>
                  {statusLabel(funding.status)} / v{funding.version}
                </small>
              </article>
            ))}
          </div>
          <form className="inlineCostForm" onSubmit={handleFundingSubmit}>
            <input
              disabled={costDisabled}
              onChange={(event) => setFundingDraft((current) => ({ ...current, code: event.target.value }))}
              placeholder="Code"
              required
              value={fundingDraft.code}
            />
            <input
              disabled={costDisabled}
              onChange={(event) => setFundingDraft((current) => ({ ...current, name: event.target.value }))}
              placeholder="Name"
              required
              value={fundingDraft.name}
            />
            <input
              disabled={costDisabled}
              min="0"
              onChange={(event) => setFundingDraft((current) => ({ ...current, amount: event.target.value }))}
              placeholder="Amount"
              required
              type="number"
              value={fundingDraft.amount}
            />
            <select
              disabled={costDisabled}
              onChange={(event) => setFundingDraft((current) => ({ ...current, status: event.target.value }))}
              value={fundingDraft.status}
            >
              <option value="approved">Approved</option>
              <option value="planned">Planned</option>
              <option value="on_hold">On Hold</option>
            </select>
            <button
              className="workflowAction primary"
              disabled={costDisabled || captureAction !== null}
              type="submit"
            >
              {captureAction === "funding" ? "Saving..." : "Add Funding"}
            </button>
          </form>
          <div className="subHeader spaced">
            <strong>Cash Flow</strong>
            <span>{dashboard.cash_flow.length} periods</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>Period</th>
                <th>Planned Out</th>
                <th>Actual Out</th>
                <th>Forecast Out</th>
              </tr>
            </thead>
            <tbody>
              {dashboard.cash_flow.map((period) => (
                <tr key={period.id}>
                  <td>{period.period_label}</td>
                  <td>{currency(period.planned_outflow, project.currency)}</td>
                  <td>{currency(period.actual_outflow, project.currency)}</td>
                  <td>{currency(period.forecast_outflow, project.currency)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <form className="inlineCostForm cashFlowForm" onSubmit={handleCashFlowSubmit}>
            <input
              disabled={costDisabled}
              onChange={(event) =>
                setCashFlowDraft((current) => ({ ...current, period_label: event.target.value }))
              }
              placeholder="YYYY-MM"
              required
              value={cashFlowDraft.period_label}
            />
            <input
              disabled={costDisabled}
              min="0"
              onChange={(event) =>
                setCashFlowDraft((current) => ({ ...current, planned_inflow: event.target.value }))
              }
              placeholder="Planned in"
              type="number"
              value={cashFlowDraft.planned_inflow}
            />
            <input
              disabled={costDisabled}
              min="0"
              onChange={(event) =>
                setCashFlowDraft((current) => ({ ...current, planned_outflow: event.target.value }))
              }
              placeholder="Planned out"
              type="number"
              value={cashFlowDraft.planned_outflow}
            />
            <input
              disabled={costDisabled}
              min="0"
              onChange={(event) =>
                setCashFlowDraft((current) => ({ ...current, actual_inflow: event.target.value }))
              }
              placeholder="Actual in"
              type="number"
              value={cashFlowDraft.actual_inflow}
            />
            <input
              disabled={costDisabled}
              min="0"
              onChange={(event) =>
                setCashFlowDraft((current) => ({ ...current, actual_outflow: event.target.value }))
              }
              placeholder="Actual out"
              type="number"
              value={cashFlowDraft.actual_outflow}
            />
            <input
              disabled={costDisabled}
              min="0"
              onChange={(event) =>
                setCashFlowDraft((current) => ({ ...current, forecast_outflow: event.target.value }))
              }
              placeholder="Forecast out"
              type="number"
              value={cashFlowDraft.forecast_outflow}
            />
            <button
              className="workflowAction primary"
              disabled={costDisabled || captureAction !== null}
              type="submit"
            >
              {captureAction === "cash-flow" ? "Saving..." : "Add Period"}
            </button>
          </form>
        </div>
      </div>
    </section>
  );
}
