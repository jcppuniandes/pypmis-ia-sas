/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { Copy, Eye, Save, Send } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { portfolioPlanningApi } from "../portfolio-planning/api";
import { permitReadinessApi } from "./api";
import "./permitReadiness.css";
import type { PermitConfiguration } from "./types";

const TABS = [
  "Configuration Overview",
  "Permit Types",
  "Requirement Catalog",
  "Project Type Applicability",
  "Geography Applicability",
  "Gate Profile Rules",
  "Permit Status Rules",
  "Condition Rules",
  "Evidence Rules",
  "Validity / Expiry",
  "Renewal Rules",
  "Readiness Criteria",
  "Project Set Coverage",
  "Provider Contract",
  "Inheritance / Overrides",
  "Segregation of Duties",
  "Versioning / Publish",
] as const;

function parse(value: string) {
  try {
    return JSON.parse(value) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export default function PermitReadinessAdminView({ token }: { token: string }) {
  const [records, setRecords] = useState<PermitConfiguration[]>([]);
  const [selected, setSelected] = useState<PermitConfiguration | null>(null);
  const [content, setContent] = useState("");
  const [tab, setTab] = useState<(typeof TABS)[number]>(TABS[0]);
  const [portfolios, setPortfolios] = useState<Array<Record<string, unknown>>>([]);
  const [portfolioId, setPortfolioId] = useState(0);
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [message, setMessage] = useState("");
  const parsed = useMemo(() => parse(content), [content]);

  async function load(preferredId?: number) {
    const [items, options] = await Promise.all([
      permitReadinessApi.configurations(token),
      portfolioPlanningApi.portfolioOptions(token),
    ]);
    const next =
      items.find((item) => item.id === preferredId) ||
      items.find((item) => item.status === "draft") ||
      items[0] ||
      null;
    setRecords(items);
    setSelected(next);
    setContent(next ? JSON.stringify(next.content_json, null, 2) : "");
    setPortfolios(options);
    setPortfolioId((current) => current || Number(options[0]?.id || 0));
  }

  useEffect(() => {
    void load().catch((error) => setMessage(error instanceof Error ? error.message : "Unable to load configuration"));
  }, [token]);

  function patchValue(key: string, value: unknown) {
    if (parsed) setContent(JSON.stringify({ ...parsed, [key]: value }, null, 2));
  }

  async function execute(action: "clone" | "save" | "publish") {
    if (!selected) return;
    try {
      let result = selected;
      if (action === "clone") result = await permitReadinessApi.cloneConfiguration(token, selected);
      if (action === "save") {
        if (!parsed) throw new Error("Configuration JSON is invalid.");
        result = await permitReadinessApi.updateConfiguration(token, selected, parsed);
      }
      if (action === "publish") result = await permitReadinessApi.publishConfiguration(token, selected);
      await load(result.id);
      setMessage(`Permit Readiness configuration ${action} completed.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Unable to ${action} configuration`);
    }
  }

  async function dryRun() {
    if (!selected || !parsed) return;
    try {
      setPreview(await permitReadinessApi.previewConfiguration(token, selected, parsed, portfolioId));
      setMessage("Dry-run completed: persisted=false; no permit, condition or assessment was created.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to run preview");
    }
  }

  const permitTypes = Array.isArray(parsed?.permit_types)
    ? (parsed?.permit_types as Array<Record<string, unknown>>)
    : [];
  const requirements = Array.isArray(parsed?.requirements)
    ? (parsed?.requirements as Array<Record<string, unknown>>)
    : [];

  return (
    <section aria-label="Permit Readiness Configuration" className="permitReadiness permitAdmin">
      <CompactModuleHeader
        description="Controls the permit catalog, contextual applicability, qualifying statuses, conditions, evidence, validity, inheritance and the governed Gate 07J provider. The starter remains DRAFT until explicitly published."
        eyebrow="ADMIN MODE · INVESTMENT GOVERNANCE · GATE 07J-PERMIT"
        metrics={[
          { label: "Revisions", value: records.length },
          { label: "Permit types", value: permitTypes.length },
          { label: "Requirements", value: requirements.length },
        ]}
        title="Permit Readiness Configuration"
        tone="admin"
      />
      {message ? (
        <div className="permitMessage" role="status">
          {message}
        </div>
      ) : null}
      <nav aria-label="Permit Readiness configuration sections" className="permitAdminTabs">
        {TABS.map((item) => (
          <button className={tab === item ? "active" : ""} key={item} onClick={() => setTab(item)} type="button">
            {item}
          </button>
        ))}
      </nav>
      <div className="permitAdminGrid">
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
              <strong>{item.name}</strong>
              <span>
                {item.status} · rev {item.revision}
              </span>
            </button>
          ))}
        </aside>
        <article className="permitSurface">
          <header>
            <div>
              <span>{tab}</span>
              <h3>{selected?.name || "No configuration"}</h3>
            </div>
            <span className="permitStatus">{selected?.status || "none"}</span>
          </header>
          {tab === "Configuration Overview" ? (
            <div className="permitPolicyGrid">
              <Policy label="Code" value={String(parsed?.configuration_code || "—")} />
              <Policy label="Governance model" value="CAPITAL_OWNER" />
              <Policy label="Final output" value="READY_FOR_GOVERNED_PERMIT_EVIDENCE" />
              <Policy label="Provider" value="PERMIT_READINESS_PROVIDER" />
            </div>
          ) : null}
          {tab === "Permit Types" ? (
            <ConfigTable rows={permitTypes} columns={["code", "name", "authority_type"]} />
          ) : null}
          {tab === "Requirement Catalog" ||
          tab === "Project Type Applicability" ||
          tab === "Geography Applicability" ||
          tab === "Gate Profile Rules" ? (
            <ConfigTable
              rows={requirements}
              columns={[
                "requirement_key",
                "permit_type_code",
                "applicable_project_types",
                "applicable_geographies",
                "applicable_gate_profiles",
                "blocking",
              ]}
            />
          ) : null}
          {tab === "Permit Status Rules" ? <JsonValue value={parsed?.qualifying_statuses} /> : null}
          {tab === "Condition Rules" ? (
            <SelectRule
              disabled={selected?.status !== "draft"}
              label="Condition policy"
              value={String(parsed?.condition_policy || "BLOCK_ONLY_ON_BLOCKING_CONDITIONS")}
              options={[
                "ALLOW_NON_BLOCKING_CONDITIONS",
                "BLOCK_ON_ANY_OPEN_CONDITION",
                "BLOCK_ONLY_ON_BLOCKING_CONDITIONS",
              ]}
              onChange={(value) => patchValue("condition_policy", value)}
            />
          ) : null}
          {tab === "Evidence Rules" ? (
            <NumberRule
              disabled={selected?.status !== "draft"}
              label="Evidence coverage %"
              value={Number(parsed?.evidence_coverage_percent || 100)}
              onChange={(value) => patchValue("evidence_coverage_percent", value)}
            />
          ) : null}
          {tab === "Validity / Expiry" || tab === "Renewal Rules" ? (
            <NumberRule
              disabled={selected?.status !== "draft"}
              label="Assessment validity days"
              value={Number(parsed?.validity_days || 180)}
              onChange={(value) => patchValue("validity_days", value)}
            />
          ) : null}
          {tab === "Readiness Criteria" ? (
            <JsonValue
              value={{
                evidence_coverage_percent: parsed?.evidence_coverage_percent,
                qualifying_statuses: parsed?.qualifying_statuses,
                condition_policy: parsed?.condition_policy,
              }}
            />
          ) : null}
          {tab === "Project Set Coverage" ? (
            <NumberRule
              disabled={selected?.status !== "draft"}
              label="Contextual Class A Project coverage %"
              value={Number(parsed?.class_a_project_coverage_percent || 100)}
              onChange={(value) => patchValue("class_a_project_coverage_percent", value)}
            />
          ) : null}
          {tab === "Provider Contract" ? (
            <div className="permitPolicyGrid">
              <Policy label="Status" value="AVAILABLE" />
              <Policy label="Source" value="PERMIT_READINESS" />
              <Policy label="Scope" value="PROJECT / PROJECT_SET" />
              <Policy label="FID authority" value="FALSE" />
            </div>
          ) : null}
          {tab === "Inheritance / Overrides" ? (
            <JsonValue value={{ inheritance: parsed?.inheritance, scope_workspace_id: parsed?.scope_workspace_id }} />
          ) : null}
          {tab === "Segregation of Duties" ? <JsonValue value={parsed?.separation_of_duties} /> : null}
          {tab === "Versioning / Publish" ? (
            <div className="permitPublish">
              <p>
                Published revisions are immutable. Clone to create an editable DRAFT, validate with dry-run, then
                publish with ETag protection.
              </p>
              <code>{selected?.content_hash || "—"}</code>
            </div>
          ) : null}
          <details className="permitJson">
            <summary>Advanced JSON editor</summary>
            <textarea
              disabled={selected?.status !== "draft"}
              onChange={(event) => setContent(event.target.value)}
              rows={20}
              value={content}
            />
          </details>
          <div className="permitAdminActions">
            <button onClick={() => execute("clone")} type="button">
              <Copy size={15} /> Clone
            </button>
            <button disabled={selected?.status !== "draft" || !parsed} onClick={() => execute("save")} type="button">
              <Save size={15} /> Save
            </button>
            <button disabled={!parsed} onClick={dryRun} type="button">
              <Eye size={15} /> Dry-run
            </button>
            <button disabled={selected?.status !== "draft" || !parsed} onClick={() => execute("publish")} type="button">
              <Send size={15} /> Publish
            </button>
            <select value={portfolioId} onChange={(event) => setPortfolioId(Number(event.target.value))}>
              {portfolios.map((item) => (
                <option key={Number(item.id)} value={Number(item.id)}>
                  {String(item.name)}
                </option>
              ))}
            </select>
          </div>
          {preview ? (
            <details className="permitJson" open>
              <summary>Non-persistent preview</summary>
              <pre>{JSON.stringify(preview, null, 2)}</pre>
            </details>
          ) : null}
        </article>
      </div>
    </section>
  );
}

function Policy({ label, value }: { label: string; value: string }) {
  return (
    <article>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}
function JsonValue({ value }: { value: unknown }) {
  return <pre className="permitConfigPre">{JSON.stringify(value, null, 2)}</pre>;
}
function ConfigTable({ rows, columns }: { rows: Array<Record<string, unknown>>; columns: string[] }) {
  return (
    <table>
      <thead>
        <tr>
          {columns.map((item) => (
            <th key={item}>{item.split("_").join(" ")}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, index) => (
          <tr key={String(row.requirement_key || row.code || index)}>
            {columns.map((column) => (
              <td key={column}>
                {Array.isArray(row[column]) ? (row[column] as unknown[]).join(", ") : String(row[column] ?? "—")}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
function NumberRule({
  disabled,
  label,
  value,
  onChange,
}: {
  disabled: boolean;
  label: string;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="permitRule">
      {label}
      <input
        disabled={disabled}
        max={3650}
        min={0}
        type="number"
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}
function SelectRule({
  disabled,
  label,
  value,
  options,
  onChange,
}: {
  disabled: boolean;
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="permitRule">
      {label}
      <select disabled={disabled} value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((item) => (
          <option key={item}>{item}</option>
        ))}
      </select>
    </label>
  );
}
