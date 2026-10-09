/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { BadgeDollarSign, Banknote, CircleDollarSign, RefreshCw, ShieldCheck, Waypoints } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { portfolioPlanningApi } from "../portfolio-planning/api";
import { fundsManagerApi } from "./api";
import "./fundsManager.css";
import type { Fund, FundingAssignment, FundingSource, FundsOverview } from "./types";

type FundsView = "overview" | "sources" | "funds" | "assignments" | "coverage" | "readiness" | "history";

const VIEW_BY_ROUTE: Record<string, FundsView> = {
  "funds-overview": "overview",
  "funds-sources": "sources",
  "funds-envelopes": "funds",
  "funds-assignments": "assignments",
  "funds-coverage": "coverage",
  "funds-readiness": "readiness",
  "funds-history": "history",
};

const money = (value: number | null | undefined, currency = "") =>
  value == null
    ? "Not comparable"
    : `${currency} ${Number(value).toLocaleString("en-US", { maximumFractionDigits: 2 })}`.trim();

export default function FundsManagerWorkspace({ token, initialView }: { token: string; initialView?: string }) {
  const [portfolios, setPortfolios] = useState<Array<Record<string, unknown>>>([]);
  const [portfolioId, setPortfolioId] = useState(0);
  const [overview, setOverview] = useState<FundsOverview | null>(null);
  const [view, setView] = useState<FundsView>(VIEW_BY_ROUTE[initialView || ""] || "overview");
  const [message, setMessage] = useState("");
  const [sourceName, setSourceName] = useState("Corporate CAPEX source");
  const [sourceType, setSourceType] = useState("CORPORATE_CAPEX");
  const [currency, setCurrency] = useState("COP");
  const [fundName, setFundName] = useState("Portfolio investment fund");
  const [fundSourceId, setFundSourceId] = useState(0);
  const [authorizedAmount, setAuthorizedAmount] = useState(0);
  const [assignmentFundId, setAssignmentFundId] = useState(0);
  const [assignmentAmount, setAssignmentAmount] = useState(0);
  const [evidence, setEvidence] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    setView(VIEW_BY_ROUTE[initialView || ""] || "overview");
  }, [initialView]);

  useEffect(() => {
    void portfolioPlanningApi.portfolioOptions(token).then((items) => {
      setPortfolios(items);
      setPortfolioId((current) => current || Number(items[0]?.id || 0));
    });
  }, [token]);

  async function load(clearMessage = true) {
    if (!portfolioId) return;
    try {
      const result = await fundsManagerApi.overview(token, portfolioId);
      setOverview(result);
      setFundSourceId((current) => current || result.funding_sources[0]?.id || 0);
      setAssignmentFundId((current) => current || result.funds[0]?.id || 0);
      setAssignmentAmount((current) => current || Number(result.readiness?.required_amount || 0));
      if (clearMessage) setMessage("");
    } catch (error) {
      setOverview(null);
      setMessage(error instanceof Error ? error.message : "Unable to load Funds Manager");
    }
  }

  useEffect(() => {
    void load();
  }, [portfolioId]);

  const selectedFund = useMemo(
    () => overview?.funds.find((item) => item.id === assignmentFundId) || null,
    [assignmentFundId, overview]
  );

  async function execute<T>(work: () => Promise<T>, success: string | ((result: T) => string)) {
    try {
      const result = await work();
      await load(false);
      setMessage(typeof success === "function" ? success(result) : success);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Funds Manager action failed");
    }
  }

  const readiness = overview?.readiness;
  const comparableCurrency = overview?.comparable_currency || readiness?.required_currency || "";
  return (
    <section aria-label="Funds Manager" className="fundsManager">
      <CompactModuleHeader
        description="Governs strategic funding origins, authorized Funds, controlled assignments and Funding Readiness for Gate 07J. It never executes treasury, accounting, commitments, FID or Project activation."
        eyebrow="USER MODE · ENTERPRISE STRATEGY MANAGER · GATE 07J-FUND"
        metrics={[
          { label: "Active Funds", value: overview?.active_funds || 0 },
          { label: "Confirmed", value: `${readiness?.confirmed_coverage_percent || 0}%` },
          { label: "Readiness", value: readiness?.funding_readiness_status || "NOT STARTED" },
        ]}
        title="Funds Manager"
      />

      <div className="fundsToolbar">
        <nav aria-label="Funds Manager views">
          {(["overview", "sources", "funds", "assignments", "coverage", "readiness", "history"] as FundsView[]).map(
            (item) => (
              <button className={view === item ? "active" : ""} key={item} onClick={() => setView(item)} type="button">
                {item}
              </button>
            )
          )}
        </nav>
        <label>
          Portfolio
          <select value={portfolioId} onChange={(event) => setPortfolioId(Number(event.target.value))}>
            {portfolios.map((item) => (
              <option key={Number(item.id)} value={Number(item.id)}>
                {String(item.name)}
              </option>
            ))}
          </select>
        </label>
      </div>

      {message ? (
        <div className="fundsMessage" role="status">
          {message}
        </div>
      ) : null}

      {view === "overview" ? (
        <div className="fundsOverview">
          <section
            className={`fundingReadinessHero ${readiness?.funding_readiness_status === "READY" ? "ready" : "blocked"}`}
          >
            <div>
              <span>Final controlled output</span>
              <h3>{readiness?.final_output || "GATE07J_FUND_REWORK_REQUIRED"}</h3>
              <p>
                Budget feasibility and Funding availability remain independent. Readiness supplies evidence only; it is
                not Investment Approval or Full Funds Authorization.
              </p>
            </div>
            <ShieldCheck size={38} />
          </section>
          <div className="fundingMetricGrid">
            <article>
              <BadgeDollarSign />
              <span>Authorized funding</span>
              <strong>{money(overview?.authorized_funding, comparableCurrency)}</strong>
            </article>
            <article>
              <CircleDollarSign />
              <span>Confirmed assigned</span>
              <strong>{money(overview?.confirmed_assigned, comparableCurrency)}</strong>
            </article>
            <article>
              <Waypoints />
              <span>Reserved</span>
              <strong>{money(overview?.reserved_assigned, comparableCurrency)}</strong>
            </article>
            <article>
              <Banknote />
              <span>Available</span>
              <strong>{money(overview?.available_funding, comparableCurrency)}</strong>
            </article>
            <article>
              <span>Funding gap</span>
              <strong>{money(overview?.funding_gap, readiness?.required_currency)}</strong>
            </article>
            <article>
              <span>Coverage</span>
              <strong>{overview?.coverage_percent ?? 0}%</strong>
            </article>
          </div>
          {!overview?.governance_model_applicable ? (
            <p className="fundsGuardrail">
              Funds Manager is not required by default for CONTRACTOR_DELIVERY, DIRECT_INTERNAL or Legacy routes.
            </p>
          ) : null}
          <div className="fundsBoundaries">
            {overview?.boundaries.map((item) => (
              <span key={item}>{item}</span>
            ))}
          </div>
        </div>
      ) : null}

      {view === "sources" ? (
        <section className="fundsSurface">
          <header>
            <div>
              <span>Origin of financing</span>
              <h3>Funding Sources</h3>
            </div>
          </header>
          <form
            className="fundingInlineForm"
            onSubmit={(event) => {
              event.preventDefault();
              void execute(
                () => fundsManagerApi.createSource(token, sourceName, sourceType, currency),
                "Funding Source created as DRAFT."
              );
            }}
          >
            <label>
              Name
              <input value={sourceName} onChange={(event) => setSourceName(event.target.value)} />
            </label>
            <label>
              Type
              <select value={sourceType} onChange={(event) => setSourceType(event.target.value)}>
                {[
                  "CORPORATE_CAPEX",
                  "OPERATING_CASH",
                  "DEBT_FACILITY",
                  "BANK_LOAN",
                  "BOND",
                  "GRANT",
                  "GOVERNMENT_APPROPRIATION",
                  "JV_CONTRIBUTION",
                  "PARTNER_CONTRIBUTION",
                  "DEVELOPMENT_BANK",
                  "OTHER",
                ].map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </label>
            <label>
              Currency
              <input
                maxLength={8}
                value={currency}
                onChange={(event) => setCurrency(event.target.value.toUpperCase())}
              />
            </label>
            <button type="submit">Create Funding Source</button>
          </form>
          <div className="fundingCards">
            {overview?.funding_sources.map((source) => (
              <SourceCard
                key={source.id}
                source={source}
                onAction={(action) =>
                  void execute(
                    () => fundsManagerApi.sourceAction(token, source, action),
                    `Funding Source ${action} completed.`
                  )
                }
              />
            ))}
          </div>
        </section>
      ) : null}

      {view === "funds" ? (
        <section className="fundsSurface">
          <header>
            <div>
              <span>Governed financing capacity</span>
              <h3>Funds / Funding Envelopes</h3>
            </div>
          </header>
          <form
            className="fundingInlineForm"
            onSubmit={(event) => {
              event.preventDefault();
              void execute(
                () => fundsManagerApi.createFund(token, fundSourceId || null, fundName, currency, authorizedAmount),
                "Fund created as DRAFT."
              );
            }}
          >
            <label>
              Name
              <input value={fundName} onChange={(event) => setFundName(event.target.value)} />
            </label>
            <label>
              Funding Source
              <select value={fundSourceId} onChange={(event) => setFundSourceId(Number(event.target.value))}>
                <option value={0}>Independent Fund</option>
                {overview?.funding_sources.map((source) => (
                  <option key={source.id} value={source.id}>
                    {source.source_code} · {source.source_name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Authorized amount
              <input
                min={0}
                type="number"
                value={authorizedAmount}
                onChange={(event) => setAuthorizedAmount(Number(event.target.value))}
              />
            </label>
            <button type="submit">Create Fund</button>
          </form>
          <div className="fundingCards">
            {overview?.funds.map((fund) => (
              <FundCard
                key={fund.id}
                fund={fund}
                onAction={(action) =>
                  void execute(() => fundsManagerApi.fundAction(token, fund, action), `Fund ${action} completed.`)
                }
              />
            ))}
          </div>
        </section>
      ) : null}

      {view === "assignments" ? (
        <section className="fundsSurface">
          <header>
            <div>
              <span>Controlled allocation / earmark</span>
              <h3>Funding Assignments</h3>
            </div>
          </header>
          <form
            className="fundingInlineForm"
            onSubmit={(event) => {
              event.preventDefault();
              if (!selectedFund || !overview) return;
              void execute(
                () => fundsManagerApi.createAssignment(token, selectedFund, overview, assignmentAmount),
                "Funding Assignment created as DRAFT."
              );
            }}
          >
            <label>
              Fund
              <select
                data-testid="funding-assignment-fund"
                value={assignmentFundId}
                onChange={(event) => setAssignmentFundId(Number(event.target.value))}
              >
                {overview?.funds.map((fund) => (
                  <option key={fund.id} value={fund.id}>
                    {fund.fund_code} · {fund.currency} {fund.available_amount}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Amount
              <input
                data-testid="funding-assignment-amount"
                min={0.01}
                step="0.01"
                type="number"
                value={assignmentAmount}
                onChange={(event) => setAssignmentAmount(Number(event.target.value))}
              />
            </label>
            <label>
              Scope
              <input disabled value="RECOMMENDED_PROJECT_SET" />
            </label>
            <button disabled={!selectedFund || !readiness?.recommended_project_set_hash} type="submit">
              Create Assignment
            </button>
          </form>
          <AssignmentTable
            assignments={overview?.assignments || []}
            onAction={(assignment, action) =>
              void execute(
                () => fundsManagerApi.assignmentAction(token, assignment, action),
                `Assignment ${action} completed.`
              )
            }
          />
        </section>
      ) : null}

      {view === "coverage" ? (
        <section className="fundsSurface">
          <header>
            <div>
              <span>Governed financial coverage</span>
              <h3>Funding Coverage</h3>
            </div>
          </header>
          <div className="coverageStrip">
            <article data-testid="funding-coverage-required">
              <span>Required</span>
              <strong>{money(readiness?.required_amount, readiness?.required_currency)}</strong>
            </article>
            <article data-testid="funding-coverage-confirmed">
              <span>Confirmed</span>
              <strong>{money(readiness?.confirmed_funding_amount, readiness?.required_currency)}</strong>
            </article>
            <article data-testid="funding-coverage-reserved">
              <span>Reserved</span>
              <strong>{money(readiness?.reserved_funding_amount, readiness?.required_currency)}</strong>
            </article>
            <article data-testid="funding-coverage-gap">
              <span>Gap</span>
              <strong>{money(readiness?.funding_gap, readiness?.required_currency)}</strong>
            </article>
          </div>
          <CoverageTable title="Project Funding Matrix" rows={readiness?.project_coverage_summary || []} />
          <CoverageTable title="Funding by period" rows={readiness?.period_coverage_summary || []} />
        </section>
      ) : null}

      {view === "readiness" ? (
        <section className="fundsSurface">
          <header>
            <div>
              <span>Gate 07J governed source</span>
              <h3>Funding Readiness</h3>
            </div>
            <strong data-testid="funding-readiness-status">{readiness?.funding_readiness_status}</strong>
          </header>
          <div className="readinessDetail">
            <p>
              <b>Requirement hash</b>
              <code>{readiness?.funding_requirement_hash}</code>
            </p>
            <p>
              <b>Readiness hash</b>
              <code>{readiness?.funding_readiness_hash}</code>
            </p>
            <p>
              <b>Source current</b>
              <span>{readiness?.source_current ? "YES" : "NO · refresh required"}</span>
            </p>
            <p>
              <b>Restrictions</b>
              <span>{String(readiness?.restriction_summary.status || "—")}</span>
            </p>
            <p>
              <b>Open blocking conditions</b>
              <span>{String(readiness?.conditions_summary.open_blocking || 0)}</span>
            </p>
          </div>
          {readiness?.blockers.map((item) => (
            <p className="fundsBlocker" key={item}>
              {item}
            </p>
          ))}
          <div className="fundsActions">
            <button
              onClick={() =>
                void execute(
                  () => fundsManagerApi.refreshPreview(token, portfolioId),
                  (preview) => `Refresh Preview ready; persisted=${String(preview.persisted)}.`
                )
              }
              type="button"
            >
              <RefreshCw size={14} /> Refresh Preview
            </button>
            <button
              disabled={!readiness?.source_hash}
              onClick={() =>
                void execute(
                  () => fundsManagerApi.refresh(token, portfolioId, readiness?.source_hash || ""),
                  "Funding Readiness snapshot refreshed."
                )
              }
              type="button"
            >
              Apply Refresh
            </button>
            <button
              disabled={!readiness?.can_supply_investment_gate_evidence}
              onClick={() =>
                void execute(
                  async () => setEvidence(await fundsManagerApi.evidence(token, portfolioId)),
                  "Gate 07J evidence resolved as GOVERNED_SOURCE."
                )
              }
              type="button"
            >
              Open Gate 07J evidence
            </button>
          </div>
          {evidence ? <pre>{JSON.stringify(evidence, null, 2)}</pre> : null}
        </section>
      ) : null}

      {view === "history" ? (
        <section className="fundsSurface">
          <header>
            <div>
              <span>Immutable traceability</span>
              <h3>History / Audit</h3>
            </div>
          </header>
          <AssignmentTable assignments={overview?.assignments || []} onAction={() => undefined} readOnly />
        </section>
      ) : null}

      <p className="fundsGuardrail">
        No bank accounts · no ledger · no payments · no commitments · no Investment Decision/FID · no Project
        activation.
      </p>
    </section>
  );
}

function SourceCard({
  source,
  onAction,
}: {
  source: FundingSource;
  onAction: (action: "activate" | "suspend" | "close") => void;
}) {
  return (
    <article data-testid={`funding-source-${source.id}`}>
      <span>{source.source_type}</span>
      <h4>
        {source.source_code} · {source.source_name}
      </h4>
      <strong>
        {source.currency} · {source.status}
      </strong>
      <small>
        Effective {dateRange(source.effective_from, source.effective_to)} · {Object.keys(source.restrictions).length}{" "}
        restriction(s) · {source.evidence_refs.length} evidence ref(s)
      </small>
      <small>{source.legal_entity_provider_reference || "No provider reference"}</small>
      <div>
        {source.allowed_actions.includes("can_activate_funding_source") ? (
          <button onClick={() => onAction("activate")} type="button">
            Activate
          </button>
        ) : null}
        {source.allowed_actions.includes("can_suspend_funding_source") ? (
          <button onClick={() => onAction("suspend")} type="button">
            Suspend
          </button>
        ) : null}
        {source.allowed_actions.includes("can_close_funding_source") ? (
          <button onClick={() => onAction("close")} type="button">
            Close
          </button>
        ) : null}
      </div>
    </article>
  );
}

function FundCard({
  fund,
  onAction,
}: {
  fund: Fund;
  onAction: (action: "authorize" | "activate" | "suspend" | "close") => void;
}) {
  const lifecycleStatus =
    fund.status === "ACTIVE" && Number(fund.available_amount) === 0 ? "EXHAUSTED (derived)" : fund.status;
  return (
    <article data-testid={`fund-${fund.id}`}>
      <span>{fund.funding_source_name || "Independent"}</span>
      <h4>
        {fund.fund_code} · {fund.fund_name}
      </h4>
      <strong>
        {fund.currency} {Number(fund.authorized_amount).toLocaleString()} · {lifecycleStatus}
      </strong>
      <small>
        Assigned {fund.assigned_amount} · Available {fund.available_amount}
      </small>
      <small>
        Effective {dateRange(fund.available_from, fund.available_to)} · {Object.keys(fund.restrictions).length}{" "}
        restriction(s) · {fund.evidence_refs.length} evidence ref(s)
      </small>
      <div>
        {fund.allowed_actions.includes("can_authorize_fund") ? (
          <button onClick={() => onAction("authorize")} type="button">
            Authorize
          </button>
        ) : null}
        {fund.allowed_actions.includes("can_activate_fund") ? (
          <button onClick={() => onAction("activate")} type="button">
            Activate
          </button>
        ) : null}
        {fund.allowed_actions.includes("can_suspend_fund") ? (
          <button onClick={() => onAction("suspend")} type="button">
            Suspend
          </button>
        ) : null}
        {fund.allowed_actions.includes("can_close_fund") ? (
          <button onClick={() => onAction("close")} type="button">
            Close
          </button>
        ) : null}
      </div>
    </article>
  );
}

function AssignmentTable({
  assignments,
  onAction,
  readOnly = false,
}: {
  assignments: FundingAssignment[];
  onAction: (item: FundingAssignment, action: "reserve" | "confirm" | "release" | "cancel") => void;
  readOnly?: boolean;
}) {
  return (
    <div className="fundingTableWrap">
      <table>
        <thead>
          <tr>
            <th>Assignment</th>
            <th>Fund</th>
            <th>Scope</th>
            <th>Amount</th>
            <th>Status</th>
            <th>Eligibility / conditions</th>
            <th>Coverage contribution</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {assignments.map((item) => (
            <tr data-testid={`funding-assignment-${item.id}`} key={item.id}>
              <td>{item.assignment_number}</td>
              <td>{item.fund_code}</td>
              <td>
                {item.scope_type}
                {item.parent_assignment_id ? " · sub-allocation" : ""}
              </td>
              <td>
                {item.currency} {item.amount}
              </td>
              <td>{item.warnings.includes("ASSIGNMENT_EXPIRED") ? "EXPIRED (derived)" : item.status}</td>
              <td>
                {item.eligibility_status} · {item.conditions.length} condition(s)
              </td>
              <td>{item.coverage_contribution}</td>
              <td>
                {!readOnly && item.allowed_actions.includes("can_reserve_funding") ? (
                  <button onClick={() => onAction(item, "reserve")} type="button">
                    Reserve
                  </button>
                ) : null}
                {!readOnly && item.allowed_actions.includes("can_confirm_funding") ? (
                  <button onClick={() => onAction(item, "confirm")} type="button">
                    Confirm
                  </button>
                ) : null}
                {!readOnly && item.allowed_actions.includes("can_release_funding") ? (
                  <button onClick={() => onAction(item, "release")} type="button">
                    Release
                  </button>
                ) : null}
                {!readOnly && item.allowed_actions.includes("can_cancel_funding_assignment") ? (
                  <button onClick={() => onAction(item, "cancel")} type="button">
                    Cancel
                  </button>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function dateRange(from: string | null, to: string | null) {
  return `${from || "open"} → ${to || "open"}`;
}

function CoverageTable({ title, rows }: { title: string; rows: Array<Record<string, unknown>> }) {
  if (!rows.length) return <p className="fundsEmpty">{title}: no governed breakdown is available.</p>;
  const columns = Object.keys(rows[0]);
  return (
    <div className="fundingTableWrap">
      <h4>{title}</h4>
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column.replace(/_/g, " ")}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {columns.map((column) => (
                <td key={column}>{String(row[column] ?? "—")}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
