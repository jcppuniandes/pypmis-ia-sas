/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { Gavel, ShieldCheck, Vote } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { investmentDecisionApi } from "./api";
import type { DecisionOutcome, FrozenPreparation, InvestmentDecision } from "./types";
import "./investmentDecision.css";

type DecisionView =
  | "queue"
  | "mine"
  | "package"
  | "evidence"
  | "checklist"
  | "conditions"
  | "committee"
  | "history"
  | "output";

const VIEW_BY_ROUTE: Record<string, DecisionView> = {
  "investment-decision-queue": "queue",
  "investment-decision-mine": "mine",
  "investment-decision-package": "package",
  "investment-decision-evidence": "evidence",
  "investment-decision-checklist": "checklist",
  "investment-decision-conditions": "conditions",
  "investment-decision-committee": "committee",
  "investment-decision-history": "history",
  "investment-decision-output": "output",
};

const labels: Record<DecisionView, string> = {
  queue: "Decision Queue",
  mine: "My Decisions",
  package: "Investment Decision Package",
  evidence: "Evidence Summary",
  checklist: "Decision Checklist",
  conditions: "Conditions",
  committee: "Committee / Votes",
  history: "Decision History",
  output: "Authorization Output",
};

export default function InvestmentDecisionWorkspace({ token, initialView }: { token: string; initialView?: string }) {
  const [view, setView] = useState<DecisionView>(VIEW_BY_ROUTE[initialView || ""] || "queue");
  const [decisions, setDecisions] = useState<InvestmentDecision[]>([]);
  const [preparations, setPreparations] = useState<FrozenPreparation[]>([]);
  const [selectedId, setSelectedId] = useState(0);
  const [preparationId, setPreparationId] = useState(0);
  const [makerId, setMakerId] = useState(0);
  const [outcome, setOutcome] = useState<DecisionOutcome>("GO");
  const [amount, setAmount] = useState(0);
  const [history, setHistory] = useState<Array<Record<string, unknown>>>([]);
  const [message, setMessage] = useState("");

  const selected = decisions.find((item) => item.id === selectedId) || decisions[0] || null;
  const frozen = useMemo(
    () => preparations.filter((item) => item.status === "FROZEN" && item.readiness_status === "READY"),
    [preparations]
  );

  async function load(preferredId?: number) {
    const [rows, prepRows] = await Promise.all([
      investmentDecisionApi.list(token, view === "mine" ? "mine" : ""),
      investmentDecisionApi.preparations(token),
    ]);
    setDecisions(rows);
    setPreparations(prepRows);
    setSelectedId(preferredId || rows[0]?.id || 0);
    setPreparationId((current) => current || prepRows.find((item) => item.status === "FROZEN")?.id || 0);
  }

  useEffect(() => {
    setView(VIEW_BY_ROUTE[initialView || ""] || "queue");
  }, [initialView]);
  useEffect(() => {
    void load().catch((error) => setMessage(error instanceof Error ? error.message : "Unable to load decisions"));
  }, [token, view]);
  useEffect(() => {
    if (!selected || view !== "history") return setHistory([]);
    void investmentDecisionApi
      .history(token, selected.id)
      .then(setHistory)
      .catch(() => setHistory([]));
  }, [selected?.id, view]);

  async function replace(promise: Promise<InvestmentDecision>, success: string) {
    try {
      const result = await promise;
      await load(result.id);
      setMessage(success);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Investment Decision action failed");
    }
  }

  async function create() {
    if (!preparationId) return;
    await replace(
      investmentDecisionApi.create(token, preparationId, "Formal Investment Decision"),
      "Gate 07K Decision created from the frozen Gate 07J package."
    );
  }

  function decide() {
    if (!selected) return;
    const values =
      outcome === "GO" && selected.profile_code === "PYP-FFA"
        ? { amount, currency: "USD" }
        : outcome === "HOLD"
          ? { holdReason: "Await controlled clarification." }
          : outcome === "RECYCLE"
            ? { recycleTarget: "INVESTMENT_GATE_PREPARATION" }
            : {};
    void replace(investmentDecisionApi.decide(token, selected, outcome, values), `${outcome} recorded immutably.`);
  }

  return (
    <section aria-label="Investment Decision / FID" className="investmentDecision">
      <CompactModuleHeader
        description="Formal GO, HOLD, RECYCLE or KILL governance over an exact frozen Gate 07J package. PYP-INV-SELECT GO is not FID; only PYP-FFA GO records FID and Full Funds Authorization."
        eyebrow="USER MODE · INVESTMENT GOVERNANCE · GATE 07K"
        metrics={[
          { label: "Queue", value: decisions.filter((item) => item.status !== "DECIDED").length },
          { label: "Decided", value: decisions.filter((item) => item.status === "DECIDED").length },
          { label: "FID", value: decisions.filter((item) => item.is_fid).length },
        ]}
        title="Investment Decision / FID"
      />
      {message ? (
        <div className="decisionMessage" role="status">
          {message}
        </div>
      ) : null}

      <nav aria-label="Investment Decision views" className="decisionTabs">
        {(Object.keys(labels) as DecisionView[]).map((item) => (
          <button className={view === item ? "active" : ""} key={item} onClick={() => setView(item)} type="button">
            {labels[item]}
          </button>
        ))}
      </nav>

      <section className="decisionControls">
        <label>
          Decision
          <select value={selected?.id || 0} onChange={(event) => setSelectedId(Number(event.target.value))}>
            <option value={0}>No decision selected</option>
            {decisions.map((item) => (
              <option key={item.id} value={item.id}>
                {item.decision_number} · {item.profile_code} · {item.status}
              </option>
            ))}
          </select>
        </label>
        <label>
          Frozen Gate 07J package
          <select value={preparationId} onChange={(event) => setPreparationId(Number(event.target.value))}>
            <option value={0}>Select eligible preparation</option>
            {frozen.map((item) => (
              <option key={item.id} value={item.id}>
                {item.preparation_number} · {item.profile_code}
              </option>
            ))}
          </select>
        </label>
        <button disabled={!preparationId} onClick={() => void create()} type="button">
          Create Decision
        </button>
      </section>

      {selected ? (
        <>
          <section className={`decisionReadiness ${selected.readiness.readiness_status.toLowerCase()}`}>
            <div>
              <span>Decision</span>
              <h3>
                {selected.decision_number} · round {selected.decision_round}
              </h3>
            </div>
            <div className="decisionFlags">
              <b>{selected.profile_code}</b>
              <b>{selected.status}</b>
              <b>{selected.readiness.readiness_status}</b>
              <b className={selected.is_fid ? "fid" : "boundary"}>FID {selected.is_fid ? "YES" : "NO"}</b>
              <b className="boundary">Project activation NO</b>
            </div>
          </section>

          {view === "queue" || view === "mine" ? (
            <section className="decisionSurface">
              <header>
                <div>
                  <span>Controlled lifecycle</span>
                  <h3>Decision actions</h3>
                </div>
                <Gavel size={24} />
              </header>
              <div className="decisionFacts">
                <article>
                  <span>Package hash</span>
                  <b>{selected.source_package_hash.slice(0, 14)}…</b>
                </article>
                <article>
                  <span>Exact scope hash</span>
                  <b>{selected.decision_scope_hash.slice(0, 14)}…</b>
                </article>
                <article>
                  <span>Authority</span>
                  <b>{selected.authority_model}</b>
                </article>
                <article>
                  <span>Outcome</span>
                  <b>{selected.outcome || "PENDING"}</b>
                </article>
              </div>
              <div className="decisionActions">
                <label>
                  Decision maker user ID
                  <input
                    min={1}
                    onChange={(event) => setMakerId(Number(event.target.value))}
                    type="number"
                    value={makerId || ""}
                  />
                </label>
                <button
                  disabled={!selected.allowed_actions.includes("can_edit_decision") || !makerId}
                  onClick={() =>
                    void replace(
                      investmentDecisionApi.assignMaker(token, selected, makerId),
                      "Decision authority assigned."
                    )
                  }
                  type="button"
                >
                  Assign maker
                </button>
                <button
                  disabled={!selected.allowed_actions.includes("can_submit_decision")}
                  onClick={() =>
                    void replace(investmentDecisionApi.transition(token, selected, "submit"), "Decision submitted.")
                  }
                  type="button"
                >
                  Submit
                </button>
                <button
                  disabled={!selected.allowed_actions.includes("can_start_review")}
                  onClick={() =>
                    void replace(investmentDecisionApi.transition(token, selected, "start-review"), "Review started.")
                  }
                  type="button"
                >
                  Start review
                </button>
                <button
                  disabled={!selected.allowed_actions.includes("can_mark_ready_for_decision")}
                  onClick={() =>
                    void replace(
                      investmentDecisionApi.ready(token, selected),
                      "Checklist acknowledged; ready for decision."
                    )
                  }
                  type="button"
                >
                  Ready for decision
                </button>
              </div>
              <div className="decisionActions formal">
                <label>
                  Outcome
                  <select value={outcome} onChange={(event) => setOutcome(event.target.value as DecisionOutcome)}>
                    {["GO", "HOLD", "RECYCLE", "KILL"].map((item) => (
                      <option key={item}>{item}</option>
                    ))}
                  </select>
                </label>
                {selected.profile_code === "PYP-FFA" && outcome === "GO" ? (
                  <label>
                    Authorized amount
                    <input
                      min={0}
                      onChange={(event) => setAmount(Number(event.target.value))}
                      type="number"
                      value={amount}
                    />
                  </label>
                ) : null}
                <button disabled={!selected.allowed_actions.includes("can_decide")} onClick={decide} type="button">
                  <ShieldCheck size={15} /> Record formal decision
                </button>
              </div>
            </section>
          ) : null}

          {view === "package" ? (
            <JsonSurface title="Frozen Decision Package Snapshot" value={selected.decision_package_snapshot} />
          ) : null}
          {view === "evidence" ? (
            <JsonSurface
              title="Evidence Summary (source results only)"
              value={(selected.decision_package_snapshot.evidence_summary as Record<string, unknown>) || {}}
            />
          ) : null}
          {view === "checklist" ? <CardList title="Decision Checklist" rows={selected.checklist} /> : null}
          {view === "conditions" ? (
            <CardList title="Input and post-decision conditions" rows={selected.conditions} />
          ) : null}
          {view === "committee" ? (
            <section className="decisionSurface">
              <header>
                <div>
                  <span>Frozen authority</span>
                  <h3>Committee / Votes</h3>
                </div>
                <Vote size={24} />
              </header>
              <div className="decisionFacts">
                <article>
                  <span>Quorum</span>
                  <b>{selected.readiness.quorum_met ? "MET" : "NOT MET"}</b>
                </article>
                <article>
                  <span>Voting rule</span>
                  <b>{String(selected.voting_rule.rule || "N/A")}</b>
                </article>
                <article>
                  <span>Votes</span>
                  <b>{selected.votes.length}</b>
                </article>
              </div>
              <div className="decisionActions">
                {["GO", "HOLD", "RECYCLE", "KILL", "ABSTAIN"].map((item) => (
                  <button
                    disabled={!selected.allowed_actions.includes("can_cast_vote")}
                    key={item}
                    onClick={() =>
                      void replace(
                        investmentDecisionApi.vote(token, selected, item as DecisionOutcome | "ABSTAIN"),
                        `${item} vote recorded.`
                      )
                    }
                    type="button"
                  >
                    Vote {item}
                  </button>
                ))}
              </div>
              <pre>
                {JSON.stringify(
                  { committee: selected.committee, quorum: selected.quorum, votes: selected.votes },
                  null,
                  2
                )}
              </pre>
            </section>
          ) : null}
          {view === "history" ? <CardList title="Immutable Decision History" rows={history} /> : null}
          {view === "output" ? (
            <JsonSurface title="Authorization Output" value={selected.authorization_output} />
          ) : null}
        </>
      ) : (
        <section className="decisionSurface empty">
          <h3>No Investment Decision yet</h3>
          <p>Select a frozen, current Gate 07J preparation to start a controlled round.</p>
        </section>
      )}

      <p className="decisionGuardrail">
        STOP boundary: no Project creation or activation, contracting, accounting, payments, NTP or execution action is
        exposed here.
      </p>
    </section>
  );
}

function JsonSurface({ title, value }: { title: string; value: Record<string, unknown> }) {
  return (
    <section className="decisionSurface">
      <header>
        <div>
          <span>Historical snapshot</span>
          <h3>{title}</h3>
        </div>
      </header>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </section>
  );
}

function CardList({ title, rows }: { title: string; rows: Array<Record<string, unknown>> }) {
  return (
    <section className="decisionSurface">
      <header>
        <div>
          <span>Governed records</span>
          <h3>{title}</h3>
        </div>
      </header>
      <div className="decisionCards">
        {rows.map((item, index) => (
          <article key={String(item.id || item.code || index)}>
            <b>{String(item.label || item.code || item.event_type || `Item ${index + 1}`)}</b>
            <span>{String(item.status || item.outcome || (item.acknowledged ? "ACKNOWLEDGED" : "OPEN"))}</span>
            <small>{String(item.note || item.description || item.rationale || "")}</small>
          </article>
        ))}
      </div>
    </section>
  );
}
