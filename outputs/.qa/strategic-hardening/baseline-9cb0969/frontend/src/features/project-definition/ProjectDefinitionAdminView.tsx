/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { Copy, Eye, Save, Send } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { projectDefinitionApi } from "./api";
import type { DefinitionConfiguration } from "./types";
import "./projectDefinition.css";

const sections = [
  "General",
  "Frameworks",
  "FEL Stages",
  "Project Type Mapping",
  "Assessment Categories",
  "Assessment Elements",
  "Scoring / Maturity",
  "Thresholds",
  "Blocking Elements",
  "Evidence Requirements",
  "Actions",
  "Stage Review",
  "Inheritance",
  "Permissions",
  "Preview",
];

function parse(value: string) {
  try {
    return JSON.parse(value) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export default function ProjectDefinitionAdminView({ token }: { token: string }) {
  const [records, setRecords] = useState<DefinitionConfiguration[]>([]);
  const [selected, setSelected] = useState<DefinitionConfiguration | null>(null);
  const [content, setContent] = useState("");
  const [section, setSection] = useState("General");
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [message, setMessage] = useState("");
  const selectedId = useRef<number | null>(null);
  const parsed = useMemo(() => parse(content), [content]);

  async function load(preferredId?: number) {
    const items = await projectDefinitionApi.configurations(token);
    setRecords(items);
    const item =
      items.find((value) => value.id === (preferredId || selectedId.current)) ||
      items.find((value) => value.status === "draft") ||
      items[0] ||
      null;
    selectedId.current = item?.id || null;
    setSelected(item);
    setContent(item ? JSON.stringify(item.content_json, null, 2) : "");
  }
  useEffect(() => {
    void load().catch((error) =>
      setMessage(error instanceof Error ? error.message : "Unable to load Project Definition configuration")
    );
  }, [token]);

  async function execute(action: "clone" | "save" | "publish" | "preview") {
    if (!selected || !parsed) return;
    try {
      if (action === "preview") {
        setPreview(await projectDefinitionApi.previewConfiguration(token, selected, parsed));
        setMessage("Preview completed with persisted=false.");
        return;
      }
      let result = selected;
      if (action === "clone") result = await projectDefinitionApi.cloneConfiguration(token, selected);
      if (action === "save") result = await projectDefinitionApi.updateConfiguration(token, selected, parsed);
      if (action === "publish") result = await projectDefinitionApi.publishConfiguration(token, selected);
      await load(result.id);
      setMessage(`Project Definition configuration ${action} completed.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Unable to ${action} configuration`);
    }
  }

  return (
    <section aria-label="Project Definition / FEL Configuration" className="projectDefinition definitionAdmin">
      <CompactModuleHeader
        eyebrow="ADMIN MODE · ENTERPRISE STRATEGY MANAGER"
        title="Project Definition / FEL Manager Configuration"
        description="Configures non-proprietary frameworks, FEL stages, mappings, elements, scoring direction, framework-specific thresholds, evidence, review, permissions and inheritance."
        tone="admin"
        metrics={[
          { label: "Frameworks", value: records.length },
          { label: "Type", value: String(parsed?.framework_type || "—") },
          { label: "Status", value: selected?.status || "—" },
        ]}
      />
      {message ? (
        <div className="definitionMessage" role="status">
          {message}
        </div>
      ) : null}
      <nav className="definitionConfigTabs" aria-label="Project Definition configuration areas">
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
      <div className="definitionAdminGrid">
        <aside>
          {records.map((item) => (
            <button
              className={selected?.id === item.id ? "active" : ""}
              key={item.id}
              onClick={() => {
                selectedId.current = item.id;
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
        <section className="definitionSurface">
          <header>
            <div>
              <span>{section}</span>
              <h3>{selected?.name || "No framework"}</h3>
            </div>
            <strong>{selected?.status}</strong>
          </header>
          <div className="definitionFacts">
            <article>
              <span>Framework type</span>
              <b>{String(parsed?.framework_type || "—")}</b>
            </article>
            <article>
              <span>Scoring</span>
              <b>{String(parsed?.scoring_method || "—")}</b>
            </article>
            <article>
              <span>Direction</span>
              <b>{String(parsed?.score_direction || "—")}</b>
            </article>
            <article>
              <span>Governance</span>
              <b>
                {Array.isArray(parsed?.applicable_governance_models)
                  ? parsed.applicable_governance_models.join(", ")
                  : "—"}
              </b>
            </article>
          </div>
          <details open>
            <summary>Controlled configuration JSON</summary>
            <textarea
              aria-label="Project Definition Framework JSON"
              disabled={selected?.status !== "draft"}
              onChange={(event) => setContent(event.target.value)}
              rows={30}
              value={content}
            />
          </details>
          <div className="definitionActions">
            <button
              disabled={!selected || selected.status !== "published"}
              onClick={() => void execute("clone")}
              type="button"
            >
              <Copy size={14} /> Clone DRAFT
            </button>
            <button disabled={!parsed} onClick={() => void execute("preview")} type="button">
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
        </section>
      </div>
      <p className="definitionGuardrail">
        PDRI-compatible and FEL-index-compatible behavior uses tenant-supplied authorized metadata only. No proprietary
        CII/IPA content, executable formulas, Funds, FID, investment decision or Project activation is included.
      </p>
    </section>
  );
}
