/* eslint-disable react-hooks/set-state-in-effect, react-hooks/exhaustive-deps */
import { Copy, Save, Send } from "lucide-react";
import { useEffect, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { portfolioPlanningApi } from "./api";
import "./portfolioPlanning.css";

const sections = [
  "General",
  "Planning Entry Mapping",
  "Project Parent Policy",
  "Template Recommendation",
  "Target Portfolio Policy",
  "Membership Policy",
  "Readiness",
  "Definition Framework",
  "Inheritance",
  "Permissions",
  "Preview",
];

export default function PortfolioPlanningAdminView({ token }: { token: string }) {
  const [records, setRecords] = useState<Array<Record<string, unknown>>>([]);
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null);
  const [content, setContent] = useState("");
  const [message, setMessage] = useState("");

  async function load() {
    const items = await portfolioPlanningApi.configurations(token);
    setRecords(items);
    const next = items.find((item) => item.status === "draft") || items[0] || null;
    setSelected(next);
    setContent(next ? JSON.stringify(next.content_json, null, 2) : "");
  }
  useEffect(() => {
    void load().catch((error) => setMessage(error instanceof Error ? error.message : "Unable to load configuration"));
  }, [token]);

  async function execute(action: "clone" | "save" | "publish") {
    if (!selected) return;
    try {
      if (action === "clone") await portfolioPlanningApi.cloneConfiguration(token, selected);
      if (action === "save")
        await portfolioPlanningApi.updateConfiguration(token, selected, JSON.parse(content) as Record<string, unknown>);
      if (action === "publish") await portfolioPlanningApi.publishConfiguration(token, selected);
      setMessage(`Configuration ${action} completed.`);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Unable to ${action} configuration`);
    }
  }

  return (
    <section className="portfolioPlanning" aria-label="Portfolio Planning Entry and Membership Configuration">
      <CompactModuleHeader
        description="Published, inheritable source of truth for strategic mapping, Project parent policy, target membership and readiness prerequisites."
        eyebrow="ADMIN MODE · ENTERPRISE STRATEGY MANAGER"
        metrics={[
          { label: "Revisions", value: records.length },
          { label: "Policy", value: "STRATEGIC_INTAKE_ONLY" },
          { label: "Scoring", value: "Out of scope" },
        ]}
        title="Portfolio Planning Entry & Membership"
        tone="admin"
      />
      <nav className="planningAdminSections" aria-label="Portfolio Planning configuration sections">
        {sections.map((item) => (
          <button key={item} type="button">
            {item}
          </button>
        ))}
      </nav>
      {message ? <div className="planningMessage">{message}</div> : null}
      <div className="planningAdminGrid">
        <aside>
          {records.map((item) => (
            <button
              className={selected?.id === item.id ? "active" : ""}
              key={String(item.id)}
              onClick={() => {
                setSelected(item);
                setContent(JSON.stringify(item.content_json, null, 2));
              }}
              type="button"
            >
              <strong>{String(item.name)}</strong>
              <span>
                {String(item.status)} · rev {String(item.revision)}
              </span>
            </button>
          ))}
        </aside>
        <article className="planningCard">
          <header>
            <div>
              <span>Controlled configuration</span>
              <h3>{String(selected?.name || "No configuration")}</h3>
            </div>
            <strong className={selected?.status === "published" ? "ready" : "blocked"}>
              {String(selected?.status || "")}
            </strong>
          </header>
          <textarea
            aria-label="Portfolio Planning configuration JSON"
            disabled={selected?.status !== "draft"}
            rows={28}
            value={content}
            onChange={(event) => setContent(event.target.value)}
          />
          <div className="planningActions">
            <button
              disabled={!selected || selected.status !== "published"}
              onClick={() => void execute("clone")}
              type="button"
            >
              <Copy size={15} /> Clone
            </button>
            <button
              disabled={!selected || selected.status !== "draft"}
              onClick={() => void execute("save")}
              type="button"
            >
              <Save size={15} /> Save
            </button>
            <button
              disabled={!selected || selected.status !== "draft"}
              onClick={() => void execute("publish")}
              type="button"
            >
              <Send size={15} /> Publish
            </button>
          </div>
        </article>
      </div>
    </section>
  );
}
