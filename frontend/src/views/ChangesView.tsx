import type { AppShellCtx } from "../components/AppShellCtx";
import { currency, statusLabel } from "../components/utils";

export default function ChangesView({ ctx }: { ctx: AppShellCtx }) {
  const { activeView, dashboard, project, setActiveView } = ctx;
  return (
    <section className={activeView === "changes" ? "viewPanel workspaceSection" : "viewPanel workspaceSection hidden"}>
      <div className="panelHeader">
        <h2>Change Management</h2>
        <button className="linkButton" onClick={() => setActiveView("bp-entry-forms")} type="button">
          Create change BP
        </button>
      </div>
      <div className="workList">
        {dashboard.changes.map((change) => (
          <article key={change.id}>
            <strong>{change.title}</strong>
            <span>{change.deviation}</span>
            <small>
              {currency(change.cost_impact, project.currency)} / {change.schedule_impact_days} days /{" "}
              {statusLabel(change.status)}
            </small>
          </article>
        ))}
      </div>
    </section>
  );
}
