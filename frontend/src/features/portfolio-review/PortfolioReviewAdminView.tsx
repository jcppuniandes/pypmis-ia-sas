import { Archive, CopyPlus, Eye, Save, Send, Settings2, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { portfolioReviewApi } from "./api";
import type { PortfolioReviewConfiguration, PortfolioReviewConfigurationPreview } from "./types";
import "./portfolioReview.css";

const configurationSections = [
  ["general", "General"],
  ["review_types", "Review Types"],
  ["cadence", "Cadence"],
  ["applicability", "Applicability"],
  ["agenda_template", "Agenda Template"],
  ["required_snapshot_sources", "Required Snapshot Sources"],
  ["source_freshness", "Source Freshness"],
  ["review_readiness", "Review Readiness"],
  ["portfolio_conclusion_types", "Portfolio Conclusion Types"],
  ["action_types", "Action Types"],
  ["action_applicability", "Action Applicability"],
  ["action_ownership_rules", "Action Ownership Rules"],
  ["thresholds_alerts", "Thresholds / Alerts"],
  ["bucket_variance_rules", "Bucket Variance Rules"],
  ["unclassified_exposure", "Unclassified Exposure"],
  ["budget_context_rules", "Budget Context Rules"],
  ["resource_context_rules", "Resource Context Rules"],
  ["gate_context_rules", "Gate Context Rules"],
  ["committee_authority", "Committee / Authority"],
  ["review_sod", "Review / SoD"],
  ["numbering", "Numbering"],
  ["inheritance", "Inheritance"],
  ["preview", "Preview"],
  ["history", "History"],
] as const;

type ConfigurationSection = (typeof configurationSections)[number][0];

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function defaultValue(section: ConfigurationSection): unknown {
  if (
    [
      "general",
      "cadence",
      "source_freshness",
      "review_readiness",
      "thresholds_alerts",
      "bucket_variance_rules",
      "unclassified_exposure",
      "budget_context_rules",
      "resource_context_rules",
      "gate_context_rules",
      "committee_authority",
      "review_sod",
      "numbering",
      "inheritance",
      "preview",
      "history",
    ].includes(section)
  )
    return {};
  return [];
}

// Several business sections project one governed policy object; never save inert UI-only keys.
const sectionPaths: Record<ConfigurationSection, string | null> = {
  general: "scope",
  review_types: "review_types",
  cadence: "cadence",
  applicability: "applicability",
  agenda_template: "agenda_template",
  required_snapshot_sources: "snapshot_policy",
  source_freshness: "source_freshness",
  review_readiness: "review_readiness",
  portfolio_conclusion_types: "conclusion_types",
  action_types: "action_types",
  action_applicability: "action_applicability",
  action_ownership_rules: null,
  thresholds_alerts: "thresholds",
  bucket_variance_rules: "thresholds.bucket_variance_tolerance_percentage",
  unclassified_exposure: "thresholds.unclassified_exposure_tolerance_percentage",
  budget_context_rules: "snapshot_policy.require_frozen_budget_when_selected",
  resource_context_rules: "snapshot_policy.require_frozen_resource_when_selected",
  gate_context_rules: "source_freshness.gate_evidence_max_age_days",
  committee_authority: "authority",
  review_sod: "separation_of_duties",
  numbering: "numbering",
  inheritance: "inherit_to_descendants",
  preview: null,
  history: null,
};

function fragment(content: Record<string, unknown>, section: ConfigurationSection) {
  const path = sectionPaths[section];
  if (!path)
    return section === "action_ownership_rules"
      ? { owner_required: true, owner_must_be_active_tenant_user: true, action_owner_updates_only_own_actions: true }
      : {
          read_only: true,
          surface:
            section === "history"
              ? "Configuration revisions and published hashes"
              : "Effective preview uses the staged DRAFT and persisted=false",
        };
  return (
    path
      .split(".")
      .reduce<unknown>(
        (value, key) => (value && typeof value === "object" ? (value as Record<string, unknown>)[key] : undefined),
        content
      ) ?? defaultValue(section)
  );
}

function applyFragment(content: Record<string, unknown>, section: ConfigurationSection, value: unknown) {
  const path = sectionPaths[section];
  if (!path) return content;
  const next = clone(content);
  const keys = path.split(".");
  let target = next;
  keys.slice(0, -1).forEach((key) => {
    if (!target[key] || typeof target[key] !== "object") target[key] = {};
    target = target[key] as Record<string, unknown>;
  });
  target[keys[keys.length - 1]] = value;
  return next;
}

function normalizedStatus(item: PortfolioReviewConfiguration) {
  return item.status.toLowerCase();
}

export default function PortfolioReviewAdminView({ token }: { token: string }) {
  const [items, setItems] = useState<PortfolioReviewConfiguration[]>([]);
  const [selected, setSelected] = useState<PortfolioReviewConfiguration | null>(null);
  const [draft, setDraft] = useState<Record<string, unknown> | null>(null);
  const [section, setSection] = useState<ConfigurationSection>("general");
  const [sectionJson, setSectionJson] = useState("");
  const [portfolioId, setPortfolioId] = useState<number | null>(null);
  const [targetWorkspaceId, setTargetWorkspaceId] = useState<number | null>(null);
  const [preview, setPreview] = useState<PortfolioReviewConfigurationPreview | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () =>
    portfolioReviewApi
      .configurations(token)
      .then((value) => {
        setItems(value);
        const preferred = value.find((item) => normalizedStatus(item) === "draft") ?? value[0] ?? null;
        setSelected((current) => value.find((item) => item.id === current?.id) ?? preferred);
      })
      .catch((error: Error) => setMessage(error.message));

  useEffect(() => {
    void load();
    // Configuration reloads are intentionally keyed by the access token.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const publishedCount = useMemo(() => items.filter((item) => normalizedStatus(item) === "published").length, [items]);
  const draftCount = useMemo(() => items.filter((item) => normalizedStatus(item) === "draft").length, [items]);

  function edit(item: PortfolioReviewConfiguration) {
    const content = clone(item.content_json ?? {});
    setSelected(item);
    setDraft(content);
    setSection("general");
    setSectionJson(JSON.stringify(fragment(content, "general"), null, 2));
    setPreview(null);
  }

  function selectSection(next: ConfigurationSection) {
    if (!draft) return;
    setSection(next);
    setSectionJson(JSON.stringify(fragment(draft, next), null, 2));
  }

  function stagedContent() {
    if (!draft) throw new Error("Open a DRAFT configuration before editing.");
    return applyFragment(draft, section, JSON.parse(sectionJson) as unknown);
  }

  function applySection() {
    try {
      const next = stagedContent();
      setDraft(next);
      setMessage(`${configurationSections.find(([key]) => key === section)?.[1]} staged in this DRAFT.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The governed JSON fragment is invalid.");
    }
  }

  async function execute(action: "clone" | "save" | "publish" | "archive", item: PortfolioReviewConfiguration) {
    setBusy(true);
    setMessage("");
    try {
      let result = item;
      if (action === "clone") result = await portfolioReviewApi.cloneConfiguration(token, item, targetWorkspaceId);
      if (action === "save") result = await portfolioReviewApi.updateConfiguration(token, item, stagedContent());
      if (action === "publish") result = await portfolioReviewApi.publishConfiguration(token, item);
      if (action === "archive") result = await portfolioReviewApi.archiveConfiguration(token, item);
      setDraft(null);
      setSectionJson("");
      setPreview(null);
      await load();
      setSelected(result);
      setMessage(`Portfolio Review configuration ${action} completed.`);
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
      const content = draft ? stagedContent() : selected?.content_json;
      const result = await portfolioReviewApi.previewConfiguration(token, portfolioId, selected?.id, content);
      setPreview(result);
      setMessage("Effective policy preview completed with persisted=false; no live Review Session was created.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Effective policy preview failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Periodic Portfolio Review configuration" className="portfolioReview portfolioReviewAdmin">
      <CompactModuleHeader
        eyebrow="ADMIN MODE / Enterprise Strategy Manager / Portfolio Planning & Review Configuration"
        title="Periodic Portfolio Review Configuration"
        description="Configure reusable Review types, cadence, snapshot requirements, readiness, conclusions, action semantics, thresholds and authority. This surface never creates or conducts a live Review Session."
        metrics={[
          { label: "Configurations", value: items.length },
          { label: "Published", value: publishedCount },
          { label: "Drafts", value: draftCount },
        ]}
        tone="admin"
      />
      <div className="reviewBoundary admin" role="note">
        <ShieldCheck aria-hidden="true" size={18} />
        <span>
          ADMIN owns reusable policy and DRAFT → PUBLISHED → ARCHIVED revisions. USER owns live Review Sessions, frozen
          snapshots, conclusions and Portfolio Review Actions.
        </span>
      </div>
      {message ? (
        <div className="reviewMessage" role="status">
          {message}
        </div>
      ) : null}

      <section aria-label="Portfolio Review configuration preview" className="reviewAdminPreview">
        <label>
          Portfolio context for effective preview
          <input
            min="1"
            onChange={(event) => setPortfolioId(event.target.value ? Number(event.target.value) : null)}
            placeholder="Optional Portfolio Workspace ID"
            type="number"
            value={portfolioId ?? ""}
          />
        </label>
        <label>
          Target Workspace for clone
          <input
            min="1"
            onChange={(event) => setTargetWorkspaceId(event.target.value ? Number(event.target.value) : null)}
            placeholder="Optional override scope"
            type="number"
            value={targetWorkspaceId ?? ""}
          />
        </label>
        <button disabled={busy || !selected} onClick={() => void showPreview()} type="button">
          <Eye aria-hidden="true" size={14} /> Preview effective configuration
        </button>
        {preview ? (
          <article>
            <strong>persisted={String(preview.persisted)}</strong>
            <span>{preview.readiness?.overall ?? "Effective policy resolved"}</span>
            <small>No Session, snapshot, conclusion, action, Gate or FID record was created.</small>
          </article>
        ) : null}
      </section>

      <div className="reviewAdminLayout">
        <aside aria-label="Portfolio Review configuration revisions">
          {items.map((item) => (
            <article className={selected?.id === item.id ? "selected" : ""} key={item.id}>
              <header>
                <Settings2 aria-hidden="true" size={18} />
                <b className={`reviewStatus status-${normalizedStatus(item)}`}>{item.status}</b>
              </header>
              <span>{item.code ?? "PORTFOLIO_REVIEW"}</span>
              <h3>{item.name}</h3>
              <p>{item.description || "Governed periodic Portfolio Review policy."}</p>
              <footer>
                <span>Revision {item.revision}</span>
                <span>Version {item.version}</span>
              </footer>
              <div>
                {normalizedStatus(item) === "published" ? (
                  <>
                    <button disabled={busy} onClick={() => void execute("clone", item)} type="button">
                      <CopyPlus aria-hidden="true" size={14} /> Clone to DRAFT
                    </button>
                    <button disabled={busy} onClick={() => void execute("archive", item)} type="button">
                      <Archive aria-hidden="true" size={14} /> Archive
                    </button>
                  </>
                ) : null}
                {normalizedStatus(item) === "draft" ? (
                  <>
                    <button disabled={busy} onClick={() => edit(item)} type="button">
                      <Settings2 aria-hidden="true" size={14} /> Edit governed sections
                    </button>
                    <button disabled={busy} onClick={() => void execute("publish", item)} type="button">
                      <Send aria-hidden="true" size={14} /> Publish
                    </button>
                  </>
                ) : null}
              </div>
            </article>
          ))}
        </aside>

        <section aria-label="Periodic Portfolio Review ADMIN scope" className="reviewAdminScope">
          <h3>Governed configuration scope</h3>
          <p>
            These sections define reusable policy only. Their values drive warnings and readiness, never an automated
            investment decision.
          </p>
          <div>
            {configurationSections.map(([, label]) => (
              <span key={label}>{label}</span>
            ))}
          </div>
        </section>
      </div>

      {selected && draft ? (
        <div className="reviewDrawerBackdrop" role="presentation">
          <section aria-label="Edit Portfolio Review configuration" className="reviewDrawer wide">
            <header>
              <div>
                <span>DRAFT revision {selected.revision}</span>
                <h3>{selected.name}</h3>
              </div>
              <button onClick={() => setDraft(null)} type="button">
                Close
              </button>
            </header>
            <nav aria-label="Portfolio Review configuration sections" className="reviewConfigSections">
              {configurationSections.map(([key, label]) => (
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
              {configurationSections.find(([key]) => key === section)?.[1]} — governed JSON fragment
              <textarea
                aria-label="Portfolio Review configuration JSON"
                readOnly={!sectionPaths[section]}
                onChange={(event) => setSectionJson(event.target.value)}
                rows={20}
                spellCheck={false}
                value={sectionJson}
              />
            </label>
            <div className="reviewAuthorityNote">
              <ShieldCheck aria-hidden="true" size={18} />
              Configuration may define cadence, alerts and action applicability. It cannot create a Session, recalculate
              rank, mutate a scenario, or issue Gate/FID.
            </div>
            <footer>
              <button disabled={!sectionPaths[section]} onClick={applySection} type="button">
                Apply section to DRAFT
              </button>
              <button disabled={busy} onClick={() => void execute("save", selected)} type="button">
                <Save aria-hidden="true" size={14} /> Save DRAFT revision
              </button>
            </footer>
          </section>
        </div>
      ) : null}
    </section>
  );
}
