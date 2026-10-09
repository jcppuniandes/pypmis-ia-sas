/* eslint-disable react-hooks/exhaustive-deps */
import { Copy, Eye, Save, Send } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import "../portfolio-planning/portfolioPlanning.css";
import { portfolioEvaluationApi } from "./api";
import type { EvaluationConfiguration } from "./types";
import "./portfolioEvaluation.css";

const sections = [
  "General",
  "Evaluation Matrix",
  "Scoring Scale",
  "Weights",
  "Required Evidence",
  "Applicability",
  "Ranking Rules",
  "Coverage/Readiness",
  "Inheritance",
  "Permissions",
  "Preview",
];

export default function PortfolioEvaluationAdminView({ token }: { token: string }) {
  const [records, setRecords] = useState<EvaluationConfiguration[]>([]);
  const [selected, setSelected] = useState<EvaluationConfiguration | null>(null);
  const [content, setContent] = useState("");
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [message, setMessage] = useState("");
  const loadSequence = useRef(0);

  async function load(preferredId?: number) {
    const sequence = ++loadSequence.current;
    const items = await portfolioEvaluationApi.configurations(token);
    if (sequence !== loadSequence.current) return;
    setRecords(items);
    const next =
      items.find((item) => item.id === preferredId) ||
      items.find((item) => item.status === "draft") ||
      items[0] ||
      null;
    setSelected(next);
    setContent(next ? JSON.stringify(next.content_json, null, 2) : "");
    setPreview(
      next
        ? await portfolioEvaluationApi.previewConfiguration(
            token,
            Number((next.content_json.scope as Record<string, unknown> | undefined)?.workspace_id || 0),
            next.id
          )
        : await portfolioEvaluationApi.previewConfiguration(token)
    );
  }
  useEffect(() => {
    void load().catch((error) =>
      setMessage(error instanceof Error ? error.message : "Unable to load Gate 07E configuration")
    );
  }, [token]);

  async function execute(action: "clone" | "save" | "publish") {
    if (!selected) return;
    try {
      let result = selected;
      if (action === "clone") result = await portfolioEvaluationApi.cloneConfiguration(token, selected);
      if (action === "save")
        result = await portfolioEvaluationApi.updateConfiguration(
          token,
          selected,
          JSON.parse(content) as Record<string, unknown>
        );
      if (action === "publish") result = await portfolioEvaluationApi.publishConfiguration(token, selected);
      setMessage(`Gate 07E configuration ${action} completed.`);
      await load(result.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Unable to ${action} configuration`);
    }
  }

  async function previewDraft() {
    if (!selected) return;
    try {
      const parsed = JSON.parse(content) as Record<string, unknown>;
      const scope = parsed.scope as Record<string, unknown> | undefined;
      setPreview(
        await portfolioEvaluationApi.previewConfiguration(token, Number(scope?.workspace_id || 0), selected.id, parsed)
      );
      setMessage("Gate 07E configuration preview completed without persisting evaluation data.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to preview configuration");
    }
  }

  return (
    <section className="portfolioEvaluation" aria-label="Portfolio Evaluation and Prioritization Configuration">
      <CompactModuleHeader
        description="Governed matrix, scale, evidence, applicability, inheritance and deterministic contextual ranking rules. Draft defaults require explicit publication."
        eyebrow="ADMIN MODE · ENTERPRISE STRATEGY MANAGER · PORTFOLIO MANAGER"
        metrics={[
          { label: "Revisions", value: records.length },
          { label: "Default state", value: "DRAFT" },
          { label: "Manual rank", value: "Disabled" },
        ]}
        title="Portfolio Evaluation & Prioritization"
        tone="admin"
      />
      <nav className="planningAdminSections" aria-label="Portfolio Evaluation configuration sections">
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
      <div className="planningAdminGrid">
        <aside>
          {records.map((item) => (
            <button
              className={selected?.id === item.id ? "active" : ""}
              data-testid={`portfolio-evaluation-configuration-${item.id}`}
              key={item.id}
              onClick={() => {
                setSelected(item);
                setContent(JSON.stringify(item.content_json, null, 2));
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
        <article className="planningCard">
          <header>
            <div>
              <span>Controlled configuration</span>
              <h3>{selected?.name || "No configuration"}</h3>
            </div>
            <strong className={selected?.status === "published" ? "ready" : "blocked"}>{selected?.status || ""}</strong>
          </header>
          <textarea
            aria-label="Portfolio Evaluation configuration JSON"
            disabled={selected?.status !== "draft"}
            onChange={(event) => setContent(event.target.value)}
            rows={28}
            value={content}
          />
          <div aria-label="Portfolio Evaluation configuration actions" className="planningActions">
            <button
              disabled={!selected || selected.status !== "published"}
              onClick={() => void execute("clone")}
              type="button"
            >
              <Copy size={15} /> Clone
            </button>
            <button disabled={!selected} onClick={() => void previewDraft()} type="button">
              <Eye size={15} /> Preview
            </button>
            <button
              disabled={!selected || selected.status !== "draft"}
              onClick={() => void execute("save")}
              type="button"
            >
              <Save size={15} /> Save
            </button>
            <button
              disabled={!selected || selected.status !== "draft"}
              onClick={() => void execute("publish")}
              type="button"
            >
              <Send size={15} /> Publish
            </button>
          </div>
          {preview ? (
            <details className="evaluationPreview">
              <summary>Effective inheritance preview</summary>
              <pre>{JSON.stringify(preview, null, 2)}</pre>
            </details>
          ) : null}
        </article>
      </div>
    </section>
  );
}
