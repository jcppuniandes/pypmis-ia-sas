import type { AppShellCtx } from "../components/AppShellCtx";
import { currency, statusLabel } from "../components/utils";

export default function ClaimsView({ ctx }: { ctx: AppShellCtx }) {
  const { activeView, dashboard, project, entitlementByClaim, noticesByClaim, impactByClaim } = ctx;
  return (
    <section className={activeView === "claims" ? "viewPanel workspaceSection" : "viewPanel workspaceSection hidden"}>
      <div className="panelHeader">
        <h2>Claims / Forensic Entitlement</h2>
        <span>Notice / causation / impact / quantum / evidence</span>
      </div>
      <div className="claimSummary">
        <article>
          <span>Forensic Readiness</span>
          <strong>{dashboard.claims_forensic_summary.forensic_readiness_score.toFixed(1)}%</strong>
          <small>Weighted from notices, impact analysis and entitlement evidence</small>
        </article>
        <article className={dashboard.claims_forensic_summary.late_notices ? "risk" : ""}>
          <span>Notice Compliance</span>
          <strong>
            {dashboard.claims_forensic_summary.compliant_notices}/{dashboard.claims_forensic_summary.notice_count}
          </strong>
          <small>
            {dashboard.claims_forensic_summary.late_notices} late notices /{" "}
            {dashboard.claims_forensic_summary.total_claims} claims
          </small>
        </article>
        <article>
          <span>Quantified Claims</span>
          <strong>{dashboard.claims_forensic_summary.quantified_claims}</strong>
          <small>{dashboard.claims_forensic_summary.impact_analyses} impact analyses registered</small>
        </article>
        <article className={dashboard.claim_entitlement_summary.cumulative_gap_items ? "risk" : ""}>
          <span>Claimed Impact</span>
          <strong>{currency(dashboard.claims_forensic_summary.total_claimed_cost, project.currency)}</strong>
          <small>
            {dashboard.claims_forensic_summary.total_schedule_impact_days} schedule days /{" "}
            {dashboard.claim_entitlement_summary.gap_items} entitlement gaps
          </small>
        </article>
      </div>

      <div className="forensicWorkspace">
        <div>
          <div className="subHeader">
            <strong>Contractual Notices</strong>
            <span>{dashboard.contract_notices.length} records</span>
          </div>
          <div className="noticeGrid">
            {dashboard.contract_notices.map((notice) => (
              <article className={notice.compliance_status === "late" ? "late" : "compliant"} key={notice.id}>
                <div>
                  <strong>{notice.reference || `Notice ${notice.id}`}</strong>
                  <span>{statusLabel(notice.compliance_status)}</span>
                </div>
                <p>{notice.subject}</p>
                <small>
                  Event {notice.event_date ?? "pending"} / due {notice.due_date ?? "pending"} / issued{" "}
                  {notice.notice_date ?? "pending"}
                </small>
              </article>
            ))}
          </div>
        </div>
        <div>
          <div className="subHeader">
            <strong>Impact Analysis</strong>
            <span>{dashboard.claim_impact_analyses.length} analyses</span>
          </div>
          <div className="impactGrid">
            {dashboard.claim_impact_analyses.map((analysis) => (
              <article key={analysis.id}>
                <div>
                  <strong>{analysis.method}</strong>
                  <span>{(analysis.confidence_score * 100).toFixed(0)}% confidence</span>
                </div>
                <p>{analysis.impacted_activity}</p>
                <small>
                  {currency(analysis.cost_impact, project.currency)} / {analysis.schedule_impact_days} days /{" "}
                  {analysis.productivity_loss_percent.toFixed(1)}% productivity loss
                </small>
              </article>
            ))}
          </div>
        </div>
      </div>

      <div className="workList">
        {dashboard.claims.map((claim) => {
          const entitlementItems = entitlementByClaim[claim.id] ?? [];
          const claimNotices = noticesByClaim[claim.id] ?? [];
          const claimImpacts = impactByClaim[claim.id] ?? [];
          const claimScore = entitlementItems.length
            ? Math.round(
                (entitlementItems.reduce((total, item) => total + item.score * item.weight, 0) /
                  entitlementItems.reduce((total, item) => total + item.weight, 0)) *
                  100
              )
            : 0;
          const claimedCost = claimImpacts.reduce((total, item) => total + item.cost_impact, 0);
          const claimedDays = claimImpacts.reduce((total, item) => total + item.schedule_impact_days, 0);
          return (
            <article className="claimCard" key={claim.id}>
              <div className="claimHeader">
                <div>
                  <strong>{claim.title}</strong>
                  <span>{claim.causality}</span>
                </div>
                <div>
                  <strong>{claimScore}%</strong>
                  <small>{statusLabel(claim.status)}</small>
                </div>
              </div>
              <p>{claim.impact}</p>
              <small>{claim.evidence_summary}</small>
              <div className="claimTrace">
                <span>{claimNotices.length} notices</span>
                <span>{claimImpacts.length} impact analyses</span>
                <span>
                  {currency(claimedCost, project.currency)} / {claimedDays} days
                </span>
              </div>
              <div className="entitlementMatrix">
                {entitlementItems.map((item) => (
                  <article className={`entitlementItem ${item.status}`} key={item.id}>
                    <div>
                      <span>
                        {item.practice_source} / {item.category}
                      </span>
                      <strong>{item.element}</strong>
                    </div>
                    <p>{item.requirement}</p>
                    <small>{item.assessment}</small>
                    <div className="entitlementMeta">
                      <span>{item.evidence_ref || "No evidence linked"}</span>
                      <strong>
                        {statusLabel(item.status)} / {(item.score * 100).toFixed(0)}%
                      </strong>
                    </div>
                  </article>
                ))}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
