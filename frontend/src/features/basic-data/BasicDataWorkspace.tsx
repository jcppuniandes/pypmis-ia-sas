import { useCallback, useEffect, useRef, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { riskGovernanceApi, type JsonRecord } from "../risk-governance/policyApi";
import {
  basicDataApi,
  type BasicDataAssessment,
  type BasicDataItem,
  type BasicDataOptions,
  type BasicDataPage,
} from "./api";
import "../risk-governance/wave2b.css";

const views = [
  "Overview",
  "Requirements",
  "Basic Data Register",
  "Gaps",
  "Validation",
  "Readiness",
  "FEL / PDRI Context",
  "Evidence Sources",
  "History",
] as const;
type View = (typeof views)[number];
const emptyPage = <T,>(): BasicDataPage<T> => ({ items: [], total: 0, page: 1, page_size: 25 });
const record = (value: unknown): JsonRecord =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as JsonRecord) : {};
const rows = (value: unknown): JsonRecord[] => (Array.isArray(value) ? value.map(record) : []);
const newItem = (): JsonRecord => ({
  requirement_code: "",
  availability: "AVAILABLE",
  quality: "PRELIMINARY",
  confidence: "PRELIMINARY",
  source_type: "REFERENCE",
  source_reference: "",
  source_version: "",
  source_hash: "",
  source_date: "",
  expires_on: "",
  source_current: true,
  limitations: "",
  assumptions: "",
  gaps: "",
  comments: "",
});

