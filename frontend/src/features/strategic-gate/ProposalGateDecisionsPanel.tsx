import { Gavel, Plus } from "lucide-react";
import { useEffect, useState } from "react";
import type { ProjectProposal } from "../project-proposal/types";
import { strategicGateApi } from "./api";
import type { StrategicGateDecision, StrategicGatePreview } from "./types";

export default function ProposalGateDecisionsPanel({ token, proposal }: { token: string; proposal: ProjectProposal }) {
  const [items, setItems] = useState<StrategicGateDecision[]>([]);
  const [preview, setPreview] = useState<StrategicGatePreview | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => strategicGateApi.relatedToProposal(token, proposal.id).then(setItems);
  useEffect(() => {
    let active = true;
    strategicGateApi
      .relatedToProposal(token, proposal.id)
      .then((records) => active && setItems(records))
      .catch((error: Error) => active && setMessage(error.message));
    return () => {
      active = false;
    };
  }, [proposal.id, token]);

  async function previewDecision() {
    setBusy(true);
    try {
      setPreview(await strategicGateApi.previewFromProposal(token, proposal.id));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Preview failed");
    } finally {
      setBusy(false);
    }
  }

  async function createDecision() {
    setBusy(true);
    try {
      const created = await strategicGateApi.create(token, proposal.id);
      setMessage(`${created.decision_number} created.`);
      setPreview(null);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Creation failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="proposalGateDecisions" aria-label="Strategic Gate Decisions for Proposal">
      <header>
        <div>
          <Gavel size={18} />
          <div>
            <strong>Strategic Gate Decisions</strong>
            <span>Immutable 1:N decision history</span>
          </div>
        </div>
        {proposal.status === "READY_FOR_STRATEGIC_GATE" &&
        !items.some((item) => ["DRAFT", "SUBMITTED", "IN_REVIEW"].includes(item.state)) ? (
          <button disabled={busy} onClick={() => void previewDecision()} type="button">
            <Plus size={15} /> Create Decision
          </button>
        ) : null}
      </header>
      {items.length ? (
        <div className="proposalDecisionHistory">
          {items.map((item) => (
            <article key={item.id}>
              <strong>{item.decision_number}</strong>
              <span>
                Round {item.gate_round} · {item.state}
              </span>
              <small>
                {item.outcome || "Outcome pending"} · {item.proposal_readiness_hash.slice(0, 12)}…
              </small>
            </article>
          ))}
        </div>
      ) : (
        <p>No Strategic Gate Decision has been created.</p>
      )}
      {preview ? (
        <div className="proposalDecisionPreview">
          <strong>
            {preview.decision_number_preview} · {preview.gate_type}
          </strong>
          <span>{String(preview.readiness.status)}</span>
          <small>{preview.blockers.length ? preview.blockers.join(" · ") : "Preview does not reserve a number."}</small>
          <button
            disabled={busy || Boolean(preview.blockers.length)}
            onClick={() => void createDecision()}
            type="button"
          >
            Create DRAFT
          </button>
        </div>
      ) : null}
      {message ? <p className="proposalDecisionMessage">{message}</p> : null}
    </section>
  );
}
