/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { Copy, Eye, Save, Send } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { BUSINESS_CASE_ADMIN_SECTIONS } from "./adminSections";
import { businessCaseApi } from "./api";
import type { BusinessCaseConfiguration } from "./types";
import "./businessCase.css";

function parse(value: string) {
  try {
    return JSON.parse(value) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export default function BusinessCaseAdminView({ token }: { token: string }) {
  const [records, setRecords] = useState<BusinessCaseConfiguration[]>([]);
  const [selected, setSelected] = useState<BusinessCaseConfiguration | null>(null);
  const [section, setSection] = useState<(typeof BUSINESS_CASE_ADMIN_SECTIONS)[number]>(
    BUSINESS_CASE_ADMIN_SECTIONS[0]
  );
  const [content, setContent] = useState("");
  const [projectId, setProjectId] = useState("");
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [message, setMessage] = useState("");
  const parsed = useMemo(() => parse(content), [content]);

  async function load(preferredId?: number) {
    const rows = await businessCaseApi.configurations(token);
    setRecords(rows);
    const next =
      rows.find((item) => item.id === preferredId) || rows.find((item) => item.status === "draft") || rows[0] || null;
    setSelected(next);
    setContent(next ? JSON.stringify(next.content_json, null, 2) : "");
  }
  useEffect(() => {
    void load().catch((error) => setMessage(error instanceof Error ? error.message : "Unable to load configuration"));
  }, [token]);

  async function execute(action: "clone" | "save" | "publish" | "preview") {
    if (!selected || !parsed) return;
    try {
      if (action === "preview") {
        setPreview(
          await businessCaseApi.previewConfiguration(token, selected.id, parsed, Number(projectId) || undefined)
        );
        setMessage("Preview completed: persisted=false and no Business Case was created.");
        return;
      }
      let result = selected;
      if (action === "clone") result = await businessCaseApi.cloneConfiguration(token, selected);
      if (action === "save") result = await businessCaseApi.updateConfiguration(token, selected, parsed);
      if (action === "publish") result = await businessCaseApi.publishConfiguration(token, selected);
      await load(result.id);
      setMessage(`Configuration ${action} completed.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Unable to ${action}`);
    }
  }

  return (
    <section aria-label="Business Case Manager Configuration" className="businessCase businessCaseAdmin">
      <CompactModuleHeader
        description="Configures Project Proposal mapping, stage-specific evidence, source freshness, review separation, material-change rules and nearest-published inheritance."
        eyebrow="ADMIN MODE · ENTERPRISE STRATEGY MANAGER · GATE 07M-BC"
        metrics={[
          { label: "Configurations", value: records.length },
          { label: "Sections", value: BUSINESS_CASE_ADMIN_SECTIONS.length },
          { label: "Preview persistence", value: "false" },
        ]}
        title="Business Case Manager"
        tone="admin"
      />
      {message ? (
        <div className="businessCaseMessage" role="status">
          {message}
        </div>
      ) : null}
      <nav aria-label="Business Case configuration sections" className="businessCaseTabs adminTabs">
        {BUSINESS_CASE_ADMIN_SECTIONS.map((item) => (
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
      <div className="businessCaseAdminGrid">
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
        <article className="businessCaseSurface">
          <header>
            <div>
              <span>{section}</span>
              <h3>{selected?.name || "No configuration"}</h3>
            </div>
            <b>{selected?.status}</b>
          </header>
          <div className="businessCaseFacts">
            <article>
              <span>Inheritance</span>
              <b>Tenant → Enterprise → BU → Portfolio</b>
            </article>
            <article>
              <span>Context</span>
              <b>Type · Governance · Gate · FEL</b>
            </article>
            <article>
              <span>Readiness</span>
              <b>Stage-specific</b>
            </article>
            <article>
              <span>Financial engine</span>
              <b>NOT_AVAILABLE</b>
            </article>
          </div>
          <label className="businessCaseProjectPicker">
            Preview Project Workspace ID
            <input inputMode="numeric" value={projectId} onChange={(event) => setProjectId(event.target.value)} />
          </label>
          <details open>
            <summary>Controlled configuration JSON</summary>
            <textarea
              aria-label="Business Case configuration JSON"
              disabled={selected?.status !== "draft"}
              onChange={(event) => setContent(event.target.value)}
              rows={30}
              value={content}
            />
          </details>
          <div className="businessCaseControls compact">
            <button
              disabled={!selected || selected.status !== "published"}
              onClick={() => void execute("clone")}
              type="button"
            >
              <Copy size={14} /> Clone
            </button>
            <button disabled={!selected || !parsed} onClick={() => void execute("preview")} type="button">
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
          {preview ? <pre>{JSON.stringify(preview, null, 2)}</pre> : null}
        </article>
      </div>
    </section>
  );
}
