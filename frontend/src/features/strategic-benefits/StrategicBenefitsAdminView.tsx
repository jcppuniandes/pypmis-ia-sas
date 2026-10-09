/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { Archive, CopyPlus, Eye, Save, Send, Settings2, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { strategicBenefitsApi } from "./api";
import type { BenefitsConfiguration } from "./types";
import "./strategicBenefits.css";

const sections = [
  "General",
  "Applicability",
  "Benefit Types",
  "Benefit Categories",
  "KPI / Measure Types",
  "Units of Measure",
  "Measurement Frequencies",
  "Benefit Owner Requirements",
  "Baseline Requirements",
  "Target Requirements",
  "Expected Value Rules",
  "Required Sections",
  "Required Fields",
  "Readiness Rules",
  "Coverage Rules",
  "FEL / Gate Requirements",
  "Project Type Overrides",
  "Governance Model Overrides",
  "Inheritance",
  "Numbering",
  "Review / SoD",
  "Preview",
  "History",
] as const;

type Section = (typeof sections)[number];
type JsonRecord = Record<string, unknown>;

const catalogKeyBySection: Partial<Record<Section, string>> = {
  "Benefit Types": "benefit_types",
  "Benefit Categories": "benefit_categories",
  "KPI / Measure Types": "measure_types",
  "Units of Measure": "units_of_measure",
  "Measurement Frequencies": "measurement_frequencies",
  "Required Sections": "required_sections",
};

const jsonKeyBySection: Partial<Record<Section, string>> = {
  "Benefit Owner Requirements": "benefit_owner_requirements",
  "Baseline Requirements": "baseline_requirements",
  "Target Requirements": "target_requirements",
  "Expected Value Rules": "expected_value_rules",
  "Required Fields": "required_fields",
  "Readiness Rules": "readiness_rules",
  "Coverage Rules": "coverage_rules",
  "FEL / Gate Requirements": "fel_gate_requirements",
  "Project Type Overrides": "project_type_overrides",
};

function status(item: BenefitsConfiguration | null) {
  return String(item?.status || "ARCHIVED").toUpperCase();
}

function record(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as JsonRecord) : {};
}

function clone(value: JsonRecord) {
  return JSON.parse(JSON.stringify(value)) as JsonRecord;
}

function valueToLines(value: unknown) {
  if (!Array.isArray(value)) return "";
  return value
    .map((item) => (typeof item === "string" ? item : String(record(item).code || record(item).label || "")))
    .filter(Boolean)
    .join("\n");
}

