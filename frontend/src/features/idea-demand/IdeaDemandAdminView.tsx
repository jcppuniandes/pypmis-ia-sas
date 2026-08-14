import { CopyPlus, Send, Settings2, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { ideaDemandApi } from "./api";
import "./ideaDemand.css";

export default function IdeaDemandAdminView({ token }: { token: string }) {
  const [items, setItems] = useState<Array<Record<string, unknown>>>([]);
  const [message, setMessage] = useState("");
  const [editing, setEditing] = useState<Record<string, unknown> | null>(null);
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);
  const load = () => ideaDemandApi.configurations(token).then(setItems).catch((error: Error) => setMessage(error.message));
  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);
  async function mutate(action: "clone" | "save" | "publish", item: Record<string, unknown>) {
    setBusy(true);
    setMessage("");
    try {
      if (action === "clone") await ideaDemandApi.cloneConfiguration(token, item);
      if (action === "publish") await ideaDemandApi.publishConfiguration(token, item);
      if (action === "save") await ideaDemandApi.updateConfiguration(token, item, JSON.parse(content));
      setEditing(null);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Configuration action failed");
    } finally {
      setBusy(false);
    }
  }
  const published = items.filter((item) => item.status === "published").length;
  const drafts = items.filter((item) => item.status === "draft").length;
  return (
    <section className="ideaLifecycle" aria-label="Idea Demand administration">
      <CompactModuleHeader
        eyebrow="ADMIN MODE / Enterprise Strategy Manager"
        title="Idea & Demand Manager"
        description="Govern lifecycle rules, screening, routing and immutable evaluation matrix revisions."
        metrics={[{ label: "Configurations", value: items.length }, { label: "Published", value: published }, { label: "Drafts", value: drafts }]}
      />
      {message ? <div className="ideaMessage">{message}</div> : null}
      <div className="ideaAdminGrid">
        {items.map((item) => (
          <article key={String(item.id)}>
            <Settings2 size={20} />
            <span>{String(item.kind).replace(/_/g, " ")}</span>
            <h3>{String(item.name)}</h3>
            <p>{String(item.description || "Controlled configuration")}</p>
            <footer><span>Revision {String(item.revision)}</span><strong><ShieldCheck size={14} /> {String(item.status)}</strong></footer>
            <div className="ideaAdminActions">
              {item.status === "published" ? <button disabled={busy} onClick={() => void mutate("clone", item)} type="button"><CopyPlus size={14} /> Clone to draft</button> : null}
              {item.status === "draft" ? <><button disabled={busy} onClick={() => { setEditing(item); setContent(JSON.stringify(item.content_json, null, 2)); }} type="button"><Settings2 size={14} /> Edit</button><button disabled={busy} onClick={() => void mutate("publish", item)} type="button"><Send size={14} /> Publish</button></> : null}
            </div>
          </article>
        ))}
      </div>
      <div className="ideaGovernanceNote"><strong>Publishing workflow</strong><p>Create, clone, edit and publish these governed revisions through General Configuration. Published revisions remain immutable and each evaluation stores the exact matrix snapshot used.</p></div>
      {editing ? <div className="ideaDrawerBackdrop"><section className="ideaDrawer" aria-label="Edit Idea configuration"><header><div><span>DRAFT REVISION {String(editing.revision)}</span><h3>{String(editing.name)}</h3></div><button onClick={() => setEditing(null)} type="button">Close</button></header><label><span>Configuration JSON</span><textarea className="ideaConfigEditor" value={content} onChange={(event) => setContent(event.target.value)} /></label><footer><button onClick={() => setEditing(null)} type="button">Cancel</button><button className="ideaPrimary" disabled={busy} onClick={() => void mutate("save", editing)} type="button">Save draft</button></footer></section></div> : null}
    </section>
  );
}
