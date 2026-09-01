/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { Copy, Database, Eye, Save, Send, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { portfolioPlanningApi } from "../portfolio-planning/api";
import { investmentEvidencePolicyApi } from "./api";
import type {
  EvidencePolicyConfiguration,
  EvidencePolicyContent,
  EvidencePolicyOverview,
  EvidencePolicyPreview,
  EvidenceRequirement,
} from "./types";
import "./investmentEvidencePolicy.css";

const sections = [
  "Overview",
  "Investment Gate Profiles",
  "Evidence Matrix",
  "Project Type Overrides",
  "Provider Registry",
  "Readiness Rules",
  "Validity",
  "Coverage",
  "Blocking Policy",
  "Missing Providers",
  "Preview",
  "History",
] as const;

type Section = (typeof sections)[number];

function parseContent(value: string): EvidencePolicyContent | null {
  try {
    return JSON.parse(value) as EvidencePolicyContent;
  } catch {
    return null;
  }
}

function classLabel(value: string) {
  if (value === "A") return "A · Governed source required";
  if (value === "B") return "B · Governed evidence sufficient";
  return "C · Not required";
}

export default function InvestmentEvidencePolicyAdminView({ token }: { token: string }) {
  const [overview, setOverview] = useState<EvidencePolicyOverview | null>(null);
  const [selected, setSelected] = useState<EvidencePolicyConfiguration | null>(null);
  const [content, setContent] = useState("");
  const [section, setSection] = useState<Section>("Overview");
  const [portfolios, setPortfolios] = useState<Array<Record<string, unknown>>>([]);
  const [portfolioId, setPortfolioId] = useState(0);
  const [gateProfile, setGateProfile] = useState("PYP-FFA");
  const [preview, setPreview] = useState<EvidencePolicyPreview | null>(null);
  const [message, setMessage] = useState("");
  const parsed = useMemo(() => parseContent(content), [content]);

  const matrixRows = useMemo(() => {
    if (!parsed) return [];
    return Object.entries(parsed.gate_profiles || {}).flatMap(([profile, value]) =>
      (value.requirements || []).map((item) => ({ profile, ...item }))
    );
  }, [parsed]);

  async function load(preferredId?: number) {
    const [nextOverview, portfolioOptions] = await Promise.all([
      investmentEvidencePolicyApi.overview(token),
      portfolioPlanningApi.portfolioOptions(token),
    ]);
    setOverview(nextOverview);
    setPortfolios(portfolioOptions);
    setPortfolioId((current) => current || Number(portfolioOptions[0]?.id || 0));
    const next =
      nextOverview.configurations.find((item) => item.id === preferredId) ||
      nextOverview.configurations.find((item) => item.status === "draft") ||
      nextOverview.configurations[0] ||
      null;
    setSelected(next);
    setContent(next ? JSON.stringify(next.content_json, null, 2) : "");
  }

  useEffect(() => {
    void load().catch((error) =>
      setMessage(error instanceof Error ? error.message : "Unable to load Investment Evidence Policy")
    );
  }, [token]);

  async function execute(action: "clone" | "save" | "publish") {
    if (!selected) return;
    try {
      let result = selected;
      if (action === "clone") result = await investmentEvidencePolicyApi.clone(token, selected);
      if (action === "save") {
        if (!parsed) throw new Error("Policy JSON is invalid.");
        result = await investmentEvidencePolicyApi.save(token, selected, parsed);
      }
      if (action === "publish") result = await investmentEvidencePolicyApi.publish(token, selected);
      await load(result.id);
      setPreview(null);
      setMessage(`Evidence policy ${action} completed.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Unable to ${action} evidence policy`);
    }
  }

  async function previewPolicy() {
    if (!selected || !parsed) return;
    try {
      const result = await investmentEvidencePolicyApi.preview(
        token,
        selected,
        portfolioId || null,
        gateProfile,
        parsed
      );
      setPreview(result);
      setSection("Preview");
      setMessage("Dry-run completed: persisted=false; no Preparation, Investment Decision or FID was created.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to preview evidence policy");
    }
  }

  function renderMatrix(rows: Array<EvidenceRequirement & { profile?: string }>) {
    return (
      <div className="evidencePolicyTableWrap">
        <table className="evidencePolicyTable">
          <thead>
            <tr>
              <th>Evidence</th>
              <th>Gate Profile</th>
              <th>Class</th>
              <th>Required / Blocking</th>
              <th>Provider</th>
              <th>Scope</th>
              <th>Validity</th>
              <th>Coverage</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((item, index) => (
              <tr key={`${item.profile || gateProfile}-${item.requirement_key}-${index}`}>
                <td>
                  <strong>{item.evidence_type.replace(/_/g, " ")}</strong>
                  <small>{item.rationale}</small>
                </td>
                <td>{item.profile || gateProfile}</td>
                <td>
                  <span className={`evidenceClass evidenceClass${item.classification}`}>
                    {classLabel(item.classification)}
                  </span>
                </td>
                <td>{item.required ? (item.blocking ? "Required · Blocking" : "Required · Warning") : "No"}</td>
                <td>{item.provider_key || "Controlled manual evidence"}</td>
                <td>{item.scope}</td>
                <td>{item.validity_period_days ? `${item.validity_period_days} days` : "Contextual"}</td>
                <td>{item.coverage_requirement == null ? "—" : `${item.coverage_requirement}%`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  function sectionContent() {
    if (!overview || !parsed) return <p>Loading controlled evidence policy…</p>;
    if (section === "Evidence Matrix") return renderMatrix(matrixRows);
    if (section === "Investment Gate Profiles") {
      return (
        <div className="evidencePolicyCards">
          {Object.entries(parsed.gate_profiles).map(([code, profile]) => (
            <article key={code}>
              <span>Investment Gate Profile</span>
              <h3>{code}</h3>
              <b>{profile.requirements.length} governed matrix rows</b>
              <p>Conditions: {profile.allow_valid_with_conditions ? "allowed by policy" : "not allowed"}</p>
            </article>
          ))}
        </div>
      );
    }
    if (section === "Project Type Overrides") {
      return (
        <div className="evidencePolicyTableWrap">
          <table className="evidencePolicyTable">
            <thead>
              <tr>
                <th>Profile</th>
                <th>Project Type</th>
                <th>Evidence</th>
                <th>Resolution</th>
                <th>Provider</th>
                <th>Rationale</th>
              </tr>
            </thead>
            <tbody>
              {parsed.project_type_overrides.map((item, index) => (
                <tr key={index}>
                  <td>{String(item.gate_profile_code)}</td>
                  <td>{String((item.project_type_filter as string[])?.join(", "))}</td>
                  <td>{String(item.evidence_type)}</td>
                  <td>{String(item.classification)}</td>
                  <td>{String(item.provider_key || "—")}</td>
                  <td>{String(item.rationale)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    if (section === "Provider Registry") {
      return (
        <div className="evidencePolicyTableWrap">
          <table className="evidencePolicyTable">
            <thead>
              <tr>
                <th>Evidence / Provider</th>
                <th>Source Module</th>
                <th>Contract</th>
                <th>Status</th>
                <th>Supported Scope</th>
                <th>Version</th>
                <th>Hash / Current / Readiness</th>
              </tr>
            </thead>
            <tbody>
              {overview.providers.map((item) => (
                <tr key={item.provider_key}>
                  <td>
                    <strong>{item.evidence_type}</strong>
                    <small>{item.provider_key}</small>
                  </td>
                  <td>{item.source_module}</td>
                  <td>{item.source_contract}</td>
                  <td>
                    <span className={`providerState ${item.status.toLowerCase()}`}>{item.status}</span>
                  </td>
                  <td>
                    {[
                      item.supports_portfolio_scope && "Portfolio",
                      item.supports_project_set_scope && "Project Set",
                      item.supports_project_scope && "Project",
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </td>
                  <td>{item.version}</td>
                  <td>
                    {item.supports_hash && item.supports_current_flag && item.supports_readiness
                      ? "Yes / Yes / Yes"
                      : "No / No / No"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    if (section === "Missing Providers") {
      const rows = preview?.missing_providers || overview.missing_providers;
      return (
        <div className="evidencePolicyTableWrap">
          <table className="evidencePolicyTable">
            <thead>
              <tr>
                <th>Evidence</th>
                <th>Gate Profile</th>
                <th>Project Type</th>
                <th>Provider</th>
                <th>Gap</th>
                <th>Recommended Action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((item, index) => (
                <tr key={`${item.gate_profile}-${item.evidence_type}-${index}`}>
                  <td>{item.evidence_type}</td>
                  <td>{item.gate_profile}</td>
                  <td>{item.project_type || "Base"}</td>
                  <td>{item.provider || "MISSING"}</td>
                  <td>{item.gap_status}</td>
                  <td>{item.recommended_action}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    if (section === "Preview") {
      if (!preview) return <p>Choose a Portfolio and Gate Profile, then run Preview.</p>;
      return (
        <>
          <div className="evidencePolicyCards">
            <article>
              <span>Persisted</span>
              <h3>{String(preview.persisted)}</h3>
            </article>
            <article>
              <span>Class A / B / C</span>
              <h3>{`${preview.class_A_count} / ${preview.class_B_count} / ${preview.class_C_count}`}</h3>
            </article>
            <article>
              <span>Missing required providers</span>
              <h3>{preview.missing_required_provider_count}</h3>
            </article>
            <article>
              <span>Gate 07J readiness</span>
              <h3>{preview.would_gate07j_be_ready ? "READY" : "BLOCKED"}</h3>
            </article>
          </div>
          <div className="evidencePolicyCallout danger">
            <strong>No silent fallback</strong>
            <span>{preview.blockers.join(" · ") || "No blocking provider gaps for this context."}</span>
          </div>
          {renderMatrix(preview.effective_matrix)}
          <details open className="evidencePolicyJson">
            <summary>Deterministic next-development decision</summary>
            <pre>{JSON.stringify(preview.recommended_next_development, null, 2)}</pre>
          </details>
        </>
      );
    }
    if (section === "History") {
      return (
        <div className="evidencePolicyHistory">
          {overview.configurations.map((item) => (
            <article key={item.id}>
              <b>Revision {item.revision}</b>
              <span>{item.status}</span>
              <code>{item.content_hash.slice(0, 18)}…</code>
            </article>
          ))}
        </div>
      );
    }
    const policyValue =
      section === "Validity"
        ? parsed.validity_policy
        : section === "Coverage"
          ? parsed.coverage_policy
          : section === "Blocking Policy"
            ? parsed.blocking_policy
            : parsed;
    return (
      <>
        {section === "Overview" ? (
          <div className="evidencePolicyCallout">
            <ShieldCheck size={20} />
            <div>
              <strong>A/B/C policy boundary</strong>
              <span>
                Class A requires an available governed provider. Class B requires controlled validated evidence. Class C
                never blocks.
              </span>
            </div>
          </div>
        ) : null}
        <details open className="evidencePolicyJson">
          <summary>{section === "Overview" ? "Controlled policy JSON" : `${section} policy`}</summary>
          {section === "Overview" ? (
            <textarea
              aria-label="Investment Decision Evidence Policy JSON"
              disabled={selected?.status !== "draft"}
              onChange={(event) => setContent(event.target.value)}
              rows={30}
              value={content}
            />
          ) : (
            <pre>{JSON.stringify(policyValue, null, 2)}</pre>
          )}
        </details>
      </>
    );
  }

  return (
    <section aria-label="Investment Decision Evidence Policy" className="investmentEvidencePolicy">
      <CompactModuleHeader
        description="Defines the contextual A/B/C evidence matrix required before a future Investment Decision. Gate 07J remains the owner of Preparation readiness; this policy never creates FID."
        eyebrow="ADMIN MODE · ENTERPRISE STRATEGY MANAGER · INVESTMENT GOVERNANCE · GATE 07J-EVID"
        metrics={[
          { label: "Policy revisions", value: overview?.configurations.length || 0 },
          { label: "Providers", value: overview?.providers.length || 0 },
          { label: "Blocking gaps", value: preview?.missing_required_provider_count ?? "Preview" },
        ]}
        title="Investment Decision Evidence Policy"
        tone="admin"
      />
      {message ? (
        <div className="evidencePolicyMessage" role="status">
          {message}
        </div>
      ) : null}
      <div className="evidencePolicyCommandBar">
        <label>
          Policy revision
          <select
            aria-label="Policy revision"
            value={selected?.id || 0}
            onChange={(event) => {
              const next = overview?.configurations.find((item) => item.id === Number(event.target.value)) || null;
              setSelected(next);
              setContent(next ? JSON.stringify(next.content_json, null, 2) : "");
              setPreview(null);
            }}
          >
            {(overview?.configurations || []).map((item) => (
              <option key={item.id} value={item.id}>{`rev ${item.revision} · ${item.status}`}</option>
            ))}
          </select>
        </label>
        <label>
          Portfolio
          <select
            aria-label="Evidence policy Portfolio"
            value={portfolioId}
            onChange={(event) => setPortfolioId(Number(event.target.value))}
          >
            <option value={0}>Configuration only</option>
            {portfolios.map((item) => (
              <option key={Number(item.id)} value={Number(item.id)}>
                {String(item.name)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Gate Profile
          <select
            aria-label="Investment Gate Profile"
            value={gateProfile}
            onChange={(event) => setGateProfile(event.target.value)}
          >
            <option value="PYP-INV-SELECT">PYP-INV-SELECT</option>
            <option value="PYP-FFA">PYP-FFA</option>
          </select>
        </label>
        <div aria-label="Evidence policy actions" className="evidencePolicyActions" role="group">
          <button
            disabled={!selected || selected.status !== "published"}
            onClick={() => void execute("clone")}
            type="button"
          >
            <Copy size={15} /> Clone DRAFT
          </button>
          <button disabled={!selected || !parsed} onClick={() => void previewPolicy()} type="button">
            <Eye size={15} /> Preview
          </button>
          <button
            disabled={!selected || selected.status !== "draft" || !parsed}
            onClick={() => void execute("save")}
            type="button"
          >
            <Save size={15} /> Save
          </button>
          <button
            disabled={!selected || selected.status !== "draft" || !parsed}
            onClick={() => void execute("publish")}
            type="button"
          >
            <Send size={15} /> Publish
          </button>
        </div>
      </div>
      <nav aria-label="Investment evidence policy sections" className="evidencePolicyTabs">
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
      <div className="evidencePolicySurface">
        <header>
          <div>
            <Database size={18} />
            <span>{section}</span>
          </div>
          <strong>{selected ? `rev ${selected.revision} · ${selected.status}` : "No policy"}</strong>
        </header>
        {sectionContent()}
      </div>
      <p className="evidencePolicyGuardrail">
        STOP boundary: no Risk, Permit, Contracting, Execution Plan, Schedule or Cost Estimate engine; no Investment
        Decision, FID, GO/HOLD/RECYCLE/KILL, Project activation or execution.
      </p>
    </section>
  );
}
