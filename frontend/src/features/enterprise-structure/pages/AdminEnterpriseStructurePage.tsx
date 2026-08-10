import { Archive, CheckCircle2, CopyPlus, GitFork, Layers3, Plus, Save, Send, Settings2, Tags } from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { ApiError } from "../../../api/client";
import { enterpriseStructureApi } from "../api";
import CompactModuleHeader from "../components/CompactModuleHeader";
import EnterpriseTree from "../components/EnterpriseTree";
import StructureNodeForm from "../components/StructureNodeForm";
import type {
  CategoryItem,
  CompositionRule,
  ConfigurationValidation,
  ConfigurationVersion,
  EnterpriseNode,
  EnterpriseStructureConfiguration,
  EnterpriseTreeNode,
  NodePayload,
} from "../types";
import "../enterpriseStructure.css";

type AdminTab = "hierarchy" | "catalogs" | "rules" | "publication";

const emptyNode: NodePayload = {
  code: "",
  name: "",
  workspace_type_code: "business-unit",
  parent_id: null,
  description: "",
  region_code: "",
  status: "active",
  sort_order: 0,
};

function flattenTree(nodes: EnterpriseTreeNode[]): EnterpriseNode[] {
  return nodes.flatMap((node) => [node, ...flattenTree(node.children)]);
}

function messageFrom(error: unknown) {
  if (!(error instanceof ApiError))
    return error instanceof Error ? error.message : "No fue posible completar la operación.";
  try {
    const body = JSON.parse(error.message) as { detail?: string | string[] };
    return Array.isArray(body.detail) ? body.detail.join(" · ") : body.detail || error.message;
  } catch {
    return error.message;
  }
}

function categoryContent(category: ConfigurationVersion) {
  const content = category.content_json as { applicable_types?: string[]; items?: CategoryItem[] };
  return {
    applicableTypes: content.applicable_types ?? [],
    items: content.items ?? [],
  };
}

