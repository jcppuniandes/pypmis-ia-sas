/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import {
  AlertTriangle,
  CheckCircle2,
  FilePlus2,
  History,
  Link2,
  Plus,
  RefreshCw,
  Save,
  Send,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { strategicBenefitsApi, type BenefitWrite, type BenefitsPlanVersionUpdate, type MeasureWrite } from "./api";
import type {
  BenefitMeasure,
  BenefitOwner,
  BenefitsOptions,
  BenefitsPlanHistory,
  BenefitsPlanQueue,
  BenefitsPlanVersion,
  BenefitsReadiness,
  BenefitsRefreshPreview,
  BenefitsTraceabilityPage,
  StrategicBenefit,
  StrategicBenefitsPlan,
} from "./types";
import "./strategicBenefits.css";

type View =
  | "mine"
  | "overview"
  | "strategic-alignment"
  | "outputs"
  | "outcomes"
  | "register"
  | "measures"
  | "owners"
  | "baselines-targets"
  | "expected-value"
  | "dependencies"
  | "assumptions-constraints"
  | "risk-references"
  | "traceability"
  | "readiness"
  | "history";

const VIEW_BY_ROUTE: Record<string, View> = {
  "strategic-benefits-my": "mine",
  "strategic-benefits-overview": "overview",
  "strategic-benefits-strategic-alignment": "strategic-alignment",
  "strategic-benefits-outputs": "outputs",
  "strategic-benefits-outcomes": "outcomes",
  "strategic-benefits-register": "register",
  "strategic-benefits-measures": "measures",
  "strategic-benefits-owners": "owners",
  "strategic-benefits-baselines-targets": "baselines-targets",
  "strategic-benefits-expected-value": "expected-value",
  "strategic-benefits-dependencies": "dependencies",
  "strategic-benefits-assumptions-constraints": "assumptions-constraints",
  "strategic-benefits-risk-references": "risk-references",
  "strategic-benefits-traceability": "traceability",
  "strategic-benefits-readiness": "readiness",
  "strategic-benefits-history": "history",
};

const VIEW_LABELS: Record<View, string> = {
  mine: "My Plans",
  overview: "Overview",
  "strategic-alignment": "Strategic Alignment",
  outputs: "Outputs",
  outcomes: "Outcomes",
  register: "Benefits Register",
  measures: "Measures / KPIs",
  owners: "Benefit Owners",
  "baselines-targets": "Baselines & Targets",
  "expected-value": "Expected Value",
  dependencies: "Dependencies",
  "assumptions-constraints": "Assumptions / Constraints",
  "risk-references": "Risk References",
  traceability: "Traceability",
  readiness: "Readiness",
  history: "History",
};

const QUEUE_LABELS: Record<BenefitsPlanQueue, string> = {
  mine: "My Plans",
  draft: "Draft",
  in_review: "In Review",
  returned: "Returned",
  ready: "Ready",
  completed: "Completed",
  stale: "Stale",
  all_authorized: "All Authorized",
};

type PlanDraft = Pick<
  BenefitsPlanVersion,
  "assumptions_json" | "constraints_json" | "outcomes_json" | "outputs_json" | "overview_json"
>;

const blankPlanDraft = (): PlanDraft => ({
  overview_json: {},
  outputs_json: [],
  outcomes_json: [],
  assumptions_json: [],
  constraints_json: [],
});

const blankOwner = (): BenefitOwner => ({
  owner_type: null,
  owner_user_id: null,
  owner_organization_unit_id: null,
  owner_security_role_id: null,
  owner_reference: null,
  effective_from: null,
  effective_to: null,
  accountability_statement: "",
  acceptance_status: null,
});

const blankBenefit = (): BenefitWrite => ({
  benefit_name: "",
  benefit_description: "",
  benefit_direction: "BENEFIT",
  benefit_type: "",
  benefit_category: "",
  strategic_objective_refs: [],
  source_need_reference: {},
  source_business_analysis_reference: {},
  source_project_proposal_reference: {},
  source_business_case_reference: {},
  expected_outputs: [],
  expected_outcomes: [],
  benefit_statement: "",
  owner: blankOwner(),
  expected_value: {},
  monetizable_flag: false,
  dependencies: [],
  assumptions: [],
  constraints: [],
  risk_references: [],
});

const blankMeasure = (): MeasureWrite => ({
  measure_code: "",
  measure_name: "",
  definition: "",
  unit_of_measure: "",
  direction: "INCREASE",
  is_primary: true,
  baseline_status: "UNKNOWN",
  baseline_value: null,
  baseline_as_of_date: null,
  baseline_source: null,
  baseline_evidence_reference: null,
  baseline_confidence: null,
  target_value: null,
  target_date: null,
  target_basis: null,
  tolerance: {},
  measurement_method: "",
  measurement_frequency: null,
  data_source_description: null,
  measurement_owner_reference: {},
});

function clonePlanDraft(version: BenefitsPlanVersion | null): PlanDraft {
  if (!version) return blankPlanDraft();
  return JSON.parse(
    JSON.stringify({
      overview_json: version.overview_json || {},
      outputs_json: version.outputs_json || [],
      outcomes_json: version.outcomes_json || [],
      assumptions_json: version.assumptions_json || [],
      constraints_json: version.constraints_json || [],
    })
  ) as PlanDraft;
}

function benefitWrite(value: StrategicBenefit): BenefitWrite {
  const copy = JSON.parse(JSON.stringify(value)) as Record<string, unknown>;
  for (const key of [
    "allowed_actions",
    "benefit_number",
    "id",
    "identity_status",
    "measures",
    "revision_version",
    "snapshot_hash",
    "snapshot_id",
    "status",
  ])
    delete copy[key];
  return { ...blankBenefit(), ...copy } as BenefitWrite;
}

function measureWrite(value: BenefitMeasure): MeasureWrite {
  const copy = JSON.parse(JSON.stringify(value)) as Record<string, unknown>;
  for (const key of ["benefit_snapshot_id", "created_at", "id", "measure_hash", "revision_version", "updated_at"])
    delete copy[key];
  return { ...blankMeasure(), ...copy } as MeasureWrite;
}

function recordValue(value: unknown) {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function textValue(value: unknown) {
  return value === null || value === undefined ? "" : String(value);
}

function actionAllowed(plan: StrategicBenefitsPlan | null, version: BenefitsPlanVersion | null, action: string) {
  const key = action.startsWith("can_") ? action : `can_${action.replace(/-/g, "_")}`;
  for (const actions of [version?.allowed_actions, plan?.allowed_actions]) {
    if (Array.isArray(actions) && (actions.includes(action) || actions.includes(key))) return true;
    if (actions && !Array.isArray(actions) && actions[key]) return true;
  }
  return false;
}

function recordsToLines(value: Array<Record<string, unknown>>, field = "description") {
  return value
    .map((item) => String(item[field] || ""))
    .filter(Boolean)
    .join("\n");
}

function linesToRecords(value: string, field = "description") {
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => ({ [field]: item }));
}

function statusValue(readiness: BenefitsReadiness | null, version: BenefitsPlanVersion | null) {
  return (
    readiness?.overall_benefits_readiness || readiness?.status || version?.overall_benefits_readiness || "NOT_STARTED"
  );
}

export default function StrategicBenefitsWorkspace({ token, initialView }: { token: string; initialView?: string }) {
  const [view, setView] = useState<View>(VIEW_BY_ROUTE[initialView || ""] || "mine");
  const [queue, setQueue] = useState<BenefitsPlanQueue>("mine");
  const [records, setRecords] = useState<StrategicBenefitsPlan[]>([]);
  const [selectedId, setSelectedId] = useState(0);
  const [benefitId, setBenefitId] = useState(0);
  const [measureId, setMeasureId] = useState(0);
  const [draft, setDraft] = useState<PlanDraft>(blankPlanDraft);
  const [benefitDraft, setBenefitDraft] = useState<BenefitWrite>(blankBenefit);
  const [measureDraft, setMeasureDraft] = useState<MeasureWrite>(blankMeasure);
  const [readiness, setReadiness] = useState<BenefitsReadiness | null>(null);
  const [history, setHistory] = useState<BenefitsPlanHistory[]>([]);
  const [traceability, setTraceability] = useState<BenefitsTraceabilityPage | null>(null);
  const [preview, setPreview] = useState<BenefitsRefreshPreview | null>(null);
  const [options, setOptions] = useState<BenefitsOptions | null>(null);
  const [projectId, setProjectId] = useState("");
  const [versionPurpose, setVersionPurpose] = useState("INITIAL_BENEFITS_PLAN");
  const [felStage, setFelStage] = useState("");
  const [reviewerId, setReviewerId] = useState("");
  const [reason, setReason] = useState("");
  const [search, setSearch] = useState("");
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const selected = records.find((item) => item.id === selectedId) || records[0] || null;
  const version = selected?.current_version || null;
  const benefits = version?.benefits || [];
  const selectedBenefit = benefits.find((item) => item.id === benefitId) || benefits[0] || null;
  const measures = selectedBenefit?.measures || [];
  const selectedMeasure = measures.find((item) => item.id === measureId) || measures[0] || null;

  const metrics = useMemo(
    () => [
      { label: "Plans", value: records.length },
      { label: "Benefits", value: benefits.length },
      { label: "Readiness", value: statusValue(readiness, version) },
      { label: "Provider", value: readiness?.can_supply_investment_gate_evidence ? "AVAILABLE" : "NOT SUPPLYING" },
    ],
    [records.length, benefits.length, readiness, version]
  );

  async function loadPage(cursor?: string | null, append = false, preferredId?: number) {
    const page = await strategicBenefitsApi.listPage(token, { queue, search, cursor, limit: 50 });
    setRecords((current) => (append ? [...current, ...page.items] : page.items));
    setNextCursor(page.nextCursor);
    if (!append) setSelectedId(preferredId || page.items[0]?.id || 0);
  }

  async function reload(planId = selected?.id) {
    if (!planId) return loadPage();
    const result = await strategicBenefitsApi.detail(token, planId);
    setRecords((current) => {
      const remaining = current.filter((item) => item.id !== result.id);
      return [result, ...remaining];
    });
    setSelectedId(result.id);
  }

  useEffect(() => setView(VIEW_BY_ROUTE[initialView || ""] || "mine"), [initialView]);
  useEffect(() => {
    void loadPage().catch((error) =>
      setMessage(error instanceof Error ? error.message : "Unable to load Benefits Plans")
    );
  }, [token, queue]);
  useEffect(() => {
    if (!selected || !version) {
      setDraft(blankPlanDraft());
      setReadiness(null);
      setHistory([]);
      return;
    }
    setDraft(clonePlanDraft(version));
    setFelStage(version.fel_stage_code || "");
    setReviewerId(version.reviewer_user_id ? String(version.reviewer_user_id) : "");
    setBenefitId(version.benefits?.[0]?.id || 0);
    void Promise.all([
      strategicBenefitsApi.options(token, selected.project_workspace_id),
      strategicBenefitsApi.readiness(token, selected.id),
      strategicBenefitsApi.history(token, selected.id),
    ])
      .then(([optionRows, readinessResult, historyRows]) => {
        setOptions(optionRows);
        setReadiness(readinessResult);
        setHistory(historyRows);
      })
      .catch((error) => setMessage(error instanceof Error ? error.message : "Unable to load Plan evidence"));
  }, [selected?.id, version?.id]);
  useEffect(() => {
    if (!selectedBenefit) {
      setBenefitDraft(blankBenefit());
      setMeasureId(0);
      return;
    }
    setBenefitDraft(benefitWrite(selectedBenefit));
    setMeasureId(selectedBenefit.measures?.[0]?.id || 0);
  }, [selectedBenefit?.id, selectedBenefit?.revision_version]);
  useEffect(() => {
    setMeasureDraft(selectedMeasure ? measureWrite(selectedMeasure) : blankMeasure());
  }, [selectedMeasure?.id, selectedMeasure?.revision_version]);
  useEffect(() => {
    if (view !== "traceability" || !selected) return;
    void strategicBenefitsApi
      .traceabilityPage(token, selected.id)
      .then(setTraceability)
      .catch((error) => setMessage(error instanceof Error ? error.message : "Unable to load traceability"));
  }, [view, selected?.id]);

  async function execute(work: () => Promise<unknown>, success: string) {
    setBusy(true);
    setMessage("");
    try {
      await work();
      await reload();
      setMessage(success);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Benefits Plan action failed");
    } finally {
      setBusy(false);
    }
  }

  async function create() {
    setBusy(true);
    try {
      const result = await strategicBenefitsApi.create(token, Number(projectId), versionPurpose);
      await loadPage(null, false, result.id);
      setMessage(`${result.plan_number} created with one governed identity for the Project Workspace.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Benefits Plan creation failed");
    } finally {
      setBusy(false);
    }
  }

  function savePlan() {
    if (!selected || !version) return;
    const payload: BenefitsPlanVersionUpdate = {
      ...draft,
      fel_stage_code: felStage || null,
      reviewer_user_id: reviewerId ? Number(reviewerId) : null,
    };
    void execute(
      () => strategicBenefitsApi.updateVersion(token, selected, version, payload),
      "Benefits Plan DRAFT saved under ETag control."
    );
  }

  function saveBenefit() {
    if (!selected || !version) return;
    if (selectedBenefit) {
      void execute(
        () => strategicBenefitsApi.updateBenefit(token, selected, version, selectedBenefit, benefitDraft),
        `${selectedBenefit.benefit_number} updated without changing its stable identity.`
      );
      return;
    }
    void execute(
      () => strategicBenefitsApi.addBenefit(token, selected, version, benefitDraft),
      "Benefit added with a stable governed identity."
    );
  }

  function saveMeasure() {
    if (!selected || !version || !selectedBenefit) return;
    const payload: MeasureWrite = {
      ...measureDraft,
      baseline_value: measureDraft.baseline_status === "UNKNOWN" ? null : measureDraft.baseline_value,
      baseline_as_of_date: measureDraft.baseline_status === "UNKNOWN" ? null : measureDraft.baseline_as_of_date,
    };
    if (selectedMeasure) {
      void execute(
        () => strategicBenefitsApi.updateMeasure(token, selected, version, selectedBenefit, selectedMeasure, payload),
        "Measure updated under ETag control."
      );
      return;
    }
    void execute(
      () => strategicBenefitsApi.addMeasure(token, selected, version, selectedBenefit, payload),
      "Measure added to the selected stable Benefit."
    );
  }

  function lifecycle(action: "submit" | "start-review" | "return" | "complete" | "void") {
    if (!selected || !version) return;
    void execute(
      () => strategicBenefitsApi.lifecycle(token, selected, version, action, reason || undefined),
      `Benefits Plan lifecycle action ${action} completed.`
    );
  }

  async function showRefreshPreview() {
    if (!selected) return;
    setBusy(true);
    try {
      setPreview(await strategicBenefitsApi.refreshPreview(token, selected.id));
      setMessage("Refresh Preview resolved with persisted=false; the completed version remains immutable.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Refresh Preview failed");
    } finally {
      setBusy(false);
    }
  }

  const canEditPlan = actionAllowed(selected, version, "edit");
  const canEditBenefit = actionAllowed(selected, version, selectedBenefit ? "edit_benefit" : "add_benefit");

  return (
    <section aria-label="Strategic Benefits Plan and Traceability" className="strategicBenefits">
      <CompactModuleHeader
        description="Govern expected outputs, outcomes, Benefits, measures, ownership and value as one versioned pre-FID evidence source. Benefits actual realization remains outside this release."
        eyebrow="USER MODE · PROJECT DEFINITION & INVESTMENT CASE · GATE 07M-BEN"
        metrics={metrics}
        title="Strategic Benefits Plan & Traceability"
        tone="user"
      />

      {message ? (
        <div className="benefitsMessage" role="status">
          {message}
        </div>
      ) : null}

      <nav aria-label="Strategic Benefits views" className="benefitsTabs">
        {(Object.keys(VIEW_LABELS) as View[]).map((item) => (
          <button
            aria-current={view === item ? "page" : undefined}
            className={view === item ? "active" : ""}
            key={item}
            onClick={() => setView(item)}
            type="button"
          >
            {VIEW_LABELS[item]}
          </button>
        ))}
      </nav>

      <section aria-label="Strategic Benefits queue" className="benefitsQueue">
        <div aria-label="Strategic Benefits queues" role="group">
          {(Object.keys(QUEUE_LABELS) as BenefitsPlanQueue[]).map((item) => (
            <button
              aria-pressed={queue === item}
              className={queue === item ? "active" : ""}
              key={item}
              onClick={() => setQueue(item)}
              type="button"
            >
              {QUEUE_LABELS[item]}
            </button>
          ))}
        </div>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void loadPage();
          }}
        >
          <label>
            Search authorized Plans
            <input value={search} onChange={(event) => setSearch(event.target.value)} />
          </label>
          <button type="submit">Search</button>
        </form>
      </section>

      <div className="benefitsControls">
        <label>
          Benefits Plan
          <select value={selected?.id || 0} onChange={(event) => setSelectedId(Number(event.target.value))}>
            {!records.length ? <option value={0}>No authorized Benefits Plans</option> : null}
            {records.map((item) => (
              <option key={item.id} value={item.id}>
                {item.plan_number} · Project {item.project_workspace_id} · {item.current_version?.status || item.status}
              </option>
            ))}
          </select>
        </label>
        <button disabled={busy || !canEditPlan} onClick={savePlan} type="button">
          <Save size={15} /> Save Plan
        </button>
        <button
          disabled={busy || !actionAllowed(selected, version, "submit")}
          onClick={() => lifecycle("submit")}
          type="button"
        >
          <Send size={15} /> Submit
        </button>
        <button
          disabled={busy || !actionAllowed(selected, version, "start_review")}
          onClick={() => lifecycle("start-review")}
          type="button"
        >
          Start review
        </button>
        <button
          disabled={busy || !actionAllowed(selected, version, "return") || reason.trim().length < 3}
          onClick={() => lifecycle("return")}
          type="button"
        >
          Return
        </button>
        <button
          disabled={busy || !actionAllowed(selected, version, "complete")}
          onClick={() => lifecycle("complete")}
          type="button"
        >
          <CheckCircle2 size={15} /> Complete
        </button>
        <button
          disabled={busy || !actionAllowed(selected, version, "void") || reason.trim().length < 3}
          onClick={() => lifecycle("void")}
          type="button"
        >
          Void
        </button>
        <button
          disabled={busy || !actionAllowed(selected, version, "create_revision")}
          onClick={() =>
            selected &&
            void execute(
              () => strategicBenefitsApi.newRevision(token, selected, "MATERIAL_CHANGE_UPDATE"),
              "Successor DRAFT created; the completed Plan remains immutable."
            )
          }
          type="button"
        >
          <FilePlus2 size={15} /> New revision
        </button>
        <button
          disabled={busy || !actionAllowed(selected, version, "refresh_preview")}
          onClick={() => void showRefreshPreview()}
          type="button"
        >
          <RefreshCw size={15} /> Refresh Preview
        </button>
        <button
          disabled={busy || !preview || !selected || !actionAllowed(selected, version, "refresh_apply")}
          onClick={() =>
            selected &&
            void execute(
              () => strategicBenefitsApi.refreshApply(token, selected),
              "Refresh applied as a new DRAFT Plan version."
            )
          }
          type="button"
        >
          <RefreshCw size={15} /> Apply as new DRAFT
        </button>
      </div>

      {actionAllowed(selected, version, "return") || actionAllowed(selected, version, "void") ? (
        <label className="benefitsReason">
          Return / void reason
          <input value={reason} onChange={(event) => setReason(event.target.value)} />
        </label>
      ) : null}

      <details className="benefitsSurface benefitsCreate" open={!records.length}>
        <summary>Create another governed Strategic Benefits Plan</summary>
        <div>
          <p>
            Uses the canonical Project Workspace identity; it does not create a parallel Project or a second operational
            Benefits Register.
          </p>
          <label>
            Project Workspace ID
            <input inputMode="numeric" value={projectId} onChange={(event) => setProjectId(event.target.value)} />
          </label>
          <label>
            Version purpose
            <select value={versionPurpose} onChange={(event) => setVersionPurpose(event.target.value)}>
              {(options?.version_purposes?.length ? options.version_purposes : [versionPurpose]).map((item) => (
                <option key={item}>{item}</option>
              ))}
            </select>
          </label>
          <button disabled={busy || !Number(projectId)} onClick={() => void create()} type="button">
            <FilePlus2 size={15} /> Create Benefits Plan
          </button>
        </div>
      </details>

      {selected && version ? (
        <section className="benefitsSurface">
          <header>
            <div>
              <span>{VIEW_LABELS[view]}</span>
              <h3>
                {selected.plan_number} · Version {version.version_number}
              </h3>
            </div>
            <Status value={statusValue(readiness, version)} />
          </header>
          <div className="benefitsFacts">
            <Fact label="Project Workspace" value={selected.project_workspace_id} />
            <Fact label="Lifecycle" value={version.status} />
            <Fact label="Purpose" value={version.version_purpose} />
            <Fact label="FEL stage" value={version.fel_stage_code || "Not assigned"} />
            <Fact label="Source" value={version.source_current ? "CURRENT" : "STALE"} />
            <Fact label="Provider supply" value={readiness?.can_supply_investment_gate_evidence ? "YES" : "NO"} />
          </div>
          {renderView({
            view,
            draft,
            setDraft,
            canEditPlan,
            benefitDraft,
            setBenefitDraft,
            selectedBenefit,
            benefits,
            benefitId,
            setBenefitId,
            canEditBenefit,
            saveBenefit,
            measureDraft,
            setMeasureDraft,
            selectedMeasure,
            measures,
            measureId,
            setMeasureId,
            saveMeasure,
            readiness,
            history,
            traceability,
            setTraceability,
            selected,
            token,
            options,
            felStage,
            setFelStage,
            reviewerId,
            setReviewerId,
          })}
        </section>
      ) : null}

      {nextCursor ? (
        <button
          className="benefitsLoadMore"
          disabled={busy}
          onClick={() => void loadPage(nextCursor, true)}
          type="button"
        >
          Load more Plans
        </button>
      ) : null}

      {preview ? (
        <section aria-label="Strategic Benefits refresh preview" className="benefitsSurface benefitsPreview">
          <h3>Refresh Preview · persisted=false</h3>
          <div className="benefitsPreviewGrid">
            {(
              [
                "source_delta",
                "benefit_delta",
                "owner_delta",
                "measure_delta",
                "target_delta",
                "policy_delta",
                "readiness_delta",
              ] as const
            ).map((key) => (
              <PreviewColumn key={key} label={key.replace(/_/g, " ")} value={preview[key]} />
            ))}
          </div>
          <IssueList blockers={preview.blockers} warnings={preview.warnings} />
        </section>
      ) : null}

      <p className="benefitsBoundary">
        <strong>Domain boundary:</strong> Output is what the Project delivers; Outcome is the change produced when the
        output is used; Benefit is the measurable positive or negative change enabled by the outcome; Value is its
        strategic, economic or financial significance. This workspace does not record actual KPI, realized Benefit,
        procurement execution or Project delivery.
      </p>
    </section>
  );
}

type RenderProps = {
  view: View;
  draft: PlanDraft;
  setDraft: React.Dispatch<React.SetStateAction<PlanDraft>>;
  canEditPlan: boolean;
  benefitDraft: BenefitWrite;
  setBenefitDraft: React.Dispatch<React.SetStateAction<BenefitWrite>>;
  selectedBenefit: StrategicBenefit | null;
  benefits: StrategicBenefit[];
  benefitId: number;
  setBenefitId: (value: number) => void;
  canEditBenefit: boolean;
  saveBenefit: () => void;
  measureDraft: MeasureWrite;
  setMeasureDraft: React.Dispatch<React.SetStateAction<MeasureWrite>>;
  selectedMeasure: BenefitMeasure | null;
  measures: BenefitMeasure[];
  measureId: number;
  setMeasureId: (value: number) => void;
  saveMeasure: () => void;
  readiness: BenefitsReadiness | null;
  history: BenefitsPlanHistory[];
  traceability: BenefitsTraceabilityPage | null;
  setTraceability: React.Dispatch<React.SetStateAction<BenefitsTraceabilityPage | null>>;
  selected: StrategicBenefitsPlan;
  token: string;
  options: BenefitsOptions | null;
  felStage: string;
  setFelStage: (value: string) => void;
  reviewerId: string;
  setReviewerId: (value: string) => void;
};

function renderView(props: RenderProps) {
  const {
    view,
    draft,
    setDraft,
    canEditPlan,
    benefitDraft,
    setBenefitDraft,
    selectedBenefit,
    benefits,
    benefitId,
    setBenefitId,
    canEditBenefit,
    saveBenefit,
    measureDraft,
    setMeasureDraft,
    selectedMeasure,
    measures,
    setMeasureId,
    saveMeasure,
    readiness,
    history,
    traceability,
    setTraceability,
    selected,
    token,
    options,
    felStage,
    setFelStage,
    reviewerId,
    setReviewerId,
  } = props;
  const updateBenefit = <K extends keyof BenefitWrite>(key: K, value: BenefitWrite[K]) =>
    setBenefitDraft((current) => ({ ...current, [key]: value }));
  const updateMeasure = <K extends keyof MeasureWrite>(key: K, value: MeasureWrite[K]) =>
    setMeasureDraft((current) => ({ ...current, [key]: value }));
  const owner = { ...blankOwner(), ...(benefitDraft.owner || {}) };
  const expectedValue = recordValue(benefitDraft.expected_value);

  if (view === "mine" || view === "overview")
    return (
      <div className="benefitsOverview">
        <article>
          <strong>Output</strong>
          <p>What the Project delivers. It is traceability evidence, not a WBS or Deliverable Manager.</p>
        </article>
        <article>
          <strong>Outcome</strong>
          <p>What changes when the organization uses the delivered Output.</p>
        </article>
        <article>
          <strong>Benefit</strong>
          <p>The measurable change enabled by an Outcome and preserved under a stable BEN number.</p>
        </article>
        <article>
          <strong>Value</strong>
          <p>The strategic, economic, financial or non-financial significance of the Benefit.</p>
        </article>
        <label>
          FEL stage
          <input disabled={!canEditPlan} value={felStage} onChange={(event) => setFelStage(event.target.value)} />
        </label>
        <label>
          Reviewer user ID
          <input
            disabled={!canEditPlan}
            inputMode="numeric"
            value={reviewerId}
            onChange={(event) => setReviewerId(event.target.value)}
          />
        </label>
        <JsonSummary label="Source lineage" value={selected.current_version?.source_references_json || {}} />
      </div>
    );
  if (view === "strategic-alignment")
    return (
      <div className="benefitsGrid">
        <JsonSummary label="Governed source lineage" value={selected.current_version?.source_references_json || {}} />
        <JsonSummary
          label="Benefit strategic objective references"
          value={benefits.map((item) => ({
            benefit_number: item.benefit_number,
            strategic_objective_refs: item.strategic_objective_refs,
          }))}
        />
        <p className="benefitsNotice">
          <Link2 size={17} /> Strategic Objectives, Need / Opportunity, Business Analysis, Recommended Option, Project
          and Business Case remain governed by their source domains. This view never asks the user to re-enter that
          lineage.
        </p>
      </div>
    );
  if (view === "outputs" || view === "outcomes") {
    const key = view === "outputs" ? "outputs_json" : "outcomes_json";
    const noun = view === "outputs" ? "Expected outputs" : "Expected outcomes";
    return (
      <LinesEditor
        disabled={!canEditPlan}
        help={
          view === "outputs"
            ? "One Project-delivered output per line."
            : "One business or operational change enabled by output use per line."
        }
        label={noun}
        onChange={(value) =>
          setDraft((current) => ({
            ...current,
            [key]: linesToRecords(value, view === "outputs" ? "output_name" : "outcome_name"),
          }))
        }
        value={recordsToLines(draft[key], view === "outputs" ? "output_name" : "outcome_name")}
      />
    );
  }
  if (["register", "owners", "expected-value", "dependencies", "risk-references"].includes(view))
    return (
      <div className="benefitsRegister">
        <BenefitPicker
          benefits={benefits}
          selected={benefitId}
          setSelected={setBenefitId}
          startNew={() => {
            setBenefitId(0);
            setBenefitDraft(blankBenefit());
          }}
        />
        {view === "register" ? (
          <div className="benefitsEditorGrid">
            <Field
              disabled={!canEditBenefit}
              label="Benefit name"
              value={benefitDraft.benefit_name}
              onChange={(value) => updateBenefit("benefit_name", value)}
            />
            <Field
              disabled={!canEditBenefit}
              label="Benefit statement"
              value={benefitDraft.benefit_statement}
              onChange={(value) => updateBenefit("benefit_statement", value)}
            />
            <Field
              disabled={!canEditBenefit}
              label="Benefit description"
              value={benefitDraft.benefit_description}
              onChange={(value) => updateBenefit("benefit_description", value)}
              multiline
            />
            <CatalogField
              disabled={!canEditBenefit}
              label="Benefit direction"
              options={options?.benefit_directions || ["BENEFIT", "DISBENEFIT"]}
              value={benefitDraft.benefit_direction}
              onChange={(value) => updateBenefit("benefit_direction", value)}
            />
            <CatalogField
              disabled={!canEditBenefit}
              label="Benefit type"
              options={options?.benefit_types || []}
              value={benefitDraft.benefit_type}
              onChange={(value) => updateBenefit("benefit_type", value)}
            />
            <CatalogField
              disabled={!canEditBenefit}
              label="Benefit category"
              options={options?.benefit_categories || []}
              value={benefitDraft.benefit_category || ""}
              onChange={(value) => updateBenefit("benefit_category", value || null)}
            />
            <LinesEditor
              disabled={!canEditBenefit}
              label="Expected output links"
              value={recordsToLines(benefitDraft.expected_outputs, "reference")}
              onChange={(value) => updateBenefit("expected_outputs", linesToRecords(value, "reference"))}
            />
            <LinesEditor
              disabled={!canEditBenefit}
              label="Expected outcome links"
              value={recordsToLines(benefitDraft.expected_outcomes, "reference")}
              onChange={(value) => updateBenefit("expected_outcomes", linesToRecords(value, "reference"))}
            />
          </div>
        ) : null}
        {view === "owners" ? (
          <div className="benefitsEditorGrid">
            <Field
              disabled={!canEditBenefit}
              label="Owner reference"
              value={owner.owner_reference || ""}
              onChange={(value) => updateBenefit("owner", { ...owner, owner_reference: value || null })}
            />
            <CatalogField
              disabled={!canEditBenefit}
              label="Owner type"
              options={options?.owner_types || ["USER", "ORGANIZATION_UNIT", "SECURITY_ROLE", "EXTERNAL_REFERENCE"]}
              value={owner.owner_type || ""}
              onChange={(value) => updateBenefit("owner", { ...owner, owner_type: value || null })}
            />
            <Field
              disabled={!canEditBenefit}
              label="Effective from"
              type="date"
              value={owner.effective_from || ""}
              onChange={(value) => updateBenefit("owner", { ...owner, effective_from: value || null })}
            />
            <Field
              disabled={!canEditBenefit}
              label="Effective to"
              type="date"
              value={owner.effective_to || ""}
              onChange={(value) => updateBenefit("owner", { ...owner, effective_to: value || null })}
            />
            <Field
              disabled={!canEditBenefit}
              label="Accountability statement"
              multiline
              value={owner.accountability_statement}
              onChange={(value) => updateBenefit("owner", { ...owner, accountability_statement: value })}
            />
            <CatalogField
              disabled={!canEditBenefit}
              label="Owner acceptance status"
              options={options?.owner_acceptance_statuses || ["PENDING", "ACCEPTED", "DECLINED"]}
              value={owner.acceptance_status || ""}
              onChange={(value) => updateBenefit("owner", { ...owner, acceptance_status: value || null })}
            />
            <p className="benefitsNotice">
              <ShieldCheck size={17} /> Benefit Owner is business accountability; it is not automatically the Project
              Manager.
            </p>
          </div>
        ) : null}
        {view === "expected-value" ? (
          <div className="benefitsEditorGrid">
            <label className="benefitsCheck">
              <input
                checked={benefitDraft.monetizable_flag}
                disabled={!canEditBenefit}
                onChange={(event) => updateBenefit("monetizable_flag", event.target.checked)}
                type="checkbox"
              />{" "}
              Monetizable Benefit
            </label>
            <Field
              disabled={!canEditBenefit || !benefitDraft.monetizable_flag}
              label="Expected value"
              value={textValue(expectedValue.amount)}
              onChange={(value) => updateBenefit("expected_value", { ...expectedValue, amount: value || null })}
            />
            <Field
              disabled={!canEditBenefit || !benefitDraft.monetizable_flag}
              label="Currency"
              value={textValue(expectedValue.currency)}
              onChange={(value) => updateBenefit("expected_value", { ...expectedValue, currency: value || null })}
            />
            <Field
              disabled={!canEditBenefit}
              label="Value description"
              multiline
              value={textValue(expectedValue.description)}
              onChange={(value) => updateBenefit("expected_value", { ...expectedValue, description: value })}
            />
            <p className="benefitsNotice">
              FIN remains authoritative for financial calculations. Store governed FIN references and hashes; do not
              recompute NPV, IRR or cash flow here.
            </p>
          </div>
        ) : null}
        {view === "dependencies" ? (
          <LinesEditor
            disabled={!canEditBenefit}
            label="Benefit dependencies"
            value={recordsToLines(benefitDraft.dependencies)}
            onChange={(value) => updateBenefit("dependencies", linesToRecords(value))}
          />
        ) : null}
        {view === "risk-references" ? (
          <LinesEditor
            disabled={!canEditBenefit}
            help="References only; Risk Register remains authoritative."
            label="Risk references"
            value={recordsToLines(benefitDraft.risk_references, "risk_id")}
            onChange={(value) => updateBenefit("risk_references", linesToRecords(value, "risk_id"))}
          />
        ) : null}
        <button disabled={!canEditBenefit || !benefitDraft.benefit_name.trim()} onClick={saveBenefit} type="button">
          <Save size={15} /> {selectedBenefit ? `Save ${selectedBenefit.benefit_number}` : "Add Benefit"}
        </button>
      </div>
    );
  if (view === "measures" || view === "baselines-targets")
    return (
      <div className="benefitsMeasure">
        <BenefitPicker benefits={benefits} selected={benefitId} setSelected={setBenefitId} />
        <div className="benefitsPickerRow">
          <label>
            Measure / KPI
            <select value={selectedMeasure?.id || 0} onChange={(event) => setMeasureId(Number(event.target.value))}>
              <option value={0}>New measure</option>
              {measures.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.measure_code || "KPI"} · {item.measure_name}
                </option>
              ))}
            </select>
          </label>
          <button
            disabled={!selectedBenefit}
            onClick={() => {
              setMeasureId(0);
              setMeasureDraft(blankMeasure());
            }}
            type="button"
          >
            <Plus size={15} /> New measure
          </button>
        </div>
        <div className="benefitsEditorGrid">
          <Field
            disabled={!canEditBenefit}
            label="Measure code"
            value={measureDraft.measure_code}
            onChange={(value) => updateMeasure("measure_code", value)}
          />
          <Field
            disabled={!canEditBenefit}
            label="Measure name"
            value={measureDraft.measure_name}
            onChange={(value) => updateMeasure("measure_name", value)}
          />
          <Field
            disabled={!canEditBenefit}
            label="Definition"
            multiline
            value={measureDraft.definition}
            onChange={(value) => updateMeasure("definition", value)}
          />
          <CatalogField
            disabled={!canEditBenefit}
            label="Unit of measure"
            options={options?.units_of_measure || []}
            value={measureDraft.unit_of_measure}
            onChange={(value) => updateMeasure("unit_of_measure", value)}
          />
          <CatalogField
            disabled={!canEditBenefit}
            label="Direction"
            options={
              options?.measure_directions || [
                "INCREASE",
                "DECREASE",
                "MAINTAIN_ABOVE",
                "MAINTAIN_BELOW",
                "BINARY_ACHIEVEMENT",
              ]
            }
            value={measureDraft.direction}
            onChange={(value) => updateMeasure("direction", value)}
          />
          <label className="benefitsCheck">
            <input
              checked={measureDraft.is_primary}
              disabled={!canEditBenefit}
              onChange={(event) => updateMeasure("is_primary", event.target.checked)}
              type="checkbox"
            />{" "}
            Primary measure
          </label>
          <CatalogField
            disabled={!canEditBenefit}
            label="Baseline status"
            options={["UNKNOWN", "KNOWN"]}
            value={measureDraft.baseline_status}
            onChange={(value) => updateMeasure("baseline_status", value as "KNOWN" | "UNKNOWN")}
          />
          <Field
            disabled={!canEditBenefit || measureDraft.baseline_status === "UNKNOWN"}
            label="Baseline value"
            value={textValue(measureDraft.baseline_value)}
            onChange={(value) => updateMeasure("baseline_value", value || null)}
          />
          <Field
            disabled={!canEditBenefit || measureDraft.baseline_status === "UNKNOWN"}
            label="Baseline as-of date"
            type="date"
            value={measureDraft.baseline_as_of_date || ""}
            onChange={(value) => updateMeasure("baseline_as_of_date", value || null)}
          />
          <Field
            disabled={!canEditBenefit}
            label="Baseline source"
            value={measureDraft.baseline_source || ""}
            onChange={(value) => updateMeasure("baseline_source", value || null)}
          />
          <Field
            disabled={!canEditBenefit}
            label="Target value"
            value={textValue(measureDraft.target_value)}
            onChange={(value) => updateMeasure("target_value", value || null)}
          />
          <Field
            disabled={!canEditBenefit}
            label="Target date"
            type="date"
            value={measureDraft.target_date || ""}
            onChange={(value) => updateMeasure("target_date", value || null)}
          />
          <Field
            disabled={!canEditBenefit}
            label="Target basis"
            value={measureDraft.target_basis || ""}
            onChange={(value) => updateMeasure("target_basis", value || null)}
          />
          <Field
            disabled={!canEditBenefit}
            label="Measurement method"
            multiline
            value={measureDraft.measurement_method}
            onChange={(value) => updateMeasure("measurement_method", value)}
          />
          <CatalogField
            disabled={!canEditBenefit}
            label="Measurement frequency"
            options={options?.measurement_frequencies || []}
            value={measureDraft.measurement_frequency || ""}
            onChange={(value) => updateMeasure("measurement_frequency", value || null)}
          />
          <Field
            disabled={!canEditBenefit}
            label="Data source description"
            value={measureDraft.data_source_description || ""}
            onChange={(value) => updateMeasure("data_source_description", value || null)}
          />
        </div>
        {measureDraft.baseline_status === "UNKNOWN" ? (
          <p className="benefitsNotice">
            <AlertTriangle size={17} /> Baseline is explicitly UNKNOWN. It remains null and is never silently converted
            to zero.
          </p>
        ) : null}
        <button
          disabled={!canEditBenefit || !selectedBenefit || !measureDraft.measure_name.trim()}
          onClick={saveMeasure}
          type="button"
        >
          <Save size={15} /> {selectedMeasure ? "Save measure" : "Add measure"}
        </button>
      </div>
    );
  if (view === "assumptions-constraints")
    return (
      <div className="benefitsEditorGrid">
        <LinesEditor
          disabled={!canEditPlan}
          label="Plan assumptions"
          value={recordsToLines(draft.assumptions_json)}
          onChange={(value) => setDraft((current) => ({ ...current, assumptions_json: linesToRecords(value) }))}
        />
        <LinesEditor
          disabled={!canEditPlan}
          label="Plan constraints"
          value={recordsToLines(draft.constraints_json)}
          onChange={(value) => setDraft((current) => ({ ...current, constraints_json: linesToRecords(value) }))}
        />
      </div>
    );
  if (view === "traceability")
    return (
      <TraceabilityTable
        page={traceability}
        loadMore={async () => {
          if (!traceability?.nextCursor) return;
          const next = await strategicBenefitsApi.traceabilityPage(token, selected.id, traceability.nextCursor);
          setTraceability({ ...next, items: [...traceability.items, ...next.items] });
        }}
      />
    );
  if (view === "readiness") return <ReadinessPanel value={readiness} />;
  return <HistoryPanel rows={history} />;
}

function BenefitPicker({
  benefits,
  selected,
  setSelected,
  startNew,
}: {
  benefits: StrategicBenefit[];
  selected: number;
  setSelected: (value: number) => void;
  startNew?: () => void;
}) {
  return (
    <div className="benefitsPickerRow">
      <label>
        Stable Benefit identity
        <select value={selected} onChange={(event) => setSelected(Number(event.target.value))}>
          {!benefits.length ? <option value={0}>No Benefits</option> : null}
          {benefits.map((item) => (
            <option key={item.id} value={item.id}>
              {item.benefit_number} · {item.benefit_name}
            </option>
          ))}
        </select>
      </label>
      {startNew ? (
        <button onClick={startNew} type="button">
          <Plus size={15} /> New Benefit
        </button>
      ) : null}
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string | number }) {
  return (
    <article>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}
function Status({ value }: { value: string }) {
  return <span className={`benefitsStatus ${value.toLowerCase()}`}>{value}</span>;
}
function Field({
  label,
  value,
  onChange,
  disabled,
  multiline = false,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
  multiline?: boolean;
  type?: string;
}) {
  return (
    <label className="benefitsField">
      <span>{label}</span>
      {multiline ? (
        <textarea
          aria-label={label}
          disabled={disabled}
          rows={4}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      ) : (
        <input
          aria-label={label}
          disabled={disabled}
          type={type}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      )}
    </label>
  );
}
function CatalogField({
  label,
  value,
  options,
  onChange,
  disabled,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
  disabled: boolean;
}) {
  return (
    <label className="benefitsField">
      <span>{label}</span>
      <select aria-label={label} disabled={disabled} value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">Select…</option>
        {[...new Set(options)].map((item) => (
          <option key={item}>{item}</option>
        ))}
      </select>
    </label>
  );
}
function LinesEditor({
  label,
  value,
  onChange,
  disabled,
  help,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
  help?: string;
}) {
  return (
    <label className="benefitsField">
      <span>{label}</span>
      {help ? <small>{help}</small> : null}
      <textarea
        aria-label={label}
        disabled={disabled}
        rows={8}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}
function JsonSummary({ label, value }: { label: string; value: unknown }) {
  return (
    <section className="benefitsJson">
      <h4>{label}</h4>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </section>
  );
}

function ReadinessPanel({ value }: { value: BenefitsReadiness | null }) {
  if (!value) return <p>Backend readiness is not available.</p>;
  return (
    <div className="benefitsReadiness">
      <header>
        <div>
          <ShieldCheck size={20} />
          <strong>Backend-owned Benefits Readiness</strong>
        </div>
        <Status value={value.overall_benefits_readiness || value.status} />
      </header>
      <div>
        {Object.entries(value.dimensions).map(([name, state]) => (
          <article key={name}>
            <span>{name.replace(/_/g, " ")}</span>
            <Status value={state} />
          </article>
        ))}
      </div>
      <section>
        <h4>Coverage · explicit denominators</h4>
        {Object.entries(value.coverage || {}).map(([name, amount]) => (
          <p key={name}>
            <span>{name.replace(/_/g, " ")}</span>
            <strong>{amount}%</strong>
          </p>
        ))}
      </section>
      <IssueList blockers={value.blockers} warnings={value.warnings} />
    </div>
  );
}

function referenceLabel(value: unknown): string {
  if (Array.isArray(value)) return value.map(referenceLabel).filter(Boolean).join(" · ");
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value !== "object") return String(value);
  const item = value as Record<string, unknown>;
  for (const key of [
    "owner_reference",
    "code",
    "number",
    "reference",
    "name",
    "title",
    "description",
    "amount",
    "value",
    "id",
  ]) {
    if (item[key] !== null && item[key] !== undefined && item[key] !== "") return String(item[key]);
  }
  return Object.keys(item).length ? JSON.stringify(item) : "—";
}

function measureNames(row: BenefitsTraceabilityPage["items"][number]) {
  return (
    row.measures
      .map((item) => item.name || item.code)
      .filter(Boolean)
      .join(" · ") || "—"
  );
}

function measureBaselines(row: BenefitsTraceabilityPage["items"][number]) {
  return (
    row.measures
      .map((item) => (item.baseline_status === "UNKNOWN" ? "UNKNOWN" : referenceLabel(item.baseline)))
      .filter(Boolean)
      .join(" · ") || "—"
  );
}

function measureTargets(row: BenefitsTraceabilityPage["items"][number]) {
  return (
    row.measures
      .map((item) => referenceLabel(item.target))
      .filter((item) => item !== "—")
      .join(" · ") || "—"
  );
}

function TraceabilityTable({
  page,
  loadMore,
}: {
  page: BenefitsTraceabilityPage | null;
  loadMore: () => Promise<void>;
}) {
  if (!page) return <p>Loading the optimized Benefits Traceability Matrix…</p>;
  return (
    <div className="benefitsTraceability">
      <p>
        <Link2 size={16} /> Derived, paginated read model · {page.resultCount} row(s). No double-entry and no
        per-Benefit browser fetch.
      </p>
      <div>
        <table>
          <thead>
            <tr>
              {[
                "Strategic Objective",
                "Need / Opportunity",
                "Business Analysis",
                "Recommended Option",
                "Project",
                "Business Case",
                "Expected Output",
                "Expected Outcome",
                "Benefit ID",
                "Benefit",
                "KPI / Measure",
                "Baseline",
                "Target",
                "Benefit Owner",
                "Target Date",
                "Expected Value",
                "Status",
              ].map((label) => (
                <th key={label}>{label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {page.items.map((row) => (
              <tr key={row.benefit_id}>
                {[
                  referenceLabel(row.strategic_objectives),
                  referenceLabel(row.need_opportunity),
                  referenceLabel(row.business_analysis),
                  referenceLabel(row.recommended_option),
                  referenceLabel(row.project),
                  referenceLabel(row.business_case),
                  referenceLabel(row.expected_outputs),
                  referenceLabel(row.expected_outcomes),
                  row.benefit_number,
                  row.benefit_name,
                  measureNames(row),
                  measureBaselines(row),
                  measureTargets(row),
                  referenceLabel(row.owner),
                  row.target_dates.join(" · ") || "—",
                  referenceLabel(row.expected_value),
                  row.status,
                ].map((value, column) => (
                  <td key={column}>{value || "—"}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {page.nextCursor ? (
        <button onClick={() => void loadMore()} type="button">
          Load more traceability rows
        </button>
      ) : null}
    </div>
  );
}

function HistoryPanel({ rows }: { rows: BenefitsPlanHistory[] }) {
  return (
    <div className="benefitsHistory">
      {rows.map((row) => (
        <article key={row.version.id}>
          <History size={17} />
          <div>
            <strong>
              Version {row.version.version_number} · {row.version.status}
            </strong>
            <span>{row.version.version_purpose}</span>
            <small>{row.version.benefits_plan_hash || row.version.content_hash || "Hash pending"}</small>
          </div>
        </article>
      ))}
    </div>
  );
}
function IssueList({ blockers = [], warnings = [] }: { blockers?: string[]; warnings?: string[] }) {
  return (
    <div className="benefitsIssues">
      {blockers.map((item) => (
        <p className="blocker" key={item}>
          <AlertTriangle size={16} /> {item}
        </p>
      ))}
      {warnings.map((item) => (
        <p className="warning" key={item}>
          <AlertTriangle size={16} /> {item}
        </p>
      ))}
    </div>
  );
}
function PreviewColumn({ label, value }: { label: string; value: unknown }) {
  return (
    <article>
      <strong>{label}</strong>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </article>
  );
}
