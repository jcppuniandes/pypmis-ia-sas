import { useCallback, useEffect, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { type GovernanceConfiguration, type JsonRecord, governancePolicyApi } from "./policyApi";
import "./wave2b.css";

export type PolicySection = readonly [label: string, path: string | null];

function allows(item: GovernanceConfiguration, action: string) {
  // Older compatible payloads retain their status-based affordances. An
  // explicit empty list from the current backend always denies mutations.
  return item.allowed_actions === undefined || item.allowed_actions.includes(action);
}

function getPath(content: JsonRecord, path: string) {
  return path
    .split(".")
    .reduce<unknown>(
      (value, key) => (value && typeof value === "object" ? (value as JsonRecord)[key] : undefined),
      content
    );
}
function setPath(content: JsonRecord, path: string, value: unknown) {
  const next = structuredClone(content);
  const keys = path.split(".");
  let target = next;
  for (const key of keys.slice(0, -1)) {
    if (!target[key] || typeof target[key] !== "object") target[key] = {};
    target = target[key] as JsonRecord;
  }
  target[keys[keys.length - 1]] = value;
  return next;
}

// Both Wave 2B policies reuse this configuration lifecycle. The backend, not this
// editor, owns validation, scope precedence, publish authority and SoD.
export default function GovernedPolicyEditor({
  token,
  root,
  title,
  eyebrow,
  boundary,
  sections,
}: {
  token: string;
  root: string;
  title: string;
  eyebrow: string;
  boundary: string;
  sections: readonly PolicySection[];
}) {
  const [records, setRecords] = useState<GovernanceConfiguration[]>([]);
  const [selected, setSelected] = useState<GovernanceConfiguration | null>(null);
  const [draft, setDraft] = useState<JsonRecord | null>(null);
  const [section, setSection] = useState<PolicySection>(sections[0]);
  const [fragment, setFragment] = useState("");
  const [workspaceId, setWorkspaceId] = useState<number | null>(null);
  const [targetId, setTargetId] = useState<number | null>(null);
  const [preview, setPreview] = useState<JsonRecord | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const api = governancePolicyApi(root);
  const load = useCallback(
    async (preferredId?: number) => {
      const next = await governancePolicyApi(root).configurations(token);
      setRecords(next);
      setSelected((current) => next.find((item) => item.id === (preferredId ?? current?.id)) ?? next[0] ?? null);
    },
    [root, token]
  );
  useEffect(() => {
    let active = true;
    void governancePolicyApi(root)
      .configurations(token)
      .then((next) => {
        if (!active) return;
        setRecords(next);
        setSelected(next[0] ?? null);
      })
      .catch((error: Error) => {
        if (active) setMessage(error.message);
      });
    return () => {
      active = false;
    };
  }, [root, token]);

  function edit(item: GovernanceConfiguration) {
    const content = structuredClone(item.content_json);
    setSelected(item);
    setDraft(content);
    setSection(sections[0]);
    setFragment(JSON.stringify(getPath(content, sections[0][1] ?? "scope") ?? {}, null, 2));
    setPreview(null);
  }
  function stagedContent() {
    if (!draft) return selected?.content_json ?? {};
    return section[1] ? setPath(draft, section[1], JSON.parse(fragment) as unknown) : draft;
  }
  function selectSection(next: PolicySection) {
    try {
      const content = stagedContent();
      setDraft(content);
      setSection(next);
      setFragment(JSON.stringify(next[1] ? (getPath(content, next[1]) ?? null) : content, null, 2));
    } catch {
      setMessage("Invalid JSON. Correct this section before changing sections.");
    }
  }
  async function execute(action: "clone" | "save" | "publish" | "archive", item: GovernanceConfiguration) {
    setBusy(true);
    setMessage("");
    try {
      const result =
        action === "clone"
          ? await api.clone(token, item, targetId)
          : action === "save"
            ? await api.update(token, item, stagedContent())
            : action === "publish"
              ? await api.publish(token, item)
              : await api.archive(token, item);
      setDraft(null);
      setPreview(null);
      await load(result.id);
      setMessage(`${title}: ${action} completed.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Configuration operation failed.");
      // Keep unsaved input and the previous version on 412; never silently retry
      // an edit or hide the conflict with a frontend-generated version.
    } finally {
      setBusy(false);
    }
  }
  async function showPreview() {
    setBusy(true);
    setMessage("");
    try {
      setPreview(
        await api.preview(token, {
          configuration_id: selected?.id,
          content_json: draft ? stagedContent() : undefined,
          ...(root.endsWith("/basic-data") ? { project_id: workspaceId } : { workspace_id: workspaceId }),
        })
      );
      setMessage("Effective preview resolved by backend. persisted=false; no live transaction created.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Preview failed.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="wave2b" aria-label={title}>
      <CompactModuleHeader
        title={title}
        eyebrow={eyebrow}
        description={boundary}
        tone="admin"
        metrics={[
          { label: "Revisions", value: records.length },
          { label: "Published", value: records.filter((item) => item.status.toLowerCase() === "published").length },
        ]}
      />
      <p className="wave2bBoundary" role="note">
        {boundary}
      </p>
      {message ? (
        <p role="status" className="wave2bMessage">
          {message}
        </p>
      ) : null}
      <div className="wave2bToolbar">
        <label>
          Workspace context for preview
          <input
            aria-label="Workspace context for preview"
            type="number"
            min="1"
            value={workspaceId ?? ""}
            onChange={(event) => setWorkspaceId(event.target.value ? Number(event.target.value) : null)}
          />
        </label>
        <label>
          Target Workspace for clone
          <input
            aria-label="Target Workspace for clone"
            type="number"
            min="1"
            value={targetId ?? ""}
            onChange={(event) => setTargetId(event.target.value ? Number(event.target.value) : null)}
          />
        </label>
        <small>Leave the clone target empty to preserve the source policy scope.</small>
        <button disabled={busy || !selected} onClick={() => void showPreview()} type="button">
          Preview persisted=false
        </button>
      </div>
      {preview ? (
        <article aria-label="Effective configuration preview">
          <strong>persisted={String(preview.persisted)}</strong>
          <pre>{JSON.stringify(preview, null, 2)}</pre>
        </article>
      ) : null}
      <nav className="wave2bTabs" aria-label={`${title} governed sections`}>
        {sections.map(([label]) => (
          <span key={label}>{label}</span>
        ))}
      </nav>
      <div className="wave2bCards" aria-label="Configuration history">
        {records.map((item) => (
          <article key={item.id} data-configuration-id={item.id}>
            <h3>{item.name}</h3>
            <p>{item.description}</p>
            <p>
              {item.code} · revision {item.revision} · version {item.version} · <strong>{item.status}</strong>
            </p>
            <small>Hash {item.content_hash ?? "DRAFT"}</small>
            <div className="wave2bToolbar">
              <button
                onClick={() => {
                  setSelected(item);
                  setDraft(null);
                }}
                type="button"
              >
                Inspect revision
              </button>
              {item.status.toLowerCase() === "published" ? (
                <>
                  {allows(item, "clone") ? (
                    <button disabled={busy} onClick={() => void execute("clone", item)} type="button">
                      Clone to DRAFT
                    </button>
                  ) : null}
                  {allows(item, "archive") ? (
                    <button disabled={busy} onClick={() => void execute("archive", item)} type="button">
                      Archive
                    </button>
                  ) : null}
                </>
              ) : null}
              {item.status.toLowerCase() === "draft" ? (
                <>
                  {allows(item, "edit") ? (
                    <button disabled={busy} onClick={() => edit(item)} type="button">
                      Edit policy
                    </button>
                  ) : null}
                  {allows(item, "publish") ? (
                    <button disabled={busy} onClick={() => void execute("publish", item)} type="button">
                      Publish
                    </button>
                  ) : null}
                </>
              ) : null}
            </div>
          </article>
        ))}
      </div>
      {selected && !draft ? (
        <details>
          <summary>Selected configuration and immutable hash</summary>
          <pre>{JSON.stringify(selected.content_json, null, 2)}</pre>
        </details>
      ) : null}
      {selected && draft ? (
        <section className="wave2bEditor" aria-label={`Edit ${title}`}>
          <header>
            <h3>DRAFT revision {selected.revision}</h3>
            <button onClick={() => setDraft(null)} type="button">
              Close editor
            </button>
          </header>
          <nav className="wave2bTabs" aria-label="Policy section editor">
            {sections.map((next) => (
              <button
                aria-current={next[0] === section[0] ? "page" : undefined}
                key={next[0]}
                onClick={() => selectSection(next)}
                type="button"
              >
                {next[0]}
              </button>
            ))}
          </nav>
          <p>
            Only reusable policy is edited. Scope and effective precedence are resolved on the server. Published
            versions remain immutable.
          </p>
          <label>
            {section[0]} — governed values
            <textarea
              aria-label="Governed policy section JSON"
              readOnly={!section[1]}
              rows={15}
              value={fragment}
              onChange={(event) => setFragment(event.target.value)}
              spellCheck={false}
            />
          </label>
          <button disabled={busy} onClick={() => void execute("save", selected)} type="button">
            Save DRAFT revision
          </button>
        </section>
      ) : null}
    </section>
  );
}
