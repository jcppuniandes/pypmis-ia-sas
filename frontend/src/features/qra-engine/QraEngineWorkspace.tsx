import { useCallback, useEffect, useRef, useState } from "react";
import { createIdempotencyKey } from "../capital-planning/api";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { qraFoundationApi, type QraOptions } from "../qra-foundation/api";
import type { JsonRecord } from "../risk-governance/policyApi";
import { qraEngineApi, type QraEngineOptions, type QraRun, type QraRunAction, type QraRunPage } from "./api";
import "../risk-governance/wave2b.css";
import "./qraEngine.css";

const sections = [
  "Approved Models",
  "Runs",
  "Run Overview",
  "Cost Results",
  "Schedule Results",
  "Percentiles",
  "Sensitivity / Drivers",
  "Convergence",
  "Evidence / Traceability",
  "Run Comparison",
  "History",
] as const;
type Section = (typeof sections)[number];
const viewSections: Record<string, Section> = {
  "qra-approved-models": "Approved Models",
  "qra-runs": "Runs",
  "qra-run-overview": "Run Overview",
  "qra-cost-results": "Cost Results",
  "qra-schedule-results": "Schedule Results",
  "qra-percentiles": "Percentiles",
  "qra-sensitivity": "Sensitivity / Drivers",
  "qra-convergence": "Convergence",
  "qra-run-evidence": "Evidence / Traceability",
  "qra-run-comparison": "Run Comparison",
  "qra-run-history": "History",
};
const active = (run: QraRun | null) => !!run && ["QUEUED", "VALIDATING", "RUNNING"].includes(run.status);
const record = (value: unknown): JsonRecord =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as JsonRecord) : {};
const rows = (value: unknown): JsonRecord[] => (Array.isArray(value) ? value.map(record) : []);
const text = (value: unknown): string => (value === undefined || value === null || value === "" ? "—" : String(value));
const pretty = (value: unknown) => JSON.stringify(value ?? {}, null, 2);
const emptyPage = (): QraRunPage => ({ items: [], total: 0, page: 1, page_size: 25 });
const resourceFor: Partial<Record<Section, string>> = {
  "Run Overview": "summary",
  "Cost Results": "summary",
  "Schedule Results": "milestones",
  Percentiles: "percentiles",
  "Sensitivity / Drivers": "sensitivity",
  Convergence: "convergence",
  "Evidence / Traceability": "evidence",
  History: "evidence",
};

