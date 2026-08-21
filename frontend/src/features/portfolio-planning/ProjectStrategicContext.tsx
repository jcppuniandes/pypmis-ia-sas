import { GitBranch, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { portfolioPlanningApi } from "./api";
import type { StrategicPlanningEntry } from "./types";
import "./portfolioPlanning.css";

export default function ProjectStrategicContext({ token, projectId }: { token: string; projectId: number }) {
  const [entry, setEntry] = useState<StrategicPlanningEntry | null>(null);
  const [message, setMessage] = useState("");
  useEffect(() => {
    portfolioPlanningApi
      .projectReadiness(token, projectId)
      .then(setEntry)
      .catch((error) => setMessage(error instanceof Error ? error.message : "Strategic context unavailable"));
  }, [projectId, token]);
  if (message) return <div className="planningMessage">{message}</div>;
  if (!entry) return <div className="planningEmpty">Loading Strategic Context…</div>;
  return (
    <section className="portfolioPlanning projectStrategicContext">
      <div className="planningGrid">
        <article className="planningCard">
          <header>
            <GitBranch size={18} />
            <h3>Strategic lineage</h3>
          </header>
          <p>
            {String(entry.source_idea.idea_number || "Idea")} → {String(entry.proposal.proposal_number || "Proposal")} →{" "}
            {String(entry.decision.decision_number || "Decision")}
          </p>
          <p>Portfolio: {String(entry.target_portfolio?.name || "—")}</p>
          <p>Memberships: {entry.portfolio_memberships.length}</p>
        </article>
        <article className="planningCard">
          <header>
            <ShieldCheck size={18} />
            <h3>Planning readiness</h3>
          </header>
          <strong className={entry.status === "READY_FOR_PORTFOLIO_PLANNING" ? "ready" : "blocked"}>
            {entry.status}
          </strong>
          <p>Portfolio Evaluation: {entry.portfolio_evaluation_readiness.status}</p>
          <p>Project Definition: {entry.project_definition_readiness.status}</p>
        </article>
      </div>
    </section>
  );
}
