import { Archive, CopyPlus, Eye, Send, Settings2, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "../../api/client";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import "./businessAnalysis.css";

const root = "/api/v1/business-analyses";
const sections = [
  "General",
  "Analysis Types",
  "Need / Opportunity Taxonomy",
  "Business Drivers",
  "Stakeholder Categories",
  "Stakeholder Scales",
  "Value Dimensions",
  "Option Types",
  "Required Option Rules",
  "Evaluation Matrix",
  "Scoring Scales",
  "Weights",
  "Required Fields",
  "Readiness Checklist",
  "Proposal Mapping",
  "Numbering",
  "Inheritance",
  "Permissions / SoD",
  "Preview",
  "History / Revisions",
] as const;

type ConfigurationSection = (typeof sections)[number];
type JsonRecord = Record<string, unknown>;

const governanceModels = ["CAPITAL_OWNER", "CONTRACTOR_DELIVERY", "DIRECT_INTERNAL", "LEGACY_UNCLASSIFIED"];
const versionHeaders = (item: JsonRecord) => ({ "If-Match": `"${Number(item.version)}"` });

function record(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as JsonRecord) : {};
}

function records(value: unknown): JsonRecord[] {
  return Array.isArray(value) ? value.map(record) : [];
}

function lines(value: unknown): string {
  return Array.isArray(value) ? value.map(String).join("\n") : "";
}

