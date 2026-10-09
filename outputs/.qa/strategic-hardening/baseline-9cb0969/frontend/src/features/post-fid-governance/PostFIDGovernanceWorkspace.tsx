/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { ArrowRightLeft, RefreshCw, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { postFIDGovernanceApi } from "./api";
import type { PostFIDDecision, PostFIDEligibility, RefreshPreview } from "./types";
import "./postFIDGovernance.css";

type View = "queue" | "handoff" | "matrix" | "conditions" | "initialization" | "activation" | "history";

const VIEW_BY_ROUTE: Record<string, View> = {
  "post-fid-queue": "queue",
  "post-fid-handoff": "handoff",
  "post-fid-eligibility-matrix": "matrix",
  "post-fid-conditions": "conditions",
  "post-fid-initialization-handoff": "initialization",
  "post-fid-activation-handoff": "activation",
  "post-fid-history": "history",
};

const labels: Record<View, string> = {
  queue: "Post-FID Queue",
  handoff: "FID Handoff",
  matrix: "Project Eligibility Matrix",
  conditions: "Post-FID Conditions",
  initialization: "Initialization Handoff",
  activation: "Activation Handoff",
  history: "History / Audit",
};

export default function PostFIDGovernanceWorkspace({ token, initialView }: { token: string; initialView?: string }) {
  const [view, setView] = useState<View>(VIEW_BY_ROUTE[initialView || ""] || "queue");
  const [decisions, setDecisions] = useState<PostFIDDecision[]>([]);
  const [selectedId, setSelectedId] = useState(0);
  const [preview, setPreview] = useState<RefreshPreview | null>(null);
  const [history, setHistory] = useState<Array<Record<string, unknown>>>([]);
  const [message, setMessage] = useState("");
  const selected = decisions.find((item) => item.investment_decision_id === selectedId) || decisions[0] || null;
  const projects = selected?.projects || [];
  const revisionVersion = Math.max(1, ...projects.map((item) => item.revision_version));
  const metrics = useMemo(
    () => [
      { label: "FID queue", value: decisions.filter((item) => item.is_fid).length },
      { label: "Initialize", value: projects.filter((item) => item.can_initialize).length },
      { label: "Activate", value: projects.filter((item) => item.can_activate).length },
      { label: "Blocked / stale", value: projects.filter((item) => item.blockers.length || item.stale).length },
    ],
    [decisions, projects]
  );

  async function load(preferredId?: number) {
    const rows = await postFIDGovernanceApi.list(token);
    setDecisions(rows);
    setSelectedId(preferredId || rows[0]?.investment_decision_id || 0);
  }

  useEffect(() => setView(VIEW_BY_ROUTE[initialView || ""] || "queue"), [initialView]);
  useEffect(() => {
    void load().catch((error) => setMessage(error instanceof Error ? error.message : "Unable to load Gate 07L"));
  }, [token]);
  useEffect(() => {
    if (!selected || view !== "history") return setHistory([]);
    void postFIDGovernanceApi
      .history(token, selected.investment_decision_id)
      .then(setHistory)
      .catch(() => setHistory([]));
  }, [selected?.investment_decision_id, view]);

  async function evaluate() {
    if (!selected) return;
    try {
      await postFIDGovernanceApi.evaluate(token, selected.investment_decision_id, revisionVersion);
      await load(selected.investment_decision_id);
      setMessage("Eligibility snapshot evaluated and persisted without mutating Project Workspace state.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Eligibility evaluation failed");
    }
  }

  async function previewRefresh() {
    if (!selected) return;
    try {
      setPreview(await postFIDGovernanceApi.previewRefresh(token, selected.investment_decision_id));
      setMessage("Refresh preview completed with persisted=false.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Refresh preview failed");
    }
  }

  async function applyRefresh() {
    if (!selected) return;
    try {
      await postFIDGovernanceApi.refresh(token, selected.investment_decision_id, revisionVersion);
      setPreview(null);
      await load(selected.investment_decision_id);
      setMessage("A new immutable eligibility round was applied only where source hashes changed.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Refresh failed");
    }
  }

  async function handoff(item: PostFIDEligibility, kind: "initialization" | "activation") {
    try {
      const contract = await postFIDGovernanceApi.handoff(token, item, kind);
      setMessage(
        `Delegated handoff ready: ${String(contract.delegated_service)} → ${String(contract.delegated_endpoint)}. No lifecycle mutation executed by Gate 07L.`
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Handoff is not available");
    }
  }

  return (
    <section aria-label="Post-FID Project Governance" className="postFID">
      <CompactModuleHeader
        description="Governance, eligibility and delegated handoff from a current Gate 07K FID to the existing Project Workspace Initialization and Activation processes."
        eyebrow="USER MODE · INVESTMENT GOVERNANCE · GATE 07L"
        metrics={metrics}
        title="Post-FID Project Governance"
      />
      {message ? (
        <div className="postFIDMessage" role="status">
          {message}
        </div>
      ) : null}
      <nav aria-label="Post-FID Governance views" className="postFIDTabs">
        {(Object.keys(labels) as View[]).map((item) => (
          <button className={view === item ? "active" : ""} key={item} onClick={() => setView(item)} type="button">
            {labels[item]}
          </button>
        ))}
      </nav>
      <div className="postFIDControls">
        <label>
          Investment Decision / FID
          <select
            value={selected?.investment_decision_id || 0}
            onChange={(event) => setSelectedId(Number(event.target.value))}
          >
            {!decisions.length ? <option value={0}>No decided Gate 07K records</option> : null}
            {decisions.map((item) => (
              <option key={item.investment_decision_id} value={item.investment_decision_id}>
                {item.decision_number} · {item.gate_profile} · {item.outcome}
              </option>
            ))}
          </select>
        </label>
        <button disabled={!selected} onClick={() => void evaluate()} type="button">
          <ShieldCheck size={15} /> Evaluate
        </button>
        <button disabled={!selected} onClick={() => void previewRefresh()} type="button">
          <RefreshCw size={15} /> Refresh preview
        </button>
        <button disabled={!preview} onClick={() => void applyRefresh()} type="button">
          <ArrowRightLeft size={15} /> Apply refresh
        </button>
      </div>

      {selected ? (
        <>
          {view === "queue" ? (
            <section className="postFIDSurface">
              <header>
                <div>
                  <span>Current queue item</span>
                  <h3>{selected.title}</h3>
                </div>
                <b>{selected.final_output}</b>
              </header>
              <div className="postFIDFacts">
                <article>
                  <span>Gate profile</span>
                  <b>{selected.gate_profile}</b>
                </article>
                <article>
                  <span>FID handoff</span>
                  <b>{selected.post_fid_handoff || "NOT APPLICABLE"}</b>
                </article>
                <article>
                  <span>Projects</span>
                  <b>{selected.project_count}</b>
                </article>
                <article>
                  <span>NEXT</span>
                  <b>{selected.next}</b>
                </article>
              </div>
            </section>
          ) : null}
          {view === "handoff" ? (
            <JsonSurface title="Gate 07K FID Handoff" value={selected as unknown as Record<string, unknown>} />
          ) : null}
          {view === "matrix" ? <EligibilityMatrix projects={projects} /> : null}
          {view === "conditions" ? <ConditionCards projects={projects} /> : null}
          {view === "initialization" ? (
            <HandoffCards
              kind="initialization"
              onHandoff={handoff}
              projects={projects.filter((item) => item.can_initialize)}
            />
          ) : null}
          {view === "activation" ? (
            <HandoffCards
              kind="activation"
              onHandoff={handoff}
              projects={projects.filter((item) => item.can_activate)}
            />
          ) : null}
          {view === "history" ? <JsonSurface title="Eligibility History / SecurityEvent" value={{ history }} /> : null}
        </>
      ) : (
        <section className="postFIDSurface">
          <h3>No Gate 07K decision is available</h3>
        </section>
      )}
      {preview ? (
        <JsonSurface title="Refresh deltas · persisted=false" value={preview as unknown as Record<string, unknown>} />
      ) : null}
      <p className="postFIDGuardrail">
        STOP boundary: Gate 07L does not create a Project, execute Initialization or Activation, issue NTP, or create
        procurement, commitment, contract, payment, accounting or execution records.
      </p>
    </section>
  );
}

function EligibilityMatrix({ projects }: { projects: PostFIDEligibility[] }) {
  return (
    <section className="postFIDSurface matrix">
      <header>
        <div>
          <span>Per-Project routing</span>
          <h3>Project Eligibility Matrix</h3>
        </div>
      </header>
      <div className="postFIDTableWrap">
        <table>
          <thead>
            <tr>
              <th>Project Number</th>
              <th>Project Name</th>
              <th>Project Type</th>
              <th>Current Workspace State</th>
              <th>FID Current</th>
              <th>Open Activation Blockers</th>
              <th>Initialization Status</th>
              <th>Activation Status</th>
              <th>Eligibility</th>
              <th>Next Allowed Process</th>
            </tr>
          </thead>
          <tbody>
            {projects.map((item) => (
              <tr key={item.project_workspace_id}>
                <td>{item.project_number}</td>
                <td>{item.project_name}</td>
                <td>{item.project_type}</td>
                <td>{item.project_state}</td>
                <td>{item.fid_current ? "YES" : "NO"}</td>
                <td>{item.open_activation_blockers}</td>
                <td>{item.can_initialize ? "ELIGIBLE" : "—"}</td>
                <td>{item.can_activate ? "ELIGIBLE" : "—"}</td>
                <td>
                  <b className={`postFIDStatus ${item.stale ? "stale" : ""}`}>{item.eligibility_status}</b>
                </td>
                <td>{item.next_allowed_process}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ConditionCards({ projects }: { projects: PostFIDEligibility[] }) {
  return (
    <section className="postFIDSurface">
      <header>
        <div>
          <span>Frozen Gate 07K conditions</span>
          <h3>Post-FID Conditions</h3>
        </div>
      </header>
      <div className="postFIDCards">
        {projects.map((item) => (
          <article key={item.project_workspace_id}>
            <b>
              {item.project_number} · {item.project_name}
            </b>
            <span>Activation blockers: {item.open_activation_blockers}</span>
            <span>Commitment-only open: {item.open_commitment_conditions_count}</span>
            <small>{item.warnings.join(" · ") || "No downstream warnings"}</small>
            <pre>{JSON.stringify(item.post_fid_conditions, null, 2)}</pre>
          </article>
        ))}
      </div>
    </section>
  );
}

function HandoffCards({
  kind,
  projects,
  onHandoff,
}: {
  kind: "initialization" | "activation";
  projects: PostFIDEligibility[];
  onHandoff: (item: PostFIDEligibility, kind: "initialization" | "activation") => Promise<void>;
}) {
  return (
    <section className="postFIDSurface">
      <header>
        <div>
          <span>Delegated existing service</span>
          <h3>{kind === "initialization" ? "Initialization Handoff" : "Activation Handoff"}</h3>
        </div>
      </header>
      <div className="postFIDCards">
        {projects.length ? (
          projects.map((item) => (
            <article key={item.project_workspace_id}>
              <b>
                {item.project_number} · {item.project_name}
              </b>
              <span>{item.eligibility_status}</span>
              <small>{item.eligibility_hash}</small>
              <button onClick={() => void onHandoff(item, kind)} type="button">
                Prepare delegated {kind} contract
              </button>
            </article>
          ))
        ) : (
          <p>No Project is currently eligible for this handoff.</p>
        )}
      </div>
    </section>
  );
}

function JsonSurface({ title, value }: { title: string; value: Record<string, unknown> }) {
  return (
    <section className="postFIDSurface">
      <header>
        <div>
          <span>Governed read model</span>
          <h3>{title}</h3>
        </div>
      </header>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </section>
  );
}