export default function AdminEnterpriseStructurePage({
  token,
  canConfigure,
}: {
  token: string;
  canConfigure: boolean;
}) {
  const [data, setData] = useState<EnterpriseStructureConfiguration | null>(null);
  const [tab, setTab] = useState<AdminTab>("hierarchy");
  const [selectedNodeId, setSelectedNodeId] = useState<number | null>(null);
  const [nodeMode, setNodeMode] = useState<"create" | "edit">("create");
  const [nodeDraft, setNodeDraft] = useState<NodePayload>(emptyNode);
  const [selectedCategoryCode, setSelectedCategoryCode] = useState("");
  const [categoryName, setCategoryName] = useState("");
  const [categoryDescription, setCategoryDescription] = useState("");
  const [categoryTypes, setCategoryTypes] = useState<string[]>([]);
  const [categoryItems, setCategoryItems] = useState<CategoryItem[]>([]);
  const [newItem, setNewItem] = useState<CategoryItem>({ code: "", label: "" });
  const [selectedRuleCode, setSelectedRuleCode] = useState("");
  const [ruleDraft, setRuleDraft] = useState<CompositionRule | null>(null);
  const [classificationSet, setClassificationSet] = useState("");
  const [classificationItem, setClassificationItem] = useState("");
  const [linkTarget, setLinkTarget] = useState("");
  const [linkType, setLinkType] = useState("ALIGNED_TO");
  const [validation, setValidation] = useState<ConfigurationValidation | null>(null);
  const [busy, setBusy] = useState(true);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const nodes = useMemo(() => flattenTree(data?.tree ?? []), [data]);
  const coreLocked = Boolean(data?.published_release);
  const selectedNode = nodes.find((node) => node.id === selectedNodeId) ?? null;
  const selectedCategory = data?.categories.find((item) => item.code === selectedCategoryCode) ?? null;
  const selectedClassifications = data?.classifications.filter((item) => item.workspace_id === selectedNodeId) ?? [];
  const selectedLinks =
    data?.links.filter(
      (item) => item.source_workspace_id === selectedNodeId || item.target_workspace_id === selectedNodeId
    ) ?? [];
  const recordCodePreview = useMemo(() => {
    if (nodeMode === "edit" && selectedNode) return selectedNode.record_code;
    const parent = nodes.find((node) => node.id === nodeDraft.parent_id) ?? null;
    const siblings = nodes.filter((node) => node.parent_id === nodeDraft.parent_id);
    const nextSequence =
      Math.max(
        0,
        ...siblings.map((node) => {
          const segments = node.record_code.split(".");
          return Number(segments[segments.length - 1]) || 0;
        })
      ) + 1;
    const segment = String(nextSequence).padStart(2, "0");
    return parent ? `${parent.record_code}.${segment}` : segment;
  }, [nodeDraft.parent_id, nodeMode, nodes, selectedNode]);

  const load = useCallback(
    async (preferredNodeId?: number | null) => {
      const response = await enterpriseStructureApi.configuration(token);
      setData(response);
      setSelectedCategoryCode((current) => current || response.categories[0]?.code || "");
      setSelectedRuleCode((current) => current || response.composition_rules[0]?.parent_type_code || "");
      if (preferredNodeId !== undefined) setSelectedNodeId(preferredNodeId);
      else setSelectedNodeId((current) => current ?? flattenTree(response.tree)[0]?.id ?? null);
      return response;
    },
    [token]
  );

  useEffect(() => {
    // Initial remote synchronization is the purpose of this effect.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load()
      .catch((caught) => setError(messageFrom(caught)))
      .finally(() => setBusy(false));
  }, [load]);

  useEffect(() => {
    if (!selectedCategory) return;
    const content = categoryContent(selectedCategory);
    // The editor intentionally mirrors the currently selected persisted category revision.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCategoryName(selectedCategory.name);
    setCategoryDescription(selectedCategory.description);
    setCategoryTypes(content.applicableTypes);
    setCategoryItems(content.items);
  }, [selectedCategory]);

  useEffect(() => {
    const selected = data?.composition_rules.find((item) => item.parent_type_code === selectedRuleCode) ?? null;
    // The editor intentionally mirrors the currently selected persisted composition rule.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setRuleDraft(
      selected
        ? {
            ...selected,
            allowed_children: [...selected.allowed_children],
            required_categories: [...selected.required_categories],
            required_fields: [...selected.required_fields],
          }
        : null
    );
  }, [data, selectedRuleCode]);

  function selectNode(nodeId: number) {
    const node = nodes.find((item) => item.id === nodeId);
    if (!node) return;
    setSelectedNodeId(nodeId);
    setNodeMode("edit");
    setNodeDraft({
      code: node.code,
      name: node.name,
      workspace_type_code: node.workspace_type_code,
      parent_id: node.parent_id,
      description: node.description,
      region_code: node.region_code,
      status: node.status,
      sort_order: node.sort_order,
    });
  }

  function startNode() {
    setNodeMode("create");
    setNodeDraft({ ...emptyNode, parent_id: selectedNodeId });
    setNotice("");
    setError("");
  }

  async function run(action: () => Promise<unknown>, success: string, preferredNodeId?: number | null) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      await load(preferredNodeId);
      setNotice(success);
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(false);
    }
  }

  async function submitNode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (nodeMode === "create") {
      setBusy(true);
      setError("");
      try {
        const created = await enterpriseStructureApi.createNode(token, nodeDraft);
        await load(created.id);
        setNodeMode("edit");
        setNodeDraft({ ...nodeDraft, code: created.code });
        setNotice("Nodo empresarial creado.");
      } catch (caught) {
        setError(messageFrom(caught));
      } finally {
        setBusy(false);
      }
      return;
    }
    if (!selectedNode) return;
    await run(
      () =>
        enterpriseStructureApi.updateNode(token, selectedNode.id, {
          ...nodeDraft,
          expected_version: selectedNode.version,
        }),
      "Cambios guardados.",
      selectedNode.id
    );
  }

  async function archiveSelectedNode() {
    if (!selectedNode) return;
    await run(() => enterpriseStructureApi.archiveNode(token, selectedNode.id), "Nodo archivado.", selectedNode.id);
  }

  async function addClassification(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedNode || !classificationSet || !classificationItem) return;
    await run(
      () => enterpriseStructureApi.addClassification(token, selectedNode.id, classificationSet, classificationItem),
      "Clasificación asignada.",
      selectedNode.id
    );
    setClassificationItem("");
  }

  async function addLink(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedNode || !linkTarget) return;
    await run(
      () => enterpriseStructureApi.addLink(token, selectedNode.id, Number(linkTarget), linkType),
      "Relación transversal creada.",
      selectedNode.id
    );
    setLinkTarget("");
  }

  async function prepareCategoryDraft() {
    if (!selectedCategory) return;
    if (selectedCategory.status === "draft") {
      setNotice("La categoría ya está en borrador y puede editarse.");
      return;
    }
    await run(
      () => enterpriseStructureApi.cloneCategory(token, selectedCategory.code),
      "Borrador de categoría creado."
    );
  }

  async function saveCategory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedCategory || selectedCategory.status !== "draft") {
      setError("Cree un borrador antes de editar esta categoría publicada.");
      return;
    }
    await run(
      () =>
        enterpriseStructureApi.updateCategory(token, selectedCategory.id, {
          name: categoryName,
          description: categoryDescription,
          applicable_types: categoryTypes,
          items: categoryItems,
        }),
      "Catálogo actualizado."
    );
  }

  async function saveRule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!ruleDraft) return;
    await run(
      () =>
        enterpriseStructureApi.updateCompositionRule(token, ruleDraft.parent_type_code, {
          allowed_children: ruleDraft.allowed_children,
          max_depth: ruleDraft.max_depth,
          can_be_root: ruleDraft.can_be_root,
          required_categories: ruleDraft.required_categories,
          required_fields: ruleDraft.required_fields,
        }),
      "Regla de composición guardada."
    );
  }

  async function validateRelease() {
    setBusy(true);
    setError("");
    try {
      setValidation(await enterpriseStructureApi.validate(token));
      setNotice("Validación terminada.");
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(false);
    }
  }

  async function publishRelease() {
    const drafts = data?.drafts ?? [];
    const ids = drafts.map((draft) => draft.id);
    const expectedHashes = Object.fromEntries(drafts.map((draft) => [draft.id, draft.content_hash]));
    await run(() => enterpriseStructureApi.publish(token, ids, expectedHashes), "Configuraciones publicadas.");
    setValidation(null);
  }

  const classificationCategory = data?.categories.find((item) => item.code === classificationSet);
  const classificationItems = classificationCategory ? categoryContent(classificationCategory).items : [];

  return (
    <section className="enterpriseWorkspace adminEnterpriseWorkspace">
      <CompactModuleHeader
        actions={
          <button
            className="enterpriseButton primary"
            disabled={!canConfigure || busy || coreLocked}
            onClick={() => {
              setTab("hierarchy");
              startNode();
            }}
            type="button"
          >
            <Plus size={15} /> Agregar nodo
          </button>
        }
        description="Gobierne la jerarquía, sus clasificaciones y reglas sin mezclar operación de proyectos."
        eyebrow="ADMIN MODE · ENTERPRISE STRUCTURE"
        metrics={[
          { label: "Nodos", value: data?.summary.nodes ?? 0 },
          { label: "Tipos", value: data?.summary.types ?? 0 },
          { label: "Borradores", value: data?.summary.drafts ?? 0 },
        ]}
        title="Enterprise Structure Configuration"
      />

      {data?.published_release ? (
        <section className="coreReleaseBanner" aria-label="Release CORE publicado">
          <CheckCircle2 size={20} />
          <div>
            <strong>CORE publicado · {data.published_release.release_code}</strong>
            <span>
              {new Date(data.published_release.published_at).toLocaleString("es-CO")} ·{" "}
              {data.published_release.published_by}
            </span>
          </div>
          <code title={data.published_release.content_fingerprint}>
            {data.published_release.content_fingerprint.slice(0, 16)}…
          </code>
          <p>La estructura es inmutable. Cualquier cambio requiere una nueva revisión aprobada.</p>
        </section>
      ) : null}

      <nav className="enterpriseTabs" aria-label="Configuración de estructura empresarial">
        <button className={tab === "hierarchy" ? "active" : ""} onClick={() => setTab("hierarchy")} type="button">
          <GitFork size={16} /> Jerarquía
        </button>
        <button className={tab === "catalogs" ? "active" : ""} onClick={() => setTab("catalogs")} type="button">
          <Tags size={16} /> Tipos y categorías
        </button>
        <button className={tab === "rules" ? "active" : ""} onClick={() => setTab("rules")} type="button">
          <Settings2 size={16} /> Reglas de composición
        </button>
        <button className={tab === "publication" ? "active" : ""} onClick={() => setTab("publication")} type="button">
          <Send size={16} /> Publicación
        </button>
      </nav>

      {error ? (
        <div className="enterpriseAlert error" role="alert">
          {error}
        </div>
      ) : null}
      {notice ? (
        <div className="enterpriseAlert success" role="status">
          {notice}
        </div>
      ) : null}
      {!canConfigure ? (
        <div className="enterpriseAlert">Vista de consulta: su rol no tiene alcance de configuración.</div>
      ) : null}

      {tab === "hierarchy" ? (
        <div className="enterpriseAdminGrid">
          <section className="enterprisePanel enterpriseHierarchyPanel">
            <header>
              <div>
                <span>Estructura vigente</span>
                <h3>Árbol empresarial</h3>
              </div>
              <button
                className="enterpriseButton primary"
                disabled={!canConfigure || busy || coreLocked}
                onClick={startNode}
                type="button"
              >
                <Plus size={15} /> Nuevo nodo
              </button>
            </header>
            {busy && !data ? (
              <p>Cargando configuración…</p>
            ) : (
              <EnterpriseTree nodes={data?.tree ?? []} onSelect={selectNode} selectedNodeId={selectedNodeId} />
            )}
          </section>
          <section className="enterprisePanel enterpriseEditorPanel">
            <header>
              <div>
                <span>Formulario común</span>
                <h3>{nodeMode === "create" ? "Crear nodo" : `Editar ${selectedNode?.name ?? "nodo"}`}</h3>
              </div>
              {nodeMode === "edit" ? (
                <button
                  className="enterpriseButton danger"
                  disabled={!canConfigure || busy || coreLocked || selectedNode?.workspace_type_code === "enterprise"}
                  onClick={archiveSelectedNode}
                  type="button"
                >
                  <Archive size={15} /> Archivar
                </button>
              ) : null}
            </header>
            <StructureNodeForm
              busy={busy || !canConfigure || coreLocked}
              draft={nodeDraft}
              mode={nodeMode}
              nodes={nodes.filter((node) => node.id !== selectedNodeId)}
              recordCodePreview={recordCodePreview}
              onChange={setNodeDraft}
              onSubmit={submitNode}
              workspaceTypes={data?.workspace_types ?? []}
            />
            {selectedNode ? (
              <>
                <div className="enterpriseRelationsGrid">
                  <form onSubmit={addClassification}>
                    <strong>Clasificación</strong>
                    <select
                      value={classificationSet}
                      onChange={(event) => {
                        setClassificationSet(event.target.value);
                        setClassificationItem("");
                      }}
                    >
                      <option value="">Categoría</option>
                      {data?.categories.map((item) => (
                        <option key={item.code} value={item.code}>
                          {item.name}
                        </option>
                      ))}
                    </select>
                    <select value={classificationItem} onChange={(event) => setClassificationItem(event.target.value)}>
                      <option value="">Valor</option>
                      {classificationItems.map((item) => (
                        <option key={item.code} value={item.code}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                    <button
                      className="enterpriseButton"
                      disabled={!canConfigure || busy || coreLocked || !classificationItem}
                      type="submit"
                    >
                      Asignar
                    </button>
                  </form>
                  <form onSubmit={addLink}>
                    <strong>Relación transversal</strong>
                    <select value={linkTarget} onChange={(event) => setLinkTarget(event.target.value)}>
                      <option value="">Nodo destino</option>
                      {nodes
                        .filter((node) => node.id !== selectedNode.id)
                        .map((node) => (
                          <option key={node.id} value={node.id}>
                            {node.code} · {node.name}
                          </option>
                        ))}
                    </select>
                    <select value={linkType} onChange={(event) => setLinkType(event.target.value)}>
                      {["ALIGNED_TO", "AFFECTS", "LOCATED_AT", "SERVES", "RESPONSIBLE_FOR"].map((item) => (
                        <option key={item}>{item}</option>
                      ))}
                    </select>
                    <button
                      className="enterpriseButton"
                      disabled={!canConfigure || busy || coreLocked || !linkTarget}
                      type="submit"
                    >
                      Relacionar
                    </button>
                  </form>
                </div>
                <div className="enterpriseAssignments">
                  <section>
                    <strong>Clasificaciones asignadas</strong>
                    {selectedClassifications.length ? (
                      selectedClassifications.map((item) => (
                        <article key={item.id}>
                          <span>
                            {item.category_set_code}: {item.category_item_code}
                          </span>
                          <button
                            aria-label={`Quitar clasificación ${item.category_item_code}`}
                            disabled={!canConfigure || busy || coreLocked}
                            onClick={() =>
                              run(
                                () => enterpriseStructureApi.removeClassification(token, item.id),
                                "Clasificación retirada.",
                                selectedNode.id
                              )
                            }
                            type="button"
                          >
                            ×
                          </button>
                        </article>
                      ))
                    ) : (
                      <p>Sin clasificaciones.</p>
                    )}
                  </section>
                  <section>
                    <strong>Relaciones registradas</strong>
                    {selectedLinks.length ? (
                      selectedLinks.map((item) => (
                        <article key={item.id}>
                          <span>
                            {item.relationship_type} · {item.source_workspace_id} → {item.target_workspace_id}
                          </span>
                          <button
                            aria-label={`Quitar relación ${item.relationship_type}`}
                            disabled={!canConfigure || busy || coreLocked}
                            onClick={() =>
                              run(
                                () => enterpriseStructureApi.removeLink(token, item.id),
                                "Relación retirada.",
                                selectedNode.id
                              )
                            }
                            type="button"
                          >
                            ×
                          </button>
                        </article>
                      ))
                    ) : (
                      <p>Sin relaciones.</p>
                    )}
                  </section>
                </div>
              </>
            ) : null}
          </section>
        </div>
      ) : null}

      {tab === "catalogs" ? (
        <div className="enterpriseCatalogLayout">
          <section className="enterprisePanel">
            <header>
              <div>
                <span>Modelo controlado</span>
                <h3>Siete tipos de workspace</h3>
              </div>
            </header>
            <div className="enterpriseTypeCards">
              {data?.workspace_types.map((item) => (
                <button key={item.id} type="button">
                  <Layers3 size={18} />
                  <strong>{item.name}</strong>
                  <span>{item.code}</span>
                  <em>
                    {item.status} · r{item.revision}
                  </em>
                </button>
              ))}
            </div>
          </section>
          <section className="enterprisePanel categoryEditor">
            <header>
              <div>
                <span>Catálogos empresariales</span>
                <h3>Tipos y categorías</h3>
              </div>
              <button
                className="enterpriseButton"
                disabled={!canConfigure || busy || !selectedCategory}
                onClick={prepareCategoryDraft}
                type="button"
              >
                <CopyPlus size={15} /> Preparar borrador
              </button>
            </header>
            <div className="categoryPills">
              {data?.categories.map((item) => (
                <button
                  className={selectedCategoryCode === item.code ? "active" : ""}
                  key={item.id}
                  onClick={() => setSelectedCategoryCode(item.code)}
                  type="button"
                >
                  {item.name}
                  <small>{item.status}</small>
                </button>
              ))}
            </div>
            {selectedCategory ? (
              <form className="enterpriseNodeForm" onSubmit={saveCategory}>
                <label>
                  <span>Nombre</span>
                  <input
                    disabled={!canConfigure || selectedCategory.status !== "draft"}
                    value={categoryName}
                    onChange={(event) => setCategoryName(event.target.value)}
                  />
                </label>
                <label>
                  <span>Descripción</span>
                  <textarea
                    disabled={!canConfigure || selectedCategory.status !== "draft"}
                    value={categoryDescription}
                    onChange={(event) => setCategoryDescription(event.target.value)}
                  />
                </label>
                <fieldset>
                  <legend>Tipos aplicables</legend>
                  {data?.workspace_types.map((item) => (
                    <label className="checkLine" key={item.code}>
                      <input
                        checked={categoryTypes.includes(item.code)}
                        disabled={!canConfigure || selectedCategory.status !== "draft"}
                        onChange={(event) =>
                          setCategoryTypes((current) =>
                            event.target.checked
                              ? [...current, item.code]
                              : current.filter((code) => code !== item.code)
                          )
                        }
                        type="checkbox"
                      />{" "}
                      {item.name}
                    </label>
                  ))}
                </fieldset>
                <div className="categoryItems">
                  <strong>Valores controlados</strong>
                  {categoryItems.map((item, index) => (
                    <div key={`${item.code}-${index}`}>
                      <input
                        disabled={!canConfigure || selectedCategory.status !== "draft"}
                        value={item.code}
                        onChange={(event) =>
                          setCategoryItems((current) =>
                            current.map((value, itemIndex) =>
                              itemIndex === index ? { ...value, code: event.target.value } : value
                            )
                          )
                        }
                      />
                      <input
                        disabled={!canConfigure || selectedCategory.status !== "draft"}
                        value={item.label}
                        onChange={(event) =>
                          setCategoryItems((current) =>
                            current.map((value, itemIndex) =>
                              itemIndex === index ? { ...value, label: event.target.value } : value
                            )
                          )
                        }
                      />
                      <button
                        disabled={!canConfigure || selectedCategory.status !== "draft"}
                        onClick={() =>
                          setCategoryItems((current) => current.filter((_value, itemIndex) => itemIndex !== index))
                        }
                        type="button"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
                <div className="newCategoryItem">
                  <input
                    disabled={!canConfigure || selectedCategory.status !== "draft"}
                    placeholder="Código"
                    value={newItem.code}
                    onChange={(event) => setNewItem({ ...newItem, code: event.target.value })}
                  />
                  <input
                    disabled={!canConfigure || selectedCategory.status !== "draft"}
                    placeholder="Etiqueta"
                    value={newItem.label}
                    onChange={(event) => setNewItem({ ...newItem, label: event.target.value })}
                  />
                  <button
                    className="enterpriseButton"
                    disabled={!newItem.code || !newItem.label || selectedCategory.status !== "draft"}
                    onClick={() => {
                      setCategoryItems((current) => [...current, newItem]);
                      setNewItem({ code: "", label: "" });
                    }}
                    type="button"
                  >
                    <Plus size={14} /> Añadir
                  </button>
                </div>
                <button
                  className="enterpriseButton primary"
                  disabled={!canConfigure || busy || selectedCategory.status !== "draft"}
                  type="submit"
                >
                  <Save size={15} /> Guardar catálogo
                </button>
              </form>
            ) : null}
          </section>
        </div>
      ) : null}

      {tab === "rules" ? (
        <div className="enterpriseRulesLayout">
          <aside className="enterprisePanel ruleList">
            {data?.composition_rules.map((item) => (
              <button
                className={selectedRuleCode === item.parent_type_code ? "active" : ""}
                key={item.parent_type_code}
                onClick={() => setSelectedRuleCode(item.parent_type_code)}
                type="button"
              >
                <strong>{item.parent_type_name}</strong>
                <span>{item.allowed_children.length} hijos permitidos</span>
                <em>{item.status}</em>
              </button>
            ))}
          </aside>
          <section className="enterprisePanel">
            <header>
              <div>
                <span>Guardrails de jerarquía</span>
                <h3>{ruleDraft?.parent_type_name ?? "Regla de composición"}</h3>
              </div>
            </header>
            {ruleDraft ? (
              <form className="enterpriseNodeForm" onSubmit={saveRule}>
                <fieldset>
                  <legend>Tipos hijo permitidos</legend>
                  {data?.workspace_types.map((item) => (
                    <label className="checkLine" key={item.code}>
                      <input
                        checked={ruleDraft.allowed_children.includes(item.code)}
                        disabled={!canConfigure}
                        onChange={(event) =>
                          setRuleDraft({
                            ...ruleDraft,
                            allowed_children: event.target.checked
                              ? [...ruleDraft.allowed_children, item.code]
                              : ruleDraft.allowed_children.filter((code) => code !== item.code),
                          })
                        }
                        type="checkbox"
                      />{" "}
                      {item.name}
                    </label>
                  ))}
                </fieldset>
                <div className="formColumns">
                  <label>
                    <span>Profundidad máxima</span>
                    <input
                      disabled={!canConfigure}
                      min="1"
                      onChange={(event) =>
                        setRuleDraft({
                          ...ruleDraft,
                          max_depth: event.target.value ? Number(event.target.value) : null,
                        })
                      }
                      type="number"
                      value={ruleDraft.max_depth ?? ""}
                    />
                  </label>
                  <label className="checkLine rootRule">
                    <input
                      checked={ruleDraft.can_be_root}
                      disabled={!canConfigure}
                      onChange={(event) => setRuleDraft({ ...ruleDraft, can_be_root: event.target.checked })}
                      type="checkbox"
                    />{" "}
                    Puede ser raíz
                  </label>
                </div>
                <label>
                  <span>Categorías requeridas (separadas por coma)</span>
                  <input
                    disabled={!canConfigure}
                    value={ruleDraft.required_categories.join(", ")}
                    onChange={(event) =>
                      setRuleDraft({
                        ...ruleDraft,
                        required_categories: event.target.value
                          .split(",")
                          .map((item) => item.trim())
                          .filter(Boolean),
                      })
                    }
                  />
                </label>
                <label>
                  <span>Campos requeridos (separados por coma)</span>
                  <input
                    disabled={!canConfigure}
                    value={ruleDraft.required_fields.join(", ")}
                    onChange={(event) =>
                      setRuleDraft({
                        ...ruleDraft,
                        required_fields: event.target.value
                          .split(",")
                          .map((item) => item.trim())
                          .filter(Boolean),
                      })
                    }
                  />
                </label>
                <button className="enterpriseButton primary" disabled={!canConfigure || busy} type="submit">
                  <Save size={15} /> Guardar regla
                </button>
              </form>
            ) : null}
          </section>
        </div>
      ) : null}

      {tab === "publication" ? (
        <div className="enterprisePublication">
          <section className="enterprisePanel publicationSummary">
            <header>
              <div>
                <span>Ciclo controlado</span>
                <h3>Validar y publicar</h3>
              </div>
            </header>
            <p>
              Las versiones publicadas son inmutables. Para iniciar otro ciclo, clone la publicación vigente y trabaje
              sobre borradores.
            </p>
            <div className="publicationSteps">
              <article>
                <CopyPlus />
                <strong>1. Clonar</strong>
                <span>Prepare una nueva revisión editable.</span>
              </article>
              <article>
                <CheckCircle2 />
                <strong>2. Validar</strong>
                <span>Compruebe raíz, reglas y catálogos.</span>
              </article>
              <article>
                <Send />
                <strong>3. Publicar</strong>
                <span>Selle hash, versión y trazabilidad.</span>
              </article>
            </div>
            <div className="publicationActions">
              <button
                className="enterpriseButton"
                disabled={!canConfigure || busy}
                onClick={() => run(() => enterpriseStructureApi.cloneRelease(token), "Borradores preparados.")}
                type="button"
              >
                <CopyPlus size={15} /> Clonar publicación
              </button>
              <button className="enterpriseButton" disabled={busy} onClick={validateRelease} type="button">
                <CheckCircle2 size={15} /> Validar
              </button>
              <button
                className="enterpriseButton primary"
                disabled={!canConfigure || busy || validation?.valid !== true || !data?.summary.drafts}
                onClick={publishRelease}
                type="button"
              >
                <Send size={15} /> Publicar borradores
              </button>
            </div>
          </section>
          <section className="enterprisePanel validationPanel">
            <header>
              <div>
                <span>Resultado</span>
                <h3>
                  {validation
                    ? validation.valid
                      ? "Configuración válida"
                      : "Requiere ajustes"
                    : "Pendiente de validación"}
                </h3>
              </div>
            </header>
            {validation ? (
              <>
                <strong>{validation.configuration_ids.length} configuración(es) seleccionada(s)</strong>
                {validation.issues.length ? (
                  <ul className="issues">
                    {validation.issues.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="validationOk">No se detectaron bloqueos.</p>
                )}
                {validation.warnings.length ? (
                  <ul className="warnings">
                    {validation.warnings.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                ) : null}
              </>
            ) : (
              <p>Ejecute la validación antes de publicar.</p>
            )}
          </section>
        </div>
      ) : null}
    </section>
  );
}