/** Presents only backend-governed results: no sampling, percentile or schedule calculations. */
export default function QraEngineWorkspace({ token, initialView }: { token: string; initialView?: string }) {
  const [section, setSection] = useState<Section>(viewSections[initialView ?? ""] ?? "Approved Models");
  const [projects, setProjects] = useState<QraOptions | null>(null);
  const [search, setSearch] = useState("");
  const [projectId, setProjectId] = useState(0);
  const [options, setOptions] = useState<QraEngineOptions | null>(null);
  const [history, setHistory] = useState(emptyPage);
  const [run, setRun] = useState<QraRun | null>(null);
  const [modelId, setModelId] = useState(0);
  const [modelPage, setModelPage] = useState(1);
  const [modelTotal, setModelTotal] = useState(0);
  const [seed, setSeed] = useState("");
  const [iterations, setIterations] = useState("");
  const [comments, setComments] = useState("");
  const [preflight, setPreflight] = useState<JsonRecord | null>(null);
  const [content, setContent] = useState<JsonRecord>({});
  const [contentKey, setContentKey] = useState("");
  const [resultPage, setResultPage] = useState(1);
  const [loadedContext, setLoadedContext] = useState({ token, initialView });
  const [comparisonId, setComparisonId] = useState(0);
  const [comparison, setComparison] = useState<JsonRecord | null>(null);
  const [busy, setBusy] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const context = useRef(0);
  const mounted = useRef(false);
  const selectedRef = useRef<QraRun | null>(null);
  const createRequest = useRef<{ signature: string; key: string } | null>(null);
  const selectedModel = options?.approved_models.find((item) => item.id === modelId);
  const actions = options?.allowed_actions ?? [];
  const allows = (action: string) => run?.allowed_actions?.includes(action) === true;
  const enginePolicy = options?.engine_policy ?? {};
  const iterationPolicy = record(enginePolicy.iteration_policy);
  const seedPolicy = text(enginePolicy.seed_policy);
  const pollingRunId = active(run) ? run?.id : undefined;
  const contentIdentity = `${run?.id ?? 0}|${section}|${resultPage}`;
  const currentContent = contentKey === contentIdentity ? content : {};

  const loadProject = useCallback(
    async (id: number, page = 1, preferred?: number, signal?: AbortSignal) => {
      const generation = ++context.current;
      setProjectId(id);
      selectedRef.current = null;
      setRun(null);
      setContent({});
      setPreflight(null);
      setComparison(null);
      setComparisonId(0);
      createRequest.current = null;
      if (!id) {
        setOptions(null);
        setHistory(emptyPage());
        setModelId(0);
        return;
      }
      const [nextOptions, nextHistory] = await Promise.all([
        qraEngineApi.options(token, id, signal),
        qraEngineApi.runs(token, id, page, signal),
      ]);
      if (!mounted.current || generation !== context.current) return;
      setOptions(nextOptions);
      setHistory(nextHistory);
      setModelPage(1);
      setModelTotal(Number(nextOptions.approved_model_total ?? nextOptions.approved_models.length));
      setModelId(nextOptions.approved_models[0]?.id ?? 0);
      setIterations(String(record(nextOptions.engine_policy.iteration_policy).default ?? ""));
      setSeed("");
      const candidate = nextHistory.items.find((item) => item.id === preferred) ?? nextHistory.items[0];
      if (candidate) {
        const full = await qraEngineApi.run(token, candidate.id, signal);
        if (!mounted.current || generation !== context.current) return;
        selectedRef.current = full;
        setRun(full);
      }
    },
    [token]
  );

  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    const generation = ++context.current;
    void Promise.resolve().then(async () => {
      if (controller.signal.aborted || !mounted.current || generation !== context.current) return;
      setBusy(true);
      setError("");
      setMessage("");
      setProjects(null);
      setOptions(null);
      setProjectId(0);
      setModelId(0);
      setPreflight(null);
      setComparison(null);
      setComparisonId(0);
      setRun(null);
      selectedRef.current = null;
      setHistory(emptyPage());
      setContent({});
      setResultPage(1);
      setSection(viewSections[initialView ?? ""] ?? "Approved Models");
      try {
        const next = await qraFoundationApi.options(token);
        if (!mounted.current || generation !== context.current) return;
        setProjects(next);
        await loadProject(next.projects[0]?.id ?? 0, 1, undefined, controller.signal);
      } catch (cause: unknown) {
        if (!controller.signal.aborted && mounted.current)
          setError(cause instanceof Error ? cause.message : String(cause));
      } finally {
        if (!controller.signal.aborted && mounted.current) {
          setBusy(false);
          setLoadedContext({ token, initialView });
        }
      }
    });
    return () => {
      mounted.current = false;
      context.current += 1;
      controller.abort();
    };
  }, [token, initialView, loadProject]);

  useEffect(() => {
    if (!run?.id) return;
    const controller = new AbortController();
    const generation = context.current;
    const id = run.id;
    const resource = resourceFor[section];
    if (run.status !== "COMPLETED" && !["Evidence / Traceability", "History"].includes(section)) return;
    if (resource) {
      const reads =
        (section === "Evidence / Traceability" || section === "History") && run.status === "COMPLETED"
          ? Promise.all([
              qraEngineApi.read(token, id, "evidence", controller.signal),
              qraEngineApi.read(token, id, "provenance", controller.signal),
            ]).then(([evidence, provenance]) => ({ ...evidence, frozen_provenance: provenance.data }))
          : section === "Run Overview" || section === "Cost Results"
            ? Promise.all([
                qraEngineApi.read(token, id, "summary", controller.signal),
                qraEngineApi.read(token, id, "histogram", controller.signal),
                qraEngineApi.read(token, id, "cdf", controller.signal),
              ]).then(([summary, histogram, cdf]) => ({ ...summary, histogram: histogram.data, cdf: cdf.data }))
            : qraEngineApi.read(token, id, resource, controller.signal, resultPage);
      void reads
        .then((next) => {
          if (
            !controller.signal.aborted &&
            mounted.current &&
            generation === context.current &&
            selectedRef.current?.id === id
          ) {
            setContent(next);
            setContentKey(`${id}|${section}|${resultPage}`);
          }
        })
        .catch((cause: unknown) => {
          if (!controller.signal.aborted && mounted.current && generation === context.current)
            setError(cause instanceof Error ? cause.message : String(cause));
        });
    }
    return () => controller.abort();
  }, [token, run?.id, run?.status, run?.review_status, section, resultPage]);

  useEffect(() => {
    if (!pollingRunId) return;
    const controller = new AbortController();
    const generation = context.current;
    const id = pollingRunId;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const next = await qraEngineApi.status(token, id, controller.signal);
        if (
          controller.signal.aborted ||
          !mounted.current ||
          generation !== context.current ||
          selectedRef.current?.id !== id
        )
          return;
        if (active(next)) {
          selectedRef.current = next;
          setRun(next);
          timer = setTimeout(() => void poll(), 1500);
        } else {
          // Committing a terminal status stops this effect and aborts its controller.
          // Finish the detail read first so history and comparison receive the final run.
          const full = await qraEngineApi.run(token, id, controller.signal);
          if (
            !controller.signal.aborted &&
            mounted.current &&
            generation === context.current &&
            selectedRef.current?.id === id
          ) {
            selectedRef.current = full;
            setRun(full);
            setHistory((previous) => ({
              ...previous,
              items: previous.items.map((item) => (item.id === id ? full : item)),
            }));
            setMessage(`Run ${full.run_number}: ${full.status}. Completion does not imply investment approval.`);
          }
        }
      } catch (cause) {
        if (!controller.signal.aborted && mounted.current && generation === context.current) {
          setError(`Progress could not be refreshed: ${cause instanceof Error ? cause.message : String(cause)}`);
          timer = setTimeout(() => void poll(), 5000);
        }
      }
    };
    timer = setTimeout(() => void poll(), 500);
    return () => {
      controller.abort();
      if (timer) clearTimeout(timer);
    };
    // A single serial polling loop per active run; revision updates do not recreate it.
  }, [token, pollingRunId]);

  const perform = async (operation: () => Promise<void>, success: string) => {
    const generation = context.current;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await operation();
      if (mounted.current && generation === context.current) setMessage(success);
    } catch (cause) {
      if (mounted.current && generation === context.current)
        setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      if (mounted.current) setBusy(false);
    }
  };
  const chooseRun = async (id: number) => {
    const generation = ++context.current;
    selectedRef.current = null;
    setRun(null);
    setContent({});
    setComparison(null);
    if (!id) return;
    const full = await qraEngineApi.run(token, id);
    if (mounted.current && generation === context.current) {
      selectedRef.current = full;
      setRun(full);
    }
  };
  const createRun = async () => {
    const generation = context.current;
    const body: JsonRecord = { comments };
    if (seed !== "") {
      const parsed = Number(seed);
      if (!Number.isSafeInteger(parsed) || parsed < 0) throw new Error("Seed must be a non-negative safe integer.");
      body.seed = parsed;
    }
    if (iterations !== "") {
      const parsed = Number(iterations);
      if (!Number.isSafeInteger(parsed) || parsed < 1) throw new Error("Iterations must be a positive safe integer.");
      body.iterations = parsed;
    }
    const signature = pretty({ token, projectId, modelId, body });
    if (createRequest.current?.signature !== signature)
      createRequest.current = { signature, key: createIdempotencyKey() };
    const created = await qraEngineApi.create(token, modelId, body, createRequest.current.key);
    if (!mounted.current || generation !== context.current) return;
    createRequest.current = null;
    selectedRef.current = created;
    setRun(created);
    setSection("Run Overview");
    setHistory((previous) => ({
      ...previous,
      items: [created, ...previous.items.filter((item) => item.id !== created.id)].slice(0, 25),
      total: previous.total + 1,
    }));
  };
  const changeState = async (action: QraRunAction) => {
    if (!run) return;
    const generation = context.current;
    const updated = await qraEngineApi.action(token, run, action, comments);
    if (!mounted.current || generation !== context.current) return;
    selectedRef.current = updated;
    setRun(updated);
    setHistory((previous) => ({
      ...previous,
      items: previous.items.map((item) => (item.id === updated.id ? updated : item)),
    }));
  };

  if (loadedContext.token !== token || loadedContext.initialView !== initialView)
    return (
      <section className="wave2b qraEngine" aria-label="QRA Calculation Engine workspace">
        <p role="status">Loading authorized QRA context…</p>
      </section>
    );
  return (
    <section className="wave2b qraEngine" aria-label="QRA Calculation Engine workspace">
      <CompactModuleHeader
        eyebrow="USER MODE / Business Case & Investment Development"
        title="QRA Calculation Engine"
        tone="user"
        description="Execute current approved model definitions in the governed worker. Preserve immutable, reproducible probabilistic analysis separately from Foundation and operational sources."
        metrics={[
          { label: "Execution", value: run?.status ?? "No run" },
          { label: "Analysis", value: run?.analysis_type ?? "—" },
          { label: "Progress", value: `${run?.iterations_completed ?? 0}/${run?.iterations_requested ?? 0}` },
        ]}
      />
      <p role="note" className="wave2bBoundary">
        QRA results are analytical evidence, not approved Budget, contingency, Management Reserve, FID or a new schedule
        baseline. Integrated cost-schedule execution is not supported in this release. Existing QRA methodology remains
        authoritative; no duplicate ADMIN module.
      </p>
      {error ? (
        <p role="alert" className="wave2bMessage">
          {error}
        </p>
      ) : null}
      {message ? (
        <p role="status" className="wave2bMessage">
          {message}
        </p>
      ) : null}
      <div className="wave2bToolbar">
        <label>
          Find authorized Projects
          <input value={search} disabled={busy} onChange={(event) => setSearch(event.target.value)} />
        </label>
        <button
          type="button"
          disabled={busy}
          onClick={() =>
            void perform(async () => {
              const generation = context.current;
              const next = await qraFoundationApi.options(token, search);
              if (!mounted.current || generation !== context.current) return;
              setProjects(next);
              await loadProject(next.projects[0]?.id ?? 0);
            }, "Authorized Project search completed.")
          }
        >
          Search Projects
        </button>
        <label>
          Project Workspace
          <select
            value={projectId}
            disabled={busy}
            onChange={(event) => void perform(() => loadProject(Number(event.target.value)), "Project loaded.")}
          >
            <option value={0}>Select Project</option>
            {projects?.projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.code} · {project.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <nav className="wave2bTabs" aria-label="QRA execution views">
        {sections.map((item) => (
          <button
            key={item}
            type="button"
            aria-current={section === item ? "page" : undefined}
            disabled={busy}
            onClick={() => {
              setSection(item);
              setResultPage(1);
              setError("");
            }}
          >
            {item}
          </button>
        ))}
      </nav>
      {projectId ? (
        <article aria-label="Approved QRA model execution">
          <h3>Approved Models</h3>
          <div className="wave2bToolbar">
            <label>
              Approved model
              <select
                value={modelId}
                disabled={busy}
                onChange={(event) => {
                  setModelId(Number(event.target.value));
                  setPreflight(null);
                }}
              >
                <option value={0}>Select approved model</option>
                {options?.approved_models.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.model_number ?? model.number} · v{model.version} · {model.analysis_type} · {model.status}
                  </option>
                ))}
              </select>
            </label>
            {selectedModel ? (
              <span>
                {selectedModel.title} · {selectedModel.status}
              </span>
            ) : (
              <span>No approved definitions are available on this page. Complete Foundation governance first.</span>
            )}
          </div>
          {modelTotal > 25 ? (
            <div className="wave2bToolbar">
              <button
                type="button"
                disabled={busy || modelPage <= 1}
                onClick={() =>
                  void perform(async () => {
                    const generation = context.current;
                    const page = await qraEngineApi.models(token, projectId, modelPage - 1);
                    if (!mounted.current || generation !== context.current) return;
                    setOptions((previous) => (previous ? { ...previous, approved_models: page.items } : previous));
                    setModelPage(page.page);
                    setModelTotal(page.total);
                    setModelId(page.items[0]?.id ?? 0);
                    setPreflight(null);
                  }, "Approved model page loaded.")
                }
              >
                Previous model page
              </button>
              <span>
                Page {modelPage} · {modelTotal} approved models
              </span>
              <button
                type="button"
                disabled={busy || modelPage * 25 >= modelTotal}
                onClick={() =>
                  void perform(async () => {
                    const generation = context.current;
                    const page = await qraEngineApi.models(token, projectId, modelPage + 1);
                    if (!mounted.current || generation !== context.current) return;
                    setOptions((previous) => (previous ? { ...previous, approved_models: page.items } : previous));
                    setModelPage(page.page);
                    setModelTotal(page.total);
                    setModelId(page.items[0]?.id ?? 0);
                    setPreflight(null);
                  }, "Approved model page loaded.")
                }
              >
                Next model page
              </button>
            </div>
          ) : null}
          {actions.includes("create") ? (
            <>
              <div className="wave2bToolbar qraRunSettings">
                <label>
                  PRNG seed
                  <input
                    type="number"
                    min="0"
                    step="1"
                    value={seed}
                    disabled={busy || seedPolicy !== "USER_SPECIFIED"}
                    onChange={(event) => {
                      setSeed(event.target.value);
                      setPreflight(null);
                    }}
                    placeholder={seedPolicy === "USER_SPECIFIED" ? "Required governed seed" : seedPolicy}
                  />
                </label>
                <label>
                  Iterations
                  <input
                    type="number"
                    min="1"
                    step="1"
                    value={iterations}
                    disabled={busy || iterationPolicy.allow_override === false}
                    onChange={(event) => {
                      setIterations(event.target.value);
                      setPreflight(null);
                    }}
                  />
                </label>
                <span>
                  Methodology: {seedPolicy}; {text(iterationPolicy.minimum)}–{text(iterationPolicy.maximum)} iterations.
                </span>
                <button
                  type="button"
                  disabled={busy || !modelId}
                  onClick={() =>
                    void perform(async () => {
                      const generation = context.current;
                      const preview = await qraEngineApi.preflight(token, modelId);
                      if (mounted.current && generation === context.current) setPreflight(preview);
                    }, "Pre-run context revalidated by backend; preview is not a run.")
                  }
                >
                  Validate pre-run
                </button>
                <button
                  type="button"
                  disabled={busy || !modelId || selectedModel?.analysis_type === "INTEGRATED_COST_SCHEDULE_QRA"}
                  onClick={() =>
                    void perform(createRun, "Run queued. Creation revalidated currentness; execute starts the worker.")
                  }
                >
                  Create governed run
                </button>
              </div>
            </>
          ) : null}
          <label>
            Run / review comments
            <textarea value={comments} disabled={busy} onChange={(event) => setComments(event.target.value)} rows={2} />
          </label>
          {preflight ? (
            <article aria-label="QRA pre-run validation">
              <h4>Pre-run validation</h4>
              <Data value={preflight} />
            </article>
          ) : null}
        </article>
      ) : (
        <p>No authorized Project selected.</p>
      )}
      <article aria-label="QRA run selection">
        <div className="wave2bToolbar">
          <label>
            Selected QRA run
            <select
              value={run?.id ?? 0}
              disabled={busy}
              onChange={(event) => void perform(() => chooseRun(Number(event.target.value)), "Selected run loaded.")}
            >
              <option value={0}>Select run</option>
              {history.items.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.run_number} · {item.analysis_type} · {item.status} · {text(item.review_status)}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            disabled={busy || !projectId}
            onClick={() => void perform(() => loadProject(projectId, history.page, run?.id), "Run status refreshed.")}
          >
            Refresh runs
          </button>
          {(
            [
              ["execute", "Execute approved run"],
              ["cancel", "Cancel run"],
              ["review", "Submit result for review"],
              ["accept", "Accept analysis evidence"],
            ] as const
          ).map(([action, label]) =>
            allows(action) ? (
              <button
                key={action}
                type="button"
                disabled={busy}
                onClick={() => void perform(() => changeState(action), `Run action ${action} completed by backend.`)}
              >
                {label}
              </button>
            ) : null
          )}
        </div>
        {history.total > history.page_size ? (
          <div className="wave2bToolbar">
            <button
              disabled={busy || history.page <= 1}
              onClick={() => void perform(() => loadProject(projectId, history.page - 1), "Previous run page loaded.")}
            >
              Previous run page
            </button>
            <span>
              Page {history.page} · {history.total} runs
            </span>
            <button
              disabled={busy || history.page * history.page_size >= history.total}
              onClick={() => void perform(() => loadProject(projectId, history.page + 1), "Next run page loaded.")}
            >
              Next run page
            </button>
          </div>
        ) : null}
        {run ? (
          <>
            <dl className="qraRunMetadata">
              {[
                ["Run", run.run_number],
                ["Execution status", run.status],
                ["Review status", run.review_status],
                ["Analytical readiness", run.analytical_readiness ?? run.readiness],
                ["Convergence status", run.convergence_status],
                ["Engine version", run.engine_version],
                ["Seed", run.seed],
                ["Heartbeat", run.heartbeat_at],
              ].map(([label, value]) => (
                <div key={String(label)}>
                  <dt>{String(label)}</dt>
                  <dd>{text(value)}</dd>
                </div>
              ))}
            </dl>
            <label>
              Run progress
              <progress
                value={run.iterations_completed}
                max={run.iterations_requested || 1}
                aria-label="Run iteration progress"
              />
              {run.iterations_completed} / {run.iterations_requested}
            </label>
            {run.failure_reason ? <p role="alert">Run failed: {text(run.failure_reason)}</p> : null}
            {section === "Runs" || section === "Approved Models" ? (
              <Data value={{ model_id: run.model_id, model_hash: run.model_hash, source_hashes: run.source_hashes }} />
            ) : section === "Run Comparison" ? (
              <>
                <h3>Compatible run comparison</h3>
                <div className="wave2bToolbar">
                  <label>
                    Compare against run
                    <select
                      value={comparisonId}
                      disabled={busy}
                      onChange={(event) => {
                        setComparisonId(Number(event.target.value));
                        setComparison(null);
                      }}
                    >
                      <option value={0}>Select comparison run</option>
                      {history.items
                        .filter((item) => item.id !== run.id && item.status === "COMPLETED")
                        .map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.run_number} · {item.analysis_type}
                          </option>
                        ))}
                    </select>
                  </label>
                  <button
                    disabled={busy || !comparisonId || run.status !== "COMPLETED"}
                    onClick={() =>
                      void perform(async () => {
                        const generation = context.current;
                        const result = await qraEngineApi.compare(token, run.id, comparisonId);
                        if (mounted.current && generation === context.current) setComparison(result);
                      }, "Compatibility and deltas resolved by backend.")
                    }
                  >
                    Compare governed runs
                  </button>
                </div>
                {comparison ? (
                  <Data value={comparison} />
                ) : (
                  <p>
                    Backend checks scope, analysis type, currency and units; incompatible runs are never silently
                    compared.
                  </p>
                )}
              </>
            ) : (
              <ResultSection section={section} content={currentContent} run={run} />
            )}
            {Number(currentContent.total ?? 0) > Number(currentContent.page_size ?? 100) ? (
              <div className="wave2bToolbar">
                <button
                  type="button"
                  disabled={busy || resultPage <= 1}
                  onClick={() => setResultPage((page) => page - 1)}
                >
                  Previous result page
                </button>
                <span>
                  Page {resultPage} · {text(currentContent.total)} result rows
                </span>
                <button
                  type="button"
                  disabled={
                    busy || resultPage * Number(currentContent.page_size ?? 100) >= Number(currentContent.total)
                  }
                  onClick={() => setResultPage((page) => page + 1)}
                >
                  Next result page
                </button>
              </div>
            ) : null}
          </>
        ) : (
          <p>No governed runs in this Project.</p>
        )}
      </article>
    </section>
  );
}

