/* eslint-disable react-hooks/exhaustive-deps */
import { Copy, Eye, Save, Send } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { ECONOMIC_FINANCIAL_ADMIN_SECTIONS } from "./adminSections";
import { economicFinancialModelApi } from "./api";
import type { FinancialConfiguration } from "./types";
import "./economicFinancialModel.css";

const parse = (value: string) => {
  try {
    return JSON.parse(value) as Record<string, unknown>;
  } catch {
    return null;
  }
};

export default function EconomicFinancialModelAdminView({ token }: { token: string }) {
  const [records, setRecords] = useState<FinancialConfiguration[]>([]);
  const [selected, setSelected] = useState<FinancialConfiguration | null>(null);
  const [section, setSection] = useState<(typeof ECONOMIC_FINANCIAL_ADMIN_SECTIONS)[number]>("General");
  const [content, setContent] = useState("");
  const [projectId, setProjectId] = useState("");
  const [businessCaseId, setBusinessCaseId] = useState("");
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [message, setMessage] = useState("");
  const parsed = useMemo(() => parse(content), [content]);
  async function load(preferred?: number) {
    const rows = await economicFinancialModelApi.configurations(token);
    setRecords(rows);
    const next =
      rows.find((item) => item.id === preferred) || rows.find((item) => item.status === "draft") || rows[0] || null;
    setSelected(next);
    setContent(next ? JSON.stringify(next.content_json, null, 2) : "");
  }
  useEffect(() => {
    void load().catch((error) => setMessage(error instanceof Error ? error.message : "Unable to load configuration"));
  }, [token]);
  async function act(action: "clone" | "preview" | "save" | "publish") {
    if (!selected || !parsed) return;
    try {
      if (action === "preview") {
        setPreview(
          await economicFinancialModelApi.previewConfiguration(
            token,
            selected.id,
            parsed,
            Number(projectId),
            Number(businessCaseId) || undefined
          )
        );
        setMessage("Preview completed with persisted=false.");
        return;
      }
      let result = selected;
      if (action === "clone") result = await economicFinancialModelApi.cloneConfiguration(token, selected);
      if (action === "save") result = await economicFinancialModelApi.updateConfiguration(token, selected, parsed);
      if (action === "publish") result = await economicFinancialModelApi.publishConfiguration(token, selected);
      await load(result.id);
      setMessage(`Configuration ${action} completed.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Unable to ${action}`);
    }
  }
  return (
    <section aria-label="Economic & Financial Model Configuration" className="financialModel financialModelAdmin">
      <CompactModuleHeader
        description="Configures applicability, horizon, currency/FX, assumptions, capital structure, investors, debt, metrics, scenarios, thresholds, freshness and Four-Eyes review."
        eyebrow="ADMIN MODE · ENTERPRISE STRATEGY MANAGER · GATE 07M-FIN"
        metrics={[
          { label: "Configurations", value: records.length },
          { label: "Sections", value: ECONOMIC_FINANCIAL_ADMIN_SECTIONS.length },
          { label: "Preview persistence", value: "false" },
        ]}
        title="Economic & Financial Model"
        tone="admin"
      />
      {message ? (
        <div className="financialModelMessage" role="status">
          {message}
        </div>
      ) : null}
      <nav aria-label="Economic financial configuration sections" className="financialModelTabs">
        {ECONOMIC_FINANCIAL_ADMIN_SECTIONS.map((item) => (
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
      <div className="financialModelAdminGrid">
        <aside>
          {records.map((item) => (
            <button
              className={selected?.id === item.id ? "active" : ""}
              key={item.id}
              onClick={() => {
                setSelected(item);
                setContent(JSON.stringify(item.content_json, null, 2));
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
        <article className="financialModelSurface">
          <header>
            <div>
              <span>{section}</span>
              <h3>{selected?.name || "No configuration"}</h3>
            </div>
            <b>{selected?.status}</b>
          </header>
          <div className="financialModelPreviewInputs">
            <label>
              Project Workspace ID
              <input inputMode="numeric" onChange={(event) => setProjectId(event.target.value)} value={projectId} />
            </label>
            <label>
              Business Case ID
              <input
                inputMode="numeric"
                onChange={(event) => setBusinessCaseId(event.target.value)}
                value={businessCaseId}
              />
            </label>
          </div>
          <textarea
            aria-label="Economic financial configuration JSON"
            disabled={selected?.status !== "draft"}
            onChange={(event) => setContent(event.target.value)}
            rows={28}
            value={content}
          />
          <div className="financialModelControls compact">
            <button
              disabled={!selected || selected.status !== "published"}
              onClick={() => void act("clone")}
              type="button"
            >
              <Copy size={14} /> Clone
            </button>
            <button disabled={!selected || !parsed || !projectId} onClick={() => void act("preview")} type="button">
              <Eye size={14} /> Preview
            </button>
            <button
              disabled={!selected || selected.status !== "draft" || !parsed}
              onClick={() => void act("save")}
              type="button"
            >
              <Save size={14} /> Save
            </button>
            <button
              disabled={!selected || selected.status !== "draft" || !parsed}
              onClick={() => void act("publish")}
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
