import { CopyPlus, Eye, Send, Settings2, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { strategicGateApi } from "./api";
import "./strategicGate.css";

const sections = [
  "Gate Types",
  "Outcomes",
  "Required Fields",
  "Decision Checklist",
  "Decision Criteria",
  "Decision Authority",
  "Committee Policy",
  "Quorum",
  "Four-Eyes / SoD",
  "Return / Reject / Defer Rules",
  "APPROVE Output Policy",
  "Numbering",
  "Inheritance",
  "Permissions",
  "Preview",
];

export default function StrategicGateAdminView({ token }: { token: string }) {
  const [items, setItems] = useState<Array<Record<string, unknown>>>([]);
  const [options, setOptions] = useState<Array<Record<string, unknown>>>([]);
  const [editing, setEditing] = useState<Record<string, unknown> | null>(null);
  const [content, setContent] = useState("");
  const [proposalId, setProposalId] = useState(0);
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const [nextItems, nextOptions] = await Promise.all([
        strategicGateApi.configurations(token),
        strategicGateApi.options(token),
      ]);
      setItems(nextItems);
      setOptions(nextOptions.eligible_proposals);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Configuration load failed");
    }
  };

  useEffect(() => {
    const frame = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(frame);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function mutate(action: "clone" | "save" | "publish", item: Record<string, unknown>) {
    setBusy(true);
    setMessage("");
    try {
      if (action === "clone") await strategicGateApi.cloneConfiguration(token, item);
      if (action === "save") await strategicGateApi.updateConfiguration(token, item, JSON.parse(content));
      if (action === "publish") await strategicGateApi.publishConfiguration(token, item);
      setEditing(null);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Configuration action failed");
    } finally {
      setBusy(false);
    }
  }

  async function previewConfiguration() {
    if (!proposalId) return;
    setBusy(true);
    try {
      setPreview(await strategicGateApi.previewConfiguration(token, proposalId));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Preview failed");
    } finally {
      setBusy(false);
    }
  }

  const published = items.filter((item) => item.status === "published").length;
  const drafts = items.filter((item) => item.status === "draft").length;

  return (
    <section className="strategicGate" aria-label="Strategic Gate Decision Configuration">
      <CompactModuleHeader
        eyebrow="ADMIN MODE / Enterprise Strategy Manager"
        title="Strategic Gate Decision Configuration"
        description="Govern Gate 07C outcomes, authority, quorum, separation of duties and Portfolio Intake readiness without creating a Candidate or Workspace."
        tone="admin"
        metrics={[
          { label: "Configurations", value: items.length },
          { label: "Published", value: published },
          { label: "Drafts", value: drafts },
        ]}
      />

      <nav className="gateAdminSections" aria-label="Strategic Gate configuration sections">
        {sections.map((section) => (
          <span key={section}>{section}</span>
        ))}
      </nav>
      {message ? (
        <div className="gateMessage" role="alert">
          {message}
        </div>
      ) : null}

      <div className="gateAdminGrid">
        {items.map((item) => (
          <article key={String(item.id)}>
            <div>
              <Settings2 size={18} />
              <span>strategic gate configuration</span>
            </div>
            <h3>{String(item.name)}</h3>
            <p>{String(item.description || "Gate 07C governed configuration")}</p>
            <small>Revision {String(item.revision)}</small>
            <strong className={`gateChip state-${String(item.status)}`}>{String(item.status)}</strong>
            <footer>
              {item.status === "published" ? (
                <button disabled={busy} onClick={() => void mutate("clone", item)} type="button">
                  <CopyPlus size={15} /> Clone to draft
                </button>
              ) : null}
              {item.status === "draft" ? (
                <button
                  onClick={() => {
                    setEditing(item);
                    setContent(JSON.stringify(item.content_json, null, 2));
                  }}
                  type="button"
                >
                  <Eye size={15} /> Edit JSON
                </button>
              ) : null}
              {item.status === "draft" ? (
                <button disabled={busy} onClick={() => void mutate("publish", item)} type="button">
                  <Send size={15} /> Publish
                </button>
              ) : null}
            </footer>
          </article>
        ))}
      </div>

      <section className="gateAdminPreview">
        <div>
          <ShieldCheck size={20} />
          <div>
            <strong>Preview before persistence</strong>
            <p>
              Resolve Enterprise → Business Unit → Portfolio inheritance and verify readiness without consuming an SGD
              number.
            </p>
          </div>
        </div>
        <select
          aria-label="Proposal for configuration preview"
          onChange={(event) => setProposalId(Number(event.target.value))}
          value={proposalId || ""}
        >
          <option value="">Select a gate-ready Proposal…</option>
          {options.map((item) => (
            <option key={String(item.id)} value={Number(item.id)}>
              {String(item.proposal_number)} · {String(item.name)}
            </option>
          ))}
        </select>
        <button disabled={!proposalId || busy} onClick={() => void previewConfiguration()} type="button">
          Preview configuration
        </button>
        {preview ? <pre>{JSON.stringify(preview, null, 2)}</pre> : null}
      </section>

      {editing ? (
        <div className="gateDrawerBackdrop">
          <section className="gateDrawer" aria-label="Edit Strategic Gate Configuration">
            <header>
              <div>
                <span>REVISION {String(editing.revision)}</span>
                <h3>{String(editing.name)}</h3>
              </div>
              <button onClick={() => setEditing(null)} type="button">
                Close
              </button>
            </header>
            <textarea className="gateJsonEditor" onChange={(event) => setContent(event.target.value)} value={content} />
            <footer>
              <button onClick={() => setEditing(null)} type="button">
                Cancel
              </button>
              <button
                className="gatePrimary"
                disabled={busy}
                onClick={() => void mutate("save", editing)}
                type="button"
              >
                Save draft
              </button>
            </footer>
          </section>
        </div>
      ) : null}
    </section>
  );
}
