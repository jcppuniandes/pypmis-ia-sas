import {
  Archive,
  BadgeCheck,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleDot,
  GitCompareArrows,
  GitFork,
  Pencil,
  Plus,
  Send,
} from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { ApiError } from "../../../api/client";
import { enterpriseStructureApi } from "../api";
import type {
  CoreRevision,
  EnterpriseStructureConfiguration,
  RecordCodePreview,
  RevisionClassification,
  RevisionDiff,
  RevisionWorkspace,
} from "../types";

type RevisionForm = {
  name: string;
  workspace_type_code: string;
  parent_key: string;
  description: string;
  responsible_user_id: string;
  status: RevisionWorkspace["status"];
};

const emptyForm: RevisionForm = {
  name: "",
  workspace_type_code: "business-unit",
  parent_key: "",
  description: "",
  responsible_user_id: "",
  status: "draft",
};

const changeLabels: Record<string, string> = {
  add: "Added",
  modify: "Modified",
  move: "Moved",
  archive: "Archived",
  classification: "Classification changed",
  unchanged: "Published baseline",
};

function revisionOperationError(error: unknown, fallback: string) {
  if (error instanceof ApiError && error.status === 409 && error.message.includes("REVISION_VERSION_CONFLICT")) {
    return "This revision changed since you opened it. Reload the latest version before continuing.";
  }
  return error instanceof Error ? error.message : fallback;
}

function categoryItems(data: EnterpriseStructureConfiguration, categoryCode: string) {
  const category = data.categories.find((item) => item.code === categoryCode);
  const content = category?.content_json as { items?: Array<{ code: string; label: string }> } | undefined;
  return content?.items ?? [];
}

function byRecordCode(left: RevisionWorkspace, right: RevisionWorkspace) {
  return left.record_code.localeCompare(right.record_code, undefined, { numeric: true });
}

function RevisionTree({
  nodes,
  parentKey,
  selectedKey,
  onSelect,
}: {
  nodes: RevisionWorkspace[];
  parentKey: string | null;
  selectedKey: string | null;
  onSelect: (workspace: RevisionWorkspace) => void;
}) {
  const children = nodes.filter((item) => item.parent_key === parentKey).sort(byRecordCode);
  return (
    <ul className={parentKey ? "revisionTreeBranch" : "revisionTreeRoot"}>
      {children.map((node) => (
        <RevisionTreeRow
          key={node.workspace_key}
          node={node}
          nodes={nodes}
          onSelect={onSelect}
          selectedKey={selectedKey}
        />
      ))}
    </ul>
  );
}

function RevisionTreeRow({
  node,
  nodes,
  selectedKey,
  onSelect,
}: {
  node: RevisionWorkspace;
  nodes: RevisionWorkspace[];
  selectedKey: string | null;
  onSelect: (workspace: RevisionWorkspace) => void;
}) {
  const [open, setOpen] = useState(true);
  const hasChildren = nodes.some((item) => item.parent_key === node.workspace_key);
  return (
    <li>
      <div className={`revisionTreeRow ${selectedKey === node.workspace_key ? "selected" : ""}`}>
        <button
          aria-label={`${open ? "Contraer" : "Expandir"} ${node.name}`}
          className="revisionTreeToggle"
          disabled={!hasChildren}
          onClick={() => setOpen((current) => !current)}
          type="button"
        >
          {hasChildren ? open ? <ChevronDown size={14} /> : <ChevronRight size={14} /> : <CircleDot size={8} />}
        </button>
        <button className="revisionTreeSelect" onClick={() => onSelect(node)} type="button">
          <span className="enterpriseRecordCode">{node.record_code}</span>
          <strong>{node.name}</strong>
          <small>
            {node.workspace_type_code} ·{" "}
            <span className={`revisionState ${node.change_state}`}>{changeLabels[node.change_state]}</span>
          </small>
        </button>
      </div>
      {open ? (
        <RevisionTree nodes={nodes} onSelect={onSelect} parentKey={node.workspace_key} selectedKey={selectedKey} />
      ) : null}
    </li>
  );
}

