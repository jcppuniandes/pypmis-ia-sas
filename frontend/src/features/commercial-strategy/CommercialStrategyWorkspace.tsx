/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { AlertTriangle, CheckCircle2, FilePlus2, History, RefreshCw, Save, Send, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { commercialStrategyApi } from "./api";
import type {
  CommercialContractingStrategy,
  CommercialPackage,
  CommercialRefreshPreview,
  CommercialRiskAllocation,
  CommercialStrategyContent,
  CommercialStrategyHistory,
  CommercialStrategyQueue,
  CommercialStrategyReadiness,
  CommercialStrategyOptions,
} from "./types";
import "./commercialStrategy.css";

type View =
  | "mine"
  | "overview"
  | "context"
  | "procurement"
  | "packages"
  | "contracting"
  | "market"
  | "supply-chain"
  | "risk-allocation"
  | "payment-incentives"
  | "assumptions"
  | "recommendation"
  | "readiness"
  | "history";

const VIEW_BY_ROUTE: Record<string, View> = {
  "commercial-strategy-my": "mine",
  "commercial-strategy-overview": "overview",
  "commercial-strategy-context": "context",
  "commercial-strategy-procurement": "procurement",
  "commercial-strategy-packages": "packages",
  "commercial-strategy-contracting-model": "contracting",
  "commercial-strategy-market": "market",
  "commercial-strategy-supply-chain": "supply-chain",
  "commercial-strategy-risk-allocation": "risk-allocation",
  "commercial-strategy-payment-incentives": "payment-incentives",
  "commercial-strategy-assumptions": "assumptions",
  "commercial-strategy-recommendation": "recommendation",
  "commercial-strategy-readiness": "readiness",
  "commercial-strategy-history": "history",
};

const VIEW_LABELS: Record<View, string> = {
  mine: "My Strategies",
  overview: "Overview",
  context: "Commercial Context",
  procurement: "Procurement Approach",
  packages: "Packages",
  contracting: "Contracting Model",
  market: "Market Assessment",
  "supply-chain": "Supply Chain",
  "risk-allocation": "Risk Allocation",
  "payment-incentives": "Payment & Incentives",
  assumptions: "Assumptions / Constraints",
  recommendation: "Recommendation",
  readiness: "Readiness",
  history: "History",
};

const QUEUE_LABELS: Record<CommercialStrategyQueue, string> = {
  mine: "My Strategies",
  draft: "Draft",
  in_review: "In Review",
  returned: "Returned",
  ready: "Ready",
  completed: "Completed",
  stale: "Stale",
  all_authorized: "All Authorized",
};

const defaultContent = (): CommercialStrategyContent => ({
  commercial_context: "",
  procurement_approach: "",
  procurement_rationale: "",
  packaging_strategy_summary: "",
  packages: [],
  contracting_model: "",
  contracting_model_rationale: "",
  market_assessment: { overall_score: 0, summary: "", criteria: {} },
  supply_chain_constraints: [],
  risk_allocations: [],
  payment_mechanism: "",
  payment_mechanism_rationale: "",
  incentive_strategy: { mechanism: "", philosophy: "" },
  guarantees_securities_strategy: {},
  commercial_assumptions: [],
  commercial_constraints: [],
  dependencies: [],
  legal_regulatory_considerations: [],
  alternatives: [],
  recommendation: {
    recommended_procurement_approach: "",
    recommended_packaging_strategy: "",
    recommended_contracting_model: "",
    recommended_payment_mechanism: "",
    recommended_incentive_strategy: "",
    rationale: "",
    tradeoffs: [],
    commercial_recommendation_status: "DRAFT",
  },
  conditions_open_issues: [],
});

function cloneContent(value: CommercialStrategyContent | undefined): CommercialStrategyContent {
  const defaults = defaultContent();
  const supplied = value ? (JSON.parse(JSON.stringify(value)) as Partial<CommercialStrategyContent>) : {};
  const commercialContext = supplied.commercial_context;
  return {
    ...defaults,
    ...supplied,
    commercial_context:
      typeof commercialContext === "string"
        ? commercialContext
        : commercialContext
          ? JSON.stringify(commercialContext, null, 2)
          : "",
    market_assessment: { ...defaults.market_assessment, ...supplied.market_assessment },
    incentive_strategy: { ...defaults.incentive_strategy, ...supplied.incentive_strategy },
    recommendation: { ...defaults.recommendation, ...supplied.recommendation },
    packages: Array.isArray(supplied.packages) ? supplied.packages : [],
    supply_chain_constraints: Array.isArray(supplied.supply_chain_constraints) ? supplied.supply_chain_constraints : [],
    risk_allocations: Array.isArray(supplied.risk_allocations) ? supplied.risk_allocations : [],
    alternatives: Array.isArray(supplied.alternatives) ? supplied.alternatives : [],
    conditions_open_issues: Array.isArray(supplied.conditions_open_issues) ? supplied.conditions_open_issues : [],
  };
}

function actionAllowed(item: CommercialContractingStrategy | null, action: string) {
  const allowed = item?.allowed_actions;
  if (Array.isArray(allowed)) return allowed.includes(action) || allowed.includes(`can_${action.replace(/-/g, "_")}`);
  return Boolean(allowed?.[`can_${action.replace(/-/g, "_")}` as keyof typeof allowed]);
}

function providerAvailable(readiness: CommercialStrategyReadiness | null) {
  return Boolean(
    readiness &&
    (readiness.can_supply_investment_gate_evidence ??
      (readiness.status === "READY" && readiness.source_current && readiness.configuration_current !== false))
  );
}

function recordsToLines(value: Array<Record<string, unknown>>, field = "statement") {
  return value
    .map((item) => String(item[field] || ""))
    .filter(Boolean)
    .join("\n");
}

function linesToRecords(value: string, field = "statement") {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => ({ [field]: item }));
}

