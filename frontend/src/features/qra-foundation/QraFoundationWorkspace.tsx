import { useCallback, useEffect, useRef, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import type { JsonRecord } from "../risk-governance/policyApi";
import { qraFoundationApi, type QraKind, type QraOptions, type QraPage, type QraRecord, type QraItemPage } from "./api";
import "../risk-governance/wave2b.css";
import "./qraFoundation.css";

const tabs = ["Cost Source Readiness", "Schedule Source Readiness", "Model Definition", "History"] as const;
type Tab = (typeof tabs)[number];
const sections: Record<QraKind, readonly string[]> = {
  cost: [
    "Overview",
    "Sources",
    "Scope / Basis",
    "Reconciliation",
    "Quality",
    "Uncertainty Input Readiness",
    "Gaps",
    "Readiness",
    "History",
  ],
  schedule: [
    "Overview",
    "Source Snapshot",
    "Scope",
    "Logic Quality",
    "Calendars",
    "Constraints / Lags",
    "Open Ends",
    "Data Date / Status",
    "Uncertainty Input Readiness",
    "Gaps",
    "Readiness",
    "History",
  ],
  model: [
    "Overview",
    "Scope",
    "Source Readiness",
    "Risk Context",
    "Methodology",
    "Uncertainty Rules",
    "Distribution Rules",
    "Correlation Rules",
    "Governance / SoD",
    "Validity",
    "Readiness",
    "History",
  ],
};
const record = (value: unknown): JsonRecord =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as JsonRecord) : {};
const rows = (value: unknown): JsonRecord[] => (Array.isArray(value) ? value.map(record) : []);
const text = (value: unknown, fallback = "—") => (value == null || value === "" ? fallback : String(value));
const json = (value: unknown) => JSON.stringify(value ?? {}, null, 2);
const emptyPage = (): QraPage => ({ items: [], total: 0, page: 1, page_size: 25 });
const kindFor = (tab: Tab): QraKind =>
  tab === "Schedule Source Readiness" ? "schedule" : tab === "Model Definition" ? "model" : "cost";
const initialTabFor = (view?: string): Tab =>
  view === "qra-schedule-source-readiness"
    ? "Schedule Source Readiness"
    : view === "qra-model-definition"
      ? "Model Definition"
      : view === "qra-foundation-history"
        ? "History"
        : "Cost Source Readiness";
const needsFullRecord = (section: string) =>
  [
    "History",
    "Sources",
    "Source Snapshot",
    "Scope",
    "Scope / Basis",
    "Reconciliation",
    "Quality",
    "Logic Quality",
    "Calendars",
    "Constraints / Lags",
    "Open Ends",
    "Data Date / Status",
    "Gaps",
    "Source Readiness",
    "Validity",
    "Correlation Rules",
  ].includes(section);