function linesToCatalog(value: string) {
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function JsonEditor({
  label,
  value,
  disabled,
  shape = "object",
  onChange,
  onError,
}: {
  label: string;
  value: unknown;
  disabled: boolean;
  shape?: "array" | "object";
  onChange: (value: unknown) => void;
  onError: (value: string) => void;
}) {
  const [source, setSource] = useState(() => JSON.stringify(value ?? (shape === "array" ? [] : {}), null, 2));
  const [error, setError] = useState("");
  useEffect(() => {
    setSource(JSON.stringify(value ?? (shape === "array" ? [] : {}), null, 2));
    setError("");
  }, [value, shape]);
  function update(next: string) {
    setSource(next);
    try {
      const parsed = JSON.parse(next) as unknown;
      if (shape === "array" ? !Array.isArray(parsed) : !parsed || typeof parsed !== "object" || Array.isArray(parsed))
        throw new Error(`Expected a JSON ${shape}`);
      setError("");
      onError("");
      onChange(parsed);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Invalid JSON";
      setError(message);
      onError(message);
    }
  }
  const errorId = `${label.replace(/\W+/g, "-").toLowerCase()}-error`;
  return (
    <label className="benefitsField">
      <span>{label}</span>
      <small>Governed JSON. Invalid content blocks save and publish.</small>
      <textarea
        aria-describedby={error ? errorId : undefined}
        aria-invalid={Boolean(error)}
        aria-label={label}
        disabled={disabled}
        rows={14}
        spellCheck={false}
        value={source}
        onChange={(event) => update(event.target.value)}
      />
      {error ? (
        <small className="benefitsFieldError" id={errorId} role="alert">
          {error}
        </small>
      ) : null}
    </label>
  );
}

export default function StrategicBenefitsAdminView({ token }: { token: string }) {
  const [items, setItems] = useState<BenefitsConfiguration[]>([]);
  const [selectedId, setSelectedId] = useState(0);
  const [draft, setDraft] = useState<JsonRecord>({});
  const [activeSection, setActiveSection] = useState<Section>("General");
  const [projectId, setProjectId] = useState(0);
  const [preview, setPreview] = useState<JsonRecord | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [jsonErrors, setJsonErrors] = useState<Record<string, string>>({});
  const selected = items.find((item) => item.id === selectedId) || items[0] || null;
  const hasJsonErrors = Object.values(jsonErrors).some(Boolean);

  async function load(preferredId?: number) {
    const rows = await strategicBenefitsApi.configurations(token);
    setItems(rows);
    setSelectedId(preferredId || rows[0]?.id || 0);
  }
  useEffect(() => {
    void load().catch((error) =>
      setMessage(error instanceof Error ? error.message : "Unable to load Benefits configuration")
    );
  }, [token]);
  useEffect(() => {
    setDraft(clone(record(selected?.content_json)));
    setPreview(null);
    setJsonErrors({});
  }, [selected?.id, selected?.version]);

  const metrics = useMemo(
    () => [
      { label: "Revisions", value: items.length },
      { label: "Published", value: items.filter((item) => status(item) === "PUBLISHED").length },
      { label: "Drafts", value: items.filter((item) => status(item) === "DRAFT").length },
      { label: "Mode", value: "CONFIGURE" },
    ],
    [items]
  );

  async function execute(work: () => Promise<BenefitsConfiguration>, success: string) {
    if (!selected) return;
    setBusy(true);
    setMessage("");
    try {
      const result = await work();
      await load(result.id);
      setMessage(success);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Benefits configuration action failed");
    } finally {
      setBusy(false);
    }
  }
  async function showPreview() {
    if (!selected) return;
    setBusy(true);
    setMessage("");
    try {
      setPreview(await strategicBenefitsApi.effectivePreview(token, projectId, selected.id, draft));
      setMessage("Effective Benefits policy preview resolved with persisted=false.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Effective preview failed");
    } finally {
      setBusy(false);
    }
  }
  function change(key: string, value: unknown) {
    setDraft((current) => ({ ...current, [key]: value }));
  }
  function reportJsonError(key: string, error: string) {
    setJsonErrors((current) => ({ ...current, [key]: error }));
  }
  const editable = status(selected) === "DRAFT" && !busy;

  return (
    <section aria-label="Benefits Configuration" className="strategicBenefits benefitsAdmin">
      <CompactModuleHeader
        description="Configure and publish reusable Benefit catalogs, applicability, ownership, measurement, coverage, readiness, numbering and review policy. This surface cannot operate live Project Benefits Plans."
        eyebrow="ADMIN MODE · PROJECT DEFINITION & INVESTMENT CASE CONFIGURATION · GATE 07M-BEN"
        metrics={metrics}
        title="Benefits Configuration"
      />
      {message ? (
        <div className="benefitsMessage" role="status">
          {message}
        </div>
      ) : null}
      <div className="benefitsAdminLayout">
        <aside aria-label="Benefits configuration revisions">
          {items.map((item) => (
            <button
              className={selected?.id === item.id ? "active" : ""}
              key={item.id}
              onClick={() => setSelectedId(item.id)}
              type="button"
            >
              <Settings2 size={17} />
              <span>{item.name}</span>
              <small>
                Revision {item.revision} · {status(item)}
              </small>
            </button>
          ))}
          {!items.length ? <p>No authorized configuration revisions.</p> : null}
        </aside>
        <section className="benefitsSurface">
          <header>
            <div>
              <span>Controlled configuration revision</span>
              <h3>{selected?.name || "Strategic Benefits policy"}</h3>
            </div>
            {selected ? (
              <span className={`benefitsStatus ${status(selected).toLowerCase()}`}>{status(selected)}</span>
            ) : null}
          </header>
          <div className="benefitsAdminActions">
            <button
              disabled={busy || !selected || status(selected) !== "PUBLISHED"}
              onClick={() =>
                selected &&
                void execute(
                  () => strategicBenefitsApi.cloneConfiguration(token, selected),
                  "Published policy cloned to a controlled DRAFT."
                )
              }
              type="button"
            >
              <CopyPlus size={15} /> Clone
            </button>
            <button
              disabled={busy || hasJsonErrors || !selected || status(selected) !== "DRAFT"}
              onClick={() =>
                selected &&
                void execute(
                  () => strategicBenefitsApi.updateConfiguration(token, selected, draft),
                  "Benefits policy DRAFT saved under ETag control."
                )
              }
              type="button"
            >
              <Save size={15} /> Save draft
            </button>
            <button
              disabled={busy || hasJsonErrors || !selected || status(selected) !== "DRAFT"}
              onClick={() =>
                selected &&
                void execute(
                  () => strategicBenefitsApi.publishConfiguration(token, selected),
                  "Benefits policy published; historical Plan versions remain unchanged."
                )
              }
              type="button"
            >
              <Send size={15} /> Publish
            </button>
            <button
              disabled={busy || !selected || status(selected) !== "PUBLISHED"}
              onClick={() =>
                selected &&
                void execute(
                  () => strategicBenefitsApi.archiveConfiguration(token, selected),
                  "Benefits policy archived without mutating completed Plans."
                )
              }
              type="button"
            >
              <Archive size={15} /> Archive
            </button>
          </div>
          <nav aria-label="Benefits configuration sections" className="benefitsConfigTabs">
            {sections.map((section) => (
              <button
                aria-current={activeSection === section ? "page" : undefined}
                className={activeSection === section ? "active" : ""}
                key={section}
                onClick={() => setActiveSection(section)}
                type="button"
              >
                {section}
              </button>
            ))}
          </nav>
          <div className="benefitsConfigEditor">
            {renderSection(activeSection, draft, selected, editable, change, reportJsonError)}
          </div>
          <details className="benefitsAdvanced">
            <summary>Advanced effective configuration snapshot · read only</summary>
            <pre aria-label="Advanced Benefits configuration read only">{JSON.stringify(draft, null, 2)}</pre>
          </details>
        </section>
      </div>
      <section aria-label="Benefits effective preview" className="benefitsSurface benefitsAdminPreview">
        <div>
          <Eye size={19} />
          <div>
            <strong>Effective policy preview</strong>
            <p>
              Resolve Tenant → Enterprise → Business Unit → Portfolio inheritance without persisting a live Project
              Plan.
            </p>
          </div>
        </div>
        <label>
          Project Workspace ID (optional)
          <input
            inputMode="numeric"
            value={projectId || ""}
            onChange={(event) => setProjectId(Number(event.target.value))}
          />
        </label>
        <button disabled={busy || hasJsonErrors || !selected} onClick={() => void showPreview()} type="button">
          <Eye size={15} /> Preview persisted=false
        </button>
        {preview ? (
          <output>
            <strong>persisted={String(preview.persisted ?? false)}</strong>
            <span>{String(preview.configuration_hash || preview.content_hash || "Effective policy resolved")}</span>
          </output>
        ) : null}
      </section>
      <p className="benefitsBoundary">
        <strong>ADMIN boundary:</strong> configuration administrators cannot create, edit, assign owners, submit,
        review, complete or revise a live Project Benefits Plan from this surface. Published policy revisions are
        immutable and do not reinterpret historical evidence.
      </p>
    </section>
  );
}

function renderSection(
  section: Section,
  draft: JsonRecord,
  selected: BenefitsConfiguration | null,
  editable: boolean,
  change: (key: string, value: unknown) => void,
  reportJsonError: (key: string, error: string) => void
) {
  const catalogKey = catalogKeyBySection[section];
  if (catalogKey)
    return (
      <label className="benefitsField">
        <span>{section}</span>
        <small>One governed catalog code per line.</small>
        <textarea
          aria-label={section}
          disabled={!editable}
          rows={12}
          value={valueToLines(draft[catalogKey])}
          onChange={(event) => change(catalogKey, linesToCatalog(event.target.value))}
        />
      </label>
    );
  const jsonKey = jsonKeyBySection[section];
  if (jsonKey)
    return (
      <JsonEditor
        disabled={!editable}
        label={section}
        onChange={(value) => change(jsonKey, value)}
        onError={(error) => reportJsonError(jsonKey, error)}
        shape={section === "Project Type Overrides" ? "array" : "object"}
        value={draft[jsonKey]}
      />
    );
  if (section === "General")
    return (
      <div className="benefitsEditorGrid">
        <label className="benefitsField">
          <span>Policy code</span>
          <input
            aria-label="Policy code"
            disabled={!editable}
            value={String(draft.configuration_code || "")}
            onChange={(event) => change("configuration_code", event.target.value.toUpperCase())}
          />
        </label>
        <label className="benefitsField">
          <span>Policy description</span>
          <textarea
            aria-label="Policy description"
            disabled={!editable}
            rows={5}
            value={String(draft.policy_description || "")}
            onChange={(event) => change("policy_description", event.target.value)}
          />
        </label>
      </div>
    );
  if (section === "Applicability" || section === "Governance Model Overrides") {
    const enabled = record(draft.enabled_by_governance_model);
    return (
      <fieldset className="benefitsChecks">
        <legend>Governance Model applicability</legend>
        <p>
          CAPITAL_OWNER is policy-driven. Other models remain unaffected unless a published policy explicitly enables
          them.
        </p>
        {["CAPITAL_OWNER", "CONTRACTOR_DELIVERY", "DIRECT_INTERNAL", "LEGACY_UNCLASSIFIED"].map((model) => (
          <label key={model}>
            <input
              checked={Boolean(enabled[model])}
              disabled={!editable}
              onChange={(event) => change("enabled_by_governance_model", { ...enabled, [model]: event.target.checked })}
              type="checkbox"
            />{" "}
            {model}
          </label>
        ))}
      </fieldset>
    );
  }
  if (section === "Inheritance") {
    const scope = record(draft.scope);
    return (
      <fieldset className="benefitsChecks">
        <legend>Tenant → Enterprise → Business Unit → Portfolio</legend>
        <label>
          <input
            checked={Boolean(scope.inherit_to_descendants)}
            disabled={!editable}
            onChange={(event) => change("scope", { ...scope, inherit_to_descendants: event.target.checked })}
            type="checkbox"
          />{" "}
          Inherit published policy to descendants
        </label>
        <p>Each Benefits Plan Version freezes configuration ID, revision and hash.</p>
      </fieldset>
    );
  }
  if (section === "Numbering") {
    const numbering = record(draft.numbering);
    return (
      <div className="benefitsEditorGrid">
        <label className="benefitsField">
          <span>Plan prefix</span>
          <input
            aria-label="Plan prefix"
            disabled={!editable}
            value={String(numbering.plan_prefix || "BPL")}
            onChange={(event) => change("numbering", { ...numbering, plan_prefix: event.target.value.toUpperCase() })}
          />
        </label>
        <label className="benefitsField">
          <span>Benefit prefix</span>
          <input
            aria-label="Benefit prefix"
            disabled={!editable}
            value={String(numbering.benefit_prefix || "BEN")}
            onChange={(event) =>
              change("numbering", { ...numbering, benefit_prefix: event.target.value.toUpperCase() })
            }
          />
        </label>
        <label className="benefitsField">
          <span>Padding</span>
          <input
            aria-label="Numbering padding"
            disabled={!editable}
            min={1}
            max={12}
            type="number"
            value={Number(numbering.padding || 6)}
            onChange={(event) => change("numbering", { ...numbering, padding: Number(event.target.value) })}
          />
        </label>
      </div>
    );
  }
  if (section === "Review / SoD") {
    const sod = record(draft.separation_of_duties);
    return (
      <fieldset className="benefitsChecks">
        <legend>Review and separation of duties</legend>
        <label>
          <input
            checked={Boolean(sod.reviewer_must_differ_from_author ?? true)}
            disabled={!editable}
            onChange={(event) =>
              change("separation_of_duties", { ...sod, reviewer_must_differ_from_author: event.target.checked })
            }
            type="checkbox"
          />{" "}
          Author must differ from final reviewer
        </label>
        <p>Benefit Owner is not automatically required to differ from author.</p>
      </fieldset>
    );
  }
  if (section === "Preview")
    return (
      <p>
        Use the Effective policy preview below. Preview always reports <strong>persisted=false</strong> and cannot
        create a live Project Plan.
      </p>
    );
  return (
    <div className="benefitsHistory">
      <article>
        <ShieldCheck size={17} />
        <div>
          <strong>{selected?.name || "Strategic Benefits policy"}</strong>
          <span>Revision {selected?.revision || 0}</span>
          <small>{status(selected)}</small>
        </div>
      </article>
      <p>Publication and archive events remain backend-audited; historical configuration pins remain readable.</p>
    </div>
  );
}