export default function WorkspaceRevisionManager({
  token,
  canConfigure,
  data,
  busy,
  onBusy,
  onReload,
  onNotice,
  onError,
}: {
  token: string;
  canConfigure: boolean;
  data: EnterpriseStructureConfiguration;
  busy: boolean;
  onBusy: (busy: boolean) => void;
  onReload: () => Promise<EnterpriseStructureConfiguration>;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
}) {
  const release = data.draft_release;
  const [selectedKey, setSelectedKey] = useState<string | null>(release?.workspaces[0]?.workspace_key ?? null);
  const [mode, setMode] = useState<"view" | "create" | "edit">("view");
  const [form, setForm] = useState<RevisionForm>(emptyForm);
  const [classifications, setClassifications] = useState<RevisionClassification[]>([]);
  const [categoryCode, setCategoryCode] = useState("");
  const [categoryItem, setCategoryItem] = useState("");
  const [preview, setPreview] = useState<RecordCodePreview | null>(null);
  const [diff, setDiff] = useState<RevisionDiff | null>(null);

  const selected = release?.workspaces.find((item) => item.workspace_key === selectedKey) ?? null;
  const parent = release?.workspaces.find((item) => item.workspace_key === form.parent_key) ?? null;
  const allowedTypes = useMemo(() => {
    if (!parent) return [];
    return (
      data.composition_rules.find((item) => item.parent_type_code === parent.workspace_type_code)?.allowed_children ??
      []
    );
  }, [data.composition_rules, parent]);
  const applicableCategories = useMemo(
    () =>
      data.categories.filter((category) => {
        const content = category.content_json as { applicable_types?: string[] };
        return content.applicable_types?.includes(form.workspace_type_code);
      }),
    [data.categories, form.workspace_type_code]
  );

  useEffect(() => {
    if (!release || !form.parent_key || !form.workspace_type_code || mode === "view") {
      // The preview belongs to the active editor inputs and must be discarded when that editor closes.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setPreview(null);
      return;
    }
    let active = true;
    enterpriseStructureApi
      .previewRecordCode(
        token,
        release.id,
        form.parent_key,
        form.workspace_type_code,
        mode === "edit" ? (selectedKey ?? undefined) : undefined
      )
      .then((response) => active && setPreview(response))
      .catch(() => active && setPreview(null));
    return () => {
      active = false;
    };
  }, [form.parent_key, form.workspace_type_code, mode, release, selectedKey, token]);

  function choose(workspace: RevisionWorkspace) {
    setSelectedKey(workspace.workspace_key);
    setMode("view");
    setDiff(null);
  }

  function startCreate() {
    if (!release) return;
    const selectedParent = selected ?? release.workspaces.find((item) => item.parent_key === null) ?? null;
    const firstAllowed =
      data.composition_rules.find((item) => item.parent_type_code === selectedParent?.workspace_type_code)
        ?.allowed_children[0] ?? "business-unit";
    setForm({ ...emptyForm, parent_key: selectedParent?.workspace_key ?? "", workspace_type_code: firstAllowed });
    setClassifications([]);
    setMode("create");
  }

  function startEdit() {
    if (!selected) return;
    setForm({
      name: selected.name,
      workspace_type_code: selected.workspace_type_code,
      parent_key: selected.parent_key ?? "",
      description: selected.description,
      responsible_user_id: selected.responsible_user_id?.toString() ?? "",
      status: selected.status,
    });
    setClassifications([...selected.classifications]);
    setMode("edit");
  }

  async function execute(action: () => Promise<CoreRevision>, message: string) {
    onBusy(true);
    onError("");
    try {
      const response = await action();
      setSelectedKey((current) => current ?? response.workspaces[0]?.workspace_key ?? null);
      await onReload();
      onNotice(message);
      setMode("view");
      setDiff(null);
    } catch (error) {
      onError(revisionOperationError(error, "No fue posible completar la operación."));
    } finally {
      onBusy(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!release) return;
    if (mode === "create") {
      await execute(
        () =>
          enterpriseStructureApi.addRevisionWorkspace(token, release.id, release.revision_version, {
            name: form.name,
            workspace_type_code: form.workspace_type_code,
            parent_key: form.parent_key,
            description: form.description,
            responsible_user_id: form.responsible_user_id ? Number(form.responsible_user_id) : null,
            status: form.status,
            applicable_classifications: classifications,
          }),
        "Workspace agregado a la revisión DRAFT."
      );
      return;
    }
    if (!selected) return;
    onBusy(true);
    onError("");
    try {
      let currentRevision = release;
      if (form.parent_key && form.parent_key !== selected.parent_key) {
        currentRevision = await enterpriseStructureApi.moveRevisionWorkspace(
          token,
          release.id,
          selected.workspace_key,
          form.parent_key,
          currentRevision.revision_version
        );
      }
      currentRevision = await enterpriseStructureApi.editRevisionWorkspace(
        token,
        release.id,
        selected.workspace_key,
        currentRevision.revision_version,
        {
          name: form.name,
          description: form.description,
          responsible_user_id: form.responsible_user_id ? Number(form.responsible_user_id) : null,
          status: form.status,
        }
      );
      await enterpriseStructureApi.setRevisionClassifications(
        token,
        release.id,
        selected.workspace_key,
        currentRevision.revision_version,
        classifications
      );
      await onReload();
      onNotice("Workspace actualizado dentro de la revisión DRAFT.");
      setMode("view");
      setDiff(null);
    } catch (error) {
      onError(revisionOperationError(error, "No fue posible guardar el workspace."));
    } finally {
      onBusy(false);
    }
  }

  async function createRevision() {
    if (!data.published_release) return;
    await execute(
      () => enterpriseStructureApi.createCoreRevision(token, data.published_release!.id),
      "Nueva revisión DRAFT creada desde el release publicado."
    );
  }

  async function validateRevision() {
    if (!release) return;
    onBusy(true);
    try {
      const result = await enterpriseStructureApi.validateCoreRevision(token, release.id);
      await onReload();
      onNotice(result.valid ? "VALID · 0 errors · 0 conflicts" : "La revisión requiere correcciones.");
    } catch (error) {
      onError(error instanceof Error ? error.message : "No fue posible validar.");
    } finally {
      onBusy(false);
    }
  }

  async function compareRevision() {
    if (!release) return;
    onBusy(true);
    try {
      setDiff(await enterpriseStructureApi.compareCoreRevision(token, release.id));
      onNotice("Comparación DRAFT vs PUBLISHED actualizada.");
    } catch (error) {
      onError(error instanceof Error ? error.message : "No fue posible comparar.");
    } finally {
      onBusy(false);
    }
  }

  async function approveRevision() {
    if (!release) return;
    await execute(
      () => enterpriseStructureApi.approveCoreRevision(token, release.id, release.draft_hash, release.diff_hash),
      "Revisión aprobada explícitamente."
    );
  }

  async function publishRevision() {
    if (!release) return;
    await execute(
      () => enterpriseStructureApi.publishCoreRevision(token, release.id, release.draft_hash, release.diff_hash),
      "Release sucesor publicado. USER MODE ya consulta la nueva estructura vigente."
    );
  }

  const validation = release?.validation;
  return (
    <div className="revisionManager">
      <section className="revisionReleaseStrip">
        <div>
          <span>Current Published Release</span>
          <strong>{data.published_release?.release_code ?? "No published release"}</strong>
          <em>Published</em>
        </div>
        {release ? (
          <div>
            <span>Revision {release.revision_number} · DRAFT</span>
            <strong>{release.release_code}</strong>
            <small>
              Version {release.revision_version} · Based on: {data.published_release?.release_code}
            </small>
          </div>
        ) : (
          <button
            className="enterpriseButton primary"
            disabled={!canConfigure || busy || !data.published_release}
            onClick={createRevision}
            type="button"
          >
            <GitFork size={15} /> Create New Revision
          </button>
        )}
        {release ? (
          <div className="revisionGateActions">
            <button className="enterpriseButton" disabled={busy} onClick={validateRevision} type="button">
              <CheckCircle2 size={15} /> Validate
            </button>
            <button className="enterpriseButton" disabled={busy} onClick={compareRevision} type="button">
              <GitCompareArrows size={15} /> Compare
            </button>
            <button
              className="enterpriseButton"
              disabled={busy || validation?.valid !== true}
              onClick={approveRevision}
              type="button"
            >
              <BadgeCheck size={15} /> Approve
            </button>
            <button
              className="enterpriseButton primary"
              disabled={busy || !release.approved_at}
              onClick={publishRevision}
              type="button"
            >
              <Send size={15} /> Publish
            </button>
          </div>
        ) : null}
      </section>

      {release ? (
        <>
          <section className="revisionStatusBar" aria-label="Estado de la revisión">
            <span>
              Draft hash <code>{release.draft_hash.slice(0, 12)}…</code>
            </span>
            <span>
              Diff hash <code>{release.diff_hash.slice(0, 12)}…</code>
            </span>
            <strong>
              {validation ? (validation.valid ? "VALID · 0 errors · 0 conflicts" : "INVALID") : "Not validated"}
            </strong>
            <strong>{release.approved_at ? `Approved by ${release.approved_by}` : "Approval pending"}</strong>
            <span>Last modified by {release.last_modified_by ?? release.created_by}</span>
          </section>
          {validation && !validation.valid ? (
            <section className="enterpriseAlert error">
              {[...validation.errors, ...validation.conflicts].map((item) => (
                <div key={item}>{item}</div>
              ))}
            </section>
          ) : null}
          <div className="revisionWorkspaceGrid">
            <section className="enterprisePanel revisionTreePanel">
              <header>
                <div>
                  <span>Draft structure</span>
                  <h3>Workspace tree</h3>
                </div>
                <button
                  className="enterpriseButton primary"
                  disabled={busy || !canConfigure}
                  onClick={startCreate}
                  type="button"
                >
                  <Plus size={15} /> Add Child
                </button>
              </header>
              <div className="revisionLegend" aria-label="Leyenda de cambios">
                {Object.entries(changeLabels).map(([key, label]) => (
                  <span key={key} className={`revisionState ${key}`}>
                    {label}
                  </span>
                ))}
              </div>
              <RevisionTree nodes={release.workspaces} onSelect={choose} parentKey={null} selectedKey={selectedKey} />
            </section>

            <section className="enterprisePanel revisionEditorPanel">
              <header>
                <div>
                  <span>{mode === "view" ? "Workspace detail" : "Single configurable form"}</span>
                  <h3>{mode === "create" ? "Add Workspace" : (selected?.name ?? "Select a workspace")}</h3>
                </div>
                {selected && mode === "view" ? (
                  <div className="revisionEditorActions">
                    <button className="enterpriseButton" disabled={busy} onClick={startEdit} type="button">
                      <Pencil size={14} /> Edit / Move / Classify
                    </button>
                    <button
                      className="enterpriseButton danger"
                      disabled={busy || selected.parent_key === null}
                      onClick={() =>
                        execute(
                          () =>
                            enterpriseStructureApi.archiveRevisionWorkspace(
                              token,
                              release.id,
                              selected.workspace_key,
                              release.revision_version
                            ),
                          "Workspace archivado lógicamente en el DRAFT."
                        )
                      }
                      type="button"
                    >
                      <Archive size={14} /> Archive
                    </button>
                  </div>
                ) : null}
              </header>
              {mode === "view" && selected ? (
                <dl className="revisionWorkspaceDetail">
                  <div>
                    <dt>Record code</dt>
                    <dd>{selected.record_code}</dd>
                  </div>
                  <div>
                    <dt>Type</dt>
                    <dd>{selected.workspace_type_code}</dd>
                  </div>
                  <div>
                    <dt>Parent</dt>
                    <dd>{selected.parent_key ?? "Enterprise root"}</dd>
                  </div>
                  <div>
                    <dt>Status</dt>
                    <dd>{selected.status}</dd>
                  </div>
                  <div>
                    <dt>Change</dt>
                    <dd>{changeLabels[selected.change_state]}</dd>
                  </div>
                  <div>
                    <dt>Description</dt>
                    <dd>{selected.description || "—"}</dd>
                  </div>
                  <div>
                    <dt>Classifications</dt>
                    <dd>
                      {selected.classifications.length
                        ? selected.classifications
                            .map((item) => `${item.category_set_code}: ${item.category_item_code}`)
                            .join(" · ")
                        : "—"}
                    </dd>
                  </div>
                </dl>
              ) : mode !== "view" ? (
                <form className="enterpriseNodeForm revisionForm" onSubmit={submit}>
                  <label>
                    <span>Name</span>
                    <input
                      required
                      value={form.name}
                      onChange={(event) => setForm({ ...form, name: event.target.value })}
                    />
                  </label>
                  <div className="formColumns">
                    <label>
                      <span>Type</span>
                      <select
                        disabled={mode === "edit"}
                        value={form.workspace_type_code}
                        onChange={(event) => setForm({ ...form, workspace_type_code: event.target.value })}
                      >
                        {(mode === "edit" ? [form.workspace_type_code] : allowedTypes).map((type) => (
                          <option key={type} value={type}>
                            {data.workspace_types.find((item) => item.code === type)?.name ?? type}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      <span>Parent</span>
                      <select
                        required
                        value={form.parent_key}
                        onChange={(event) => {
                          const nextParent = release.workspaces.find(
                            (item) => item.workspace_key === event.target.value
                          );
                          const nextAllowed = data.composition_rules.find(
                            (item) => item.parent_type_code === nextParent?.workspace_type_code
                          )?.allowed_children;
                          setForm({
                            ...form,
                            parent_key: event.target.value,
                            workspace_type_code:
                              mode === "create" && nextAllowed?.length ? nextAllowed[0] : form.workspace_type_code,
                          });
                        }}
                      >
                        {release.workspaces
                          .filter(
                            (item) => item.workspace_key !== selected?.workspace_key && item.status !== "archived"
                          )
                          .map((item) => (
                            <option key={item.workspace_key} value={item.workspace_key}>
                              {item.record_code} · {item.name}
                            </option>
                          ))}
                      </select>
                    </label>
                  </div>
                  <label>
                    <span>Description</span>
                    <textarea
                      value={form.description}
                      onChange={(event) => setForm({ ...form, description: event.target.value })}
                    />
                  </label>
                  <div className="formColumns">
                    <label>
                      <span>Responsible</span>
                      <input
                        min="1"
                        placeholder="User ID (optional)"
                        type="number"
                        value={form.responsible_user_id}
                        onChange={(event) => setForm({ ...form, responsible_user_id: event.target.value })}
                      />
                    </label>
                    <label>
                      <span>Status</span>
                      <select
                        value={form.status}
                        onChange={(event) => setForm({ ...form, status: event.target.value as RevisionForm["status"] })}
                      >
                        {(["draft", "active", "inactive", "archived"] as const).map((status) => (
                          <option key={status}>{status}</option>
                        ))}
                      </select>
                    </label>
                  </div>
                  {preview ? (
                    <section className="recordCodePreview">
                      <strong>Record Code Preview</strong>
                      {preview.current_record_code ? <span>BEFORE · {preview.current_record_code}</span> : null}
                      <span>AFTER · {preview.record_code}</span>
                      {preview.affected_descendants.map((item) => (
                        <small key={item.workspace_key}>
                          {item.before} → {item.after}
                        </small>
                      ))}
                    </section>
                  ) : null}
                  <fieldset className="revisionClassificationEditor">
                    <legend>Applicable Classifications</legend>
                    <div>
                      <select
                        value={categoryCode}
                        onChange={(event) => {
                          setCategoryCode(event.target.value);
                          setCategoryItem("");
                        }}
                      >
                        <option value="">Category</option>
                        {applicableCategories.map((item) => (
                          <option key={item.code} value={item.code}>
                            {item.name}
                          </option>
                        ))}
                      </select>
                      <select value={categoryItem} onChange={(event) => setCategoryItem(event.target.value)}>
                        <option value="">Value</option>
                        {categoryItems(data, categoryCode).map((item) => (
                          <option key={item.code} value={item.code}>
                            {item.label}
                          </option>
                        ))}
                      </select>
                      <button
                        className="enterpriseButton"
                        disabled={!categoryCode || !categoryItem}
                        onClick={() => {
                          if (
                            !classifications.some(
                              (item) =>
                                item.category_set_code === categoryCode && item.category_item_code === categoryItem
                            )
                          ) {
                            setClassifications([
                              ...classifications,
                              { category_set_code: categoryCode, category_item_code: categoryItem },
                            ]);
                          }
                          setCategoryItem("");
                        }}
                        type="button"
                      >
                        Add
                      </button>
                    </div>
                    {classifications.map((item) => (
                      <button
                        className="revisionClassificationTag"
                        key={`${item.category_set_code}-${item.category_item_code}`}
                        onClick={() => setClassifications(classifications.filter((value) => value !== item))}
                        type="button"
                      >
                        {item.category_set_code}: {item.category_item_code} ×
                      </button>
                    ))}
                  </fieldset>
                  <div className="revisionFormActions">
                    <button className="enterpriseButton" onClick={() => setMode("view")} type="button">
                      Cancel
                    </button>
                    <button className="enterpriseButton primary" disabled={busy} type="submit">
                      Save to Draft
                    </button>
                  </div>
                </form>
              ) : (
                <p>Select a workspace in the draft tree.</p>
              )}
            </section>
          </div>
          {diff ? (
            <section className="enterprisePanel revisionDiffPanel">
              <header>
                <div>
                  <span>Compare with Published</span>
                  <h3>Detailed release diff</h3>
                </div>
                <div className="revisionDiffSummary">
                  {Object.entries(diff.summary).map(([key, value]) => (
                    <span key={key}>
                      {key}: <strong>{value}</strong>
                    </span>
                  ))}
                </div>
              </header>
              <div className="enterpriseTableWrap">
                <table className="enterpriseTable">
                  <thead>
                    <tr>
                      <th>Action</th>
                      <th>Old Record Code</th>
                      <th>New Record Code</th>
                      <th>Type</th>
                      <th>Name</th>
                      <th>Parent Before</th>
                      <th>Parent After</th>
                    </tr>
                  </thead>
                  <tbody>
                    {diff.items.map((item, index) => (
                      <tr key={`${item.workspace_key}-${item.action}-${index}`}>
                        <td>
                          <strong>{item.action}</strong>
                        </td>
                        <td>{item.old_record_code ?? "—"}</td>
                        <td>{item.new_record_code ?? "—"}</td>
                        <td>{item.workspace_type}</td>
                        <td>{item.name}</td>
                        <td>{item.parent_before ?? "—"}</td>
                        <td>{item.parent_after ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}
        </>
      ) : (
        <section className="enterprisePanel revisionEmptyState">
          <GitFork size={32} />
          <h3>Published CORE is immutable</h3>
          <p>Create a governed DRAFT revision to add, edit, move, classify or archive workspaces.</p>
        </section>
      )}
    </div>
  );
}
