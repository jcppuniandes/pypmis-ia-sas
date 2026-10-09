/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { Copy, Eye, Save, Send } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { portfolioPlanningApi } from "../portfolio-planning/api";
import "../portfolio-planning/portfolioPlanning.css";
import { investmentGatePreparationApi } from "./api";
import type { InvestmentGateConfiguration } from "./types";
import "./investmentGatePreparation.css";

const sections = [
  "Profiles",
  "Evidence Requirements",
  "Validity & Refresh",
  "Readiness & Blocking",
  "Roles & Segregation",
  "Inheritance & Precedence",
];
function parse(value: string) {
  try {
    return JSON.parse(value) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export default function InvestmentGatePreparationAdminView({ token }: { token: string }) {
  const [records, setRecords] = useState<InvestmentGateConfiguration[]>([]);
  const [selected, setSelected] = useState<InvestmentGateConfiguration | null>(null);
  const [content, setContent] = useState("");
  const [section, setSection] = useState(sections[0]);
  const [portfolios, setPortfolios] = useState<Array<Record<string, unknown>>>([]);
  const [portfolioId, setPortfolioId] = useState(0);
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [message, setMessage] = useState("");
  const parsed = useMemo(() => parse(content), [content]);

  async function load(preferredId?: number) {
    const [items, portfolioItems] = await Promise.all([
      investmentGatePreparationApi.configurations(token),
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
      setMessage(error instanceof Error ? error.message : "Unable to load Gate 07J configuration")
    );
  }, [token]);

  async function execute(action: "clone" | "save" | "publish") {
    if (!selected) return;
    try {
      let result = selected;
      if (action === "clone") result = await investmentGatePreparationApi.cloneConfiguration(token, selected);
      if (action === "save") {
        if (!parsed) throw new Error("Configuration JSON is invalid.");
        result = await investmentGatePreparationApi.updateConfiguration(token, selected, parsed);
      }
      if (action === "publish") result = await investmentGatePreparationApi.publishConfiguration(token, selected);
      await load(result.id);
      setMessage(`Gate 07J configuration ${action} completed.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Unable to ${action} configuration`);
    }
  }
  async function previewDraft() {
    if (!selected || !parsed) return;
    try {
      setPreview(
        await investmentGatePreparationApi.previewConfiguration(token, portfolioId || null, selected.id, parsed)
      );
      setMessage("Dry-run completed: persisted=false; no preparation, decision or FID was created.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to preview configuration");
    }
  }

  return (
    <section
      aria-label="Investment Gate Preparation Configuration"
      className="investmentGatePreparation gatePreparationAdmin"
    >
      <CompactModuleHeader
        description="Configures profiles, evidence requirements, validity, refresh, readiness, blockers, SOD and inherited scope. Publishing never creates an investment decision, FID, funds or project activation."
        eyebrow="ADMIN MODE · ENTERPRISE STRATEGY MANAGER · PORTFOLIO MANAGER · GATE 07J"
        metrics={[
          { label: "Profiles", value: records.length },
          { label: "Selected", value: String(parsed?.profile_code || "—") },
          { label: "FEL", value: String(parsed?.required_FEL_stage || "—") },
        ]}
        title="Investment Gate Preparation Configuration"
        tone="admin"
      />
      {message ? (
        <div className="planningMessage" role="status">
          {message}
        </div>
      ) : null}
      <nav aria-label="Investment gate configuration sections" className="gateConfigTabs">
        {sections.map((item) => (
          <button
            className={section === item ? "active" : ""}
            key={item}
            onClick={() => setSection(item)}
            type="button"
          >
            {item}
          </button>
        ))}
      </nav>
      <div className="gateAdminGrid">
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
        <article className="gateSurface">
          <header>
            <div>
              <span>{section}</span>
              <h3>{selected?.name || "No configuration"}</h3>
            </div>
            <strong>{selected?.status}</strong>
          </header>
          <div className="gatePolicySummary">
            <article>
              <span>Purpose</span>
              <b>{String(parsed?.gate_purpose || "—")}</b>
            </article>
            <article>
              <span>Governance</span>
              <b>CAPITAL_OWNER only</b>
            </article>
            <article>
              <span>Coverage</span>
              <b>{String(parsed?.project_coverage_threshold_percent || 0)}%</b>
            </article>
            <article>
              <span>Scoring</span>
              <b>Source result only</b>
            </article>
          </div>
          <label className="gatePreviewPortfolio">
            Dry-run Portfolio
            <select value={portfolioId} onChange={(event) => setPortfolioId(Number(event.target.value))}>
              <option value={0}>Configuration only</option>
              {portfolios.map((item) => (
                <option key={Number(item.id)} value={Number(item.id)}>
                  {String(item.name)}
                </option>
              ))}
            </select>
          </label>
          <details open className="gateConfigJson">
            <summary>Controlled configuration JSON</summary>
            <textarea
              aria-label="Investment Gate Preparation configuration JSON"
              disabled={selected?.status !== "draft"}
              onChange={(event) => setContent(event.target.value)}
              rows={28}
              value={content}
            />
          </details>
          <div className="gateActions">
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
      <p className="gateGuardrail">
        No controls for GO/HOLD/RECYCLE/KILL, investment approval, FID, Funds, FEL/PDRI scoring, project initialization,
        activation or execution exist in Gate 07J.
      </p>
    </section>
  );
}