function parseLines(value: string): string[] {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function cloneConfiguration(value: unknown): JsonRecord {
  return JSON.parse(JSON.stringify(record(value))) as JsonRecord;
}

export default function BusinessAnalysisAdminView({ token }: { token: string }) {
  const [items, setItems] = useState<JsonRecord[]>([]);
  const [editing, setEditing] = useState<JsonRecord | null>(null);
  const [draft, setDraft] = useState<JsonRecord | null>(null);
  const [activeSection, setActiveSection] = useState<ConfigurationSection>("General");
  const [workspaceId, setWorkspaceId] = useState(1);
  const [preview, setPreview] = useState<JsonRecord | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () =>
    apiFetch<JsonRecord[]>(`${root}/admin/configurations`, { token })
      .then(setItems)
      .catch((error: Error) => setMessage(error.message));

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const matrix = useMemo(() => record(draft?.evaluation_matrix), [draft]);
  const scale = useMemo(() => record(matrix.scale), [matrix]);
  const criteria = useMemo(() => records(matrix.criteria), [matrix]);
  const requiredByGovernanceModel = useMemo(
    () => record(draft?.business_analysis_required_by_governance_model),
    [draft]
  );

  function changeDraft(key: string, value: unknown) {
    setDraft((current) => ({ ...record(current), [key]: value }));
  }

  function changeGovernanceRequirement(model: string, required: boolean) {
    changeDraft("business_analysis_required_by_governance_model", {
      ...requiredByGovernanceModel,
      [model]: required,
    });
  }

  function changeScale(key: string, value: unknown) {
    changeDraft("evaluation_matrix", { ...matrix, scale: { ...scale, [key]: value } });
  }

  function changeCriterion(index: number, key: string, value: unknown) {
    const next = criteria.map((criterion, itemIndex) =>
      itemIndex === index ? { ...criterion, [key]: value } : criterion
    );
    changeDraft("evaluation_matrix", { ...matrix, criteria: next });
  }

  function addCriterion() {
    changeDraft("evaluation_matrix", {
      ...matrix,
      criteria: [...criteria, { code: "", label: "", weight: 0 }],
    });
  }

  function removeCriterion(index: number) {
    changeDraft("evaluation_matrix", {
      ...matrix,
      criteria: criteria.filter((_criterion, itemIndex) => itemIndex !== index),
    });
  }

  function openEditor(item: JsonRecord) {
    setEditing(item);
    setDraft(cloneConfiguration(item.content_json));
    setActiveSection("General");
  }

  function closeEditor() {
    setEditing(null);
    setDraft(null);
  }

  async function mutate(action: "clone" | "save" | "publish" | "archive", item: JsonRecord) {
    setBusy(true);
    setMessage("");
    try {
      if (action === "clone") {
        await apiFetch(`${root}/admin/configurations/${String(item.id)}/clone`, {
          method: "POST",
          token,
          headers: versionHeaders(item),
        });
      }
      if (action === "save") {
        if (!draft) throw new Error("No structured configuration draft is open.");
        await apiFetch(`${root}/admin/configurations/${String(item.id)}`, {
          method: "PUT",
          token,
          headers: versionHeaders(item),
          body: JSON.stringify({
            name: item.name,
            description: item.description || "",
            content_json: draft,
          }),
        });
      }
      if (action === "publish" || action === "archive") {
        await apiFetch(`${root}/admin/configurations/${String(item.id)}/${action}`, {
          method: "POST",
          token,
          headers: versionHeaders(item),
        });
      }
      closeEditor();
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Configuration action failed");
    } finally {
      setBusy(false);
    }
  }

  async function showPreview() {
    setBusy(true);
    setMessage("");
    try {
      setPreview(
        await apiFetch<JsonRecord>(`${root}/admin/configuration/preview`, {
          method: "POST",
          token,
          body: JSON.stringify({ owning_workspace_id: workspaceId }),
        })
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Preview failed");
    } finally {
      setBusy(false);
    }
  }

  function structuredSection() {
    if (!draft) return null;
    if (activeSection === "General") {
      return (
        <fieldset>
          <legend>Governance Model applicability</legend>
          <p>
            Business Analysis is required by default only for CAPITAL_OWNER. Published policy may opt in other models.
          </p>
          <div className="baChecks baGovernanceChecks">
            {governanceModels.map((model) => (
              <label key={model}>
                <input
                  checked={Boolean(requiredByGovernanceModel[model])}
                  onChange={(event) => changeGovernanceRequirement(model, event.target.checked)}
                  type="checkbox"
                />
                <span>{model}</span>
              </label>
            ))}
          </div>
        </fieldset>
      );
    }

    if (activeSection === "Required Option Rules") {
      const rules = record(draft.required_option_rules);
      return (
        <fieldset>
          <legend>Required option rules</legend>
          <label>
            <span>Minimum options</span>
            <input
              aria-label="Minimum options"
              min="1"
              onChange={(event) =>
                changeDraft("required_option_rules", { ...rules, minimum_options: Number(event.target.value) })
              }
              type="number"
              value={Number(rules.minimum_options || 1)}
            />
          </label>
          <label>
            <span>Required option types</span>
            <input
              aria-label="Required option types"
              onChange={(event) =>
                changeDraft("required_option_rules", {
                  ...rules,
                  required_option_types: parseLines(event.target.value),
                })
              }
              value={lines(rules.required_option_types).replace(/\n/g, ", ")}
            />
          </label>
        </fieldset>
      );
    }

    if (["Evaluation Matrix", "Scoring Scales", "Weights"].includes(activeSection)) {
      return (
        <div className="baStructuredEditor">
          <fieldset>
            <legend>Published scoring scale</legend>
            <div className="baFormGrid">
              <label>
                <span>Minimum rating</span>
                <input
                  aria-label="Minimum rating"
                  onChange={(event) => changeScale("min", Number(event.target.value))}
                  type="number"
                  value={Number(scale.min ?? 1)}
                />
              </label>
              <label>
                <span>Maximum rating</span>
                <input
                  aria-label="Maximum rating"
                  onChange={(event) => changeScale("max", Number(event.target.value))}
                  type="number"
                  value={Number(scale.max ?? 5)}
                />
              </label>
            </div>
            <label>
              <span>Allowed rating values</span>
              <input
                aria-label="Allowed rating values"
                onChange={(event) =>
                  changeScale(
                    "allowed_values",
                    parseLines(event.target.value).map((value) => Number(value))
                  )
                }
                value={lines(scale.allowed_values).replace(/\n/g, ", ")}
              />
            </label>
          </fieldset>
          <fieldset>
            <legend>Evaluation criteria and weights</legend>
            <div className="baMatrixHeader" aria-hidden="true">
              <span>Code</span>
              <span>Label</span>
              <span>Weight</span>
              <span>Action</span>
            </div>
            {criteria.map((criterion, index) => {
              const code = String(criterion.code || `criterion-${index + 1}`);
              return (
                <div className="baMatrixRow" key={`${code}-${index}`}>
                  <input
                    aria-label={`Criterion code ${index + 1}`}
                    onChange={(event) => changeCriterion(index, "code", event.target.value.toUpperCase())}
                    value={String(criterion.code || "")}
                  />
                  <input
                    aria-label={`Criterion label ${code}`}
                    onChange={(event) => changeCriterion(index, "label", event.target.value)}
                    value={String(criterion.label || "")}
                  />
                  <input
                    aria-label={`Weight ${code}`}
                    min="0"
                    onChange={(event) => changeCriterion(index, "weight", Number(event.target.value))}
                    type="number"
                    value={Number(criterion.weight || 0)}
                  />
                  <button aria-label={`Remove criterion ${code}`} onClick={() => removeCriterion(index)} type="button">
                    Remove
                  </button>
                </div>
              );
            })}
            <button className="baSecondary" onClick={addCriterion} type="button">
              Add evaluation criterion
            </button>
          </fieldset>
        </div>
      );
    }

    if (activeSection === "Required Fields" || activeSection === "Readiness Checklist") {
      const key = activeSection === "Required Fields" ? "required_fields" : "readiness_checklist";
      return (
        <fieldset>
          <legend>{activeSection}</legend>
          <label>
            <span>One governed value per line</span>
            <textarea
              aria-label={activeSection}
              onChange={(event) => changeDraft(key, parseLines(event.target.value))}
              value={lines(draft[key])}
            />
          </label>
        </fieldset>
      );
    }

    const sectionKey: Record<string, string> = {
      "Analysis Types": "analysis_types",
      "Business Drivers": "business_drivers",
      Inheritance: "inherit_to_descendants",
      "Need / Opportunity Taxonomy": "analysis_types",
      Numbering: "numbering",
      "Option Types": "option_types",
      "Permissions / SoD": "sod_policy",
      "Proposal Mapping": "proposal_mapping",
      "Stakeholder Categories": "stakeholder_categories",
      "Stakeholder Scales": "stakeholder_scales",
      "Value Dimensions": "value_dimensions",
    };
    const value = sectionKey[activeSection] ? draft[sectionKey[activeSection]] : draft;
    return (
      <section className="baSectionReadOnly" aria-label={`${activeSection} summary`}>
        <h4>{activeSection}</h4>
        <p>This section is governed through its typed contract. The current effective values are shown read-only.</p>
        <pre>{JSON.stringify(value ?? null, null, 2)}</pre>
      </section>
    );
  }

  return (
    <section className="baWorkspace" aria-label="Business Analysis Configuration">
      <CompactModuleHeader
        eyebrow="ADMIN MODE / Enterprise Strategy Manager / Idea & Demand Configuration"
        title="Business Analysis Configuration"
        description="Configure reusable Business Analysis policy, catalogs, scoring, readiness, mapping and separation of duties."
        metrics={[
          { label: "Revisions", value: items.length },
          { label: "Published", value: items.filter((item) => item.status === "published").length },
          { label: "Drafts", value: items.filter((item) => item.status === "draft").length },
        ]}
      />

      {message ? (
        <div className="baMessage" role="alert">
          {message}
        </div>
      ) : null}

      <section className="baConfigPreview" aria-label="Configuration preview">
        <div>
          <Eye size={18} />
          <div>
            <strong>Effective preview</strong>
            <p>
              Resolve Tenant to Enterprise to Business Unit to Portfolio inheritance without persisting a transaction.
            </p>
          </div>
        </div>
        <label>
          <span>Owning Workspace ID</span>
          <input
            min="1"
            type="number"
            value={workspaceId}
            onChange={(event) => setWorkspaceId(Number(event.target.value))}
          />
        </label>
        <button className="baSecondary" disabled={busy} onClick={() => void showPreview()} type="button">
          Preview persisted=false
        </button>
        {preview ? (
          <output>
            <strong>{String(record(preview.validation).valid ? "VALID" : "INVALID")}</strong>
            <span>
              Revision {String(record(preview.source).revision)} · persisted {String(preview.persisted)}
            </span>
          </output>
        ) : null}
      </section>

      <div className="baAdminGrid">
        {items.map((item) => (
          <article key={String(item.id)}>
            <Settings2 size={20} />
            <span>{String(item.kind).replace(/_/g, " ")}</span>
            <h3>{String(item.name)}</h3>
            <p>{String(item.description || "Controlled Business Analysis configuration")}</p>
            <footer>
              <span>Revision {String(item.revision)}</span>
              <strong>
                <ShieldCheck size={14} /> {String(item.status)}
              </strong>
            </footer>
            <div className="baActions">
              {item.status === "published" ? (
                <button disabled={busy} onClick={() => void mutate("clone", item)} type="button">
                  <CopyPlus size={14} /> Clone draft
                </button>
              ) : null}
              {item.status === "published" ? (
                <button disabled={busy} onClick={() => void mutate("archive", item)} type="button">
                  <Archive size={14} /> Archive
                </button>
              ) : null}
              {item.status === "draft" ? (
                <button disabled={busy} onClick={() => openEditor(item)} type="button">
                  <Settings2 size={14} /> Edit policy
                </button>
              ) : null}
              {item.status === "draft" ? (
                <button
                  className="baPrimary"
                  disabled={busy}
                  onClick={() => void mutate("publish", item)}
                  type="button"
                >
                  <Send size={14} /> Publish
                </button>
              ) : null}
            </div>
          </article>
        ))}
      </div>

      <p className="baBoundary">
        <strong>Mode boundary</strong> This ADMIN surface never creates, submits, reviews or completes a live Business
        Analysis record. Transactional work remains in USER MODE.
      </p>

      {editing && draft ? (
        <div className="baDrawerBackdrop">
          <section className="baDrawer baEditor" aria-label="Edit Business Analysis configuration">
            <header>
              <div>
                <span>DRAFT REVISION {String(editing.revision)}</span>
                <h3>{String(editing.name)}</h3>
              </div>
              <button onClick={closeEditor} type="button">
                Close
              </button>
            </header>
            <nav className="baSections baSectionButtons" aria-label="Business Analysis configuration sections">
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
            <div className="baEditorScroll">{structuredSection()}</div>
            <details className="baAdvancedJson">
              <summary>Advanced configuration JSON read only</summary>
              <pre aria-label="Advanced configuration JSON read only">{JSON.stringify(draft, null, 2)}</pre>
            </details>
            <footer>
              <button onClick={closeEditor} type="button">
                Cancel
              </button>
              <button className="baPrimary" disabled={busy} onClick={() => void mutate("save", editing)} type="button">
                Save draft
              </button>
            </footer>
          </section>
        </div>
      ) : null}
    </section>
  );
}
