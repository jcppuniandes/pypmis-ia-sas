import { useCallback, useEffect, useRef, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import type { JsonRecord } from "../risk-governance/policyApi";
import {
  ownerCapabilityApi,
  type OwnerCapabilityAssessment,
  type OwnerCapabilityOptions,
  type OwnerCapabilityPage,
} from "./api";
import "../risk-governance/wave2b.css";
import "./ownerCapability.css";

const views = [
  "Overview",
  "Requirements",
  "Capability Assessment",
  "Dimension Summary",
  "Gaps",
  "Mitigation Plan",
  "Evidence",
  "Resource Context",
  "Commercial Context",
  "FEL / PDRI Context",
  "Readiness",
  "History",
] as const;
type View = (typeof views)[number];
type Editor = "item" | "gap" | "mitigation";
type ScaleLabels = Record<string, { name: string; description: string }>;
const record = (value: unknown): JsonRecord =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as JsonRecord) : {};
const rows = (value: unknown): JsonRecord[] => (Array.isArray(value) ? value.map(record) : []);
const value = (input: unknown, fallback = "—") => (input == null || input === "" ? fallback : String(input));
const scaleRows = (scale: unknown): JsonRecord[] =>
  Array.isArray(scale)
    ? scale
        .map((item: unknown, index) => (typeof item === "string" ? { code: item, order: index } : record(item)))
        .sort((left, right) => Number(left.order ?? 0) - Number(right.order ?? 0))
    : [];
const scaleValues = (scale: unknown): string[] =>
  scaleRows(scale)
    .map((item) => String(item.code ?? item.value ?? item.label ?? ""))
    .filter(Boolean);
const scaleLabels = (scale: unknown): ScaleLabels =>
  Object.fromEntries(
    scaleRows(scale).map((item) => [
      String(item.code ?? item.value ?? item.label ?? ""),
      { name: String(item.name ?? item.label ?? item.code ?? ""), description: String(item.description ?? "") },
    ])
  );
const emptyPage = (): OwnerCapabilityPage<OwnerCapabilityAssessment> => ({
  items: [],
  total: 0,
  page: 1,
  page_size: 25,
});
const itemKeys = [
  "requirement_code",
  "current_maturity",
  "evidence_quality",
  "confidence",
  "capability_source",
  "rationale",
  "evidence_refs",
  "source_current",
  "source_date",
  "expires_on",
  "source_hash",
  "source_version",
  "responsible_function",
  "role_refs",
  "related_risk_ids",
  "review_notes",
];
const gapKeys = [
  "requirement_code",
  "description",
  "severity",
  "blocking",
  "owner",
  "target_date",
  "status",
  "closure_evidence",
];
const mitigationKeys = [
  "requirement_code",
  "approach",
  "description",
  "owner",
  "target_date",
  "status",
  "closure_evidence",
  "evidence_refs",
];
const pick = (row: JsonRecord, keys: string[]) =>
  Object.fromEntries(keys.filter((key) => row[key] !== undefined).map((key) => [key, row[key]]));
function aggregateBody(assessment: OwnerCapabilityAssessment) {
  return {
    title: String(assessment.title ?? "Owner Capability Readiness"),
    comments: String(assessment.comments ?? ""),
    items: rows(assessment.aggregate_json?.items).map((row) => pick(row, itemKeys)),
    gaps: rows(assessment.aggregate_json?.gaps).map((row) => pick(row, gapKeys)),
    mitigations: rows(assessment.aggregate_json?.mitigations).map((row) => pick(row, mitigationKeys)),
  };
}