function Data({ value }: { value: unknown }) {
  return <pre>{pretty(value)}</pre>;
}
function ResultSection({ section, content, run }: { section: Section; content: JsonRecord; run: QraRun }) {
  const summary = record(content.data);
  if (run.status !== "COMPLETED" && !["Evidence / Traceability", "History"].includes(section))
    return (
      <p>
        Final results are available only after COMPLETED execution. Cancelled or failed runs have no final analytical
        evidence.
      </p>
    );
  return (
    <article aria-label={`QRA ${section}`}>
      <h3>{section}</h3>
      {section === "Run Overview" || section === "Cost Results" ? (
        <dl className="qraRunMetadata">
          {[
            ["Mean outcome", summary.mean],
            ["Standard deviation", summary.standard_deviation],
            ["Currency / duration unit", summary.currency ?? summary.unit],
            ["Cost source basis", summary.cost_basis],
            ["QRA mean completion date", summary.mean_completion_date],
            [
              "Probability meeting target",
              summary.probability_meeting_target_amount ?? summary.probability_meeting_target_date,
            ],
          ]
            .filter(([, value]) => value !== undefined && value !== null)
            .map(([label, value]) => (
              <div key={String(label)}>
                <dt>{String(label)}</dt>
                <dd>{text(value)}</dd>
              </div>
            ))}
        </dl>
      ) : null}
      {section === "Cost Results" && run.analysis_type !== "COST_QRA" ? (
        <p>This run is not Cost QRA.</p>
      ) : section === "Schedule Results" && run.analysis_type !== "SCHEDULE_QRA" ? (
        <p>This run is not Schedule QRA.</p>
      ) : (
        <>
          {section === "Percentiles" ? <Rows title="Backend-governed percentiles" items={rows(content.data)} /> : null}
          {section === "Percentiles" && run.analysis_type === "SCHEDULE_QRA" ? (
            <p role="note">
              QRA percentile completion dates are analytical normalized-time results, not an approved forecast,
              contractual date or new baseline.
            </p>
          ) : null}
          {section === "Sensitivity / Drivers" ? (
            <Rows title="Backend-governed sensitivity" items={rows(content.data)} />
          ) : null}
          {section === "Schedule Results" ? (
            <Rows title="QRA milestone distributions" items={rows(content.data)} />
          ) : null}
          {section === "Run Overview" || section === "Cost Results" ? (
            <>
              <ServerChart title="Simulated outcome histogram" points={rows(content.histogram)} kind="histogram" />
              <ServerChart title="Empirical CDF / S-curve" points={rows(content.cdf)} kind="cdf" />
            </>
          ) : null}
          <Data value={content} />
        </>
      )}
    </article>
  );
}
function Rows({ title, items }: { title: string; items: JsonRecord[] }) {
  if (!items.length) return null;
  const fields = [...new Set(items.flatMap((item) => Object.keys(item)))].slice(0, 8);
  return (
    <div className="wave2bTableScroll">
      <table aria-label={title}>
        <thead>
          <tr>
            {fields.map((field) => (
              <th key={field} scope="col">
                {field}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((item, index) => (
            <tr key={index}>
              {fields.map((field) => (
                <td key={field}>{typeof item[field] === "object" ? pretty(item[field]) : text(item[field])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function ServerChart({ title, points, kind }: { title: string; points: JsonRecord[]; kind: "histogram" | "cdf" }) {
  if (!points.length) return null;
  const values = points.map((point) => Number(point.count ?? point.probability ?? point.cumulative_probability ?? 0));
  const maximum = Math.max(...values, 1);
  const width = 600 / points.length;
  return (
    <figure className="qraResultChart">
      <figcaption>{title} · backend buckets</figcaption>
      <svg viewBox="0 0 620 180" role="img" aria-label={title}>
        {kind === "histogram" ? (
          points.map((point, index) => (
            <rect
              key={index}
              x={10 + index * width}
              y={150 - (values[index] / maximum) * 130}
              width={Math.max(1, width - 2)}
              height={(values[index] / maximum) * 130}
            >
              <title>{pretty(point)}</title>
            </rect>
          ))
        ) : (
          <polyline
            points={points
              .map(
                (_point, index) =>
                  `${10 + (index * 600) / Math.max(points.length - 1, 1)},${150 - (values[index] / maximum) * 130}`
              )
              .join(" ")}
          />
        )}
        <path className="axis" d="M10 10V150H610" />
      </svg>
      <details>
        <summary>Chart data table</summary>
        <Rows title={`${title} source data`} items={points} />
      </details>
    </figure>
  );
}
