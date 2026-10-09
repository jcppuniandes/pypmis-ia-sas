/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { Copy, Eye, Save, Send } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { portfolioPlanningApi } from "../portfolio-planning/api";
import "../portfolio-planning/portfolioPlanning.css";
import { portfolioConvergenceApi } from "./api";
import type { ConvergenceConfiguration } from "./types";
import "./portfolioConvergence.css";

function parse(value: string) {
  try {
    return JSON.parse(value) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export default function PortfolioConvergenceAdminView({ token }: { token: string }) {
  const [records, setRecords] = useState<ConvergenceConfiguration[]>([]);
  const [selected, setSelected] = useState<ConvergenceConfiguration | null>(null);
  const [content, setContent] = useState("");
  const [portfolios, setPortfolios] = useState<Array<Record<string, unknown>>>([]);
  const [portfolioId, setPortfolioId] = useState(0);
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [message, setMessage] = useState("");
  const parsed = useMemo(() => parse(content), [content]);

  async function load(preferredId?: number) {
    const [items, portfolioItems] = await Promise.all([
      portfolioConvergenceApi.configurations(token),
      portfolioPlanningApi.portfolioOptions(token),
    ]);
    setRecords(items);
    setPortfolios(portfolioItems);
    setPortfolioId((current) => current || Number(portfolioItems[0]?.id || 0));
    const next =
      items.find((item) => item.id === preferredId) ||
      items.find((item) => item.status === "draft") ||
      items[0] ||
      null;
    setSelected(next);
    setContent(next ? JSON.stringify(next.content_json, null, 2) : "");
  }

  useEffect(() => {
    void load().catch((error) =>
      setMessage(error instanceof Error ? error.message : "Unable to load Gate 07I configuration")
    );
  }, [token]);

  function patch(key: string, value: unknown) {
    if (!parsed) return;
    setContent(JSON.stringify({ ...parsed, [key]: value }, null, 2));
  }

  async function execute(action: "clone" | "save" | "publish") {
    if (!selected) return;
    try {
      let result = selected;
      if (action === "clone") result = await portfolioConvergenceApi.cloneConfiguration(token, selected);
      if (action === "save") {
        if (!parsed) throw new Error("Configuration JSON is invalid.");
        result = await portfolioConvergenceApi.updateConfiguration(token, selected, parsed);
      }
      if (action === "publish") result = await portfolioConvergenceApi.publishConfiguration(token, selected);
      await load(result.id);
      setMessage(`Gate 07I configuration ${action} completed.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Unable to ${action} configuration`);
    }
  }

  async function previewDraft() {
    if (!selected || !parsed) return;
    try {
      setPreview(await portfolioConvergenceApi.previewConfiguration(token, portfolioId || null, selected.id, parsed));
      setMessage("Dry-run completed: persisted=false; no convergence or recommendation was created.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to preview configuration");
    }
  }

  return (
    <section
      aria-label="Portfolio Scenario Convergence Configuration"
      className="portfolioConvergence portfolioConvergenceAdmin"
    >
      <CompactModuleHeader
        description="Governed source branches, project-set alignment, forced-conflict treatment, conditional recommendation, evidence, roles, inheritance and readiness. Configuration does not approve investment or enable FID."
        eyebrow="ADMIN MODE · ENTERPRISE STRATEGY MANAGER · PORTFOLIO MANAGER · GATE 07I"
        metrics={[
          { label: "Revisions", value: records.length },
          { label: "Budget", value: parsed?.required_budget_branch === false ? "OPTIONAL" : "REQUIRED" },
          { label: "Resource", value: parsed?.required_resource_branch === false ? "OPTIONAL" : "REQUIRED" },
        ]}
        title="Portfolio Scenario Convergence Configuration"
        tone="admin"
      />
      {message ? (
        <div className="planningMessage" role="status">
          {message}
        </div>
      ) : null}
      <div className="convergenceAdminGrid">
        <aside>
          {records.map((item) => (
            <button
              className={selected?.id === item.id ? "active" : ""}
              key={item.id}
              onClick={() => {
                setSelected(item);
                setContent(JSON.stringify(item.content_json, null, 2));
                setPreview(null);
              }}
              type="button"
            >
              <strong>{item.name}</strong>
              <span>
                {item.status} · rev {item.revision}
              </span>
            </button>
          ))}
        </aside>
        <article className="convergenceSurface">
          <header>
            <div>
              <span>Controlled Gate 07I policy</span>
              <h3>{selected?.name || "No configuration"}</h3>
            </div>
            <strong>{selected?.status}</strong>
          </header>
          <section className="convergencePolicyGrid">
            <label>
              <input
                checked={Boolean(parsed?.required_budget_branch)}
                disabled={selected?.status !== "draft"}
                onChange={(event) => patch("required_budget_branch", event.target.checked)}
                type="checkbox"
              />{" "}
              Require Gate 07G budget branch
            </label>
            <label>
              <input
                checked={Boolean(parsed?.required_resource_branch)}
                disabled={selected?.status !== "draft"}
                onChange={(event) => patch("required_resource_branch", event.target.checked)}
                type="checkbox"
              />{" "}
              Require Gate 07H resource branch
            </label>
            <label>
              <input
                checked={Boolean(parsed?.require_identical_project_sets)}
                disabled={selected?.status !== "draft"}
                onChange={(event) => patch("require_identical_project_sets", event.target.checked)}
                type="checkbox"
              />{" "}
              Require identical project sets
            </label>
            <label>
              <input
                checked={Boolean(parsed?.forced_conflict_is_blocker)}
                disabled={selected?.status !== "draft"}
                onChange={(event) => patch("forced_conflict_is_blocker", event.target.checked)}
                type="checkbox"
              />{" "}
              Forced conflicts block recommendation
            </label>
            <label>
              <input
                checked={Boolean(parsed?.allow_conditional_recommendation)}
                disabled={selected?.status !== "draft"}
                onChange={(event) => patch("allow_conditional_recommendation", event.target.checked)}
                type="checkbox"
              />{" "}
              Allow conditional recommendation
            </label>
            <label>
              <input
                checked={Boolean(parsed?.recommender_sod_required)}
                disabled={selected?.status !== "draft"}
                onChange={(event) => patch("recommender_sod_required", event.target.checked)}
                type="checkbox"
              />{" "}
              Require recommender segregation of duties
            </label>
            <label className="wide">
              Preview Portfolio
              <select value={portfolioId} onChange={(event) => setPortfolioId(Number(event.target.value))}>
                <option value={0}>Configuration only</option>
                {portfolios.map((item) => (
                  <option key={Number(item.id)} value={Number(item.id)}>
                    {String(item.name)}
                  </option>
                ))}
              </select>
            </label>
          </section>
          <details className="convergenceJson">
            <summary>Advanced controlled JSON</summary>
            <textarea
              aria-label="Portfolio Convergence configuration JSON"
              disabled={selected?.status !== "draft"}
              onChange={(event) => setContent(event.target.value)}
              rows={26}
              value={content}
            />
          </details>
          <div className="convergenceActions">
            <button
              disabled={!selected || selected.status !== "published"}
              onClick={() => void execute("clone")}
              type="button"
            >
              <Copy size={14} /> Clone
            </button>
            <button disabled={!selected || !parsed} onClick={() => void previewDraft()} type="button">
              <Eye size={14} /> Preview
            </button>
            <button
              disabled={!selected || selected.status !== "draft" || !parsed}
              onClick={() => void execute("save")}
              type="button"
            >
              <Save size={14} /> Save
            </button>
            <button
              disabled={!selected || selected.status !== "draft" || !parsed}
              onClick={() => void execute("publish")}
              type="button"
            >
              <Send size={14} /> Publish
            </button>
          </div>
          {preview ? (
            <details open>
              <summary>Effective policy preview</summary>
              <pre>{JSON.stringify(preview, null, 2)}</pre>
            </details>
          ) : null}
        </article>
      </div>
      <p className="convergenceGuardrail">
        ADMIN configuration cannot create alternatives, make a recommendation, approve investment, enter FID, initialize
        or execute projects.
      </p>
    </section>
  );
}
