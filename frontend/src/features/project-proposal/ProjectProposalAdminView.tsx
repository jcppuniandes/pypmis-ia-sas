import { CopyPlus, Eye, Send, Settings2, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { projectProposalApi } from "./api";
import "./projectProposal.css";

const sections = [
  "General",
  "Numbering",
  "Idea → Proposal Mapping",
  "Required Fields",
  "Review Checklist",
  "Ownership",
  "Target Portfolio Rules",
  "Proposal Evaluation Matrix",
  "Criteria / Weights / Ranks",
  "Gate Readiness Policy",
  "Inheritance",
  "Permissions",
  "Preview",
];

export default function ProjectProposalAdminView({ token }: { token: string }) {
  const [items, setItems] = useState<Array<Record<string, unknown>>>([]);
  const [message, setMessage] = useState("");
  const [editing, setEditing] = useState<Record<string, unknown> | null>(null);
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () =>
    projectProposalApi
      .configurations(token)
      .then(setItems)
      .catch((error: Error) => setMessage(error.message));
  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function mutate(action: "clone" | "save" | "publish", item: Record<string, unknown>) {
    setBusy(true);
    setMessage("");
    try {
      if (action === "clone") await projectProposalApi.cloneConfiguration(token, item);
      if (action === "save") await projectProposalApi.updateConfiguration(token, item, JSON.parse(content));
      if (action === "publish") await projectProposalApi.publishConfiguration(token, item);
      setEditing(null);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Configuration action failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="proposalLifecycle" aria-label="Project Proposal Configuration">
      <CompactModuleHeader
        eyebrow="ADMIN MODE / Enterprise Strategy Manager / Idea & Demand Manager"
        title="Project Proposal Configuration"
        description="Govern mapping, review, evaluation and Gate 07C readiness without creating a Project Workspace."
        metrics={[
          { label: "Configurations", value: items.length },
          { label: "Published", value: items.filter((item) => item.status === "published").length },
          { label: "Drafts", value: items.filter((item) => item.status === "draft").length },
        ]}
      />
      <nav className="proposalAdminSections" aria-label="Project Proposal configuration sections">
        {sections.map((section) => (
          <span key={section}>{section}</span>
        ))}
      </nav>
      {message ? (
        <div className="proposalMessage" role="alert">
          {message}
        </div>
      ) : null}
      <div className="proposalAdminGrid">
        {items.map((item) => (
          <article key={String(item.id)}>
            <Settings2 size={20} />
            <span>{String(item.kind).replace(/_/g, " ")}</span>
            <h3>{String(item.name)}</h3>
            <p>{String(item.description || "Controlled Project Proposal configuration")}</p>
            <footer>
              <span>Revision {String(item.revision)}</span>
              <strong>
                <ShieldCheck size={14} /> {String(item.status)}
              </strong>
            </footer>
            <div className="proposalAdminActions">
              {item.status === "published" ? (
                <button disabled={busy} onClick={() => void mutate("clone", item)} type="button">
                  <CopyPlus size={14} /> Clone to draft
                </button>
              ) : null}
              {item.status === "draft" ? (
                <>
                  <button
                    disabled={busy}
                    onClick={() => {
                      setEditing(item);
                      setContent(JSON.stringify(item.content_json, null, 2));
                    }}
                    type="button"
                  >
                    <Settings2 size={14} /> Edit
                  </button>
                  <button disabled={busy} onClick={() => void mutate("publish", item)} type="button">
                    <Send size={14} /> Publish
                  </button>
                </>
              ) : null}
            </div>
          </article>
        ))}
      </div>
      <div className="proposalGovernanceNote">
        <Eye size={18} />
        <div>
          <strong>Preview before persistence</strong>
          <p>
            Published mapping and inheritance resolve against an accepted source Idea. Preview never consumes a number
            or creates a Proposal.
          </p>
        </div>
      </div>
      {editing ? (
        <div className="proposalDrawerBackdrop">
          <section className="proposalDrawer" aria-label="Edit Project Proposal configuration">
            <header>
              <div>
                <span>DRAFT REVISION {String(editing.revision)}</span>
                <h3>{String(editing.name)}</h3>
              </div>
              <button onClick={() => setEditing(null)} type="button">
                Close
              </button>
            </header>
            <label>
              <span>Configuration JSON</span>
              <textarea
                className="proposalConfigEditor"
                value={content}
                onChange={(event) => setContent(event.target.value)}
              />
            </label>
            <footer>
              <button onClick={() => setEditing(null)} type="button">
                Cancel
              </button>
              <button
                className="proposalPrimary"
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
