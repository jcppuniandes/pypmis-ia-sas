/* eslint-disable react-hooks/exhaustive-deps */
import { Copy, Eye, Save, Send } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { portfolioPlanningApi } from "../portfolio-planning/api";
import "../portfolio-planning/portfolioPlanning.css";
import { portfolioAnalysisApi } from "./api";
import type { AnalysisConfiguration, MetricDefinition } from "./types";
import "./portfolioAnalysis.css";

const sections = [
  "General",
  "Metric Catalog",
  "Investor Map",
  "Scorecard",
  "Buckets",
  "Reference Lines",
  "Filters",
  "Readiness",
  "Inheritance",
  "Permissions",
  "Preview",
];

function parseContent(value: string) {
  try {
    return JSON.parse(value) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export default function PortfolioAnalysisAdminView({ token }: { token: string }) {
  const [records, setRecords] = useState<AnalysisConfiguration[]>([]);
  const [selected, setSelected] = useState<AnalysisConfiguration | null>(null);
  const [portfolios, setPortfolios] = useState<Array<Record<string, unknown>>>([]);
  const [portfolioId, setPortfolioId] = useState(0);
  const [content, setContent] = useState("");
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [message, setMessage] = useState("");
  const loadSequence = useRef(0);

  async function load(preferredId?: number) {
    const sequence = ++loadSequence.current;
    const [items, portfolioItems] = await Promise.all([
      portfolioAnalysisApi.configurations(token),
      portfolioPlanningApi.portfolioOptions(token),
    ]);
    if (sequence !== loadSequence.current) return;
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
      setMessage(error instanceof Error ? error.message : "Unable to load Gate 07F configuration")
    );
  }, [token]);

  const parsed = useMemo(() => parseContent(content), [content]);
  const catalog = (parsed?.metric_catalog as MetricDefinition[] | undefined) || [];
  const investorMap = (parsed?.investor_map as Record<string, unknown> | undefined) || {};
  const scorecard = (parsed?.scorecard as Record<string, unknown> | undefined) || {};
  const referenceLines = (investorMap.reference_lines as Array<Record<string, unknown>> | undefined) || [];

  function patch(mutator: (next: Record<string, unknown>) => void) {
    if (!parsed) {
      setMessage("Configuration JSON must be valid before using structured controls.");
      return;
    }
    const next = structuredClone(parsed);
    mutator(next);
    setContent(JSON.stringify(next, null, 2));
  }

  function patchMap(key: string, value: string) {
    patch((next) => {
      const map = { ...((next.investor_map as Record<string, unknown> | undefined) || {}) };
      map[key] = value;
      next.investor_map = map;
    });
  }

  function patchReference(axis: "x" | "y", value: string) {
    patch((next) => {
      const map = { ...((next.investor_map as Record<string, unknown> | undefined) || {}) };
      const lines = [...((map.reference_lines as Array<Record<string, unknown>> | undefined) || [])];
      const index = lines.findIndex((item) => item.axis === axis);
      const line = {
        axis,
        value: Number(value),
        label: axis === "x" ? "Portfolio score reference" : "Strategic alignment reference",
      };
      if (index >= 0) lines[index] = line;
      else lines.push(line);
      map.reference_lines = lines;
      next.investor_map = map;
    });
  }

  async function execute(action: "clone" | "save" | "publish") {
    if (!selected) return;
    try {
      let result = selected;
      if (action === "clone") result = await portfolioAnalysisApi.cloneConfiguration(token, selected);
      if (action === "save") {
        if (!parsed) throw new Error("Configuration JSON is invalid.");
        result = await portfolioAnalysisApi.updateConfiguration(token, selected, parsed);
      }
      if (action === "publish") result = await portfolioAnalysisApi.publishConfiguration(token, selected);
      setSelected(result);
      setContent(JSON.stringify(result.content_json, null, 2));
      setRecords((current) => {
        const present = current.some((item) => item.id === result.id);
        return present ? current.map((item) => (item.id === result.id ? result : item)) : [...current, result];
      });
      setMessage(`Gate 07F configuration ${action} completed.`);
      await load(result.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Unable to ${action} configuration`);
    }
  }

  async function previewDraft() {
    if (!selected || !parsed) {
      setMessage("Select a configuration and provide valid JSON before Preview.");
      return;
    }
    try {
      setPreview(await portfolioAnalysisApi.previewConfiguration(token, portfolioId || undefined, selected.id, parsed));
      setMessage("Gate 07F Preview completed without persisting snapshot, rank, membership or evaluation data.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to preview configuration");
    }
  }

  function options(capability: keyof MetricDefinition) {
    return catalog.filter((item) => Boolean(item[capability]));
  }

  return (
    <section aria-label="Portfolio Analysis Configuration" className="portfolioAnalysis portfolioAnalysisAdmin">
      <CompactModuleHeader
        description="Governed Metric Catalog, Investor Map, Scorecard, buckets, filters, inheritance and analysis readiness. Draft defaults require explicit publication."
        eyebrow="ADMIN MODE · ENTERPRISE STRATEGY MANAGER · PORTFOLIO MANAGER · GATE 07F"
        metrics={[
          { label: "Revisions", value: records.length },
          { label: "Starter state", value: "DRAFT" },
          { label: "Snapshot policy", value: "Derived" },
        ]}
        title="Portfolio Analysis Configuration"
        tone="admin"
      />
      <nav aria-label="Portfolio Analysis configuration sections" className="planningAdminSections">
        {sections.map((item) => (
          <button key={item} type="button">
            {item}
          </button>
        ))}
      </nav>
      {message ? (
        <div className="planningMessage" role="status">
          {message}
        </div>
      ) : null}
      <div className="planningAdminGrid analysisAdminGrid">
        <aside>
          {records.map((item) => (
            <button
              className={selected?.id === item.id ? "active" : ""}
              data-testid={`portfolio-analysis-configuration-${item.id}`}
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
        <article className="analysisAdminEditor">
          <header className="analysisSectionHeader">
            <div>
              <span>Controlled configuration</span>
              <h3>{selected?.name || "No configuration"}</h3>
            </div>
            <strong className={selected?.status === "published" ? "ready" : "blocked"}>{selected?.status || ""}</strong>
          </header>
          <section aria-label="Investor Map configuration" className="analysisStructuredConfig">
            <label>
              X Axis
              <select
                disabled={selected?.status !== "draft"}
                value={String(investorMap.x_axis || "")}
                onChange={(event) => patchMap("x_axis", event.target.value)}
              >
                {options("allowed_for_x_axis").map((item) => (
                  <option key={item.metric_key} value={item.metric_key}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Y Axis
              <select
                disabled={selected?.status !== "draft"}
                value={String(investorMap.y_axis || "")}
                onChange={(event) => patchMap("y_axis", event.target.value)}
              >
                {options("allowed_for_y_axis").map((item) => (
                  <option key={item.metric_key} value={item.metric_key}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Bubble Size
              <select
                disabled={selected?.status !== "draft"}
                value={String(investorMap.size || "")}
                onChange={(event) => patchMap("size", event.target.value)}
              >
                {options("allowed_for_size").map((item) => (
                  <option key={item.metric_key} value={item.metric_key}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Bubble Color
              <select
                disabled={selected?.status !== "draft"}
                value={String(investorMap.color || "")}
                onChange={(event) => patchMap("color", event.target.value)}
              >
                {options("allowed_for_color").map((item) => (
                  <option key={item.metric_key} value={item.metric_key}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Vertical reference line
              <input
                disabled={selected?.status !== "draft"}
                min="0"
                onChange={(event) => patchReference("x", event.target.value)}
                type="number"
                value={String(referenceLines.find((item) => item.axis === "x")?.value ?? "")}
              />
            </label>
            <label>
              Horizontal reference line
              <input
                disabled={selected?.status !== "draft"}
                min="0"
                onChange={(event) => patchReference("y", event.target.value)}
                type="number"
                value={String(referenceLines.find((item) => item.axis === "y")?.value ?? "")}
              />
            </label>
            <label className="wide">
              Scorecard columns
              <input
                disabled={selected?.status !== "draft"}
                onChange={(event) =>
                  patch((next) => {
                    const card = { ...((next.scorecard as Record<string, unknown> | undefined) || {}) };
                    card.columns = event.target.value
                      .split(",")
                      .map((item) => item.trim())
                      .filter(Boolean);
                    next.scorecard = card;
                  })
                }
                value={((scorecard.columns as string[] | undefined) || []).join(", ")}
              />
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
          <details className="analysisJsonEditor">
            <summary>Advanced JSON configuration</summary>
            <textarea
              aria-label="Portfolio Analysis configuration JSON"
              disabled={selected?.status !== "draft"}
              onChange={(event) => setContent(event.target.value)}
              rows={28}
              value={content}
            />
          </details>
          <div aria-label="Portfolio Analysis configuration actions" className="planningActions">
            <button
              disabled={!selected || selected.status !== "published"}
              onClick={() => void execute("clone")}
              type="button"
            >
              <Copy size={15} /> Clone
            </button>
            <button disabled={!selected || !parsed} onClick={() => void previewDraft()} type="button">
              <Eye size={15} /> Preview
            </button>
            <button
              disabled={!selected || selected.status !== "draft" || !parsed}
              onClick={() => void execute("save")}
              type="button"
            >
              <Save size={15} /> Save
            </button>
            <button
              disabled={!selected || selected.status !== "draft" || !parsed}
              onClick={() => void execute("publish")}
              type="button"
            >
              <Send size={15} /> Publish
            </button>
          </div>
          {preview ? (
            <details className="evaluationPreview" open>
              <summary>Effective inheritance and dataset Preview</summary>
              <pre>{JSON.stringify(preview, null, 2)}</pre>
            </details>
          ) : null}
        </article>
      </div>
    </section>
  );
}