export default function CommercialStrategyWorkspace({ token, initialView }: { token: string; initialView?: string }) {
  const [view, setView] = useState<View>(VIEW_BY_ROUTE[initialView || ""] || "mine");
  const [queue, setQueue] = useState<CommercialStrategyQueue>("mine");
  const [records, setRecords] = useState<CommercialContractingStrategy[]>([]);
  const [options, setOptions] = useState<CommercialStrategyOptions | null>(null);
  const [selectedId, setSelectedId] = useState(0);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [projectId, setProjectId] = useState("");
  const [versionPurpose, setVersionPurpose] = useState("INITIAL_COMMERCIAL_ASSESSMENT");
  const [felStage, setFelStage] = useState("");
  const [reviewerId, setReviewerId] = useState("");
  const [draft, setDraft] = useState<CommercialStrategyContent>(defaultContent);
  const [readiness, setReadiness] = useState<CommercialStrategyReadiness | null>(null);
  const [history, setHistory] = useState<CommercialStrategyHistory[]>([]);
  const [preview, setPreview] = useState<CommercialRefreshPreview | null>(null);
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const selected = records.find((item) => item.id === selectedId) || records[0] || null;
  const version = selected?.current_version || null;
  const isEditable = actionAllowed(selected, "edit") && version?.status !== "COMPLETED";

  async function loadPage(cursor: string | null = null, append = false) {
    const page = await commercialStrategyApi.listPage(token, {
      queue,
      cursor,
      search: search.trim() || undefined,
      limit: 50,
    });
    setRecords((current) => (append ? [...current, ...page.items] : page.items));
    setNextCursor(page.nextCursor);
    if (!append)
      setSelectedId((current) => (page.items.some((item) => item.id === current) ? current : page.items[0]?.id || 0));
  }

  useEffect(() => setView(VIEW_BY_ROUTE[initialView || ""] || "mine"), [initialView]);
  useEffect(() => {
    void commercialStrategyApi
      .options(token, selected?.project_workspace_id)
      .then(setOptions)
      .catch(() => setOptions(null));
  }, [token, selected?.project_workspace_id]);
  useEffect(() => {
    void loadPage().catch((error) => setMessage(error instanceof Error ? error.message : "Unable to load strategies"));
  }, [token, queue]);
  useEffect(() => {
    setDraft(cloneContent(version?.content_json));
    setFelStage(version?.fel_stage_code || "");
    setReviewerId(version?.reviewer_user_id ? String(version.reviewer_user_id) : "");
    setPreview(null);
    if (!selected) {
      setReadiness(null);
      setHistory([]);
      return;
    }
    void Promise.all([
      commercialStrategyApi.readiness(token, selected.id),
      commercialStrategyApi.history(token, selected.id),
    ])
      .then(([readinessResult, historyResult]) => {
        setReadiness(readinessResult);
        setHistory(historyResult);
      })
      .catch((error) => setMessage(error instanceof Error ? error.message : "Unable to load strategy detail"));
  }, [selected?.id, version?.id]);

  const metrics = useMemo(
    () => [
      { label: "Strategies", value: records.length },
      { label: "Completed", value: records.filter((item) => item.current_version?.status === "COMPLETED").length },
      {
        label: "Ready",
        value: records.filter(
          (item) =>
            (item.current_version?.overall_commercial_readiness || item.current_version?.readiness_status) === "READY"
        ).length,
      },
      { label: "Provider", value: providerAvailable(readiness) ? "AVAILABLE" : "NOT READY" },
    ],
    [records, readiness]
  );

  async function execute(work: () => Promise<unknown>, success: string) {
    setBusy(true);
    setMessage("");
    try {
      await work();
      await loadPage();
      setMessage(success);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Commercial Strategy action failed");
    } finally {
      setBusy(false);
    }
  }

  async function create() {
    if (!Number(projectId)) return;
    await execute(async () => {
      const item = await commercialStrategyApi.create(token, Number(projectId), versionPurpose);
      setSelectedId(item.id);
    }, "Governed Commercial Strategy created without creating a Contract or procurement transaction.");
  }

  async function save() {
    if (!selected || !version) return;
    await execute(
      () =>
        commercialStrategyApi.update(
          token,
          selected,
          version,
          draft,
          felStage || null,
          reviewerId ? Number(reviewerId) : null
        ),
      "Draft saved under ETag control."
    );
  }

  async function lifecycle(action: "submit" | "start-review" | "return" | "complete" | "void") {
    if (!selected || !version) return;
    await execute(
      () => commercialStrategyApi.lifecycle(token, selected, version, action, reason || undefined),
      `Lifecycle action ${action} completed under backend authorization.`
    );
  }

  async function showPreview() {
    if (!selected) return;
    setBusy(true);
    try {
      setPreview(await commercialStrategyApi.refreshPreview(token, selected.id));
      setMessage("Refresh Preview completed with persisted=false; no historical version was mutated.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Refresh Preview failed");
    } finally {
      setBusy(false);
    }
  }

  function update<K extends keyof CommercialStrategyContent>(key: K, value: CommercialStrategyContent[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  return (
    <section aria-label="Commercial and Contracting Strategy" className="commercialStrategy">
      <CompactModuleHeader
        description="Define a governed commercial delivery, packaging, contracting, market, risk-allocation and payment strategy. Procurement execution and Contract administration remain outside this capability."
        eyebrow="USER MODE · PROJECT DEFINITION & INVESTMENT CASE · GATE 07M-COMM"
        metrics={metrics}
        title="Commercial & Contracting Strategy"
      />

      {message ? (
        <div className="commercialMessage" role="status">
          {message}
        </div>
      ) : null}

      <nav aria-label="Commercial Strategy views" className="commercialTabs">
        {(Object.keys(VIEW_LABELS) as View[]).map((item) => (
          <button className={view === item ? "active" : ""} key={item} onClick={() => setView(item)} type="button">
            {VIEW_LABELS[item]}
          </button>
        ))}
      </nav>

      <section aria-label="Commercial Strategy queue" className="commercialQueue">
        <div role="group" aria-label="Commercial Strategy queues">
          {(Object.keys(QUEUE_LABELS) as CommercialStrategyQueue[]).map((item) => (
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
            Search authorized strategies
            <input value={search} onChange={(event) => setSearch(event.target.value)} />
          </label>
          <button type="submit">Search</button>
        </form>
      </section>

      <div className="commercialControls">
        <label>
          Commercial Strategy
          <select value={selected?.id || 0} onChange={(event) => setSelectedId(Number(event.target.value))}>
            {!records.length ? <option value={0}>No authorized strategies</option> : null}
            {records.map((item) => (
              <option key={item.id} value={item.id}>
                {item.strategy_number} · Project {item.project_workspace_id} · {item.current_version?.status || "DRAFT"}
              </option>
            ))}
          </select>
        </label>
        <button disabled={busy || !isEditable} onClick={() => void save()} type="button">
          <Save size={15} /> Save
        </button>
        <button
          disabled={busy || !actionAllowed(selected, "submit")}
          onClick={() => void lifecycle("submit")}
          type="button"
        >
          <Send size={15} /> Submit
        </button>
        <button
          disabled={busy || !actionAllowed(selected, "start_review")}
          onClick={() => void lifecycle("start-review")}
          type="button"
        >
          Start review
        </button>
        <button
          disabled={busy || !actionAllowed(selected, "return") || reason.trim().length < 3}
          onClick={() => void lifecycle("return")}
          type="button"
        >
          Return
        </button>
        <button
          disabled={busy || !actionAllowed(selected, "complete")}
          onClick={() => void lifecycle("complete")}
          type="button"
        >
          <CheckCircle2 size={15} /> Complete
        </button>
        <button
          disabled={busy || !actionAllowed(selected, "void") || reason.trim().length < 3}
          onClick={() => void lifecycle("void")}
          type="button"
        >
          Void
        </button>
        <button
          disabled={busy || !actionAllowed(selected, "create_revision")}
          onClick={() =>
            selected &&
            void execute(
              () => commercialStrategyApi.newRevision(token, selected, "MATERIAL_CHANGE_UPDATE"),
              "New governed DRAFT revision created; history remains immutable."
            )
          }
          type="button"
        >
          <FilePlus2 size={15} /> New revision
        </button>
        <button
          disabled={busy || !actionAllowed(selected, "refresh_preview")}
          onClick={() => void showPreview()}
          type="button"
        >
          <RefreshCw size={15} /> Refresh Preview
        </button>
        <button
          disabled={busy || !preview || !selected || !version || !actionAllowed(selected, "refresh_apply")}
          onClick={() =>
            selected &&
            version &&
            void execute(
              () => commercialStrategyApi.refreshApply(token, selected),
              "Refresh applied as a new DRAFT version."
            )
          }
          type="button"
        >
          <RefreshCw size={15} /> Apply as new DRAFT
        </button>
      </div>

      {actionAllowed(selected, "return") || actionAllowed(selected, "void") ? (
        <label className="commercialReason">
          Return / void reason
          <input value={reason} onChange={(event) => setReason(event.target.value)} />
        </label>
      ) : null}

      <details className="commercialSurface commercialCreate" open={!records.length}>
        <summary>Create another governed Commercial Strategy</summary>
        <div>
          <h3>Create Commercial Strategy</h3>
          <p>
            Uses the canonical Project Workspace identity; it does not create a parallel Project or procurement object.
          </p>
          <label>
            Project Workspace ID
            <input inputMode="numeric" value={projectId} onChange={(event) => setProjectId(event.target.value)} />
          </label>
          <label>
            Version purpose
            <select value={versionPurpose} onChange={(event) => setVersionPurpose(event.target.value)}>
              {(options?.version_purposes?.length ? options.version_purposes : [versionPurpose]).map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <button disabled={busy || !Number(projectId)} onClick={() => void create()} type="button">
            <FilePlus2 size={15} /> Create governed strategy
          </button>
        </div>
      </details>

      {selected && version ? (
        <section className="commercialSurface">
          <header>
            <div>
              <span>{VIEW_LABELS[view]}</span>
              <h3>
                {selected.strategy_number} · Version {version.version_number}
              </h3>
            </div>
            <Status
              value={
                readiness?.overall_commercial_readiness ||
                version.overall_commercial_readiness ||
                version.readiness_status ||
                "NOT_STARTED"
              }
            />
          </header>
          <div className="commercialFacts">
            <Fact label="Project Workspace" value={selected.project_workspace_id} />
            <Fact label="Lifecycle" value={version.status} />
            <Fact label="Purpose" value={version.version_purpose} />
            <Fact label="FEL stage" value={version.fel_stage_code || "Not assigned"} />
            <Fact label="Source current" value={version.source_current ? "CURRENT" : "STALE"} />
            <Fact label="Provider" value={providerAvailable(readiness) ? "AVAILABLE" : "NOT AVAILABLE"} />
          </div>
          {renderView({
            view,
            draft,
            editable: isEditable,
            felStage,
            reviewerId,
            readiness,
            history,
            options,
            setFelStage,
            setReviewerId,
            update,
          })}
        </section>
      ) : null}

      {nextCursor ? (
        <button
          className="commercialLoadMore"
          disabled={busy}
          onClick={() => void loadPage(nextCursor, true)}
          type="button"
        >
          Load more strategies
        </button>
      ) : null}

      {preview ? (
        <section aria-label="Commercial Strategy refresh preview" className="commercialSurface commercialPreview">
          <h3>Refresh Preview · persisted=false</h3>
          <div className="commercialPreviewGrid">
            <PreviewColumn label="Source delta" value={preview.source_delta} />
            <PreviewColumn label="Policy delta" value={preview.policy_delta} />
            <PreviewColumn label="Readiness delta" value={preview.readiness_delta} />
          </div>
          <IssueList blockers={preview.blockers} warnings={preview.warnings} />
        </section>
      ) : null}

      <p className="commercialBoundary">
        <strong>Strategic boundary:</strong> this workspace defines how the solution may be contracted. It never creates
        a Tender, Bid, Vendor, Contract, Award, Purchase Order, Invoice, Payment or procurement transaction.
      </p>
    </section>
  );
}

type RenderViewProps = {
  view: View;
  draft: CommercialStrategyContent;
  editable: boolean;
  felStage: string;
  reviewerId: string;
  readiness: CommercialStrategyReadiness | null;
  history: CommercialStrategyHistory[];
  options: CommercialStrategyOptions | null;
  setFelStage: (value: string) => void;
  setReviewerId: (value: string) => void;
  update: <K extends keyof CommercialStrategyContent>(key: K, value: CommercialStrategyContent[K]) => void;
};

function renderView(props: RenderViewProps) {
  const { view, draft, editable, readiness, history, options, update } = props;
  if (view === "mine" || view === "overview") {
    return (
      <div className="commercialOverview">
        <label>
          FEL stage
          <input
            disabled={!editable}
            value={props.felStage}
            onChange={(event) => props.setFelStage(event.target.value.toUpperCase())}
          />
        </label>
        <label>
          Independent reviewer user ID
          <input
            disabled={!editable}
            inputMode="numeric"
            value={props.reviewerId}
            onChange={(event) => props.setReviewerId(event.target.value)}
          />
        </label>
        <article>
          <ShieldCheck />
          <div>
            <strong>Governed source references</strong>
            <p>
              Business Analysis, Proposal, FEL, Budget, Funding, FIN, Risk and Permit are consumed by reference and
              never recalculated here.
            </p>
          </div>
        </article>
        <article>
          <AlertTriangle />
          <div>
            <strong>Immutable completion</strong>
            <p>A material source or policy change is represented as STALE and requires a new controlled DRAFT.</p>
          </div>
        </article>
      </div>
    );
  }
  if (view === "context")
    return (
      <TextArea
        label="Commercial context"
        value={draft.commercial_context}
        editable={editable}
        onChange={(value) => update("commercial_context", value)}
      />
    );
  if (view === "procurement")
    return (
      <div className="commercialEditorGrid">
        <CatalogField
          editable={editable}
          label="Procurement approach"
          options={options?.procurement_approaches || []}
          value={draft.procurement_approach}
          onChange={(value) => update("procurement_approach", value)}
        />
        <TextArea
          editable={editable}
          label="Rationale"
          value={draft.procurement_rationale}
          onChange={(value) => update("procurement_rationale", value)}
        />
      </div>
    );
  if (view === "packages")
    return (
      <PackagesEditor
        contractingModels={options?.contracting_models || []}
        editable={editable}
        packageTypes={options?.package_types || []}
        packages={draft.packages}
        procurementApproaches={options?.procurement_approaches || []}
        summary={draft.packaging_strategy_summary}
        onPackages={(value) => update("packages", value)}
        onSummary={(value) => update("packaging_strategy_summary", value)}
      />
    );
  if (view === "contracting")
    return (
      <div className="commercialEditorGrid">
        <CatalogField
          editable={editable}
          label="Contracting model"
          options={options?.contracting_models || []}
          value={draft.contracting_model}
          onChange={(value) => update("contracting_model", value)}
        />
        <TextArea
          editable={editable}
          label="Rationale"
          value={draft.contracting_model_rationale}
          onChange={(value) => update("contracting_model_rationale", value)}
        />
      </div>
    );
  if (view === "market")
    return (
      <MarketAssessmentEditor
        criteriaCodes={options?.market_assessment_criteria || []}
        editable={editable}
        value={draft.market_assessment}
        onChange={(value) => update("market_assessment", value)}
      />
    );
  if (view === "supply-chain")
    return (
      <ConstraintEditor
        editable={editable}
        value={draft.supply_chain_constraints}
        onChange={(value) => update("supply_chain_constraints", value)}
      />
    );
  if (view === "risk-allocation")
    return (
      <RiskAllocationEditor
        categories={options?.risk_allocation_categories || []}
        editable={editable}
        rows={draft.risk_allocations}
        onChange={(value) => update("risk_allocations", value)}
      />
    );
  if (view === "payment-incentives")
    return (
      <div className="commercialEditorGrid">
        <CatalogField
          editable={editable}
          label="Payment mechanism"
          options={options?.payment_mechanisms || []}
          value={draft.payment_mechanism}
          onChange={(value) => update("payment_mechanism", value)}
        />
        <TextArea
          editable={editable}
          label="Payment rationale"
          value={draft.payment_mechanism_rationale}
          onChange={(value) => update("payment_mechanism_rationale", value)}
        />
        <CatalogField
          editable={editable}
          label="Incentive mechanism"
          options={options?.incentive_mechanisms || []}
          value={draft.incentive_strategy.mechanism}
          onChange={(value) => update("incentive_strategy", { ...draft.incentive_strategy, mechanism: value })}
        />
        <TextArea
          editable={editable}
          label="Incentive philosophy"
          value={draft.incentive_strategy.philosophy}
          onChange={(value) => update("incentive_strategy", { ...draft.incentive_strategy, philosophy: value })}
        />
      </div>
    );
  if (view === "assumptions")
    return (
      <div className="commercialEditorGrid">
        <RecordLinesEditor
          editable={editable}
          label="Commercial assumptions"
          value={draft.commercial_assumptions}
          onChange={(value) => update("commercial_assumptions", value)}
        />
        <RecordLinesEditor
          editable={editable}
          label="Commercial constraints"
          value={draft.commercial_constraints}
          onChange={(value) => update("commercial_constraints", value)}
        />
        <RecordLinesEditor
          editable={editable}
          label="Dependencies"
          value={draft.dependencies}
          onChange={(value) => update("dependencies", value)}
        />
        <RecordLinesEditor
          editable={editable}
          label="Legal / regulatory considerations"
          value={draft.legal_regulatory_considerations}
          onChange={(value) => update("legal_regulatory_considerations", value)}
        />
        <OpenIssuesEditor
          editable={editable}
          value={draft.conditions_open_issues}
          onChange={(value) => update("conditions_open_issues", value)}
        />
      </div>
    );
  if (view === "recommendation")
    return (
      <RecommendationEditor
        alternatives={draft.alternatives}
        contractingModels={options?.contracting_models || []}
        editable={editable}
        paymentMechanisms={options?.payment_mechanisms || []}
        procurementApproaches={options?.procurement_approaches || []}
        value={draft.recommendation}
        onAlternatives={(value) => update("alternatives", value)}
        onChange={(value) => update("recommendation", value)}
      />
    );
  if (view === "readiness") return <ReadinessPanel value={readiness} />;
  return <HistoryPanel rows={history} />;
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
  return <span className={`commercialStatus ${value.toLowerCase()}`}>{value}</span>;
}
function TextArea({
  label,
  value,
  editable,
  onChange,
  hint,
}: {
  label: string;
  value: string;
  editable: boolean;
  onChange: (value: string) => void;
  hint?: string;
}) {
  return (
    <label className="commercialField">
      <span>{label}</span>
      {hint ? <small>{hint}</small> : null}
      <textarea disabled={!editable} rows={8} value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}
function RecordLinesEditor({
  editable,
  label,
  value,
  onChange,
}: {
  editable: boolean;
  label: string;
  value: Array<Record<string, unknown>>;
  onChange: (value: Array<Record<string, unknown>>) => void;
}) {
  return (
    <TextArea
      editable={editable}
      label={label}
      value={recordsToLines(value)}
      onChange={(next) => onChange(linesToRecords(next))}
      hint="One governed statement per line."
    />
  );
}

function CatalogField({
  label,
  value,
  options,
  editable,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  editable: boolean;
  onChange: (value: string) => void;
}) {
  const listId = `commercial-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  return (
    <label className="commercialField">
      <span>{label}</span>
      <small>
        {options.length
          ? "Select a value from the effective published catalog."
          : "No effective catalog values were returned."}
      </small>
      <input
        aria-label={label}
        disabled={!editable}
        list={listId}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      <datalist id={listId}>
        {options.map((item) => (
          <option key={item} value={item} />
        ))}
      </datalist>
    </label>
  );
}

function MarketAssessmentEditor({
  value,
  criteriaCodes,
  editable,
  onChange,
}: {
  value: CommercialStrategyContent["market_assessment"];
  criteriaCodes: string[];
  editable: boolean;
  onChange: (value: CommercialStrategyContent["market_assessment"]) => void;
}) {
  const criteria = value.criteria || {};
  const visibleCriteria = criteriaCodes.length ? criteriaCodes : Object.keys(criteria);
  return (
    <div className="commercialEditorGrid">
      <label className="commercialField">
        <span>Overall market capability score</span>
        <small>Backend policy evaluates this score against the published blocking threshold.</small>
        <input
          aria-label="Overall market capability score"
          disabled={!editable}
          max={100}
          min={0}
          onChange={(event) => onChange({ ...value, overall_score: Number(event.target.value) })}
          type="number"
          value={Number(value.overall_score || 0)}
        />
      </label>
      <TextArea
        editable={editable}
        hint="Assess supplier depth, concentration, capacity, competition, experience, appetite, lead times and market timing without creating a vendor shortlist."
        label="Market capability assessment summary"
        onChange={(summary) => onChange({ ...value, summary })}
        value={String(value.summary || "")}
      />
      <fieldset className="commercialCriteria">
        <legend>Published market criteria</legend>
        {visibleCriteria.length ? (
          visibleCriteria.map((code) => (
            <label key={code}>
              {code.replace(/_/g, " ")}
              <input
                aria-label={`Market criterion ${code}`}
                disabled={!editable}
                max={100}
                min={0}
                type="number"
                value={Number(criteria[code] || 0)}
                onChange={(event) =>
                  onChange({ ...value, criteria: { ...criteria, [code]: Number(event.target.value) } })
                }
              />
            </label>
          ))
        ) : (
          <p>No effective market criteria were returned.</p>
        )}
      </fieldset>
    </div>
  );
}

function ConstraintEditor({
  value,
  editable,
  onChange,
}: {
  value: Array<Record<string, unknown>>;
  editable: boolean;
  onChange: (value: Array<Record<string, unknown>>) => void;
}) {
  const add = () => onChange([...value, { statement: "", critical: false, status: "OPEN" }]);
  const change = (index: number, key: string, next: unknown) =>
    onChange(value.map((item, rowIndex) => (rowIndex === index ? { ...item, [key]: next } : item)));
  return (
    <section className="commercialRepeater">
      <header>
        <div>
          <h4>Supply-chain constraints</h4>
          <p>Record long-lead, capacity, logistics, local-content, currency or single-source constraints.</p>
        </div>
        <button disabled={!editable} onClick={add} type="button">
          Add constraint
        </button>
      </header>
      {value.map((item, index) => (
        <article key={String(item.id || index)}>
          <textarea
            aria-label={`Supply-chain constraint ${index + 1}`}
            disabled={!editable}
            value={String(item.statement || "")}
            onChange={(event) => change(index, "statement", event.target.value)}
          />
          <label>
            <input
              checked={Boolean(item.critical)}
              disabled={!editable}
              onChange={(event) => change(index, "critical", event.target.checked)}
              type="checkbox"
            />{" "}
            Critical / blocking
          </label>
          <label>
            Status
            <select
              aria-label={`Supply-chain status ${index + 1}`}
              disabled={!editable}
              value={String(item.status || "OPEN")}
              onChange={(event) => change(index, "status", event.target.value)}
            >
              <option>OPEN</option>
              <option>MITIGATED</option>
              <option>RESOLVED</option>
              <option>CLOSED</option>
            </select>
          </label>
        </article>
      ))}
    </section>
  );
}

function PackagesEditor({
  packages,
  summary,
  editable,
  packageTypes,
  procurementApproaches,
  contractingModels,
  onPackages,
  onSummary,
}: {
  packages: CommercialPackage[];
  summary: string;
  editable: boolean;
  packageTypes: string[];
  procurementApproaches: string[];
  contractingModels: string[];
  onPackages: (value: CommercialPackage[]) => void;
  onSummary: (value: string) => void;
}) {
  const add = () =>
    onPackages([
      ...packages,
      {
        package_code: `PKG-${String(packages.length + 1).padStart(3, "0")}`,
        package_name: "",
        package_type: "",
        scope_summary: "",
        interface_summary: "",
        anticipated_procurement_approach: "",
        anticipated_contracting_model: "",
        key_dependencies: [],
        critical_interfaces: [],
        market_risk: "",
        commercial_risk: "",
        status: "DRAFT",
      },
    ]);
  const change = (index: number, key: keyof CommercialPackage, value: string) =>
    onPackages(packages.map((item, rowIndex) => (rowIndex === index ? { ...item, [key]: value } : item)));
  return (
    <div className="commercialEditorGrid">
      <TextArea editable={editable} label="Packaging strategy summary" value={summary} onChange={onSummary} />
      <section className="commercialRepeater">
        <header>
          <h4>Conceptual commercial packages</h4>
          <button disabled={!editable} onClick={add} type="button">
            Add package
          </button>
        </header>
        {packages.map((item, index) => (
          <article key={`${item.package_code}-${index}`}>
            <input
              aria-label={`Package code ${index + 1}`}
              disabled={!editable}
              value={item.package_code}
              onChange={(event) => change(index, "package_code", event.target.value)}
            />
            <input
              aria-label={`Package name ${index + 1}`}
              disabled={!editable}
              placeholder="Package name"
              value={item.package_name}
              onChange={(event) => change(index, "package_name", event.target.value)}
            />
            <CatalogField
              editable={editable}
              label={`Package type ${index + 1}`}
              options={packageTypes}
              value={item.package_type}
              onChange={(value) => change(index, "package_type", value)}
            />
            <textarea
              aria-label={`Package scope ${index + 1}`}
              disabled={!editable}
              placeholder="Scope summary"
              value={item.scope_summary}
              onChange={(event) => change(index, "scope_summary", event.target.value)}
            />
            <textarea
              aria-label={`Package interfaces ${index + 1}`}
              disabled={!editable}
              placeholder="Interface summary"
              value={item.interface_summary}
              onChange={(event) => change(index, "interface_summary", event.target.value)}
            />
            <CatalogField
              editable={editable}
              label={`Package procurement approach ${index + 1}`}
              options={procurementApproaches}
              value={item.anticipated_procurement_approach}
              onChange={(value) => change(index, "anticipated_procurement_approach", value)}
            />
            <CatalogField
              editable={editable}
              label={`Package contracting model ${index + 1}`}
              options={contractingModels}
              value={item.anticipated_contracting_model}
              onChange={(value) => change(index, "anticipated_contracting_model", value)}
            />
          </article>
        ))}
      </section>
    </div>
  );
}

function RiskAllocationEditor({
  rows,
  categories,
  editable,
  onChange,
}: {
  rows: CommercialRiskAllocation[];
  categories: string[];
  editable: boolean;
  onChange: (value: CommercialRiskAllocation[]) => void;
}) {
  const add = () =>
    onChange([
      ...rows,
      {
        commercial_risk_category: "",
        risk_description: "",
        preferred_owner: "",
        allocation_rationale: "",
        transferability: "",
        pricing_implication: "",
        contractual_treatment: "",
        residual_concern: "",
        status: "OPEN",
      },
    ]);
  const change = (index: number, key: keyof CommercialRiskAllocation, value: string) =>
    onChange(rows.map((item, rowIndex) => (rowIndex === index ? { ...item, [key]: value } : item)));
  return (
    <section className="commercialRepeater">
      <header>
        <div>
          <h4>Governed risk-allocation strategy</h4>
          <p>References risk context without duplicating the Project Risk Register.</p>
        </div>
        <button disabled={!editable} onClick={add} type="button">
          Add allocation
        </button>
      </header>
      {rows.map((item, index) => (
        <article key={`${item.commercial_risk_category}-${index}`}>
          <CatalogField
            editable={editable}
            label={`Risk category ${index + 1}`}
            options={categories}
            value={item.commercial_risk_category}
            onChange={(value) => change(index, "commercial_risk_category", value)}
          />
          <input
            aria-label={`Preferred owner ${index + 1}`}
            disabled={!editable}
            placeholder="Preferred owner"
            value={item.preferred_owner}
            onChange={(event) => change(index, "preferred_owner", event.target.value)}
          />
          <textarea
            aria-label={`Risk description ${index + 1}`}
            disabled={!editable}
            placeholder="Risk description"
            value={item.risk_description}
            onChange={(event) => change(index, "risk_description", event.target.value)}
          />
          <textarea
            aria-label={`Allocation rationale ${index + 1}`}
            disabled={!editable}
            placeholder="Allocation rationale"
            value={item.allocation_rationale}
            onChange={(event) => change(index, "allocation_rationale", event.target.value)}
          />
          <input
            aria-label={`Transferability ${index + 1}`}
            disabled={!editable}
            placeholder="Transferability"
            value={item.transferability}
            onChange={(event) => change(index, "transferability", event.target.value)}
          />
          <input
            aria-label={`Pricing implication ${index + 1}`}
            disabled={!editable}
            placeholder="Pricing implication"
            value={item.pricing_implication}
            onChange={(event) => change(index, "pricing_implication", event.target.value)}
          />
          <textarea
            aria-label={`Contractual treatment ${index + 1}`}
            disabled={!editable}
            placeholder="Contractual treatment"
            value={item.contractual_treatment}
            onChange={(event) => change(index, "contractual_treatment", event.target.value)}
          />
          <textarea
            aria-label={`Residual concern ${index + 1}`}
            disabled={!editable}
            placeholder="Residual commercial concern"
            value={item.residual_concern}
            onChange={(event) => change(index, "residual_concern", event.target.value)}
          />
        </article>
      ))}
    </section>
  );
}

function OpenIssuesEditor({
  value,
  editable,
  onChange,
}: {
  value: Array<Record<string, unknown>>;
  editable: boolean;
  onChange: (value: Array<Record<string, unknown>>) => void;
}) {
  const add = () => onChange([...value, { statement: "", blocking: true, status: "OPEN" }]);
  const change = (index: number, key: string, next: unknown) =>
    onChange(value.map((item, rowIndex) => (rowIndex === index ? { ...item, [key]: next } : item)));
  return (
    <section className="commercialRepeater">
      <header>
        <h4>Conditions / open issues</h4>
        <button disabled={!editable} onClick={add} type="button">
          Add condition or issue
        </button>
      </header>
      {value.map((item, index) => (
        <article key={String(item.id || index)}>
          <textarea
            aria-label={`Open issue ${index + 1}`}
            disabled={!editable}
            value={String(item.statement || "")}
            onChange={(event) => change(index, "statement", event.target.value)}
          />
          <label>
            <input
              checked={Boolean(item.blocking)}
              disabled={!editable}
              onChange={(event) => change(index, "blocking", event.target.checked)}
              type="checkbox"
            />{" "}
            Blocking
          </label>
          <label>
            Status
            <select
              aria-label={`Open issue status ${index + 1}`}
              disabled={!editable}
              value={String(item.status || "OPEN")}
              onChange={(event) => change(index, "status", event.target.value)}
            >
              <option>OPEN</option>
              <option>RESOLVED</option>
              <option>CLOSED</option>
            </select>
          </label>
        </article>
      ))}
    </section>
  );
}

function RecommendationEditor({
  value,
  alternatives,
  procurementApproaches,
  contractingModels,
  paymentMechanisms,
  editable,
  onChange,
  onAlternatives,
}: {
  value: CommercialStrategyContent["recommendation"];
  alternatives: Array<Record<string, unknown>>;
  procurementApproaches: string[];
  contractingModels: string[];
  paymentMechanisms: string[];
  editable: boolean;
  onChange: (value: CommercialStrategyContent["recommendation"]) => void;
  onAlternatives: (value: Array<Record<string, unknown>>) => void;
}) {
  const change = (key: keyof typeof value, next: string) => onChange({ ...value, [key]: next });
  return (
    <div className="commercialEditorGrid">
      {(
        [
          "recommended_procurement_approach",
          "recommended_packaging_strategy",
          "recommended_contracting_model",
          "recommended_payment_mechanism",
          "recommended_incentive_strategy",
          "rationale",
          "commercial_recommendation_status",
        ] as const
      ).map((key) => (
        <TextArea
          editable={editable}
          key={key}
          label={key.replace(/_/g, " ")}
          value={String(value[key] || "")}
          onChange={(next) => change(key, next)}
        />
      ))}
      <AlternativesEditor
        contractingModels={contractingModels}
        editable={editable}
        paymentMechanisms={paymentMechanisms}
        procurementApproaches={procurementApproaches}
        rows={alternatives}
        onChange={onAlternatives}
      />
    </div>
  );
}

function AlternativesEditor({
  rows,
  procurementApproaches,
  contractingModels,
  paymentMechanisms,
  editable,
  onChange,
}: {
  rows: Array<Record<string, unknown>>;
  procurementApproaches: string[];
  contractingModels: string[];
  paymentMechanisms: string[];
  editable: boolean;
  onChange: (value: Array<Record<string, unknown>>) => void;
}) {
  const add = () =>
    onChange([
      ...rows,
      {
        alternative_code: `ALT-${rows.length + 1}`,
        name: "",
        procurement_approach: "",
        contracting_model: "",
        risk_allocation: "",
        payment_mechanism: "",
        market_fit: "",
        commercial_risk: "",
        pros: [],
        cons: [],
        rating: 0,
      },
    ]);
  const change = (index: number, key: string, next: unknown) =>
    onChange(rows.map((item, rowIndex) => (rowIndex === index ? { ...item, [key]: next } : item)));
  const stringList = (value: unknown) => (Array.isArray(value) ? value.map(String) : []).join("\n");
  const parseList = (value: string) =>
    value
      .split("\n")
      .map((item) => item.trim())
      .filter(Boolean);

  return (
    <section className="commercialRepeater">
      <header>
        <div>
          <h4>Comparable commercial alternatives</h4>
          <p>Compare complete market routes before recording the governed recommendation.</p>
        </div>
        <button disabled={!editable} onClick={add} type="button">
          Add alternative
        </button>
      </header>
      {rows.map((item, index) => (
        <article key={String(item.alternative_code || index)}>
          <input
            aria-label={`Alternative code ${index + 1}`}
            disabled={!editable}
            value={String(item.alternative_code || `ALT-${index + 1}`)}
            onChange={(event) => change(index, "alternative_code", event.target.value)}
          />
          <input
            aria-label={`Alternative name ${index + 1}`}
            disabled={!editable}
            placeholder="Alternative name"
            value={String(item.name || "")}
            onChange={(event) => change(index, "name", event.target.value)}
          />
          <CatalogField
            editable={editable}
            label={`Alternative procurement approach ${index + 1}`}
            options={procurementApproaches}
            value={String(item.procurement_approach || "")}
            onChange={(next) => change(index, "procurement_approach", next)}
          />
          <CatalogField
            editable={editable}
            label={`Alternative contracting model ${index + 1}`}
            options={contractingModels}
            value={String(item.contracting_model || "")}
            onChange={(next) => change(index, "contracting_model", next)}
          />
          <textarea
            aria-label={`Alternative risk allocation ${index + 1}`}
            disabled={!editable}
            placeholder="Risk allocation"
            value={String(item.risk_allocation || "")}
            onChange={(event) => change(index, "risk_allocation", event.target.value)}
          />
          <CatalogField
            editable={editable}
            label={`Alternative payment mechanism ${index + 1}`}
            options={paymentMechanisms}
            value={String(item.payment_mechanism || "")}
            onChange={(next) => change(index, "payment_mechanism", next)}
          />
          <textarea
            aria-label={`Alternative market fit ${index + 1}`}
            disabled={!editable}
            placeholder="Market fit"
            value={String(item.market_fit || "")}
            onChange={(event) => change(index, "market_fit", event.target.value)}
          />
          <textarea
            aria-label={`Alternative commercial risk ${index + 1}`}
            disabled={!editable}
            placeholder="Commercial risk"
            value={String(item.commercial_risk || "")}
            onChange={(event) => change(index, "commercial_risk", event.target.value)}
          />
          <textarea
            aria-label={`Alternative pros ${index + 1}`}
            disabled={!editable}
            placeholder="One advantage per line"
            value={stringList(item.pros)}
            onChange={(event) => change(index, "pros", parseList(event.target.value))}
          />
          <textarea
            aria-label={`Alternative cons ${index + 1}`}
            disabled={!editable}
            placeholder="One disadvantage per line"
            value={stringList(item.cons)}
            onChange={(event) => change(index, "cons", parseList(event.target.value))}
          />
          <input
            aria-label={`Alternative rating ${index + 1}`}
            disabled={!editable}
            max={100}
            min={0}
            type="number"
            value={Number(item.rating || 0)}
            onChange={(event) => change(index, "rating", Number(event.target.value))}
          />
        </article>
      ))}
    </section>
  );
}

function ReadinessPanel({ value }: { value: CommercialStrategyReadiness | null }) {
  if (!value) return <p>Readiness has not been calculated for this authorized strategy.</p>;
  return (
    <div className="commercialReadiness">
      <header>
        <Status value={value.overall_commercial_readiness || value.status} />
        <strong>
          {providerAvailable(value)
            ? "COMMERCIAL_READINESS_PROVIDER = AVAILABLE"
            : "Evidence supply conditions are not satisfied"}
        </strong>
      </header>
      <div>
        {Object.entries(value.dimensions || {}).map(([key, status]) => (
          <Fact key={key} label={key.replace(/_/g, " ")} value={status} />
        ))}
      </div>
      <IssueList blockers={value.blockers} warnings={value.warnings} />
    </div>
  );
}
function IssueList({ blockers = [], warnings = [] }: { blockers?: string[]; warnings?: string[] }) {
  return (
    <div className="commercialIssues">
      {blockers.map((item) => (
        <p className="blocked" key={item}>
          <AlertTriangle size={15} /> {item}
        </p>
      ))}
      {warnings.map((item) => (
        <p key={item}>
          <AlertTriangle size={15} /> {item}
        </p>
      ))}
      {!blockers.length && !warnings.length ? (
        <p>
          <CheckCircle2 size={15} /> No reported warnings or blockers.
        </p>
      ) : null}
    </div>
  );
}
function HistoryPanel({ rows }: { rows: CommercialStrategyHistory[] }) {
  return (
    <div className="commercialHistory">
      <h4>
        <History size={17} /> Immutable lifecycle and revision history
      </h4>
      {rows.length ? (
        rows.flatMap((item) =>
          item.lifecycle_events.length
            ? item.lifecycle_events.map((event, index) => (
                <article key={`${item.version.id}-${index}`}>
                  <strong>{String(event.event_type || event.action || item.version.status)}</strong>
                  <span>{String(event.occurred_at || event.created_at || item.version.updated_at)}</span>
                  <small>Version {item.version.version_number}</small>
                </article>
              ))
            : [
                <article key={item.version.id}>
                  <strong>{item.version.status}</strong>
                  <span>{item.version.updated_at}</span>
                  <small>Version {item.version.version_number}</small>
                </article>,
              ]
        )
      ) : (
        <p>No history entries returned.</p>
      )}
    </div>
  );
}
function PreviewColumn({ label, value }: { label: string; value: unknown }) {
  return (
    <article>
      <strong>{label}</strong>
      <pre>{JSON.stringify(value ?? null, null, 2)}</pre>
    </article>
  );
}
