/* eslint-disable react-hooks/exhaustive-deps -- reloads are intentionally keyed by the access token */
import { Archive, CopyPlus, Eye, Send, Settings2, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { capitalPlanningApi } from "./api";
import type { CapitalPlanningConfiguration, CapitalPlanningConfigurationPreview } from "./types";
import "./capitalPlanning.css";

const wave1Sections = [
  ["themes", "Strategic Investment Themes"],
  ["drivers", "Demand Drivers"],
  ["categories", "Demand Categories"],
  ["planning_horizons", "Planning Horizons"],
  ["urgency_levels", "Urgency Levels"],
  ["uncertainty_levels", "Uncertainty Levels"],
  ["required_fields", "Required Fields"],
  ["lifecycle_rules", "Lifecycle Rules"],
  ["project_type_applicability", "Project Type Applicability"],
  ["separation_of_duties", "Review / Separation of Duties"],
  ["governance_model_applicability", "Governance Model Applicability"],
  ["numbering", "Numbering"],
  ["inheritance", "Inheritance"],
] as const;

const bucketSections = [
  ["strategic_capital_buckets", "Bucket Catalog"],
  ["bucket_strategic_purpose", "Strategic Purpose"],
  ["theme_bucket_mapping", "Theme Mapping"],
  ["objective_bucket_mapping", "Strategic Objective Mapping"],
  ["allocation_basis_options", "Allocation Basis"],
  ["allocation_min_target_max_rules", "Min / Target / Max Rules"],
  ["allocation_tolerance_rules", "Tolerance Rules"],
  ["bucket_classification_policy", "Classification Policy"],
  ["unclassified_policy", "Unclassified Policy"],
  ["planning_cycle_applicability", "Planning Cycle Applicability"],
  ["portfolio_applicability", "Portfolio Applicability"],
  ["governance_model_applicability", "Governance Model"],
  ["project_type_applicability", "Project Type"],
  ["inheritance", "Inheritance"],
  ["numbering", "Numbering"],
  ["separation_of_duties", "Review / SoD"],
] as const;

const sections = [...wave1Sections, ...bucketSections] as const;

type SectionKey = (typeof sections)[number][0];
type JsonRecord = Record<string, unknown>;

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function status(item: CapitalPlanningConfiguration) {
  return item.status.toLowerCase();
}

function defaultSectionValue(key: SectionKey): unknown {
  if (
    ["lifecycle_rules", "separation_of_duties", "governance_model_applicability", "numbering", "inheritance"].includes(
      key
    )
  )
    return {};
  return [];
}

export default function CapitalPlanningAdminView({
  focus = "planning",
  initialSection,
  token,
}: {
  focus?: "planning" | "buckets";
  initialSection?: SectionKey;
  token: string;
}) {
  const [items, setItems] = useState<CapitalPlanningConfiguration[]>([]);
  const [editing, setEditing] = useState<CapitalPlanningConfiguration | null>(null);
  const [draft, setDraft] = useState<JsonRecord | null>(null);
  const firstSection: SectionKey = initialSection ?? (focus === "buckets" ? "strategic_capital_buckets" : "themes");
  const [section, setSection] = useState<SectionKey>(firstSection);
  const [sectionJson, setSectionJson] = useState("");
  const [workspaceId, setWorkspaceId] = useState<number | null>(null);
  const [preview, setPreview] = useState<CapitalPlanningConfigurationPreview | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () =>
    capitalPlanningApi
      .configurations(token)
      .then(setItems)
      .catch((error: Error) => setMessage(error.message));

  useEffect(() => {
    void load();
  }, [token]);

  const published = useMemo(() => items.filter((item) => status(item) === "published").length, [items]);
  const drafts = useMemo(() => items.filter((item) => status(item) === "draft").length, [items]);
  const displayedSections = focus === "buckets" ? bucketSections : wave1Sections;

  function openEditor(item: CapitalPlanningConfiguration) {
    const content = clone(item.content_json);
    setEditing(item);
    setDraft(content);
    setSection(firstSection);
    setSectionJson(JSON.stringify(content[firstSection] ?? defaultSectionValue(firstSection), null, 2));
  }

  function selectSection(key: SectionKey) {
    if (!draft) return;
    setSection(key);
    setSectionJson(JSON.stringify(draft[key] ?? defaultSectionValue(key), null, 2));
  }

  function applySection() {
    if (!draft) return;
    try {
      const value = JSON.parse(sectionJson) as unknown;
      const next = { ...draft, [section]: value };
      if (section === "inheritance" && value && typeof value === "object") {
        next.inherit_to_descendants = Boolean((value as JsonRecord).inherit_to_descendants);
      }
      setDraft(next);
      setMessage(`${sections.find(([key]) => key === section)?.[1]} staged in the DRAFT revision.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The section is not valid JSON.");
    }
  }

  async function mutate(action: "clone" | "save" | "publish" | "archive", item: CapitalPlanningConfiguration) {
    setBusy(true);
    setMessage("");
    try {
      if (action === "clone") await capitalPlanningApi.cloneConfiguration(token, item, workspaceId);
      if (action === "save") {
        if (!draft) throw new Error("No DRAFT configuration is open.");
        const value = JSON.parse(sectionJson) as unknown;
        const staged = { ...draft, [section]: value };
        if (section === "inheritance" && value && typeof value === "object") {
          staged.inherit_to_descendants = Boolean((value as JsonRecord).inherit_to_descendants);
        }
        await capitalPlanningApi.updateConfiguration(token, item, staged);
      }
      if (action === "publish") await capitalPlanningApi.publishConfiguration(token, item);
      if (action === "archive") await capitalPlanningApi.archiveConfiguration(token, item);
      setEditing(null);
      setDraft(null);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Configuration action failed.");
    } finally {
      setBusy(false);
    }
  }

  async function showPreview() {
    setBusy(true);
    setMessage("");
    try {
      setPreview(await capitalPlanningApi.previewConfiguration(token, workspaceId));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Effective configuration preview failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      aria-label={
        focus === "buckets"
          ? "Strategic Capital Buckets configuration"
          : "Strategic Capital Planning and Demand configuration"
      }
      className="capitalPlanning"
    >
      <CompactModuleHeader
        eyebrow="ADMIN MODE / Enterprise Strategy Manager"
        title={focus === "buckets" ? "Strategic Capital Buckets" : "Strategic Capital Planning & Demand Configuration"}
        description={
          focus === "buckets"
            ? "Configure and publish reusable Bucket definitions, mappings and allocation policy. This surface never edits a live Allocation Plan."
            : "Publish reusable Themes and policy. This surface never creates live Planning Cycles, Capital Demands or Ideas."
        }
        metrics={[
          { label: "Configurations", value: items.length },
          { label: "Published", value: published },
          { label: "Drafts", value: drafts },
        ]}
      />
      <div className="capitalBoundary" role="note">
        <ShieldCheck aria-hidden="true" size={18} />
        <span>
          ADMIN owns DRAFT → PUBLISHED → ARCHIVED configuration and non-persistent previews. USER owns live planning
          records, Bucket classifications and lifecycle decisions.
        </span>
      </div>
      {message ? (
        <div className="capitalMessage" role="status">
          {message}
        </div>
      ) : null}
      <section aria-label="Capital Planning configuration actions" className="capitalAdminPreview">
        <div>
          <label>
            Workspace context for effective inheritance preview
            <input
              min="1"
              onChange={(event) => setWorkspaceId(event.target.value ? Number(event.target.value) : null)}
              placeholder="Optional Workspace ID"
              type="number"
              value={workspaceId || ""}
            />
          </label>
          <button className="capitalSecondary" disabled={busy} onClick={() => void showPreview()} type="button">
            <Eye aria-hidden="true" size={14} /> Preview effective configuration
          </button>
          <small>
            When a Workspace ID is present, Clone to DRAFT materializes an explicit workspace override; blank clones the
            same configuration scope.
          </small>
        </div>
        {preview ? (
          <article role="status">
            <strong>persisted={String(preview.persisted)}</strong>
            <span>Effective configuration resolved from {String(preview.source.code || "governed defaults")}</span>
            <small>No live Planning Cycle, Demand, Idea, Project, Budget or Funding record was created.</small>
          </article>
        ) : null}
      </section>
      <div className="capitalAdminGrid">
        {items.map((item) => (
          <article key={item.id}>
            <header>
              <Settings2 aria-hidden="true" size={20} />
              <b className={statusClassForConfig(item.status)}>{item.status}</b>
            </header>
            <span>{item.code || "CAPITAL_PLANNING"}</span>
            <h3>{item.name}</h3>
            <p>{item.description || "Governed Capital Planning policy configuration."}</p>
            <footer>
              <span>Revision {item.revision}</span>
              <span>Version {item.version}</span>
            </footer>
            <div className="capitalAdminActions">
              {status(item) === "published" ? (
                <>
                  <button disabled={busy} onClick={() => void mutate("clone", item)} type="button">
                    <CopyPlus aria-hidden="true" size={14} /> Clone to DRAFT
                  </button>
                  <button disabled={busy} onClick={() => void mutate("archive", item)} type="button">
                    <Archive aria-hidden="true" size={14} /> Archive
                  </button>
                </>
              ) : null}
              {status(item) === "draft" ? (
                <>
                  <button disabled={busy} onClick={() => openEditor(item)} type="button">
                    <Settings2 aria-hidden="true" size={14} /> Edit governed sections
                  </button>
                  <button disabled={busy} onClick={() => void mutate("publish", item)} type="button">
                    <Send aria-hidden="true" size={14} /> Publish
                  </button>
                </>
              ) : null}
            </div>
          </article>
        ))}
      </div>
      <section
        className="capitalAdminScope"
        aria-label={focus === "buckets" ? "Strategic Capital Buckets ADMIN scope" : "Capital Planning ADMIN scope"}
      >
        {displayedSections.map(([, label]) => (
          <span key={label}>{label}</span>
        ))}
        <span>Clone / Preview / Publish / Archive</span>
      </section>

      {editing && draft ? (
        <div className="capitalDrawerBackdrop" role="presentation">
          <section aria-label="Edit Capital Planning configuration" className="capitalDrawer wide">
            <header>
              <div>
                <span>DRAFT revision {editing.revision}</span>
                <h3>{editing.name}</h3>
              </div>
              <button onClick={() => setEditing(null)} type="button">
                Close
              </button>
            </header>
            <nav
              aria-label={
                focus === "buckets"
                  ? "Strategic Capital Bucket configuration sections"
                  : "Capital Planning configuration sections"
              }
              className="capitalConfigSections"
            >
              {displayedSections.map(([key, label]) => (
                <button
                  aria-current={section === key ? "page" : undefined}
                  className={section === key ? "active" : ""}
                  key={key}
                  onClick={() => selectSection(key)}
                  type="button"
                >
                  {label}
                </button>
              ))}
            </nav>
            <label>
              {sections.find(([key]) => key === section)?.[1]} — governed JSON fragment
              <textarea
                className="capitalConfigEditor"
                onChange={(event) => setSectionJson(event.target.value)}
                spellCheck={false}
                value={sectionJson}
              />
            </label>
            <div className="capitalConfigNote">
              <strong>Policy boundaries</strong>
              <span>
                {focus === "buckets"
                  ? "A Strategic Capital Bucket is an allocation category, not a Theme, Strategic Objective, Project rank, Budget approval, Funding assignment, Resource Scenario or FID."
                  : "Keep Strategic Investment Themes distinct from Objectives, Idea Categories, Project Types and Strategic Capital Buckets. CAPITAL_OWNER may require Demand origination; alternate governance models remain policy-controlled."}
              </span>
            </div>
            <footer>
              <button onClick={applySection} type="button">
                Apply section to DRAFT
              </button>
              <button
                className="capitalPrimary"
                disabled={busy}
                onClick={() => void mutate("save", editing)}
                type="button"
              >
                Save DRAFT revision
              </button>
            </footer>
          </section>
        </div>
      ) : null}
    </section>
  );
}

function statusClassForConfig(value: string) {
  return `capitalStatus status-${value.toLowerCase()}`;
}
