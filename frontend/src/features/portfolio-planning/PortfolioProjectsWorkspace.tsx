/* eslint-disable react-hooks/set-state-in-effect, react-hooks/exhaustive-deps */
import { FolderKanban, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { portfolioPlanningApi } from "./api";
import type { PortfolioProject } from "./types";
import "./portfolioPlanning.css";

export default function PortfolioProjectsWorkspace({ token, portfolioId }: { token: string; portfolioId?: number }) {
  const [portfolios, setPortfolios] = useState<Array<Record<string, unknown>>>([]);
  const [selectedId, setSelectedId] = useState(portfolioId || 0);
  const [projects, setProjects] = useState<PortfolioProject[]>([]);
  const [message, setMessage] = useState("");

  async function loadPortfolioOptions() {
    const items = await portfolioPlanningApi.portfolioOptions(token);
    setPortfolios(items);
    setSelectedId((current) => current || portfolioId || Number(items[0]?.id || 0));
  }

  async function loadProjects(id = selectedId) {
    if (!id) return;
    try {
      setProjects(await portfolioPlanningApi.portfolioProjects(token, id));
      setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load Portfolio Projects");
    }
  }

  useEffect(() => {
    void loadPortfolioOptions().catch(() => setMessage("Unable to load Portfolios"));
  }, [token]);
  useEffect(() => {
    if (selectedId) void loadProjects(selectedId);
  }, [selectedId]);

  return (
    <section className="portfolioPlanning" aria-label="Portfolio Projects">
      <CompactModuleHeader
        description="Analytical Project memberships for Portfolio Planning. Membership does not change the Enterprise Workspace hierarchy."
        eyebrow="USER MODE · PORTFOLIO MANAGER"
        metrics={[
          { label: "Projects", value: projects.length },
          { label: "Membership", value: "N:M ready" },
          { label: "Candidate model", value: "Not used" },
        ]}
        title="Portfolio Projects"
        tone="user"
      />
      <div className="planningToolbar">
        <label>
          <span>Portfolio</span>
          <select
            aria-label="Portfolio"
            disabled={Boolean(portfolioId)}
            value={selectedId}
            onChange={(event) => setSelectedId(Number(event.target.value))}
          >
            {portfolios.map((item) => (
              <option key={String(item.id)} value={Number(item.id)}>
                {String(item.name)} · {String(item.record_code)}
              </option>
            ))}
          </select>
        </label>
        <button className="planningSecondary" onClick={() => void loadProjects()} type="button">
          <RefreshCw size={15} /> Refresh
        </button>
      </div>
      {message ? (
        <div className="planningMessage" role="status">
          {message}
        </div>
      ) : null}
      <div className="portfolioProjectRegister">
        {projects.map((item) => (
          <article className="planningCard" key={`${item.membership.id}-${item.project_workspace_id}`}>
            <header>
              <FolderKanban size={18} />
              <div>
                <span>{item.project_number}</span>
                <h3>{item.project_name}</h3>
              </div>
              <strong className="ready">{item.workspace_status}</strong>
            </header>
            <dl>
              <div>
                <dt>Planning stage</dt>
                <dd>{item.planning_stage}</dd>
              </div>
              <div>
                <dt>Membership</dt>
                <dd>
                  {item.membership.membership_source}
                  {item.membership.is_target_portfolio ? " · TARGET" : ""}
                </dd>
              </div>
              <div>
                <dt>Decision</dt>
                <dd>{item.decision_number || "—"}</dd>
              </div>
              <div>
                <dt>Proposal</dt>
                <dd>{item.proposal_number || "—"}</dd>
              </div>
              <div>
                <dt>Portfolio readiness</dt>
                <dd>{item.portfolio_evaluation_readiness.status}</dd>
              </div>
              <div>
                <dt>Definition readiness</dt>
                <dd>{item.project_definition_readiness.status}</dd>
              </div>
            </dl>
          </article>
        ))}
        {!projects.length ? (
          <article className="planningEmpty">
            <strong>No Portfolio Projects</strong>
            <span>Complete a Strategic Planning Entry and materialize its PENDING Project.</span>
          </article>
        ) : null}
      </div>
    </section>
  );
}
