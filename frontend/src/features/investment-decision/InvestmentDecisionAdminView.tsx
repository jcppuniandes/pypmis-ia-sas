/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { Copy, Eye, Save, Send } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { INVESTMENT_DECISION_ADMIN_SECTIONS } from "./adminSections";
import { investmentDecisionApi } from "./api";
import type { InvestmentDecisionConfiguration } from "./types";
import "./investmentDecision.css";

function parse(value: string) {
  try {
    return JSON.parse(value) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export default function InvestmentDecisionAdminView({ token }: { token: string }) {
  const [records, setRecords] = useState<InvestmentDecisionConfiguration[]>([]);
  const [selected, setSelected] = useState<InvestmentDecisionConfiguration | null>(null);
  const [content, setContent] = useState("");
  const [section, setSection] = useState(INVESTMENT_DECISION_ADMIN_SECTIONS[0]);
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [message, setMessage] = useState("");
  const parsed = useMemo(() => parse(content), [content]);

  async function load(preferredId?: number) {
    const rows = await investmentDecisionApi.configurations(token);
    setRecords(rows);
    const next =
      rows.find((item) => item.id === preferredId) || rows.find((item) => item.status === "draft") || rows[0] || null;
    setSelected(next);
    setContent(next ? JSON.stringify(next.content_json, null, 2) : "");
  }
  useEffect(() => {
    void load().catch((error) =>
      setMessage(error instanceof Error ? error.message : "Unable to load Gate 07K configuration")
    );
  }, [token]);

  async function execute(action: "clone" | "save" | "publish") {
    if (!selected) return;
    try {
      let result = selected;
      if (action === "clone") result = await investmentDecisionApi.cloneConfiguration(token, selected);
      if (action === "save") {
        if (!parsed) throw new Error("Configuration JSON is invalid.");
        result = await investmentDecisionApi.updateConfiguration(token, selected, parsed);
      }
      if (action === "publish") result = await investmentDecisionApi.publishConfiguration(token, selected);
      await load(result.id);
      setMessage(`Gate 07K configuration ${action} completed.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Unable to ${action} configuration`);
    }
  }

  async function dryRun() {
    if (!selected || !parsed) return;
    try {
      setPreview(await investmentDecisionApi.previewConfiguration(token, selected.id, parsed));
      setMessage("Dry-run completed: persisted=false; no Decision, FID, Project or execution record was created.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to preview configuration");
    }
  }

  return (
    <section aria-label="Investment Decision / FID Governance" className="investmentDecision decisionAdmin">
      <CompactModuleHeader
        description="Configures exact outcome semantics, authority, limits, committee, quorum, voting, SoD, checklist, FID rules and immutable authorization output."
        eyebrow="ADMIN MODE · INVESTMENT GOVERNANCE · GATE 07K"
        metrics={[
          { label: "Configurations", value: records.length },
          { label: "Sections", value: 20 },
          { label: "Outcomes", value: "4 exact" },
        ]}
        title="Investment Decision / FID Governance"
        tone="admin"
      />
      {message ? (
        <div className="decisionMessage" role="status">
          {message}
        </div>
      ) : null}
      <nav aria-label="Investment Decision configuration sections" className="decisionAdminTabs">
        {INVESTMENT_DECISION_ADMIN_SECTIONS.map((item) => (
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
      <div className="decisionAdminGrid">
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
              <b>{item.name}</b>
              <span>
                {item.status} · rev {item.revision}
              </span>
            </button>
          ))}
        </aside>
        <article className="decisionSurface">
          <header>
            <div>
              <span>{section}</span>
              <h3>{selected?.name || "No configuration"}</h3>
            </div>
            <b>{selected?.status}</b>
          </header>
          <div className="decisionFacts">
            <article>
              <span>INV-SELECT GO</span>
              <b>Not FID</b>
            </article>
            <article>
              <span>PYP-FFA GO</span>
              <b>FID + Full Funds</b>
            </article>
            <article>
              <span>Outcomes</span>
              <b>GO / HOLD / RECYCLE / KILL</b>
            </article>
            <article>
              <span>Activation</span>
              <b>Always false</b>
            </article>
          </div>
          <details open>
            <summary>Controlled configuration JSON</summary>
            <textarea
              aria-label="Investment Decision configuration JSON"
              disabled={selected?.status !== "draft"}
              onChange={(event) => setContent(event.target.value)}
              rows={30}
              value={content}
            />
          </details>
          <div className="decisionActions">
            <button
              disabled={!selected || selected.status !== "published"}
              onClick={() => void execute("clone")}
              type="button"
            >
              <Copy size={14} /> Clone
            </button>
            <button disabled={!selected || !parsed} onClick={() => void dryRun()} type="button">
              <Eye size={14} /> Dry-run
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
          {preview ? <pre>{JSON.stringify(preview, null, 2)}</pre> : null}
        </article>
      </div>
      <p className="decisionGuardrail">
        Publishing configuration never creates a Decision, FID, Project, contract, payment, NTP or execution
        authorization.
      </p>
    </section>
  );
}
