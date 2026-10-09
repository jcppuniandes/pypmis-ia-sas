/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { Copy, Eye, Save, Send } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { POST_FID_ADMIN_SECTIONS } from "./adminSections";
import { postFIDGovernanceApi } from "./api";
import type { PostFIDConfiguration, PostFIDDecision } from "./types";
import "./postFIDGovernance.css";

function parse(value: string) {
  try {
    return JSON.parse(value) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export default function PostFIDGovernanceAdminView({ token }: { token: string }) {
  const [records, setRecords] = useState<PostFIDConfiguration[]>([]);
  const [decisions, setDecisions] = useState<PostFIDDecision[]>([]);
  const [selected, setSelected] = useState<PostFIDConfiguration | null>(null);
  const [decisionId, setDecisionId] = useState(0);
  const [section, setSection] = useState<(typeof POST_FID_ADMIN_SECTIONS)[number]>(POST_FID_ADMIN_SECTIONS[0]);
  const [content, setContent] = useState("");
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [message, setMessage] = useState("");
  const parsed = useMemo(() => parse(content), [content]);

  async function load(preferredId?: number) {
    const [rows, queue] = await Promise.all([
      postFIDGovernanceApi.configurations(token),
      postFIDGovernanceApi.list(token),
    ]);
    setRecords(rows);
    setDecisions(queue);
    const next =
      rows.find((item) => item.id === preferredId) || rows.find((item) => item.status === "draft") || rows[0] || null;
    setSelected(next);
    setContent(next ? JSON.stringify(next.content_json, null, 2) : "");
    setDecisionId((current) => current || queue.find((item) => item.is_fid)?.investment_decision_id || 0);
  }
  useEffect(() => {
    void load().catch((error) =>
      setMessage(error instanceof Error ? error.message : "Unable to load Gate 07L configuration")
    );
  }, [token]);

  async function execute(action: "clone" | "save" | "publish") {
    if (!selected) return;
    try {
      let result = selected;
      if (action === "clone") result = await postFIDGovernanceApi.cloneConfiguration(token, selected);
      if (action === "save") {
        if (!parsed) throw new Error("Configuration JSON is invalid.");
        result = await postFIDGovernanceApi.updateConfiguration(token, selected, parsed);
      }
      if (action === "publish") result = await postFIDGovernanceApi.publishConfiguration(token, selected);
      await load(result.id);
      setMessage(`Gate 07L configuration ${action} completed.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Unable to ${action} configuration`);
    }
  }

  async function dryRun() {
    if (!selected || !parsed) return;
    try {
      setPreview(await postFIDGovernanceApi.previewConfiguration(token, selected.id, parsed, decisionId));
      setMessage("Dry-run completed: persisted=false; no Project, Initialization or Activation mutation was created.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to preview Gate 07L configuration");
    }
  }

  return (
    <section aria-label="Post-FID Project Governance Configuration" className="postFID postFIDAdmin">
      <CompactModuleHeader
        description="Configures FID entry semantics, Project state mapping, post-FID conditions, authorization validity, applicability, handoff delegation and staleness without changing lifecycle services."
        eyebrow="ADMIN MODE · ENTERPRISE STRATEGY MANAGER · INVESTMENT GOVERNANCE · GATE 07L"
        metrics={[
          { label: "Configurations", value: records.length },
          { label: "Sections", value: POST_FID_ADMIN_SECTIONS.length },
          { label: "Execution mutations", value: 0 },
        ]}
        title="Post-FID Project Governance"
        tone="admin"
      />
      {message ? (
        <div className="postFIDMessage" role="status">
          {message}
        </div>
      ) : null}
      <nav aria-label="Post-FID configuration sections" className="postFIDTabs adminTabs">
        {POST_FID_ADMIN_SECTIONS.map((item) => (
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
      <div className="postFIDAdminGrid">
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
        <article className="postFIDSurface">
          <header>
            <div>
              <span>{section}</span>
              <h3>{selected?.name || "No configuration"}</h3>
            </div>
            <b>{selected?.status}</b>
          </header>
          <div className="postFIDFacts">
            <article>
              <span>Entry</span>
              <b>PYP-FFA · GO · FID</b>
            </article>
            <article>
              <span>Default model</span>
              <b>CAPITAL_OWNER</b>
            </article>
            <article>
              <span>Initialization</span>
              <b>Delegated</b>
            </article>
            <article>
              <span>Activation</span>
              <b>Delegated</b>
            </article>
          </div>
          <label className="postFIDDecisionPicker">
            Preview with Investment Decision
            <select value={decisionId} onChange={(event) => setDecisionId(Number(event.target.value))}>
              <option value={0}>Configuration only</option>
              {decisions.map((item) => (
                <option key={item.investment_decision_id} value={item.investment_decision_id}>
                  {item.decision_number} · {item.gate_profile}
                </option>
              ))}
            </select>
          </label>
          <details open>
            <summary>Controlled configuration JSON</summary>
            <textarea
              aria-label="Post-FID Governance configuration JSON"
              disabled={selected?.status !== "draft"}
              onChange={(event) => setContent(event.target.value)}
              rows={30}
              value={content}
            />
          </details>
          <div className="postFIDControls compact">
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
      <p className="postFIDGuardrail">
        ADMIN Preview is a dry-run. Publishing policy never creates a FID, Project, initialization, activation, NTP,
        commitment, contract, payment or execution record.
      </p>
    </section>
  );
}