type Form = Record<string, string>;
const sourceKeys = ["source_refs", "basis", "analysis_scope", "items", "gaps", "evidence_refs"];
const modelKeys = ["analysis_scope", "inputs", "correlations"];
const metadataKeys = ["analysis_scope", "correlations"];
function formFor(item: QraRecord, kind: QraKind): Form {
  const aggregate = item.aggregate_json;
  const next: Form = {
    title: String(item.title ?? ""),
    comments: String(aggregate.comments ?? item.comments ?? ""),
    quality: String(aggregate.quality ?? "UNVERIFIED"),
    confidence: String(aggregate.confidence ?? "PRELIMINARY"),
    analysis_type: String(aggregate.analysis_type ?? item.analysis_type ?? "COST_QRA"),
    purpose: String(aggregate.purpose ?? ""),
    cost_source_assessment_id: String(aggregate.cost_source_assessment_id ?? ""),
    schedule_source_assessment_id: String(aggregate.schedule_source_assessment_id ?? ""),
    valid_from: String(aggregate.valid_from ?? ""),
    valid_until: String(aggregate.valid_until ?? ""),
  };
  for (const key of kind === "model" ? modelKeys : sourceKeys) {
    const fallback = ["source_refs", "items", "gaps", "inputs", "evidence_refs"].includes(key)
      ? []
      : key === "analysis_scope"
        ? { type: "ENTIRE_PROJECT", refs: [] }
        : key === "correlations"
          ? { method: "NO_CORRELATION", pairs: [], groups: [], matrix: [] }
          : {};
    next[key] = json(aggregate[key] ?? fallback);
  }
  return next;
}
function parseField(form: Form, key: string, array: boolean): unknown {
  let value: unknown;
  try {
    value = JSON.parse(form[key]);
  } catch {
    throw new Error(`${key} must contain valid JSON. Unsaved input has been preserved.`);
  }
  if (array ? !Array.isArray(value) : !value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${key} must be a JSON ${array ? "array" : "object"}.`);
  }
  return value;
}
function bodyFor(form: Form, kind: QraKind): JsonRecord {
  const body: JsonRecord = { title: form.title, comments: form.comments };
  for (const key of kind === "model" ? metadataKeys : sourceKeys) {
    body[key] = parseField(form, key, ["source_refs", "items", "gaps", "inputs", "evidence_refs"].includes(key));
  }
  if (kind === "model") {
    Object.assign(body, {
      analysis_type: form.analysis_type,
      purpose: form.purpose,
      cost_source_assessment_id: form.cost_source_assessment_id ? Number(form.cost_source_assessment_id) : null,
      schedule_source_assessment_id: form.schedule_source_assessment_id
        ? Number(form.schedule_source_assessment_id)
        : null,
      valid_from: form.valid_from || null,
      valid_until: form.valid_until || null,
    });
  } else Object.assign(body, { quality: form.quality, confidence: form.confidence });
  return body;
}

export default function QraFoundationWorkspace({ token, initialView }: { token: string; initialView?: string }) {
  const initialTab = initialTabFor(initialView);
  const [tab, setTab] = useState<Tab>(initialTab);
  const [kind, setKind] = useState<QraKind>(kindFor(initialTab));
  const [section, setSection] = useState(initialTab === "History" ? "History" : "Overview");
  const [options, setOptions] = useState<QraOptions | null>(null);
  const [search, setSearch] = useState("");
  const [projectId, setProjectId] = useState(0);
  const [requirements, setRequirements] = useState<JsonRecord>({});
  const [contexts, setContexts] = useState<JsonRecord>({});
  const [costSources, setCostSources] = useState<JsonRecord>({});
  const [scheduleSources, setScheduleSources] = useState<JsonRecord>({});
  const [history, setHistory] = useState(emptyPage);
  const [selected, setSelected] = useState<QraRecord | null>(null);
  const [readiness, setReadiness] = useState<JsonRecord>({});
  const [preview, setPreview] = useState<JsonRecord | null>(null);
  const [editing, setEditing] = useState(false);
  const [inputEditing, setInputEditing] = useState(false);
  const [inputForm, setInputForm] = useState("[]");
  const [form, setForm] = useState<Form>({});
  const [analysisType, setAnalysisType] = useState("COST_QRA");
  const [comments, setComments] = useState("");
  const [message, setMessage] = useState("");
  const [operationBusy, setBusy] = useState(false);
  const [rowPage, setRowPage] = useState(1);
  const [itemPage, setItemPage] = useState<QraItemPage>({ items: [], total: 0, page: 1, page_size: 25 });
  const generation = useRef(0);
  const selectedRef = useRef<QraRecord | null>(null);
  const [appliedContext, setAppliedContext] = useState<{ token: string; view?: string } | null>(null);
  const contextChanged = appliedContext?.token !== token || appliedContext.view !== initialView;
  const busy = operationBusy || inputEditing || (contextChanged && !editing);
  const policy = record(requirements.policy);
  const entityAllows = (action: string) => selected?.allowed_actions?.includes(action) === true;
  const actions = Array.isArray(requirements.allowed_actions)
    ? requirements.allowed_actions.map(String)
    : (options?.allowed_actions ?? []);
  const canCreate = actions.includes(`${kind}_create`);
  const clearProject = useCallback(() => {
    generation.current += 1;
    selectedRef.current = null;
    setProjectId(0);
    setRequirements({});
    setContexts({});
    setCostSources({});
    setScheduleSources({});
    setHistory(emptyPage());
    setReadiness({});
    setSelected(null);
    setItemPage({ items: [], total: 0, page: 1, page_size: 25 });
    setEditing(false);
    setInputEditing(false);
    setPreview(null);
    setRowPage(1);
  }, []);
  const load = useCallback(
    async (id: number, nextKind: QraKind, page = 1, preferredId?: number, detailed = false) => {
      if (!id) {
        clearProject();
        setKind(nextKind);
        return;
      }
      const current = ++generation.current;
      // A bounded, fixed batch per view, never a request per row/activity/input.
      const [rules, context, costs, schedules, records, currentReadiness] = await Promise.all([
        qraFoundationApi.requirements(token, id),
        qraFoundationApi.contexts(token, id),
        qraFoundationApi.sourceOptions(token, id, "cost"),
        qraFoundationApi.sourceOptions(token, id, "schedule"),
        qraFoundationApi.records(token, id, nextKind, page),
        qraFoundationApi.readiness(token, id, nextKind),
      ]);
      if (current !== generation.current) return;
      const candidate =
        records.items.find((item) => item.id === (preferredId ?? selectedRef.current?.id)) ?? records.items[0];
      // List payloads are summaries. Resolve a single selected record plus its
      // server-paginated population, never a request per item or historical row.
      const [full, nextItems] = candidate
        ? await Promise.all([
            qraFoundationApi.record(token, nextKind, candidate.id, !detailed),
            qraFoundationApi.recordItems(token, nextKind, candidate.id),
          ])
        : [null, { items: [], total: 0, page: 1, page_size: 25 }];
      if (current !== generation.current) return;
      setProjectId(id);
      setKind(nextKind);
      setRequirements(rules);
      setContexts(context);
      setCostSources(costs);
      setScheduleSources(schedules);
      setHistory(records);
      setReadiness(currentReadiness);
      selectedRef.current = full;
      setSelected(full);
      setItemPage(nextItems);
      setEditing(false);
      setInputEditing(false);
      setPreview(null);
      setRowPage(1);
    },
    [clearProject, token]
  );
  useEffect(() => {
    if (appliedContext?.token === token && appliedContext.view === initialView) return;
    // Sidebar routes can change independently of the disabled local tabs.
    // Defer their load until the pending editor is saved or cancelled.
    if (editing || inputEditing) return;
    let live = true;
    const nextTab = initialTabFor(initialView);
    void qraFoundationApi
      .options(token)
      .then(async (next) => {
        if (!live) return;
        setTab(nextTab);
        setKind(kindFor(nextTab));
        setSection(nextTab === "History" ? "History" : "Overview");
        setOptions(next);
        if (next.projects[0])
          await load(next.projects[0].id, kindFor(initialTabFor(initialView)), 1, undefined, nextTab === "History");
        else clearProject();
        if (live) setAppliedContext({ token, view: initialView });
      })
      .catch((error: Error) => {
        if (live) {
          setMessage(error.message);
          setAppliedContext({ token, view: initialView });
        }
      });
    return () => {
      live = false;
      generation.current += 1;
    };
  }, [appliedContext, clearProject, editing, inputEditing, initialView, load, token]);
  async function execute(work: () => Promise<unknown>, success: string) {
    setBusy(true);
    setMessage("");
    try {
      await work();
      setMessage(success);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "QRA Foundation operation failed.");
    } finally {
      setBusy(false);
    }
  }
  async function changeTab(next: Tab) {
    const nextKind = next === "History" ? kind : kindFor(next);
    setTab(next);
    setSection(next === "History" ? "History" : "Overview");
    if (projectId) await load(projectId, nextKind, 1, undefined, next === "History");
    else {
      setKind(nextKind);
      setEditing(false);
    }
  }
  async function perform(action: "preview" | "submit" | "review" | "complete" | "approve" | "refresh-apply") {
    if (!selected) return;
    const result = await qraFoundationApi.action(token, kind, selected, action, comments);
    if (action === "preview") {
      setPreview(result);
      return;
    }
    await load(projectId, kind, history.page, Number(result.id) || selected.id, needsFullRecord(section));
  }
  function chooseSource(index: string) {
    const source = rows((kind === "cost" ? costSources : scheduleSources).items)[Number(index)];
    if (!source) return;
    const ref = {
      kind: source.kind,
      id: source.id,
      reference: source.reference,
      version: source.version,
      hash: source.hash,
    };
    setForm((previous) => ({ ...previous, source_refs: json([ref]) }));
  }
  async function loadSourcePage(page: number) {
    if (kind === "model") return;
    const result = await qraFoundationApi.sourceOptions(token, projectId, kind, page);
    if (kind === "cost") setCostSources(result);
    else setScheduleSources(result);
  }
  async function loadItemPage(page: number) {
    if (!selected) return;
    const current = generation.current;
    const next = await qraFoundationApi.recordItems(token, kind, selected.id, page);
    if (current !== generation.current) return;
    setItemPage(next);
    setRowPage(next.page);
  }
  async function showSection(next: string) {
    setSection(next);
    setRowPage(1);
    if (selected && needsFullRecord(next)) {
      const current = generation.current;
      const full = await qraFoundationApi.record(token, kind, selected.id);
      if (current !== generation.current) return;
      selectedRef.current = full;
      setSelected(full);
    }
    if (selected && ["Uncertainty Input Readiness", "Uncertainty Rules"].includes(next)) await loadItemPage(1);
  }
  const coverage = record(readiness.coverage);
  const status = text(readiness.readiness_status ?? readiness.readiness ?? readiness.status, "NOT_STARTED");
  const aggregate = record(selected?.aggregate_json);
  const snapshot = record(selected?.snapshot_json);
  const scheduleSummary = record(snapshot.schedule_summary);
  const inputRows = itemPage.items;
  const sourceRequirements = rows(
    kind === "schedule" ? requirements.schedule_requirements : requirements.cost_requirements
  );
  const payload =
    section === "Methodology"
      ? {
          configuration: record(requirements.configuration),
          methodology: policy.methodology,
          analysis_types: policy.analysis_types,
        }
      : section === "Risk Context"
        ? contexts
        : section === "Uncertainty Rules"
          ? { range_policies: policy.range_policies }
          : section === "Distribution Rules"
            ? { distribution_families: policy.distribution_families }
            : section === "Correlation Rules"
              ? { policy: policy.correlation_rules, methods: policy.correlation_methods, model: aggregate.correlations }
              : section === "Governance / SoD"
                ? {
                    model_governance: policy.model_governance,
                    separation_of_duties: policy.separation_of_duties,
                    reviewed_by: selected?.reviewed_by,
                    approved_by: selected?.approved_by,
                  }
                : section === "Validity"
                  ? {
                      valid_from: aggregate.valid_from,
                      valid_until: aggregate.valid_until,
                      freshness: policy.freshness,
                      current: readiness,
                    }
                  : section === "Reconciliation"
                    ? (record(selected?.snapshot_json).reconciliation ?? aggregate.basis)
                    : section === "Logic Quality"
                      ? {
                          rules: policy.schedule_quality_rules,
                          schedule_summary: scheduleSummary,
                          requirement_results: snapshot.requirement_results,
                          blockers: snapshot.blockers,
                        }
                      : section === "Constraints / Lags"
                        ? {
                            rules: policy.schedule_quality_rules,
                            constraints: scheduleSummary.constraints,
                            negative_lags: scheduleSummary.negative_lags,
                            excessive_lags: scheduleSummary.excessive_lags,
                            invalid_relationships: scheduleSummary.invalid_relationships,
                            blockers: snapshot.blockers,
                          }
                        : section === "Open Ends"
                          ? {
                              rules: policy.schedule_quality_rules,
                              missing_predecessors: scheduleSummary.missing_predecessors,
                              missing_successors: scheduleSummary.missing_successors,
                              open_ends: scheduleSummary.open_ends,
                              blockers: snapshot.blockers,
                            }
                          : section === "Calendars" || section === "Data Date / Status"
                            ? {
                                frozen_basis: record(selected?.snapshot_json).basis ?? aggregate.basis,
                                frozen_schedule_summary: record(selected?.snapshot_json).schedule_summary,
                                current_source_options: scheduleSources,
                              }
                            : section === "Scope" || section === "Scope / Basis"
                              ? {
                                  analysis_scope: aggregate.analysis_scope,
                                  basis: aggregate.basis,
                                  requirements: sourceRequirements,
                                }
                              : section === "Quality"
                                ? {
                                    quality: aggregate.quality,
                                    confidence: aggregate.confidence,
                                    requirements: sourceRequirements,
                                    current: readiness,
                                  }
                                : section === "Gaps"
                                  ? { gaps: aggregate.gaps, blockers: readiness.blockers, warnings: readiness.warnings }
                                  : section === "Source Readiness"
                                    ? {
                                        cost_source_assessment_id: aggregate.cost_source_assessment_id,
                                        schedule_source_assessment_id: aggregate.schedule_source_assessment_id,
                                        contexts,
                                      }
                                    : null;
  return (
    <section className="wave2b qraFoundation" aria-label="QRA Foundation workspace">
      <CompactModuleHeader
        title="QRA Foundation"
        eyebrow="USER MODE / Business Case & Investment Development"
        tone="user"
        description="Govern cost and schedule source evidence, methodology and approved model definitions. The separate QRA Calculation Engine executes current approved definitions; Foundation never stores run results or changes operational CPM."
        metrics={[
          { label: "Readiness", value: status },
          {
            label: "Exact coverage",
            value: `${coverage.covered ?? coverage.satisfied ?? coverage.complete ?? 0}/${coverage.required ?? 0}`,
          },
          { label: "Governance Model", value: text(record(requirements.context).governance_model) },
        ]}
      />
      <p className="wave2bBoundary" role="note">
        APPROVED_FOR_ANALYSIS means an immutable definition eligible for governed analysis, not QRA completed. Current
        readiness is resolved by the backend; previews never replace governed evidence.
      </p>
      {message ? (
        <p role="status" className="wave2bMessage">
          {message}
        </p>
      ) : null}
      <div className="wave2bToolbar">
        <Field label="Find authorized Projects" value={search} onChange={setSearch} />
        <button
          type="button"
          disabled={busy || editing}
          onClick={() =>
            void execute(async () => {
              const next = await qraFoundationApi.options(token, search);
              setOptions(next);
              if (next.projects[0]) await load(next.projects[0].id, kind, 1, undefined, needsFullRecord(section));
              else clearProject();
            }, "Authorized Project search completed.")
          }
        >
          Search Projects
        </button>
        <Select
          label="Project Workspace"
          value={String(projectId)}
          choices={(options?.projects ?? []).map((p) => ({ value: String(p.id), label: `${p.code} · ${p.name}` }))}
          disabled={busy || editing}
          onChange={(next) =>
            void execute(
              () => load(Number(next), kind, 1, undefined, needsFullRecord(section)),
              "Project context loaded."
            )
          }
        />
        {(options?.project_total ?? 0) > (options?.page_size ?? 100) ? (
          <Pager
            label="authorized Projects"
            page={options?.page ?? 1}
            total={options?.project_total ?? 0}
            size={options?.page_size ?? 100}
            busy={busy || editing}
            onChange={(page) =>
              void execute(async () => {
                const next = await qraFoundationApi.options(token, search, page);
                setOptions(next);
                if (next.projects[0]) await load(next.projects[0].id, kind);
              }, "Project search page loaded.")
            }
          />
        ) : null}
      </div>
      <nav className="wave2bTabs" aria-label="QRA Foundation subviews">
        {tabs.map((next) => (
          <button
            key={next}
            type="button"
            aria-current={tab === next ? "page" : undefined}
            disabled={busy || editing}
            onClick={() => void execute(() => changeTab(next), "QRA Foundation view loaded.")}
          >
            {next}
          </button>
        ))}
      </nav>
      {tab === "History" ? (
        <Select
          label="History domain"
          value={kind}
          choices={[
            { value: "cost", label: "Cost Source Readiness" },
            { value: "schedule", label: "Schedule Source Readiness" },
            { value: "model", label: "Model Definition" },
          ]}
          disabled={busy || editing}
          onChange={(next) =>
            void execute(() => load(projectId, next as QraKind, 1, undefined, true), "History domain loaded.")
          }
        />
      ) : (
        <nav className="wave2bTabs qraSubsections" aria-label={`${tab} sections`}>
          {sections[kind].map((next) => (
            <button
              key={next}
              type="button"
              aria-current={section === next ? "page" : undefined}
              disabled={busy || editing}
              onClick={() => void execute(() => showSection(next), "Governed section loaded.")}
            >
              {next}
            </button>
          ))}
        </nav>
      )}
      <article aria-label="QRA governed record selection">
        <div className="wave2bToolbar">
          <Select
            label="Selected governed record"
            value={String(selected?.id ?? "")}
            choices={history.items.map((item) => ({
              value: String(item.id),
              label: `${item.model_number ?? item.number} · v${item.version} · ${item.status}`,
            }))}
            disabled={busy || editing}
            onChange={(next) =>
              void execute(async () => {
                const current = ++generation.current;
                const [full, nextItems] = next
                  ? await Promise.all([
                      qraFoundationApi.record(token, kind, Number(next), !needsFullRecord(section)),
                      qraFoundationApi.recordItems(token, kind, Number(next)),
                    ])
                  : [null, { items: [], total: 0, page: 1, page_size: 25 }];
                if (current !== generation.current) return;
                selectedRef.current = full;
                setSelected(full);
                setItemPage(nextItems);
                setPreview(null);
                setRowPage(1);
              }, "Selected governed record loaded.")
            }
          />
          {kind === "model" ? (
            <Select
              label="New model analysis type"
              value={analysisType}
              choices={(options?.analysis_types ?? []).map((code) => ({ value: code, label: code }))}
              onChange={setAnalysisType}
              disabled={busy}
            />
          ) : null}
          {canCreate ? (
            <button
              type="button"
              disabled={busy || editing || !projectId}
              onClick={() =>
                void execute(async () => {
                  const created = await qraFoundationApi.create(token, projectId, kind, {
                    title:
                      kind === "model"
                        ? "QRA Model Definition"
                        : `${kind === "cost" ? "Cost" : "Schedule"} source assessment`,
                    comments: "",
                    ...(kind === "model" ? { analysis_type: analysisType } : {}),
                  });
                  await load(projectId, kind, 1, created.id, needsFullRecord(section));
                }, "DRAFT created; no assessment or analysis result has been inferred.")
              }
            >
              {kind === "model" ? "Create model definition" : `Create ${kind} source assessment`}
            </button>
          ) : null}
          {entityAllows("edit") ? (
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                void execute(async () => {
                  if (!selected) return;
                  const full = await qraFoundationApi.record(token, kind, selected.id, kind === "model");
                  selectedRef.current = full;
                  setSelected(full);
                  setForm(formFor(full, kind));
                  setEditing(true);
                }, "Editable aggregate loaded; policy validation remains backend-owned.")
              }
            >
              Edit {kind === "model" ? "model definition" : `${kind} source assessment`}
            </button>
          ) : null}
          {kind === "model" && entityAllows("edit") ? (
            <button
              type="button"
              disabled={busy || editing}
              onClick={() => {
                setInputForm(json(itemPage.items));
                setInputEditing(true);
              }}
            >
              Edit input page
            </button>
          ) : null}
          {selected ? (
            <button
              type="button"
              disabled={busy || editing}
              onClick={() =>
                void execute(() => perform("preview"), "Readiness preview resolved by backend; persisted=false.")
              }
            >
              Preview readiness
            </button>
          ) : null}
        </div>
        {selected ? (
          <dl className="qraMetadata">
            {[
              [kind === "model" ? "Model number" : "Number", selected.model_number ?? selected.number],
              ["Status", selected.status],
              ["Definition version", selected.version],
              ["Concurrency version", selected.revision_version],
              ["Frozen hash", selected.hash],
            ].map(([label, value]) => (
              <div key={String(label)}>
                <dt>{label}</dt>
                <dd>{text(value)}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p>No governed records for this Project and domain.</p>
        )}
        <Pager
          label="governed records"
          page={history.page}
          total={history.total}
          size={history.page_size}
          busy={busy || editing}
          onChange={(page) =>
            void execute(() => load(projectId, kind, page, undefined, needsFullRecord(section)), "Record page loaded.")
          }
        />
      </article>
      {editing && selected ? (
        <article aria-label="QRA definition editor">
          <h3>{kind === "model" ? "Model definition inputs — no calculation" : "Source assessment — evidence only"}</h3>
          <div className="wave2bForm">
            <Field label="Record title" value={form.title} onChange={(next) => setForm({ ...form, title: next })} />
            <Field
              label="Record comments"
              value={form.comments}
              onChange={(next) => setForm({ ...form, comments: next })}
            />
            {kind === "model" ? (
              <>
                <Select
                  label="Model analysis type"
                  value={form.analysis_type}
                  choices={(options?.analysis_types ?? []).map((code) => ({ value: code, label: code }))}
                  onChange={(next) => setForm({ ...form, analysis_type: next })}
                />
                <Field
                  label="Model purpose"
                  value={form.purpose}
                  onChange={(next) => setForm({ ...form, purpose: next })}
                />
                <Field
                  label="Cost assessment ID"
                  value={form.cost_source_assessment_id}
                  onChange={(next) => setForm({ ...form, cost_source_assessment_id: next })}
                  type="number"
                />
                <Field
                  label="Schedule assessment ID"
                  value={form.schedule_source_assessment_id}
                  onChange={(next) => setForm({ ...form, schedule_source_assessment_id: next })}
                  type="number"
                />
                <Field
                  label="Valid from"
                  value={form.valid_from}
                  onChange={(next) => setForm({ ...form, valid_from: next })}
                  type="date"
                />
                <Field
                  label="Valid until"
                  value={form.valid_until}
                  onChange={(next) => setForm({ ...form, valid_until: next })}
                  type="date"
                />
              </>
            ) : (
              <>
                <Select
                  label="Select governed source"
                  value=""
                  choices={rows((kind === "cost" ? costSources : scheduleSources).items).map((source, index) => ({
                    value: String(index),
                    label: `${text(source.kind)} · ${text(source.reference ?? source.name ?? source.id)}`,
                  }))}
                  onChange={chooseSource}
                />
                <Select
                  label="Source evidence quality"
                  value={form.quality}
                  choices={(
                    options?.quality_values ?? ["NOT_AVAILABLE", "UNVERIFIED", "PARTIALLY_VERIFIED", "VERIFIED"]
                  ).map((code) => ({ value: code, label: code }))}
                  onChange={(next) => setForm({ ...form, quality: next })}
                />
                <Select
                  label="Source confidence"
                  value={form.confidence}
                  choices={(options?.confidence_values ?? ["PRELIMINARY", "MODERATE", "HIGH"]).map((code) => ({
                    value: code,
                    label: code,
                  }))}
                  onChange={(next) => setForm({ ...form, confidence: next })}
                />
              </>
            )}
          </div>
          {(kind === "model" ? metadataKeys : sourceKeys).map((key) => (
            <JsonField
              key={key}
              label={`${key} JSON`}
              value={form[key]}
              onChange={(next) => setForm({ ...form, [key]: next })}
            />
          ))}
          <p>
            {kind === "model"
              ? "Inputs are definitions only. Use explicit UNCERTAIN or DETERMINISTIC modes, reference the source population, preserve evidence/rationale and configured range/distribution/correlation codes. No sampling."
              : "Source IDs/versions/hashes must resolve to existing governed sources. External references require explicit lineage. Schedule data stays in its existing authority; P6 remains the external CPM engine. No silent FX conversion or new contingency."}
          </p>
          <div className="wave2bToolbar">
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                void execute(async () => {
                  const updated =
                    kind === "model"
                      ? await qraFoundationApi.updateModelMetadata(token, selected, bodyFor(form, kind))
                      : await qraFoundationApi.update(token, kind, selected, bodyFor(form, kind));
                  await load(projectId, kind, history.page, updated.id, needsFullRecord(section));
                }, "Definition saved; readiness remains backend-owned.")
              }
            >
              Save {kind === "model" ? "model definition" : `${kind} source assessment`}
            </button>
            <button type="button" disabled={busy} onClick={() => setEditing(false)}>
              Cancel edit
            </button>
          </div>
        </article>
      ) : null}
      {inputEditing && selected && kind === "model" ? (
        <article aria-label="QRA paged input editor">
          <h3>Model input definitions · page {rowPage}</h3>
          <p>
            Only the current server page is edited. Saving upserts these explicit references and preserves every other
            input and model setting. Definitions are not simulation results.
          </p>
          <JsonField label="Input page JSON" value={inputForm} onChange={setInputForm} />
          <div className="wave2bToolbar">
            <button
              type="button"
              disabled={operationBusy}
              onClick={() =>
                void execute(async () => {
                  const inputs = parseField({ inputs: inputForm }, "inputs", true) as JsonRecord[];
                  const updated = await qraFoundationApi.updateModelInputs(token, selected, inputs);
                  selectedRef.current = updated;
                  setSelected(updated);
                  setInputEditing(false);
                  await loadItemPage(rowPage);
                }, "Input page saved; other inputs preserved and completeness revalidated by backend.")
              }
            >
              Save input page
            </button>
            <button type="button" disabled={operationBusy} onClick={() => setInputEditing(false)}>
              Cancel input edit
            </button>
          </div>
        </article>
      ) : null}
      {section === "Overview" || section === "Readiness" ? (
        <article aria-label="QRA current readiness">
          <h3>
            {kind === "model"
              ? "Model definition readiness"
              : `${kind === "cost" ? "Cost" : "Schedule"} source readiness`}{" "}
            · {status}
          </h3>
          <p>
            {text(coverage.covered ?? coverage.satisfied ?? coverage.complete, "0")} satisfied /{" "}
            {text(coverage.required, "0")} required. Critical blockers cannot be bypassed by overall coverage.
          </p>
          <pre>{json(readiness)}</pre>
        </article>
      ) : null}
      {section === "Sources" || section === "Source Snapshot" ? (
        <article aria-label="QRA source lineage">
          <h3>Existing governed sources — read only</h3>
          <pre>{json(kind === "cost" ? costSources : scheduleSources)}</pre>
          <Pager
            label="source options"
            page={Number((kind === "cost" ? costSources : scheduleSources).page ?? 1)}
            total={Number((kind === "cost" ? costSources : scheduleSources).total ?? 0)}
            size={Number((kind === "cost" ? costSources : scheduleSources).page_size ?? 100)}
            busy={busy}
            onChange={(page) => void execute(() => loadSourcePage(page), "Governed source page loaded.")}
          />
          <h4>Selected source references</h4>
          <pre>{json(aggregate.source_refs ?? [])}</pre>
          {kind === "schedule" ? (
            <>
              <h4>
                {selected?.status === "COMPLETED"
                  ? "Frozen source snapshot — immutable evidence"
                  : "Draft source snapshot — not completed evidence"}
              </h4>
              <pre>
                {json({
                  source_refs: snapshot.source_refs,
                  analysis_scope: snapshot.analysis_scope,
                  basis: snapshot.basis,
                  schedule_summary: snapshot.schedule_summary,
                  as_of: snapshot.as_of,
                  hash: selected?.hash,
                  configuration: selected?.configuration,
                })}
              </pre>
            </>
          ) : null}
        </article>
      ) : null}
      {section === "Uncertainty Input Readiness" || (kind === "model" && section === "Uncertainty Rules") ? (
        <article aria-label="QRA source population">
          <h3>Explicit {kind === "model" ? "input definitions" : "source population"}</h3>
          <div className="wave2bTableScroll">
            <table>
              <thead>
                <tr>
                  <th>Reference</th>
                  <th>Classification</th>
                  <th>Evidence / rationale</th>
                </tr>
              </thead>
              <tbody>
                {inputRows.map((item, index) => (
                  <tr key={`${text(item.ref ?? item.source_item_ref)}-${index}`}>
                    <td>{text(item.ref ?? item.source_item_ref ?? item.code ?? item.id)}</td>
                    <td>{text(item.mode ?? item.uncertainty_classification ?? item.type)}</td>
                    <td>
                      {text(item.rationale)}
                      <small>
                        {rows(item.evidence_refs)
                          .map((ref) => text(ref.reference ?? ref.source_reference))
                          .join(" · ")}
                      </small>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager
            label="source inputs"
            page={rowPage}
            total={itemPage.total}
            size={itemPage.page_size}
            busy={busy}
            onChange={(page) => void execute(() => loadItemPage(page), "Governed input page loaded.")}
          />
        </article>
      ) : null}
      {payload ? (
        <article aria-label={`QRA ${section}`}>
          <h3>{section} — governed backend context</h3>
          <pre>{json(payload)}</pre>
          <p>
            Context references are read-only. No Risk, Basic Data, Owner, FEL/PDRI, FIN, Budget, schedule or Gate/FID
            authority is changed.
          </p>
        </article>
      ) : null}
      {section === "History" ? (
        <article aria-label="QRA immutable history">
          <h3>Immutable historical {kind === "model" ? "definitions" : "assessments"}</h3>
          <p>
            Completed/approved records remain frozen. Current staleness projections do not rewrite historical hashes;
            refresh apply creates a successor DRAFT.
          </p>
          <pre>
            {json({
              number: selected?.number,
              model_number: selected?.model_number,
              version: selected?.version,
              hash: selected?.hash,
              snapshot: selected?.snapshot_json,
              aggregate: selected?.aggregate_json,
            })}
          </pre>
        </article>
      ) : null}
      {selected ? (
        <article aria-label="QRA governance actions">
          <h3>Governed lifecycle</h3>
          <Field label="Review / approval comments" value={comments} onChange={setComments} />
          <div className="wave2bToolbar">
            {(
              [
                ["submit", "Submit for review"],
                ["review", "Review definition"],
                ["complete", "Complete source assessment"],
                ["approve", "Approve for analysis"],
              ] as const
            )
              .filter(([action]) => entityAllows(action))
              .map(([action, label]) => (
                <button
                  key={action}
                  type="button"
                  disabled={busy || editing}
                  onClick={() => void execute(() => perform(action), `${label} completed under backend authority.`)}
                >
                  {label}
                </button>
              ))}
            <button
              type="button"
              disabled={busy || editing}
              onClick={() =>
                void execute(async () => {
                  setPreview(await qraFoundationApi.refreshPreview(token, kind, selected.id));
                }, "Refresh preview persisted=false; history unchanged.")
              }
            >
              Refresh Preview
            </button>
            {entityAllows("refresh_apply") ? (
              <button
                type="button"
                disabled={busy || editing}
                onClick={() =>
                  void execute(() => perform("refresh-apply"), "Successor DRAFT created; frozen history preserved.")
                }
              >
                Apply refresh as successor DRAFT
              </button>
            ) : null}
          </div>
          <p>
            Only backend-authorized actions are shown. Independent reviewers/approvers must use their own authorized
            accounts.
          </p>
        </article>
      ) : null}
      {preview ? (
        <article aria-label="QRA non-persisted preview">
          <strong>persisted={String(preview.persisted)}</strong>
          <pre>{json(preview)}</pre>
        </article>
      ) : null}
    </section>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
  type?: "text" | "date" | "number";
}) {
  return (
    <label>
      {label}
      <input aria-label={label} type={type} value={value ?? ""} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}
function Select({
  label,
  value,
  choices,
  onChange,
  disabled = false,
}: {
  label: string;
  value: string;
  choices: Array<{ value: string; label: string }>;
  onChange: (next: string) => void;
  disabled?: boolean;
}) {
  return (
    <label>
      {label}
      <select aria-label={label} value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
        <option value="">Select…</option>
        {choices.map((choice) => (
          <option key={choice.value} value={choice.value}>
            {choice.label}
          </option>
        ))}
      </select>
    </label>
  );
}
function JsonField({ label, value, onChange }: { label: string; value: string; onChange: (next: string) => void }) {
  return (
    <label>
      {label}
      <textarea
        aria-label={label}
        rows={6}
        spellCheck={false}
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}
function Pager({
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
