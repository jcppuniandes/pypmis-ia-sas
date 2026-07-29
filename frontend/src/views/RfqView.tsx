import type { AppShellCtx } from "../components/AppShellCtx";
import { currency, statusLabel } from "../components/utils";

export default function RfqView({ ctx }: { ctx: AppShellCtx }) {
  const { activeView, dashboard, project, setActiveView, bidsByRfq, rfqPackageLabel, accountLabel } = ctx;
  return (
    <section className={activeView === "rfq" ? "viewPanel workspaceSection" : "viewPanel workspaceSection hidden"}>
      <div className="panelHeader">
        <h2>RFQ / Bid Evaluation</h2>
        <button className="linkButton" onClick={() => setActiveView("bp-entry-forms")} type="button">
          Open RFQ forms
        </button>
      </div>
      <div className="costManagerSummary">
        <article>
          <span>RFQ Packages</span>
          <strong>{dashboard.rfq_summary.total_packages}</strong>
          <small>{dashboard.rfq_summary.issued_packages} issued or under evaluation</small>
        </article>
        <article>
          <span>Bids Received</span>
          <strong>{dashboard.rfq_summary.bids_received}</strong>
          <small>Average score {dashboard.rfq_summary.average_weighted_score.toFixed(1)}</small>
        </article>
        <article>
          <span>Recommended Bidder</span>
          <strong>{dashboard.rfq_summary.recommended_bidder || "Pending"}</strong>
          <small>{currency(dashboard.rfq_summary.recommended_bid_amount, project.currency)}</small>
        </article>
      </div>
      <div className="viewSplit">
        <div>
          <div className="subHeader">
            <strong>RFQ Packages</strong>
            <span>{dashboard.rfq_packages.length} packages</span>
          </div>
          <div className="workList">
            {dashboard.rfq_packages.map((rfqPackage) => (
              <article key={rfqPackage.id}>
                <strong>
                  {rfqPackage.package_no} / {currency(rfqPackage.budget_amount, project.currency)}
                </strong>
                <span>{rfqPackage.title}</span>
                <small>
                  {rfqPackage.control_account_id ? accountLabel(rfqPackage.control_account_id) : "No control account"} /{" "}
                  {statusLabel(rfqPackage.status)} / {bidsByRfq[rfqPackage.id]?.length ?? 0} bids / due{" "}
                  {rfqPackage.due_date ?? "Open"}
                </small>
              </article>
            ))}
          </div>
        </div>
        <div>
          <div className="subHeader">
            <strong>Bid Leveling</strong>
            <span>{dashboard.rfq_bids.length} bids</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>Bidder</th>
                <th>RFQ</th>
                <th>Amount</th>
                <th>Score</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {dashboard.rfq_bids.map((bid) => (
                <tr key={bid.id}>
                  <td>{bid.bidder_name}</td>
                  <td>{rfqPackageLabel(bid.rfq_package_id)}</td>
                  <td>{currency(bid.bid_amount, project.currency)}</td>
                  <td>{bid.weighted_score.toFixed(1)}</td>
                  <td>{statusLabel(bid.status)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
