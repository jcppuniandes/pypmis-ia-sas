/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { Copy, Eye, Save, Send } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { portfolioPlanningApi } from "../portfolio-planning/api";
import { riskReadinessApi } from "./api";
import "./riskReadiness.css";
import type { RiskConfiguration } from "./types";

const TABS = [
  "Configuration Overview",
  "Risk Categories",
  "Likelihood Scale",
  "Impact Scale",
  "Risk Matrix",
  "Rating Bands",
  "Owner Rules",
  "Treatment Rules",
  "Residual Risk Rules",
  "Acceptance Authority",
  "Readiness Criteria",
  "Evidence Rules",
  "Validity / Expiry",
  "Gate Compatibility",
  "Inheritance / Overrides",
  "Versioning / Publish",
] as const;

function parse(value: string) {
  try {
    return JSON.parse(value) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export default function RiskReadinessAdminView({ token }: { token: string }) {
  const [records, setRecords] = useState<RiskConfiguration[]>([]);
  const [selected, setSelected] = useState<RiskConfiguration | null>(null);
  const [content, setContent] = useState("");
  const [tab, setTab] = useState<(typeof TABS)[number]>(TABS[0]);
  const [portfolios, setPortfolios] = useState<Array<Record<string, unknown>>>([]);
  const [portfolioId, setPortfolioId] = useState(0);
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [message, setMessage] = useState("");
  const parsed = useMemo(() => parse(content), [content]);

  async function load(preferredId?: number) {
    const [items, options] = await Promise.all([
      riskReadinessApi.configurations(token),
      portfolioPlanningApi.portfolioOptions(token),
    ]);
    const next =
      items.find((item) => item.id === preferredId) ||
      items.find((item) => item.status === "draft") ||
      items[0] ||
      null;
    setRecords(items);
    setSelected(next);
    setContent(next ? JSON.stringify(next.content_json, null, 2) : "");
    setPortfolios(options);
    setPortfolioId((current) => current || Number(options[0]?.id || 0));
  }

  useEffect(() => {
    void load().catch((error) => setMessage(error instanceof Error ? error.message : "Unable to load configuration"));
  }, [token]);

  function patch(key: string, value: unknown) {
    if (parsed) setContent(JSON.stringify({ ...parsed, [key]: value }, null, 2));
  }

  async function execute(action: "clone" | "save" | "publish") {
    if (!selected) return;
    try {
      let result = selected;
      if (action === "clone") result = await riskReadinessApi.cloneConfiguration(token, selected);
      if (action === "save") {
        if (!parsed) throw new Error("Configuration JSON is invalid.");
        result = await riskReadinessApi.updateConfiguration(token, selected, parsed);
      }
      if (action === "publish") result = await riskReadinessApi.publishConfiguration(token, selected);
      await load(result.id);
      setMessage(`Risk Readiness configuration ${action} completed.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Unable to ${action} configuration`);
    }
  }

  async function dryRun() {
    if (!selected || !parsed) return;
    try {
      setPreview(await riskReadinessApi.previewConfiguration(token, selected, parsed, portfolioId));
      setMessage("Dry-run completed: persisted=false; no risk, assessment or evidence snapshot was created.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to run preview");
    }
  }

  const categories = Array.isArray(parsed?.risk_categories) ? (parsed?.risk_categories as string[]) : [];
  const matrix = (parsed?.risk_matrix || {}) as Record<string, unknown>;
  const gate = (parsed?.pyp_ffa || {}) as Record<string, unknown>;

  return (
    <section aria-label="Risk Readiness Configuration" className="riskReadiness riskAdmin">
      <CompactModuleHeader
        description="Controls Project Risk categories, 5×5 scoring, treatment, residual acceptance, evidence coverage, 90-day validity, inheritance and provider compatibility. Starter configuration remains DRAFT until explicitly published."
        eyebrow="ADMIN MODE · INVESTMENT GOVERNANCE · GATE 07J-RISK"
        metrics={[
          { label: "Revisions", value: records.length },
          { label: "Evidence coverage", value: `${Number(parsed?.evidence_coverage_percent || 0)}%` },
          { label: "Validity", value: `${Number(parsed?.validity_days || 0)} days` },
        ]}
        title="Risk Readiness Configuration"
        tone="admin"
      />
      {message ? (
        <div className="riskMessage" role="status">
          {message}
        </div>
      ) : null}
      <nav aria-label="Risk Readiness configuration sections" className="riskAdminTabs">
        {TABS.map((item) => (
          <button className={tab === item ? "active" : ""} key={item} onClick={() => setTab(item)} type="button">
            {item}
          </button>
        ))}
      </nav>
      <div className="riskAdminGrid">
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
        <article className="riskSurface">
          <header>
            <div>
              <span>{tab}</span>
              <h3>{selected?.name || "No configuration"}</h3>
            </div>
            <StatusBadge value={selected?.status || "none"} />
          </header>
          {tab === "Configuration Overview" ? (
            <div className="riskPolicyGrid">
              <article>
                <span>Code</span>
                <strong>{String(parsed?.configuration_code || "—")}</strong>
              </article>
              <article>
                <span>Applicable model</span>
                <strong>CAPITAL_OWNER</strong>
              </article>
              <article>
                <span>Final output</span>
                <strong>READY_FOR_GOVERNED_RISK_EVIDENCE</strong>
              </article>
              <article>
                <span>Provider</span>
                <strong>RISK_READINESS_PROVIDER</strong>
              </article>
            </div>
          ) : null}
          {tab === "Risk Categories" ? (
            <div className="riskTags">
              {categories.map((item) => (
                <span key={item}>{item}</span>
              ))}
            </div>
          ) : null}
          {tab === "Likelihood Scale" || tab === "Impact Scale" ? (
            <ConfigList value={parsed?.[tab === "Likelihood Scale" ? "likelihood_scale" : "impact_scale"]} />
          ) : null}
          {tab === "Risk Matrix" ? <Matrix value={matrix} /> : null}
          {tab === "Rating Bands" ? (
            <div className="riskTags">
              {["LOW", "MODERATE", "HIGH", "CRITICAL"].map((item) => (
                <StatusBadge key={item} value={item} />
              ))}
            </div>
          ) : null}
          {tab === "Owner Rules" ? (
            <RuleEditor
              label="Owner required from"
              value={String(parsed?.owner_required_threshold || "HIGH")}
              onChange={(value) => patch("owner_required_threshold", value)}
            />
          ) : null}
          {tab === "Treatment Rules" ? (
            <RuleEditor
              label="Treatment required from"
              value={String(parsed?.treatment_required_threshold || "HIGH")}
              onChange={(value) => patch("treatment_required_threshold", value)}
            />
          ) : null}
          {tab === "Residual Risk Rules" ? (
            <RuleEditor
              label="Residual assessment from"
              value={String(parsed?.residual_assessment_threshold || "HIGH")}
              onChange={(value) => patch("residual_assessment_threshold", value)}
            />
          ) : null}
          {tab === "Acceptance Authority" ? <ConfigList value={parsed?.acceptance_authority} /> : null}
          {tab === "Readiness Criteria" ? <ConfigList value={parsed?.readiness_criteria} /> : null}
          {tab === "Evidence Rules" ? (
            <label className="riskField">
              Minimum evidence coverage %
              <input
                disabled={selected?.status !== "draft"}
                max={100}
                min={0}
                type="number"
                value={Number(parsed?.evidence_coverage_percent || 100)}
                onChange={(event) => patch("evidence_coverage_percent", Number(event.target.value))}
              />
            </label>
          ) : null}
          {tab === "Validity / Expiry" ? (
            <label className="riskField">
              Validity days
              <input
                disabled={selected?.status !== "draft"}
                max={3650}
                min={1}
                type="number"
                value={Number(parsed?.validity_days || 90)}
                onChange={(event) => patch("validity_days", Number(event.target.value))}
              />
            </label>
          ) : null}
          {tab === "Gate Compatibility" ? (
            <div className="riskPolicyGrid">
              <article>
                <span>PYP-INV-SELECT</span>
                <strong>Class B · 90d · nonblocking</strong>
              </article>
              <article>
                <span>PYP-FFA</span>
                <strong>
                  Class {String(gate.classification || "A")} · {String(gate.validity_days || 90)}d · blocking
                </strong>
              </article>
              <article>
                <span>Manual fallback</span>
                <strong>PROHIBITED for Class A</strong>
              </article>
              <article>
                <span>FID</span>
                <strong>Not implemented</strong>
              </article>
            </div>
          ) : null}
          {tab === "Inheritance / Overrides" ? <ConfigList value={parsed?.inheritance} /> : null}
          {tab === "Versioning / Publish" ? (
            <p>
              Only DRAFT revisions are mutable. Publish supersedes the previous revision; completed assessments retain
              their frozen configuration hash.
            </p>
          ) : null}
          <details className="riskJson">
            <summary>Advanced controlled JSON</summary>
            <textarea
              disabled={selected?.status !== "draft"}
              onChange={(event) => setContent(event.target.value)}
              value={content}
            />
          </details>
          <div className="riskActions">
            <button onClick={() => void execute("clone")} type="button">
              <Copy size={16} /> Clone
            </button>
            <button
              disabled={selected?.status !== "draft" || !parsed}
              onClick={() => void execute("save")}
              type="button"
            >
              <Save size={16} /> Save
            </button>
            <button disabled={!parsed} onClick={() => void dryRun()} type="button">
              <Eye size={16} /> Preview
            </button>
            <button
              disabled={selected?.status !== "draft" || !parsed}
              onClick={() => void execute("publish")}
              type="button"
            >
              <Send size={16} /> Publish
            </button>
          </div>
          <label className="riskField">
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
          {preview ? <pre>{JSON.stringify(preview, null, 2)}</pre> : null}
        </article>
      </div>
      <p className="riskBoundary">
        GATE07J_RISK_RELEASE_VALIDATED · No arbitrary formulas · No ERM/QRA · No Permit provider · can_enter_fid=false
      </p>
    </section>
  );
}

function StatusBadge({ value }: { value: string }) {
  return <span className={`riskStatus ${value.toLowerCase().replace(/_/g, "-")}`}>{value}</span>;
}
function ConfigList({ value }: { value: unknown }) {
  return <pre>{JSON.stringify(value ?? {}, null, 2)}</pre>;
}
function RuleEditor({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="riskField">
      {label}
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {["LOW", "MODERATE", "HIGH", "CRITICAL"].map((item) => (
          <option key={item}>{item}</option>
        ))}
      </select>
    </label>
  );
}
function Matrix({ value }: { value: Record<string, unknown> }) {
  return (
    <table className="riskMatrix">
      <thead>
        <tr>
          <th>L / I</th>
          {[1, 2, 3, 4, 5].map((item) => (
            <th key={item}>{item}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {[1, 2, 3, 4, 5].map((likelihood) => (
          <tr key={likelihood}>
            <th>{likelihood}</th>
            {[1, 2, 3, 4, 5].map((impact) => (
              <td key={impact}>
                <StatusBadge value={String(value[`${likelihood}x${impact}`] || "—")} />
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
