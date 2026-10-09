/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { AlertTriangle, Copy, Eye, Save, Send } from "lucide-react";
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

const SECTION_GUIDANCE: Partial<Record<(typeof BUSINESS_CASE_ADMIN_SECTIONS)[number], string>> = {
  "Case Applicability":
    "Enable policy-driven Five Case depth by Governance Model, Project Type, FEL Stage and Gate Profile.",
  "Strategic Case Requirements":
    "Configure required strategic sources, minimum readiness, freshness, coverage and blocking behavior.",
  "Economic Case Requirements":
    "Configure option, value-for-money, Benefits, FIN and Risk evidence without creating an options engine.",
  "Commercial Case Requirements":
    "Configure Commercial Strategy evidence requirements without executing procurement or contracting.",
  "Financial Case Requirements": "Configure Budget, Funding and FIN references; financial metrics remain owned by FIN.",
  "Management Case Requirements":
    "Configure FEL, Resources, Risk, Permit, Benefits and Commercial evidence for deliverability.",
  "Source Requirements": "Set required yes/no, applicability and blocking/warning behavior per Case and source.",
  "Source Readiness Requirements": "Set minimum source status/readiness, current flag, freshness and validity rules.",
  "Required Evidence": "Declare evidence contracts by Case; this screen never edits live source records.",
  "Case Readiness Rules": "Define backend-owned readiness rules for each of the five Cases.",
  "Overall Readiness Rules": "Compose policy-driven overall readiness; all Cases READY is not hardcoded universally.",
  "FEL / Gate Requirements": "Apply progressive maturity and gate-level revalidation rules.",
  "Project Type Overrides": "Tailor depth for Project type without changing the source authorities.",
  "Governance Model Overrides":
    "CAPITAL_OWNER is policy-driven; CONTRACTOR_DELIVERY and DIRECT_INTERNAL remain unaffected by default.",
  Tailoring: "Tailor by size, risk, complexity, Project Type, Governance Model, FEL Stage and Gate Profile.",
  Inheritance: "Resolve the nearest published policy through Tenant, Enterprise, Business Unit and Portfolio scopes.",
  "Review / SoD": "Configure preparer/reviewer separation and controlled publication rules.",
  Preview: "Dry-run the effective policy and resolution chain with persisted=false.",
  History: "Review configuration lineage; published revisions remain controlled records.",
};

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
        description="Configures Five Case applicability, source/evidence requirements, readiness, progressive FEL/Gate maturity, tailoring, inheritance and review separation."
        eyebrow="ADMIN MODE · ENTERPRISE STRATEGY MANAGER · GATE 07M-BC-5C"
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
              <span>Applicability</span>
              <b>Type · Governance · Gate · FEL</b>
            </article>
            <article>
              <span>Readiness</span>
              <b>Stage-specific</b>
            </article>
            <article>
              <span>Live source mutation</span>
              <b>DISABLED</b>
            </article>
          </div>
          <p className="businessCaseAdminGuidance">
            {SECTION_GUIDANCE[section] ||
              "Legacy Business Case policy remains available for compatibility while Five Case rules are layered additively."}
          </p>
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
      <p className="businessCaseGuardrail">
        <AlertTriangle size={15} /> ADMIN configures policy only. It cannot edit live Business Cases, source records,
        investment decisions or Project lifecycle transactions.
      </p>
    </section>
  );
}