export default function OwnerCapabilityWorkspace({ token }: { token: string }) {
  const [options, setOptions] = useState<OwnerCapabilityOptions | null>(null);
  const [projectId, setProjectId] = useState(0);
  const [search, setSearch] = useState("");
  const [view, setView] = useState<View>("Overview");
  const [requirements, setRequirements] = useState<JsonRecord>({});
  const [contexts, setContexts] = useState<JsonRecord>({});
  const [history, setHistory] = useState(emptyPage);
  const [selected, setSelected] = useState<OwnerCapabilityAssessment | null>(null);
  const [readiness, setReadiness] = useState<JsonRecord>({});
  const [preview, setPreview] = useState<JsonRecord | null>(null);
  const [editor, setEditor] = useState<Editor | null>(null);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [form, setForm] = useState<JsonRecord>({});
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [rowPage, setRowPage] = useState(1);
  const generation = useRef(0);
  const projectActions = Array.isArray(requirements.allowed_actions)
    ? requirements.allowed_actions.map(String)
    : (options?.allowed_actions ?? []);
  const allowed = (action: string, entity?: JsonRecord) => {
    const actions =
      entity && Array.isArray(entity.allowed_actions) ? entity.allowed_actions.map(String) : projectActions;
    return actions.includes(action) || actions.includes(`owner_capability.${action.replace(/_/g, ".")}`);
  };
  const load = useCallback(
    async (id: number, page = 1, preferredId?: number) => {
      const current = ++generation.current;
      const [rules, sources, results, currentReadiness] = await Promise.all([
        ownerCapabilityApi.requirements(token, id),
        ownerCapabilityApi.contexts(token, id),
        ownerCapabilityApi.assessments(token, id, page),
        ownerCapabilityApi.currentReadiness(token, id),
      ]);
      if (current !== generation.current) return;
      setProjectId(id);
      setRequirements(rules);
      setContexts(sources);
      setHistory(results);
      setReadiness(currentReadiness);
      setSelected(
        (previous) =>
          results.items.find((item) => item.id === (preferredId ?? previous?.id)) ?? results.items[0] ?? null
      );
      setEditor(null);
      setPreview(null);
      setRowPage(1);
    },
    [token]
  );
  useEffect(() => {
    let live = true;
    void ownerCapabilityApi
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
      setMessage(error instanceof Error ? error.message : "Owner Capability operation failed.");
    } finally {
      setBusy(false);
    }
  }
  const requirementRows = rows(requirements.requirements);
  const maturityValues = scaleValues(requirements.maturity_scale);
  const qualityValues = scaleValues(requirements.quality_scale).length
    ? scaleValues(requirements.quality_scale)
    : (options?.quality_values ?? []);
  const assessmentItems = rows(selected?.aggregate_json?.items);
  const gaps = rows(selected?.aggregate_json?.gaps);
  const mitigations = rows(selected?.aggregate_json?.mitigations);
  // A non-persisted preview can be READY while a DRAFT is not provider-eligible.
  // Never replace current governed readiness with that analytical preview.
  const effectiveReadiness = readiness;
  const coverage = record(effectiveReadiness.coverage);
  const status = value(effectiveReadiness.readiness_status ?? effectiveReadiness.status, "NOT_STARTED");
  const canEdit = Boolean(selected && selected.status === "DRAFT" && allowed("assessment_edit", selected));
  const canMitigate = Boolean(selected && selected.status === "DRAFT" && allowed("mitigation_edit", selected));
  function openEditor(kind: Editor, row?: JsonRecord, index?: number) {
    const code = String(row?.requirement_code ?? requirementRows[0]?.requirement_code ?? "");
    setEditingIndex(index ?? null);
    setEditor(kind);
    const initial =
      kind === "item"
        ? {
            requirement_code: code,
            current_maturity: maturityValues[0] ?? "",
            evidence_quality: qualityValues[0] ?? "NOT_AVAILABLE",
            confidence: options?.confidence_values?.[0] ?? "PRELIMINARY",
            capability_source: "INTERNAL",
            rationale: "",
            evidence_refs: [],
            source_current: true,
            responsible_function: "",
            role_refs: [],
            related_risk_ids: [],
            review_notes: "",
          }
        : kind === "gap"
          ? {
              requirement_code: code,
              description: "",
              severity: "MEDIUM",
              blocking: false,
              owner: "",
              target_date: null,
              status: "OPEN",
              closure_evidence: [],
            }
          : {
              requirement_code: code,
              description: "",
              approach: "",
              owner: "",
              target_date: null,
              status: "PROPOSED",
              closure_evidence: [],
              evidence_refs: [],
            };
    const refs = rows(row?.evidence_refs);
    setForm({
      ...initial,
      ...row,
      evidence_reference: refs[0]?.source_reference ?? refs[0]?.reference ?? "",
      closure_reference: rows(row?.closure_evidence)[0]?.source_reference ?? "",
    });
  }
  async function saveEditor() {
    if (!selected || !editor) return;
    const evidenceRefs = String(form.evidence_reference ?? "")
      ? [
          {
            source_type: "REFERENCE",
            source_reference: String(form.evidence_reference),
            source_version: form.source_version || null,
            source_hash: form.source_hash || null,
          },
          ...rows(form.evidence_refs).slice(1),
        ]
      : rows(form.evidence_refs).slice(1);
    const closureEvidence = String(form.closure_reference ?? "")
      ? [
          { source_type: "REFERENCE", source_reference: String(form.closure_reference) },
          ...rows(form.closure_evidence).slice(1),
        ]
      : rows(form.closure_evidence).slice(1);
    const roleRefs: unknown =
      form.role_refs_text == null ? (form.role_refs ?? []) : JSON.parse(String(form.role_refs_text));
    if (!Array.isArray(roleRefs)) throw new Error("Role references must be a JSON array.");
    const normalized = {
      ...form,
      role_refs: roleRefs,
      evidence_refs: evidenceRefs,
      closure_evidence: closureEvidence,
      target_date: form.target_date || null,
      source_date: form.source_date || null,
      expires_on: form.expires_on || null,
      source_hash: form.source_hash || null,
      source_version: form.source_version || null,
    };
    if (editor === "mitigation") {
      const body = pick(normalized, mitigationKeys);
      if (editingIndex == null) await ownerCapabilityApi.createMitigation(token, selected, body);
      else
        await ownerCapabilityApi.updateMitigation(
          token,
          selected,
          String(mitigations[editingIndex]?.id ?? editingIndex + 1),
          body
        );
    } else {
      const body = aggregateBody(selected);
      const list = editor === "item" ? body.items : body.gaps;
      const entry = pick(normalized, editor === "item" ? itemKeys : gapKeys);
      if (editingIndex == null) {
        const existing =
          editor === "item" ? list.findIndex((row) => row.requirement_code === entry.requirement_code) : -1;
        if (existing >= 0) list[existing] = entry;
        else list.push(entry);
      } else list[editingIndex] = entry;
      await ownerCapabilityApi.updateAssessment(token, selected, body);
    }
    await load(projectId, history.page, selected.id);
  }
  async function assessmentAction(action: "preview" | "submit" | "review" | "complete" | "refresh-apply") {
    if (!selected) return;
    const result = await ownerCapabilityApi.assessmentAction(token, selected, action);
    if (action === "preview") {
      setPreview(result);
      return;
    }
    await load(projectId, history.page, Number(result.id) || selected.id);
  }
  function changeView(next: View) {
    setView(next);
    setEditor(null);
    setRowPage(1);
  }
  const displayedRows =
    view === "Requirements"
      ? requirementRows
      : view === "Gaps"
        ? gaps
        : view === "Mitigation Plan"
          ? mitigations
          : assessmentItems;
  const pageRows = displayedRows.slice((rowPage - 1) * 25, rowPage * 25);
  return (
    <section className="wave2b ownerCapability" aria-label="Owner Capability Readiness workspace">
      <CompactModuleHeader
        title="Owner Capability Readiness"
        eyebrow="USER MODE / Business Case & Investment Development"
        tone="user"
        description="Assess Owner organizational capability to govern and oversee an investment. This is not resource planning, staffing, vendor qualification, operational readiness, FEL/PDRI or QRA."
        metrics={[
          { label: "Readiness", value: status },
          { label: "Exact coverage", value: `${coverage.satisfied ?? 0}/${coverage.required ?? 0}` },
          { label: "Governance Model", value: value(record(requirements.context).governance_model) },
        ]}
      />
      {message ? (
        <p role="status" className="wave2bMessage">
          {message}
        </p>
      ) : null}
      <div className="wave2bToolbar">
        <Field label="Find authorized Projects" text={search} onChange={setSearch} />
        <button
          type="button"
          disabled={busy}
          onClick={() =>
            void execute(async () => {
              const next = await ownerCapabilityApi.options(token, search);
              setOptions(next);
              if (next.projects[0]) await load(next.projects[0].id);
            }, "Authorized Project search completed.")
          }
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
        <button
          type="button"
          disabled={!projectId || busy}
          onClick={() =>
            void execute(
              () => load(projectId, history.page),
              "Current context refreshed. Historical snapshots unchanged."
            )
          }
        >
          Refresh current context
        </button>
        {options && (options.project_total ?? 0) > (options.page_size ?? 100) ? (
          <Pagination
            label="Projects"
            page={options.page ?? 1}
            total={options.project_total ?? 0}
            size={options.page_size ?? 100}
            busy={busy}
            onChange={(page) =>
              void execute(async () => {
                const next = await ownerCapabilityApi.options(token, search, page);
                setOptions(next);
                if (next.projects[0]) await load(next.projects[0].id);
              }, "Authorized Project page loaded.")
            }
          />
        ) : null}
      </div>
      <nav className="wave2bTabs" aria-label="Owner Capability views">
        {views.map((label) => (
          <button
            type="button"
            key={label}
            aria-current={view === label ? "page" : undefined}
            onClick={() => changeView(label)}
          >
            {label}
          </button>
        ))}
      </nav>
      <article aria-label="Owner Capability assessment controls">
        <div className="wave2bToolbar">
          {allowed("assessment_create") ? (
            <button
              type="button"
              disabled={!projectId || busy}
              onClick={() =>
                void execute(async () => {
                  const result = await ownerCapabilityApi.createAssessment(token, projectId);
                  await load(projectId, 1, result.id);
                }, "DRAFT capability assessment created with governed identity.")
              }
            >
              Create capability assessment
            </button>
          ) : null}
          <label>
            Assessment
            <select
              aria-label="Assessment"
              value={selected?.id ?? ""}
              disabled={busy}
              onChange={(event) => {
                setSelected(history.items.find((item) => item.id === Number(event.target.value)) ?? null);
                setEditor(null);
                setPreview(null);
                setRowPage(1);
              }}
            >
              {!history.items.length ? <option value="">No assessments</option> : null}
              {history.items.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.assessment_number} · v{item.assessment_version} · {item.status}
                </option>
              ))}
            </select>
          </label>
        </div>
        {selected ? (
          <>
            <p>
              <strong>
                {selected.assessment_number} · {selected.status}
              </strong>{" "}
              · version {selected.assessment_version} · hash {selected.assessment_hash ?? "Not completed"}
            </p>
            <div className="wave2bToolbar">
              <button
                type="button"
                disabled={busy}
                onClick={() => void execute(() => assessmentAction("preview"), "Assessment preview persisted=false.")}
              >
                Preview assessment
              </button>
              {selected.status === "DRAFT" && allowed("assessment_submit", selected) ? (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void execute(() => assessmentAction("submit"), "Submitted for independent review.")}
                >
                  Submit assessment
                </button>
              ) : null}
              {selected.status === "IN_REVIEW" && allowed("assessment_review", selected) ? (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void execute(() => assessmentAction("review"), "Independent review recorded.")}
                >
                  Review assessment
                </button>
              ) : null}
              {selected.status === "IN_REVIEW" && allowed("assessment_complete", selected) ? (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    void execute(() => assessmentAction("complete"), "COMPLETED immutable assessment preserved.")
                  }
                >
                  Complete assessment
                </button>
              ) : null}
              {selected.status === "COMPLETED" ? (
                <>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      void execute(
                        async () => setPreview(await ownerCapabilityApi.refreshPreview(token, selected.id)),
                        "Refresh preview persisted=false. Historical hash unchanged."
                      )
                    }
                  >
                    Refresh Preview
                  </button>
                  {allowed("assessment_create", selected) ? (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        void execute(
                          () => assessmentAction("refresh-apply"),
                          "Successor DRAFT created. Historical snapshot unchanged."
                        )
                      }
                    >
                      Apply successor DRAFT
                    </button>
                  ) : null}
                </>
              ) : null}
            </div>
          </>
        ) : (
          <p>No assessment yet. Resolve a published applicable framework before creating one.</p>
        )}
        <p>
          Preparer and final reviewer are independent according to policy. A mitigation does not establish readiness
          unless governed policy accepts it.
        </p>
      </article>
      {view === "Overview" || view === "Readiness" ? (
        <article aria-label="Owner Capability readiness summary">
          <h3>OVERALL_OWNER_CAPABILITY_READINESS · {status}</h3>
          <p>
            Coverage {value(coverage.satisfied, "0")} satisfied / {value(coverage.required, "0")} required ·{" "}
            {value(coverage.percentage, "0")}%
          </p>
          <p>
            source_current={String(effectiveReadiness.source_current ?? false)} · maturity is not readiness; one
            critical blocker overrides aggregate coverage.
          </p>
          <pre>
            {JSON.stringify(
              {
                blockers: effectiveReadiness.blockers,
                warnings: effectiveReadiness.warnings,
                critical_gaps: effectiveReadiness.critical_gaps,
                mitigation_summary: effectiveReadiness.mitigation_summary,
              },
              null,
              2
            )}
          </pre>
        </article>
      ) : null}
      {view === "Overview" ? (
        <article aria-label="Owner Capability cross-domain context">
          <h3>Read-only context and policy lineage</h3>
          <pre>
            {JSON.stringify(
              {
                configuration: requirements.configuration,
                project: requirements.context,
                risk_governance: contexts.risk_governance,
                risk_readiness: contexts.risk_readiness,
                basic_data: contexts.basic_data,
                benefits: contexts.benefits,
              },
              null,
              2
            )}
          </pre>
          <p>No source domain, Gate package or FID decision is modified.</p>
        </article>
      ) : null}
      {["Requirements", "Capability Assessment", "Evidence", "Gaps", "Mitigation Plan"].includes(view) ? (
        <article aria-label={`${view} register`}>
          <h3>
            {view}
            {view === "Requirements" ? ` · exact denominator ${requirementRows.length}` : ""}
          </h3>
          <div className="wave2bToolbar">
            {(view === "Capability Assessment" || view === "Evidence") && canEdit ? (
              <button type="button" disabled={busy} onClick={() => openEditor("item")}>
                Add capability item
              </button>
            ) : null}
            {view === "Gaps" && canEdit ? (
              <button type="button" disabled={busy} onClick={() => openEditor("gap")}>
                Add capability gap
              </button>
            ) : null}
            {view === "Mitigation Plan" && canMitigate ? (
              <button type="button" disabled={busy} onClick={() => openEditor("mitigation")}>
                Add mitigation
              </button>
            ) : null}
          </div>
          <div className="wave2bTableScroll">
            <table>
              <thead>
                <tr>
                  <th>Requirement</th>
                  <th>
                    {view === "Requirements"
                      ? "Dimension / minimums"
                      : view === "Gaps"
                        ? "Gap / severity"
                        : view === "Mitigation Plan"
                          ? "Action / approach"
                          : "Maturity / quality / confidence"}
                  </th>
                  <th>{view === "Requirements" ? "Blocking / policy" : "Evidence / responsibility"}</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {pageRows.map((row, pageIndex) => {
                  const index = (rowPage - 1) * 25 + pageIndex;
                  return (
                    <tr key={`${String(row.requirement_code)}-${index}`}>
                      <td>
                        {value(row.requirement_code)}
                        {row.name ? ` · ${value(row.name)}` : ""}
                      </td>
                      <td>
                        {view === "Requirements" ? (
                          <>
                            {value(row.dimension)} · maturity {value(row.minimum_maturity ?? row.required_maturity)} ·
                            quality {value(row.minimum_evidence_quality)}
                          </>
                        ) : view === "Gaps" ? (
                          <>
                            {value(row.description)} · {value(row.severity)} · {value(row.status)}
                          </>
                        ) : view === "Mitigation Plan" ? (
                          <>
                            {value(row.description)} · {value(row.approach)} · {value(row.status)}
                          </>
                        ) : (
                          <>
                            {value(row.current_maturity)} / {value(row.evidence_quality)} / {value(row.confidence)}
                          </>
                        )}
                      </td>
                      <td>
                        {view === "Requirements" ? (
                          <>
                            blocking={String(row.blocking ?? false)} · {value(row.responsible_function)}
                          </>
                        ) : (
                          <>
                            {value(row.owner ?? row.responsible_function)}
                            {row.target_date ? ` · ${value(row.target_date)}` : ""}
                            <small>
                              {rows(row.evidence_refs ?? row.closure_evidence)
                                .map((ref) => value(ref.source_reference ?? ref.reference))
                                .join(" · ")}
                            </small>
                            {view === "Gaps" ? ` · blocking=${String(row.blocking ?? false)}` : ""}
                          </>
                        )}
                      </td>
                      <td>
                        {view !== "Requirements" && (view === "Mitigation Plan" ? canMitigate : canEdit) ? (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() =>
                              openEditor(
                                view === "Gaps" ? "gap" : view === "Mitigation Plan" ? "mitigation" : "item",
                                row,
                                index
                              )
                            }
                          >
                            Edit {value(row.requirement_code)}
                          </button>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {!displayedRows.length ? <p>No records in this view.</p> : null}
          <Pagination
            label={view}
            page={rowPage}
            total={displayedRows.length}
            size={25}
            busy={busy}
            onChange={setRowPage}
          />
          {view === "Evidence" ? (
            <p>
              Reference metadata only. Evidence quality is configured independently of confidence. No document
              repository or HR records are created.
            </p>
          ) : null}
          {view === "Mitigation Plan" ? (
            <p>
              Internal, external-contracted and hybrid capability may be accepted according to configured policy.
              Proposed status is not independent acceptance.
            </p>
          ) : null}
        </article>
      ) : null}
      {editor ? (
        <article aria-label={`Owner Capability ${editor} editor`}>
          <h3>
            {editingIndex == null ? "Add" : "Edit"}{" "}
            {editor === "item"
              ? "capability evidence and maturity"
              : editor === "gap"
                ? "capability gap"
                : "mitigation action"}
          </h3>
          <div className="wave2bForm">
            <SelectField
              label="Requirement"
              selected={String(form.requirement_code ?? "")}
              choices={requirementRows.map((row) => String(row.requirement_code))}
              onChange={(next) => setForm({ ...form, requirement_code: next })}
            />
            {editor === "item" ? (
              <>
                <SelectField
                  label="Current maturity"
                  selected={String(form.current_maturity ?? "")}
                  choices={maturityValues}
                  labels={scaleLabels(requirements.maturity_scale)}
                  onChange={(next) => setForm({ ...form, current_maturity: next })}
                />
                <SelectField
                  label="Evidence quality"
                  selected={String(form.evidence_quality ?? "")}
                  choices={qualityValues}
                  labels={scaleLabels(requirements.quality_scale)}
                  onChange={(next) => setForm({ ...form, evidence_quality: next })}
                />
                <SelectField
                  label="Confidence"
                  selected={String(form.confidence ?? "PRELIMINARY")}
                  choices={options?.confidence_values ?? ["PRELIMINARY", "MODERATE", "HIGH"]}
                  onChange={(next) => setForm({ ...form, confidence: next })}
                />
                <SelectField
                  label="Capability source"
                  selected={String(form.capability_source ?? "INTERNAL")}
                  choices={["INTERNAL", "EXTERNAL_CONTRACTED", "HYBRID"]}
                  onChange={(next) => setForm({ ...form, capability_source: next })}
                />
                {(
                  [
                    ["rationale", "Rationale"],
                    ["responsible_function", "Responsible function"],
                    ["evidence_reference", "Evidence reference"],
                    ["source_version", "Evidence version"],
                    ["source_hash", "Evidence hash"],
                    ["source_date", "Source date"],
                    ["expires_on", "Expiry date"],
                    ["review_notes", "Review notes"],
                  ] as const
                ).map(([key, label]) => (
                  <Field
                    key={key}
                    label={label}
                    type={key === "source_date" || key === "expires_on" ? "date" : "text"}
                    text={String(form[key] ?? "")}
                    onChange={(next) => setForm({ ...form, [key]: next })}
                  />
                ))}
                <label className="ownerCapabilityCheckbox">
                  <input
                    type="checkbox"
                    checked={form.source_current !== false}
                    onChange={(event) => setForm({ ...form, source_current: event.target.checked })}
                  />
                  Evidence source current
                </label>
                <Field
                  label="Related Risk IDs"
                  text={(Array.isArray(form.related_risk_ids) ? form.related_risk_ids : []).join(", ")}
                  onChange={(next) =>
                    setForm({
                      ...form,
                      related_risk_ids: next
                        .split(",")
                        .map((id) => Number(id.trim()))
                        .filter((id) => Number.isSafeInteger(id) && id > 0),
                    })
                  }
                />
                <label>
                  Related role/function references JSON
                  <textarea
                    aria-label="Related role/function references JSON"
                    rows={3}
                    value={String(form.role_refs_text ?? JSON.stringify(form.role_refs ?? []))}
                    onChange={(event) => setForm({ ...form, role_refs_text: event.target.value })}
                  />
                </label>
              </>
            ) : (
              <>
                <Field
                  label={editor === "gap" ? "Gap" : "Action"}
                  text={String(form.description ?? "")}
                  onChange={(next) => setForm({ ...form, description: next })}
                />
                {editor === "gap" ? (
                  <>
                    <SelectField
                      label="Severity"
                      selected={String(form.severity)}
                      choices={["LOW", "MEDIUM", "HIGH", "CRITICAL"]}
                      onChange={(next) => setForm({ ...form, severity: next })}
                    />
                    <label className="ownerCapabilityCheckbox">
                      <input
                        type="checkbox"
                        checked={Boolean(form.blocking)}
                        onChange={(event) => setForm({ ...form, blocking: event.target.checked })}
                      />
                      Blocking gap
                    </label>
                  </>
                ) : (
                  <Field
                    label="Approach"
                    text={String(form.approach ?? "")}
                    onChange={(next) => setForm({ ...form, approach: next })}
                  />
                )}
                <SelectField
                  label="Status"
                  selected={String(form.status)}
                  choices={
                    editor === "gap"
                      ? ["OPEN", "IN_PROGRESS", "CLOSED"]
                      : ["PROPOSED", "ACCEPTED", "IMPLEMENTED", "CLOSED", "REJECTED"]
                  }
                  onChange={(next) => setForm({ ...form, status: next })}
                />
                <Field
                  label="Action owner"
                  text={String(form.owner ?? "")}
                  onChange={(next) => setForm({ ...form, owner: next })}
                />
                <Field
                  label="Target date"
                  type="date"
                  text={String(form.target_date ?? "")}
                  onChange={(next) => setForm({ ...form, target_date: next })}
                />
                <Field
                  label="Closure evidence"
                  text={String(form.closure_reference ?? "")}
                  onChange={(next) => setForm({ ...form, closure_reference: next })}
                />
                {editor === "mitigation" ? (
                  <Field
                    label="Evidence reference"
                    text={String(form.evidence_reference ?? "")}
                    onChange={(next) => setForm({ ...form, evidence_reference: next })}
                  />
                ) : null}
              </>
            )}
          </div>
          <div className="wave2bToolbar">
            <button
              type="button"
              disabled={busy}
              onClick={() => void execute(saveEditor, "Capability record saved. Readiness remains backend-owned.")}
            >
              Save {editor === "item" ? "capability item" : editor === "gap" ? "capability gap" : "mitigation"}
            </button>
            <button type="button" disabled={busy} onClick={() => setEditor(null)}>
              Cancel edit
            </button>
          </div>
        </article>
      ) : null}
      {view === "Dimension Summary" ? (
        <article aria-label="Owner Capability dimension readiness">
          <h3>Backend-owned dimension readiness</h3>
          <pre>
            {JSON.stringify(effectiveReadiness.dimensions ?? effectiveReadiness.dimension_readiness ?? {}, null, 2)}
          </pre>
          <p>Configured maturity and optional analytical scores cannot override critical blockers.</p>
        </article>
      ) : null}
      {view === "Resource Context" || view === "Commercial Context" || view === "FEL / PDRI Context" ? (
        <article aria-label={view}>
          <h3>Read-only {view}</h3>
          <pre>
            {JSON.stringify(
              contexts[
                view === "Resource Context" ? "resources" : view === "Commercial Context" ? "commercial" : "fel_pdri"
              ] ?? {},
              null,
              2
            )}
          </pre>
          <p>
            Source ID/version/hash are contextual references. No staffing, resource leveling, commercial revision or
            FEL/PDRI mutation.
          </p>
        </article>
      ) : null}
      {view === "History" ? (
        <article aria-label="Owner Capability assessment history">
          <h3>Immutable assessment history</h3>
          <p>Completed snapshots use frozen sources, not live context. Reassessment creates a successor DRAFT.</p>
          <Pagination
            label="Assessment history"
            page={history.page}
            total={history.total}
            size={history.page_size}
            busy={busy}
            onChange={(page) => void execute(() => load(projectId, page), "Assessment history page loaded.")}
          />
          {selected ? (
            <details>
              <summary>Frozen assessment snapshot and source lineage</summary>
              <pre>
                {JSON.stringify(
                  { assessment_hash: selected.assessment_hash, snapshot: selected.snapshot_json },
                  null,
                  2
                )}
              </pre>
            </details>
          ) : null}
        </article>
      ) : null}
      {preview ? (
        <article aria-label="Owner Capability assessment preview">
          <strong>persisted={String(preview.persisted)}</strong>
          <pre>{JSON.stringify(preview, null, 2)}</pre>
        </article>
      ) : null}
    </section>
  );
}

function Field({
  label,
  text,
  onChange,
  type = "text",
}: {
  label: string;
  text: string;
  onChange: (next: string) => void;
  type?: "text" | "date";
}) {
  return (
    <label>
      {label}
      <input aria-label={label} type={type} value={text} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}
function SelectField({
  label,
  selected,
  choices,
  labels,
  onChange,
}: {
  label: string;
  selected: string;
  choices: string[];
  labels?: ScaleLabels;
  onChange: (next: string) => void;
}) {
  const available = selected && !choices.includes(selected) ? [selected, ...choices] : choices;
  return (
    <label>
      {label}
      <select aria-label={label} value={selected} onChange={(event) => onChange(event.target.value)}>
        {!available.length ? <option value="">No configured values</option> : null}
        {available.map((choice) => (
          <option key={choice} value={choice} title={labels?.[choice]?.description || undefined}>
            {labels?.[choice]?.name && labels[choice].name !== choice ? `${labels[choice].name} (${choice})` : choice}
          </option>
        ))}
      </select>
    </label>
  );
}
function Pagination({
  label,
  page,
  total,
  size,
  busy,
  onChange,
}: {
  label: string;
  page: number;
  total: number;
  size: number;
  busy: boolean;
  onChange: (page: number) => void;
}) {
  return (
    <div className="wave2bToolbar">
      <button type="button" disabled={busy || page <= 1} onClick={() => onChange(page - 1)}>
        Previous {label} page
      </button>
      <span>
        Page {page} · {total} records
      </span>
      <button type="button" disabled={busy || page * size >= total} onClick={() => onChange(page + 1)}>
        Next {label} page
      </button>
    </div>
  );
}