export default function BasicDataWorkspace({ token }: { token: string }) {
  const [options, setOptions] = useState<BasicDataOptions | null>(null);
  const [projectId, setProjectId] = useState(0);
  const [projectSearch, setProjectSearch] = useState("");
  const [view, setView] = useState<View>("Overview");
  const [requirements, setRequirements] = useState<JsonRecord>({});
  const [items, setItems] = useState(emptyPage<BasicDataItem>());
  const [assessments, setAssessments] = useState(emptyPage<BasicDataAssessment>());
  const [selected, setSelected] = useState<BasicDataAssessment | null>(null);
  const [readiness, setReadiness] = useState<JsonRecord>({});
  const [riskContext, setRiskContext] = useState<JsonRecord | null>(null);
  const [preview, setPreview] = useState<JsonRecord | null>(null);
  const [form, setForm] = useState<JsonRecord>(newItem);
  const [editing, setEditing] = useState<BasicDataItem | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  const actions = Array.isArray(requirements.allowed_actions)
    ? requirements.allowed_actions.map(String)
    : (options?.allowed_actions ?? []);
  const allowed = (action: string) =>
    actions.includes(action) || actions.includes(`basic_data.${action.replace(/_/g, ".")}`);
  const allowedFor = (entity: JsonRecord, action: string) =>
    Array.isArray(entity.allowed_actions) ? entity.allowed_actions.includes(action) : allowed(action);
  const load = useCallback(
    async (id: number, itemPage = 1, assessmentPage = 1, preferredId?: number) => {
      const currentGeneration = ++generation.current;
      const [rules, itemResults, history, current, risk] = await Promise.all([
        basicDataApi.requirements(token, id),
        basicDataApi.items(token, id, itemPage),
        basicDataApi.assessments(token, id, assessmentPage),
        basicDataApi.currentReadiness(token, id),
        riskGovernanceApi
          .effective(token, id)
          .catch((error: Error) => ({ status: "UNAVAILABLE", warnings: [error.message] })),
      ]);
      if (currentGeneration !== generation.current) return;
      setProjectId(id);
      setRequirements(rules);
      setItems(itemResults);
      setAssessments(history);
      setReadiness(current);
      setRiskContext(risk);
      setSelected(
        (previous) =>
          history.items.find((item) => item.id === (preferredId ?? previous?.id)) ?? history.items[0] ?? null
      );
      setFormOpen(false);
      setPreview(null);
    },
    [token]
  );
  useEffect(() => {
    let live = true;
    void basicDataApi
      .options(token)
      .then(async (next) => {
        if (!live) return;
        setOptions(next);
        if (next.projects[0]) await load(next.projects[0].id);
      })
      .catch((error: Error) => {
        if (live) setMessage(error.message);
      });
    return () => {
      live = false;
      generation.current += 1;
    };
  }, [load, token]);
  async function execute(work: () => Promise<unknown>, success: string) {
    setBusy(true);
    setMessage("");
    try {
      await work();
      setMessage(success);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Basic Data operation failed.");
    } finally {
      setBusy(false);
    }
  }
  function editItem(item?: BasicDataItem) {
    setEditing(item ?? null);
    setForm(
      item
        ? { ...item }
        : {
            ...newItem(),
            quality: options?.quality_values[0] ?? "PRELIMINARY",
            confidence: options?.confidence_values[0] ?? "PRELIMINARY",
            requirement_code: String(rows(requirements.requirements)[0]?.requirement_code ?? ""),
          }
    );
    setFormOpen(true);
  }
  async function saveItem() {
    const reference = String(form.source_reference ?? "");
    const editable = Object.fromEntries(
      Object.keys(newItem())
        .filter((key) => !editing || key !== "requirement_code")
        .map((key) => [key, form[key]])
    );
    const body = {
      ...editable,
      source_date: form.source_date || null,
      expires_on: form.expires_on || null,
      source_hash: form.source_hash || null,
      source_version: form.source_version || null,
      evidence_refs: reference
        ? [
            {
              source_type: form.source_type,
              source_reference: reference,
              source_version: form.source_version || null,
              source_hash: form.source_hash || null,
            },
          ]
        : [],
    };
    if (editing) await basicDataApi.updateItem(token, editing, body);
    else await basicDataApi.createItem(token, projectId, body);
    await load(projectId, items.page, assessments.page);
  }
  async function assessmentAction(action: "preview" | "submit" | "complete" | "refresh-apply") {
    if (!selected) return;
    const result = await basicDataApi.assessmentAction(token, selected, action);
    if (action === "preview") {
      setPreview(result);
      return;
    }
    await load(projectId, items.page, assessments.page, Number(result.id) || selected.id);
  }
  const requirementRows = rows(requirements.requirements);
  const context = record(requirements.context);
  const coverage = record(readiness.coverage);
  return (
    <section className="wave2b" aria-label="Basic Data Readiness workspace">
      <CompactModuleHeader
        title="Basic Data Readiness"
        eyebrow="USER MODE / Business Case & Investment Development"
        description="Govern technical input availability, validation, quality, confidence and freshness. Basic Data does not change FEL, PDRI, Risk, Business Case, Gate or FID."
        tone="user"
        metrics={[
          { label: "Readiness", value: String(readiness.status ?? "NOT_STARTED") },
          { label: "Exact coverage", value: `${coverage.satisfied ?? 0}/${coverage.required ?? 0}` },
          { label: "FEL context", value: String(context.fel_stage ?? "NOT_STARTED") },
        ]}
      />
      {message ? (
        <p role="status" className="wave2bMessage">
          {message}
        </p>
      ) : null}
      <div className="wave2bToolbar">
        <label>
          Find authorized Projects
          <input
            aria-label="Find authorized Projects"
            value={projectSearch}
            onChange={(event) => setProjectSearch(event.target.value)}
          />
        </label>
        <button
          disabled={busy}
          onClick={() =>
            void execute(async () => {
              const next = await basicDataApi.options(token, projectSearch);
              setOptions(next);
              if (next.projects[0]) await load(next.projects[0].id);
            }, "Authorized Project search completed.")
          }
          type="button"
        >
          Search Projects
        </button>
        <label>
          Project Workspace
          <select
            aria-label="Project Workspace"
            value={projectId}
            disabled={busy}
            onChange={(event) => void execute(() => load(Number(event.target.value)), "Project context loaded.")}
          >
            {!options?.projects.length ? <option value="0">No authorized Project Workspaces</option> : null}
            {options?.projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.code} · {project.name}
              </option>
            ))}
          </select>
        </label>
        {options?.project_total != null ? (
          <span>
            {options.project_total} authorized Projects · page {options.page ?? 1}
          </span>
        ) : null}
        {options && (options.project_total ?? 0) > (options.page_size ?? 100) ? (
          <>
            <button
              disabled={busy || (options.page ?? 1) <= 1}
              onClick={() =>
                void execute(async () => {
                  const next = await basicDataApi.options(token, projectSearch, (options.page ?? 1) - 1);
                  setOptions(next);
                  if (next.projects[0]) await load(next.projects[0].id);
                }, "Previous authorized Project page loaded.")
              }
              type="button"
            >
              Previous Projects
            </button>
            <button
              disabled={busy || (options.page ?? 1) * (options.page_size ?? 100) >= (options.project_total ?? 0)}
              onClick={() =>
                void execute(async () => {
                  const next = await basicDataApi.options(token, projectSearch, (options.page ?? 1) + 1);
                  setOptions(next);
                  if (next.projects[0]) await load(next.projects[0].id);
                }, "Next authorized Project page loaded.")
              }
              type="button"
            >
              Next Projects
            </button>
          </>
        ) : null}
        <button
          disabled={!projectId || busy}
          onClick={() =>
            void execute(
              () => load(projectId, items.page, assessments.page),
              "Current readiness refreshed without changing historical assessments."
            )
          }
          type="button"
        >
          Refresh current context
        </button>
      </div>
      <nav className="wave2bTabs" aria-label="Basic Data views">
        {views.map((label) => (
          <button
            aria-current={view === label ? "page" : undefined}
            key={label}
            onClick={() => setView(label)}
            type="button"
          >
            {label}
          </button>
        ))}
      </nav>
      {view === "Overview" || view === "Readiness" ? (
        <article aria-label="Basic Data readiness summary">
          <h3>OVERALL_BASIC_DATA_READINESS · {String(readiness.status ?? "NOT_STARTED")}</h3>
          <p>
            Coverage {String(coverage.satisfied ?? 0)} satisfied / {String(coverage.required ?? 0)} required ·{" "}
            {String(coverage.partial ?? 0)} partial · {String(coverage.missing ?? 0)} missing ·{" "}
            {String(coverage.percentage ?? 0)}%
          </p>
          <p>source_current={String(readiness.source_current ?? false)}</p>
          <pre>
            {JSON.stringify(
              {
                dimensions: readiness.dimensions,
                quality: readiness.quality_summary,
                confidence: readiness.confidence_summary,
                warnings: readiness.warnings,
                blockers: readiness.blockers,
              },
              null,
              2
            )}
          </pre>
        </article>
      ) : null}
      {view === "Requirements" ? (
        <article>
          <h3>Effective requirements · exact denominator {requirementRows.length}</h3>
          <p>
            Configuration revision {String(record(requirements.configuration).revision ?? "—")} · backend-owned
            applicability / inheritance
          </p>
          <div className="wave2bTableScroll">
            <table>
              <thead>
                <tr>
                  <th>Requirement</th>
                  <th>Category</th>
                  <th>Minimum validation / quality / confidence</th>
                  <th>Freshness</th>
                  <th>Blocking</th>
                </tr>
              </thead>
              <tbody>
                {requirementRows.map((row) => (
                  <tr key={String(row.requirement_code)}>
                    <td>
                      {String(row.requirement_code)} · {String(row.name)}
                    </td>
                    <td>{String(row.category)}</td>
                    <td>
                      {String(row.minimum_validation_state)} / {String(row.minimum_quality)} /{" "}
                      {String(row.minimum_confidence)}
                    </td>
                    <td>{String(row.max_age_days ?? "Policy-specific")}</td>
                    <td>{String(row.blocking)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      ) : null}
      {view === "Gaps" ? (
        <article>
          <h3>Critical gaps and blockers</h3>
          <pre>
            {JSON.stringify(
              { critical_gaps: readiness.critical_gaps, blockers: readiness.blockers, warnings: readiness.warnings },
              null,
              2
            )}
          </pre>
          <p>
            One critical gap can block Basic Data regardless of aggregate coverage. No external domain is automatically
            blocked.
          </p>
        </article>
      ) : null}
      {view === "FEL / PDRI Context" ? (
        <article>
          <h3>Read-only FEL / PDRI Context</h3>
          <pre>{JSON.stringify(context, null, 2)}</pre>
          <p>
            FEL stage and PDRI score/hash are references only. Basic Data never recalculates or writes Definition
            Maturity.
          </p>
        </article>
      ) : null}
      {view === "Overview" || view === "FEL / PDRI Context" ? (
        <article aria-label="Effective Risk Governance Context">
          <h3>Effective Risk Governance Context — read-only</h3>
          <pre>{JSON.stringify(riskContext, null, 2)}</pre>
          <p>Enterprise Capacity / Appetite / Threshold policy is not Risk Readiness or QRA.</p>
        </article>
      ) : null}
      {["Basic Data Register", "Validation", "Evidence Sources"].includes(view) ? (
        <article>
          <h3>{view}</h3>
          {view === "Basic Data Register" && allowed("item_create") ? (
            <button disabled={busy || !projectId} onClick={() => editItem()} type="button">
              Add Basic Data item
            </button>
          ) : null}
          <div className="wave2bTableScroll">
            <table>
              <thead>
                <tr>
                  <th>Requirement</th>
                  <th>Availability / Validation</th>
                  <th>Quality / Confidence</th>
                  <th>Evidence lineage</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.items.map((item) => (
                  <tr key={item.id}>
                    <td>{item.requirement_code}</td>
                    <td>
                      {item.availability} / {item.validation_state}
                    </td>
                    <td>
                      {item.quality} / {item.confidence}
                    </td>
                    <td>
                      {item.source_reference ?? "No source reference"}
                      <small>
                        {" "}
                        · version {String(item.source_version ?? "—")} · {String(item.source_date ?? "—")}
                      </small>
                    </td>
                    <td>
                      {allowedFor(item, "item_edit") ? (
                        <button disabled={busy} onClick={() => editItem(item)} type="button">
                          Edit {item.requirement_code}
                        </button>
                      ) : null}
                      {allowedFor(item, "item_validate") ? (
                        <>
                          <button
                            disabled={busy}
                            onClick={() =>
                              void execute(async () => {
                                await basicDataApi.validateItem(token, item);
                                await load(projectId, items.page, assessments.page);
                              }, "Item validation recorded with reviewer metadata.")
                            }
                            type="button"
                          >
                            Validate {item.requirement_code}
                          </button>
                          <button
                            disabled={busy}
                            onClick={() =>
                              void execute(async () => {
                                await basicDataApi.validateItem(token, item, "REJECTED");
                                await load(projectId, items.page, assessments.page);
                              }, "Item rejected.")
                            }
                            type="button"
                          >
                            Reject {item.requirement_code}
                          </button>
                        </>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            page={items.page}
            total={items.total}
            size={items.page_size}
            disabled={busy}
            onChange={(page) => void execute(() => load(projectId, page, assessments.page), "Item page loaded.")}
          />
        </article>
      ) : null}
      {formOpen ? (
        <article aria-label="Basic Data item editor">
          <h3>{editing ? "Edit" : "Add"} technical evidence metadata</h3>
          <div className="wave2bForm">
            <label>
              Requirement
              <select
                aria-label="Requirement"
                value={String(form.requirement_code)}
                disabled={Boolean(editing)}
                onChange={(event) => setForm({ ...form, requirement_code: event.target.value })}
              >
                {requirementRows.map((row) => (
                  <option key={String(row.requirement_code)} value={String(row.requirement_code)}>
                    {String(row.requirement_code)} · {String(row.name)}
                  </option>
                ))}
              </select>
            </label>
            {(
              [
                ["availability", "Availability", options?.availability_values ?? []],
                ["quality", "Quality", options?.quality_values ?? []],
                ["confidence", "Confidence", options?.confidence_values ?? []],
              ] as const
            ).map(([key, label, values]) => (
              <label key={key}>
                {label}
                <select
                  aria-label={label}
                  value={String(form[key])}
                  onChange={(event) => setForm({ ...form, [key]: event.target.value })}
                >
                  {values.map((value) => (
                    <option key={value}>{value}</option>
                  ))}
                </select>
              </label>
            ))}
            {(
              [
                ["source_type", "Source type"],
                ["source_reference", "Evidence reference"],
                ["source_version", "Source version"],
                ["source_hash", "Source hash"],
                ["source_date", "Source date"],
                ["expires_on", "Expiry date"],
                ["limitations", "Limitations"],
                ["assumptions", "Assumptions"],
                ["gaps", "Gaps"],
                ["comments", "Comments"],
              ] as const
            ).map(([key, label]) => (
              <label key={key}>
                {label}
                <input
                  aria-label={label}
                  type={key === "source_date" || key === "expires_on" ? "date" : "text"}
                  value={String(form[key] ?? "")}
                  onChange={(event) => setForm({ ...form, [key]: event.target.value })}
                />
              </label>
            ))}
          </div>
          <p>References only — no binary documents. Validation is a separate permission-governed operation.</p>
          <div className="wave2bToolbar">
            <button disabled={busy} onClick={() => void execute(saveItem, "Basic Data item saved.")} type="button">
              Save Basic Data item
            </button>
            <button onClick={() => setFormOpen(false)} type="button">
              Cancel item edit
            </button>
          </div>
        </article>
      ) : null}
      {view === "Overview" || view === "Readiness" || view === "History" ? (
        <article aria-label="Basic Data assessment history">
          <h3>Assessment history</h3>
          {allowed("assessment_create") ? (
            <button
              disabled={busy || !projectId}
              onClick={() =>
                void execute(async () => {
                  const result = await basicDataApi.createAssessment(token, projectId);
                  await load(projectId, items.page, 1, result.id);
                }, "DRAFT assessment created using governed numbering.")
              }
              type="button"
            >
              Create readiness assessment
            </button>
          ) : null}
          <label>
            Assessment
            <select
              aria-label="Assessment"
              value={selected?.id ?? ""}
              onChange={(event) => {
                setSelected(assessments.items.find((item) => item.id === Number(event.target.value)) ?? null);
                setPreview(null);
              }}
            >
              {!assessments.items.length ? <option value="">No assessments</option> : null}
              {assessments.items.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.assessment_number} · version {item.assessment_version} · {item.status}
                </option>
              ))}
            </select>
          </label>
          {selected ? (
            <>
              <p>
                <strong>
                  {selected.assessment_number} · {selected.status}
                </strong>{" "}
                · hash {selected.assessment_hash ?? "Not completed"}
              </p>
              <div className="wave2bToolbar">
                <button
                  disabled={busy}
                  onClick={() => void execute(() => assessmentAction("preview"), "Assessment preview persisted=false.")}
                  type="button"
                >
                  Preview assessment
                </button>
                {selected.status === "DRAFT" && allowedFor(selected, "assessment_submit") ? (
                  <button
                    disabled={busy}
                    onClick={() =>
                      void execute(() => assessmentAction("submit"), "Assessment submitted for independent review.")
                    }
                    type="button"
                  >
                    Submit assessment
                  </button>
                ) : null}
                {selected.status === "IN_REVIEW" && allowedFor(selected, "assessment_complete") ? (
                  <button
                    disabled={busy}
                    onClick={() =>
                      void execute(() => assessmentAction("complete"), "COMPLETED immutable assessment preserved.")
                    }
                    type="button"
                  >
                    Complete assessment
                  </button>
                ) : null}
                {selected.status === "COMPLETED" ? (
                  <>
                    <button
                      disabled={busy}
                      onClick={() =>
                        void execute(
                          async () => setPreview(await basicDataApi.refreshPreview(token, selected.id)),
                          "Refresh preview persisted=false; historical snapshot unchanged."
                        )
                      }
                      type="button"
                    >
                      Refresh Preview
                    </button>
                    {allowedFor(selected, "assessment_create") ? (
                      <button
                        disabled={busy}
                        onClick={() =>
                          void execute(
                            () => assessmentAction("refresh-apply"),
                            "Successor DRAFT created; historical snapshot unchanged."
                          )
                        }
                        type="button"
                      >
                        Apply successor DRAFT
                      </button>
                    ) : null}
                  </>
                ) : null}
              </div>
              <details>
                <summary>Frozen assessment snapshot and source lineage</summary>
                <pre>{JSON.stringify(selected.snapshot_json, null, 2)}</pre>
              </details>
            </>
          ) : null}
          {preview ? (
            <article aria-label="Basic Data assessment preview">
              <strong>persisted={String(preview.persisted)}</strong>
              <pre>{JSON.stringify(preview, null, 2)}</pre>
            </article>
          ) : null}
          <Pagination
            page={assessments.page}
            total={assessments.total}
            size={assessments.page_size}
            disabled={busy}
            onChange={(page) =>
              void execute(() => load(projectId, items.page, page), "Assessment history page loaded.")
            }
          />
        </article>
      ) : null}
    </section>
  );
}
function Pagination({
  page,
  total,
  size,
  disabled,
  onChange,
}: {
  page: number;
  total: number;
  size: number;
  disabled: boolean;
  onChange: (page: number) => void;
}) {
  return (
    <div className="wave2bToolbar">
      <button disabled={disabled || page <= 1} onClick={() => onChange(page - 1)} type="button">
        Previous page
      </button>
      <span>
        Page {page} · {total} records
      </span>
      <button disabled={disabled || page * size >= total} onClick={() => onChange(page + 1)} type="button">
        Next page
      </button>
    </div>
  );
}
