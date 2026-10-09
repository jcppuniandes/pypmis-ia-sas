/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { Archive, CopyPlus, Eye, Save, Send, Settings2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { commercialStrategyApi } from "./api";
import type { CommercialStrategyConfiguration } from "./types";
import "./commercialStrategy.css";

const sections = [
  "General",
  "Applicability",
  "Procurement Approaches",
  "Contracting Models",
  "Package Types",
  "Market Assessment Criteria",
  "Supply Chain Criteria",
  "Risk Allocation Categories",
  "Payment Mechanisms",
  "Incentive Mechanisms",
  "Required Sections",
  "Readiness Rules",
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
type JsonShape = "array" | "object";

const keyBySection: Partial<Record<Section, string>> = {
  "Procurement Approaches": "procurement_approaches",
  "Contracting Models": "contracting_models",
  "Package Types": "package_types",
  "Market Assessment Criteria": "market_assessment_criteria",
  "Supply Chain Criteria": "supply_chain_criteria",
  "Risk Allocation Categories": "risk_allocation_categories",
  "Payment Mechanisms": "payment_mechanisms",
  "Incentive Mechanisms": "incentive_mechanisms",
  "Required Sections": "required_sections",
};

function status(item: CommercialStrategyConfiguration) {
  return item.status.toUpperCase();
}

function record(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as JsonRecord) : {};
}

function list(value: unknown): Array<JsonRecord | string> {
  return Array.isArray(value) ? (value as Array<JsonRecord | string>) : [];
}

function valueToLines(value: unknown) {
  return list(value)
    .map((item) => (typeof item === "string" ? item : String(item.code || item.label || item.name || "")))
    .filter(Boolean)
    .join("\n");
}

function linesToCatalog(value: string) {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function clone(value: JsonRecord) {
  return JSON.parse(JSON.stringify(value)) as JsonRecord;
}

function JsonEditor({
  disabled,
  help,
  label,
  onChange,
  onError,
  shape,
  value,
}: {
  disabled: boolean;
  help: string;
  label: string;
  onChange: (value: unknown) => void;
  onError: (message: string) => void;
  shape: JsonShape;
  value: unknown;
}) {
  const normalized = shape === "array" ? (Array.isArray(value) ? value : []) : record(value);
  const serialized = JSON.stringify(normalized, null, 2);
  const [source, setSource] = useState(serialized);
  const [error, setError] = useState("");

  useEffect(() => {
    setSource(serialized);
    setError("");
    onError("");
  }, [serialized]);

  function update(next: string) {
    setSource(next);
    try {
      const parsed = JSON.parse(next) as unknown;
      const valid =
        shape === "array"
          ? Array.isArray(parsed)
          : Boolean(parsed && typeof parsed === "object" && !Array.isArray(parsed));
      if (!valid) throw new Error(`Expected a JSON ${shape}.`);
      setError("");
      onError("");
      onChange(parsed);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Invalid JSON.";
      setError(message);
      onError(message);
    }
  }

  return (
    <label className="commercialField">
      <span>{label}</span>
      <small>{help}</small>
      <textarea
        aria-describedby={error ? `${label.replace(/\s+/g, "-").toLowerCase()}-error` : undefined}
        aria-invalid={Boolean(error)}
        aria-label={label}
        disabled={disabled}
        rows={14}
        spellCheck={false}
        value={source}
        onChange={(event) => update(event.target.value)}
      />
      {error ? (
        <small className="commercialFieldError" id={`${label.replace(/\s+/g, "-").toLowerCase()}-error`} role="alert">
          {error}
        </small>
      ) : null}
    </label>
  );
}

export default function CommercialStrategyAdminView({ token }: { token: string }) {
  const [items, setItems] = useState<CommercialStrategyConfiguration[]>([]);
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
    const rows = await commercialStrategyApi.configurations(token);
    setItems(rows);
    setSelectedId(preferredId || rows[0]?.id || 0);
  }

  useEffect(() => {
    void load().catch((error) => setMessage(error instanceof Error ? error.message : "Unable to load configuration"));
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

  async function execute(work: () => Promise<CommercialStrategyConfiguration>, success: string) {
    if (!selected) return;
    setBusy(true);
    setMessage("");
    try {
      const result = await work();
      await load(result.id);
      setMessage(success);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Configuration action failed");
    } finally {
      setBusy(false);
    }
  }

  async function showPreview() {
    if (!selected) return;
    setBusy(true);
    setMessage("");
    try {
      setPreview(await commercialStrategyApi.effectivePreview(token, projectId, selected.id, draft));
      setMessage("Effective configuration preview resolved with persisted=false.");
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

  return (
    <section aria-label="Commercial Strategy Configuration" className="commercialStrategy commercialAdmin">
      <CompactModuleHeader
        description="Configure, govern and publish reusable Commercial Strategy catalogs, applicability, readiness and review policy. This surface cannot operate live Project strategies."
        eyebrow="ADMIN MODE · PROJECT DEFINITION & INVESTMENT CASE CONFIGURATION · GATE 07M-COMM"
        metrics={metrics}
        title="Commercial Strategy Configuration"
      />

      {message ? (
        <div className="commercialMessage" role="status">
          {message}
        </div>
      ) : null}

      <div className="commercialAdminLayout">
        <aside aria-label="Commercial Strategy configuration revisions">
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

        <section className="commercialSurface">
          <header>
            <div>
              <span>Controlled configuration revision</span>
              <h3>{selected?.name || "Commercial Strategy policy"}</h3>
            </div>
            {selected ? (
              <span className={`commercialStatus ${status(selected).toLowerCase()}`}>{status(selected)}</span>
            ) : null}
          </header>

          <div className="commercialAdminActions">
            <button
              disabled={busy || !selected || status(selected) !== "PUBLISHED"}
              onClick={() =>
                selected &&
                void execute(
                  () => commercialStrategyApi.cloneConfiguration(token, selected),
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
                  () => commercialStrategyApi.updateConfiguration(token, selected, draft),
                  "Configuration DRAFT saved under ETag control."
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
                  () => commercialStrategyApi.publishConfiguration(token, selected),
                  "Configuration published; historical Project versions remain unchanged."
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
                  () => commercialStrategyApi.archiveConfiguration(token, selected),
                  "Configuration archived without mutating completed strategies."
                )
              }
              type="button"
            >
              <Archive size={15} /> Archive
            </button>
          </div>

          <nav aria-label="Commercial Strategy configuration sections" className="commercialConfigTabs">
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

          <div className="commercialConfigEditor">
            {renderSection(
              activeSection,
              draft,
              selected,
              status(selected || ({ status: "ARCHIVED" } as CommercialStrategyConfiguration)) === "DRAFT" && !busy,
              change,
              reportJsonError
            )}
          </div>

          <details className="commercialAdvanced">
            <summary>Advanced configuration snapshot · read only</summary>
            <pre aria-label="Advanced Commercial Strategy configuration read only">
              {JSON.stringify(draft, null, 2)}
            </pre>
          </details>
        </section>
      </div>

      <section aria-label="Commercial Strategy effective preview" className="commercialSurface commercialAdminPreview">
        <div>
          <Eye size={19} />
          <div>
            <strong>Effective policy preview</strong>
            <p>
              Resolve Tenant → Enterprise → Business Unit → Portfolio inheritance without persisting a Project
              transaction.
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

      <p className="commercialBoundary">
        <strong>ADMIN boundary:</strong> configuration administrators cannot create, edit, submit, review or complete a
        live Project Commercial Strategy from this surface. Published policies are immutable and do not retroactively
        alter historical evidence.
      </p>
    </section>
  );
}

function renderSection(
  section: Section,
  draft: JsonRecord,
  selected: CommercialStrategyConfiguration | null,
  editable: boolean,
  change: (key: string, value: unknown) => void,
  reportJsonError: (key: string, error: string) => void
) {
  const catalogKey = keyBySection[section];
  if (catalogKey) {
    return (
      <label className="commercialField">
        <span>{section}</span>
        <small>
          One governed catalog entry per line. Values are published by ADMIN and consumed by USER by reference.
        </small>
        <textarea
          aria-label={section}
          disabled={!editable}
          rows={12}
          value={valueToLines(draft[catalogKey])}
          onChange={(event) => change(catalogKey, linesToCatalog(event.target.value))}
        />
      </label>
    );
  }
  if (section === "General") {
    return (
      <div className="commercialEditorGrid">
        <label className="commercialField">
          <span>Policy code</span>
          <textarea
            aria-label="Policy code"
            disabled={!editable}
            rows={2}
            value={String(draft.configuration_code || "")}
            onChange={(event) => change("configuration_code", event.target.value.toUpperCase())}
          />
        </label>
        <label className="commercialField">
          <span>Policy description</span>
          <textarea
            aria-label="Policy description"
            disabled={!editable}
            rows={4}
            value={String(draft.policy_description || "")}
            onChange={(event) => change("policy_description", event.target.value)}
          />
        </label>
      </div>
    );
  }
  if (section === "Applicability" || section === "Governance Model Overrides") {
    const enabled = record(draft.enabled_by_governance_model);
    return (
      <fieldset className="commercialChecks">
        <legend>Governance Model applicability</legend>
        <p>
          CAPITAL_OWNER is policy-driven. Other governance models remain optional unless this published policy
          explicitly enables them.
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
  if (section === "Project Type Overrides") {
    return (
      <div className="commercialEditorGrid">
        <label className="commercialField">
          <span>Applicable Project Types</span>
          <small>One canonical Project Type code per line; * keeps the published policy broadly applicable.</small>
          <textarea
            aria-label="Applicable Project Types"
            disabled={!editable}
            rows={10}
            value={valueToLines(draft.applicable_project_types)}
            onChange={(event) => change("applicable_project_types", linesToCatalog(event.target.value))}
          />
        </label>
        <JsonEditor
          disabled={!editable}
          help="Ordered proportionality rules use a match object for project_size, project_risk, project_complexity, project_type, governance_model, gate_profile or fel_stage, then merge an overrides object."
          label="Tailoring rules"
          onChange={(value) => change("tailoring_rules", value)}
          onError={(error) => reportJsonError("tailoring_rules", error)}
          shape="array"
          value={draft.tailoring_rules}
        />
      </div>
    );
  }
  if (section === "Readiness Rules") {
    return (
      <div className="commercialEditorGrid">
        <label className="commercialField">
          <span>Blocking market threshold</span>
          <input
            aria-label="Blocking market threshold"
            disabled={!editable}
            min={0}
            max={100}
            type="number"
            value={Number(draft.market_blocking_threshold ?? 60)}
            onChange={(event) => change("market_blocking_threshold", Number(event.target.value))}
          />
        </label>
        <label className="commercialField">
          <span>Minimum alternatives</span>
          <input
            aria-label="Minimum alternatives"
            disabled={!editable}
            min={0}
            max={20}
            type="number"
            value={Number(draft.minimum_alternatives ?? 2)}
            onChange={(event) => change("minimum_alternatives", Number(event.target.value))}
          />
        </label>
        <JsonEditor
          disabled={!editable}
          help="Required field names grouped by package, risk_allocation, alternative and recommendation. Invalid JSON blocks save and publish."
          label="Required fields"
          onChange={(value) => change("required_fields", value)}
          onError={(error) => reportJsonError("required_fields", error)}
          shape="object"
          value={draft.required_fields}
        />
      </div>
    );
  }
  if (section === "FEL / Gate Requirements") {
    const requirements = record(draft.alternatives_required_by_fel_stage);
    return (
      <div className="commercialEditorGrid">
        <label className="commercialField">
          <span>Applicable FEL stages</span>
          <small>One governed stage code per line; no global USER behavior is hardcoded.</small>
          <textarea
            aria-label="Applicable FEL stages"
            disabled={!editable}
            rows={8}
            value={valueToLines(draft.applicable_fel_stages)}
            onChange={(event) => change("applicable_fel_stages", linesToCatalog(event.target.value))}
          />
        </label>
        <label className="commercialField">
          <span>Applicable Gate Profiles</span>
          <small>One governed Gate Profile code per line; * keeps the policy broadly applicable.</small>
          <textarea
            aria-label="Applicable Gate Profiles"
            disabled={!editable}
            rows={8}
            value={valueToLines(draft.applicable_gate_profiles)}
            onChange={(event) => change("applicable_gate_profiles", linesToCatalog(event.target.value))}
          />
        </label>
        <fieldset className="commercialChecks">
          <legend>Alternatives required by stage</legend>
          {["FEL-1", "FEL-2", "FEL-3", "FFA"].map((stage) => (
            <label key={stage}>
              <input
                checked={Boolean(requirements[stage])}
                disabled={!editable}
                onChange={(event) =>
                  change("alternatives_required_by_fel_stage", { ...requirements, [stage]: event.target.checked })
                }
                type="checkbox"
              />{" "}
              {stage}
            </label>
          ))}
        </fieldset>
      </div>
    );
  }
  if (section === "Inheritance") {
    const scope = record(draft.scope);
    return (
      <fieldset className="commercialChecks">
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
        <p>Each Project version freezes configuration ID, revision and hash.</p>
      </fieldset>
    );
  }
  if (section === "Numbering") {
    const numbering = record(draft.numbering);
    return (
      <div className="commercialEditorGrid">
        <label className="commercialField">
          <span>Prefix</span>
          <input
            aria-label="Numbering prefix"
            disabled={!editable}
            value={String(numbering.prefix || "CCS")}
            onChange={(event) => change("numbering", { ...numbering, prefix: event.target.value.toUpperCase() })}
          />
        </label>
        <label className="commercialField">
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
      <fieldset className="commercialChecks">
        <legend>Review and separation of duties</legend>
        <label>
          <input
            checked={Boolean(sod.reviewer_must_differ_from_preparer ?? true)}
            disabled={!editable}
            onChange={(event) =>
              change("separation_of_duties", { ...sod, reviewer_must_differ_from_preparer: event.target.checked })
            }
            type="checkbox"
          />{" "}
          Author must differ from final reviewer
        </label>
      </fieldset>
    );
  }
  if (section === "Preview")
    return (
      <p>
        Use the Effective policy preview below. Preview always reports <strong>persisted=false</strong> and cannot
        create a live Project record.
      </p>
    );
  if (section === "History")
    return (
      <div className="commercialHistory">
        <article>
          <strong>{selected?.name || "Commercial Strategy policy"}</strong>
          <span>Revision {selected?.revision || 0}</span>
          <small>{selected ? status(selected) : "NOT AVAILABLE"}</small>
        </article>
        <p>
          All configuration revisions remain available in the revision selector; publication and archive events are
          backend audited.
        </p>
      </div>
    );
  return (
    <pre>{JSON.stringify(draft[section.toLowerCase().replace(/ \/ /g, "_").replace(/ /g, "_")] || {}, null, 2)}</pre>
  );
}
