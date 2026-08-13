import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Boxes, Braces, Building2, CopyPlus, GitBranch, Hash, Layers3, RefreshCw, Send, Settings2 } from "lucide-react";
import { adminConfiguration } from "../api/adminConfiguration";
import type {
  AdminConfigurationKind,
  AdminConfigurationOverview,
  AdminConfigurationRecord,
  EnterpriseWorkspace,
  NumberingResult,
  WorkspaceEffectiveConfiguration,
} from "../types";

export type AdminConfigurationViewKey =
  | "workspace-types"
  | "enterprise-workspace-structure"
  | "workspace-defaults"
  | "module-catalog-activation"
  | "workspace-navigation-profiles"
  | "master-catalogs"
  | "numbering-rules"
  | "process-definitions";

type Props = {
  canConfigure: boolean;
  token: string;
  view: AdminConfigurationViewKey;
};

type PageDefinition = {
  title: string;
  description: string;
  kind?: AdminConfigurationKind;
  icon: typeof Building2;
};

const pages: Record<AdminConfigurationViewKey, PageDefinition> = {
  "workspace-types": {
    title: "Workspace Types",
    description: "Tipos reutilizables y reglas de composición para portafolios, programas y proyectos.",
    kind: "workspace_type",
    icon: Layers3,
  },
  "enterprise-workspace-structure": {
    title: "Enterprise Workspace Structure",
    description: "Jerarquía empresarial multi-tenant con protección de ciclos y tipos publicados.",
    icon: GitBranch,
  },
  "workspace-defaults": {
    title: "Workspace Defaults & Inheritance",
    description: "Valores por nivel y vista efectiva resultante desde la raíz hasta el workspace seleccionado.",
    icon: Braces,
  },
  "module-catalog-activation": {
    title: "Module Catalog & Activation",
    description: "Catálogo de módulos, dependencias y activación heredable por workspace.",
    kind: "module_definition",
    icon: Boxes,
  },
  "workspace-navigation-profiles": {
    title: "Workspace Navigation Profiles",
    description: "Orden, landing y visibilidad de módulos planificados por Workspace Type.",
    kind: "workspace_navigation_profile",
    icon: Layers3,
  },
  "master-catalogs": {
    title: "Master Catalogs",
    description: "Catálogos corporativos versionados para formularios, procesos y módulos operativos.",
    kind: "catalog",
    icon: Settings2,
  },
  "numbering-rules": {
    title: "Numbering & Coding Rules",
    description: "Patrones publicados, previsualización y emisión secuencial controlada por alcance.",
    kind: "numbering_rule",
    icon: Hash,
  },
  "process-definitions": {
    title: "Process Definitions",
    description: "Formularios, estados y transiciones declarativos; sin lógica de negocio embebida en la interfaz.",
    kind: "process_definition",
    icon: GitBranch,
  },
};

const contentExamples: Record<AdminConfigurationKind, Record<string, unknown>> = {
  workspace_type: { allowed_children: [], required_defaults: ["currency", "timezone"] },
  module_definition: { dependencies: [], mode: "hybrid" },
  catalog: { items: [{ code: "draft", label: "Draft" }] },
  numbering_rule: { pattern: "{prefix}-{sequence:04d}", prefix: "CFG", start: 1 },
  process_definition: {
    form: { fields: [{ key: "notes", type: "textarea", required: true }] },
    states: ["draft", "published"],
    transitions: [{ from: "draft", to: "published", permission: "admin.process_definition.publish" }],
  },
  workspace_navigation_profile: {
    default_home_route: "home",
    module_order: ["home", "overview", "documents"],
    show_planned_modules: true,
    show_overview: true,
    show_documents: true,
    show_reports: false,
  },
};

export default function AdminConfigurationView({ canConfigure, token, view }: Props) {
  const page = pages[view];
  const PageIcon = page.icon;
  const [overview, setOverview] = useState<AdminConfigurationOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [effective, setEffective] = useState<WorkspaceEffectiveConfiguration | null>(null);
  const [numberingResult, setNumberingResult] = useState<NumberingResult | null>(null);
  const [numberingScope, setNumberingScope] = useState("tenant");
  const [workspaceDraft, setWorkspaceDraft] = useState({
    code: "",
    name: "",
    workspace_type_code: "project",
    parent_id: "",
  });
  const [defaultsDraft, setDefaultsDraft] = useState("{}");
  const [configurationDraft, setConfigurationDraft] = useState(() => emptyConfigurationDraft(page.kind ?? "catalog"));

  async function loadOverview() {
    setLoading(true);
    setError(null);
    try {
      const payload = await adminConfiguration.overview(token);
      setOverview(payload);
      const workspace =
        payload.workspaces.find((item) => String(item.id) === selectedWorkspaceId) ?? payload.workspaces[0] ?? null;
      setSelectedWorkspaceId(String(workspace?.id ?? ""));
      setDefaultsDraft(JSON.stringify(workspace?.defaults_json ?? {}, null, 2));
    } catch (loadError) {
      setError(errorDetail(loadError));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    void adminConfiguration
      .overview(token)
      .then((payload) => {
        if (!active) return;
        const workspace = payload.workspaces[0] ?? null;
        setOverview(payload);
        setSelectedWorkspaceId(String(workspace?.id ?? ""));
        setDefaultsDraft(JSON.stringify(workspace?.defaults_json ?? {}, null, 2));
      })
      .catch((loadError) => {
        if (active) setError(errorDetail(loadError));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [token]);

  const selectedWorkspace = overview?.workspaces.find((item) => String(item.id) === selectedWorkspaceId) ?? null;
  const workspaceRows = useMemo(() => workspaceTreeRows(overview?.workspaces ?? []), [overview?.workspaces]);
  const currentConfigurations = useMemo(
    () => overview?.configurations.filter((item) => item.kind === page.kind) ?? [],
    [overview?.configurations, page.kind]
  );
  const publishedWorkspaceTypes = useMemo(
    () =>
      overview?.configurations.filter((item) => item.kind === "workspace_type" && item.status === "published") ?? [],
    [overview?.configurations]
  );
  const publishedModules = useMemo(
    () =>
      overview?.configurations.filter((item) => item.kind === "module_definition" && item.status === "published") ?? [],
    [overview?.configurations]
  );

  useEffect(() => {
    if (!selectedWorkspace) return;
    void adminConfiguration
      .effectiveWorkspace(token, selectedWorkspace.id)
      .then(setEffective)
      .catch((loadError) => setError(errorDetail(loadError)));
  }, [selectedWorkspace, token]);

  function selectWorkspace(value: string) {
    const workspace = overview?.workspaces.find((item) => String(item.id) === value);
    setSelectedWorkspaceId(value);
    setDefaultsDraft(JSON.stringify(workspace?.defaults_json ?? {}, null, 2));
  }

  async function runAction(key: string, task: () => Promise<unknown>, successMessage: string) {
    setAction(key);
    setMessage(null);
    setError(null);
    try {
      await task();
      setMessage(successMessage);
      await loadOverview();
    } catch (actionError) {
      setError(errorDetail(actionError));
    } finally {
      setAction(null);
    }
  }

  function createConfiguration(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!page.kind) return;
    let content: Record<string, unknown>;
    try {
      content = JSON.parse(configurationDraft.content) as Record<string, unknown>;
    } catch {
      setError("El contenido debe ser un objeto JSON válido.");
      return;
    }
    void runAction(
      "create-configuration",
      () =>
        adminConfiguration.createConfiguration(token, {
          kind: page.kind!,
          code: configurationDraft.code,
          name: configurationDraft.name,
          description: configurationDraft.description,
          content_json: content,
        }),
      "Borrador de configuración creado."
    ).then(() => setConfigurationDraft(emptyConfigurationDraft(page.kind!)));
  }

  function createWorkspace(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void runAction(
      "create-workspace",
      () =>
        adminConfiguration.createWorkspace(token, {
          code: workspaceDraft.code,
          name: workspaceDraft.name,
          workspace_type_code: workspaceDraft.workspace_type_code,
          parent_id: workspaceDraft.parent_id ? Number(workspaceDraft.parent_id) : null,
        }),
      "Workspace creado en la estructura empresarial."
    ).then(() => setWorkspaceDraft({ code: "", name: "", workspace_type_code: "project", parent_id: "" }));
  }

  function saveDefaults(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkspace) return;
    let values: Record<string, unknown>;
    try {
      values = JSON.parse(defaultsDraft) as Record<string, unknown>;
    } catch {
      setError("Los valores por defecto deben ser un objeto JSON válido.");
      return;
    }
    void runAction(
      "save-defaults",
      () =>
        adminConfiguration.updateWorkspaceDefaults(token, selectedWorkspace.id, {
          values,
          expected_version: selectedWorkspace.version,
        }),
      "Valores por defecto actualizados; la vista efectiva fue recalculada."
    );
  }

  async function runNumbering(committed: boolean) {
    const rule = currentConfigurations.find((item) => item.status === "published");
    if (!rule) return;
    setAction(committed ? "issue-number" : "preview-number");
    setError(null);
    try {
      const result = committed
        ? await adminConfiguration.issueNumber(token, rule.code, numberingScope)
        : await adminConfiguration.previewNumber(token, rule.code, numberingScope);
      setNumberingResult(result);
    } catch (numberError) {
      setError(errorDetail(numberError));
    } finally {
      setAction(null);
    }
  }

  if (loading && !overview) {
    return (
      <section aria-label={`${page.title} Module`} className="organizationSecurityLoading">
        <RefreshCw aria-hidden="true" className="spin" size={22} />
        <span>Cargando configuración de ADMIN MODE…</span>
      </section>
    );
  }

  if (!overview) {
    return (
      <section aria-label={`${page.title} Module`} className="organizationSecurityLoading error">
        <strong>No fue posible cargar la configuración.</strong>
        <span>{error}</span>
        <button className="workflowAction" onClick={() => void loadOverview()} type="button">
          Reintentar
        </button>
      </section>
    );
  }

  return (
    <section aria-label={`${page.title} Module`} className="adminConfigurationModule">
      <header className="adminConfigurationHeader">
        <div className="adminConfigurationTitleIcon">
          <PageIcon aria-hidden="true" size={24} />
        </div>
        <div>
          <span>ADMIN MODE / CONFIGURATION FOUNDATION</span>
          <h2>{page.title}</h2>
          <p>{page.description}</p>
        </div>
        <div className="adminConfigurationSummary" aria-label="Resumen de configuración">
          <strong>{overview.summary.published}</strong>
          <span>versiones publicadas</span>
          <small>{overview.summary.drafts} borradores</small>
        </div>
      </header>

      {message ? (
        <div className="uploadMessage success" role="status">
          {message}
        </div>
      ) : null}
      {error ? (
        <div className="uploadMessage error" role="alert">
          {error}
        </div>
      ) : null}

      {view === "enterprise-workspace-structure" ? (
        <div className="adminConfigurationGrid">
          <form className="securityFormCard" onSubmit={createWorkspace}>
            <div className="panelHeader compactHeader">
              <h3>
                <Building2 size={18} /> Crear workspace
              </h3>
              <span>Tipo publicado</span>
            </div>
            <div className="formColumns">
              <label>
                <span>Código</span>
                <input
                  disabled={!canConfigure || action !== null}
                  onChange={(event) => setWorkspaceDraft((current) => ({ ...current, code: event.target.value }))}
                  required
                  value={workspaceDraft.code}
                />
              </label>
              <label>
                <span>Tipo</span>
                <select
                  disabled={!canConfigure || action !== null}
                  onChange={(event) =>
                    setWorkspaceDraft((current) => ({ ...current, workspace_type_code: event.target.value }))
                  }
                  value={workspaceDraft.workspace_type_code}
                >
                  {publishedWorkspaceTypes.map((item) => (
                    <option key={item.id} value={item.code}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label>
              <span>Nombre</span>
              <input
                disabled={!canConfigure || action !== null}
                onChange={(event) => setWorkspaceDraft((current) => ({ ...current, name: event.target.value }))}
                required
                value={workspaceDraft.name}
              />
            </label>
            <label>
              <span>Workspace superior</span>
              <select
                disabled={!canConfigure || action !== null}
                onChange={(event) => setWorkspaceDraft((current) => ({ ...current, parent_id: event.target.value }))}
                value={workspaceDraft.parent_id}
              >
                <option value="">Raíz empresarial</option>
                {workspaceRows.map(({ workspace, depth }) => (
                  <option key={workspace.id} value={workspace.id}>{`${"— ".repeat(depth)}${workspace.name}`}</option>
                ))}
              </select>
            </label>
            <button className="workflowAction primary" disabled={!canConfigure || action !== null} type="submit">
              {action === "create-workspace" ? "Creando…" : "Crear workspace"}
            </button>
          </form>
          <WorkspaceTree rows={workspaceRows} />
        </div>
      ) : null}

      {view === "workspace-defaults" ? (
        <div className="adminConfigurationGrid">
          <form className="securityFormCard" onSubmit={saveDefaults}>
            <WorkspaceSelect
              disabled={action !== null}
              onChange={selectWorkspace}
              rows={workspaceRows}
              value={selectedWorkspaceId}
            />
            <label>
              <span>Valores definidos en este nivel (JSON)</span>
              <textarea
                className="configurationJsonEditor"
                disabled={!canConfigure || action !== null}
                onChange={(event) => setDefaultsDraft(event.target.value)}
                spellCheck={false}
                value={defaultsDraft}
              />
            </label>
            <button className="workflowAction primary" disabled={!canConfigure || action !== null} type="submit">
              {action === "save-defaults" ? "Guardando…" : "Guardar valores"}
            </button>
          </form>
          <section className="securityListCard effectiveConfigurationCard">
            <div className="panelHeader compactHeader">
              <h3>
                <GitBranch size={18} /> Configuración efectiva
              </h3>
              <span>{effective?.inheritance_path.length ?? 0} niveles</span>
            </div>
            <p>Resultado calculado desde la raíz; los valores más cercanos al workspace prevalecen.</p>
            <pre>{JSON.stringify(effective?.defaults ?? {}, null, 2)}</pre>
          </section>
        </div>
      ) : null}

      {view === "module-catalog-activation" ? (
        <>
          <ConfigurationCatalog
            action={action}
            canConfigure={canConfigure}
            configurations={currentConfigurations}
            draft={configurationDraft}
            onClone={(record) =>
              void runAction(
                "clone",
                () => adminConfiguration.cloneConfiguration(token, record.id),
                "Nueva revisión creada."
              )
            }
            onDraftChange={setConfigurationDraft}
            onPublish={(record) =>
              void runAction(
                "publish",
                () => adminConfiguration.publishConfiguration(token, record.id),
                "Versión publicada e inmutable."
              )
            }
            onSubmit={createConfiguration}
          />
          <section className="moduleActivationPanel">
            <div className="panelHeader compactHeader">
              <h3>
                <Boxes size={18} /> Activación por workspace
              </h3>
              <WorkspaceSelect
                disabled={action !== null}
                onChange={selectWorkspace}
                rows={workspaceRows}
                value={selectedWorkspaceId}
              />
            </div>
            <div className="moduleActivationGrid">
              {publishedModules.map((module) => {
                const setting = overview.module_settings.find(
                  (item) => item.workspace_id === selectedWorkspace?.id && item.module_key === module.code
                );
                const inherited = effective?.modules[module.code] ?? false;
                return (
                  <article key={module.id}>
                    <div>
                      <span>{module.code}</span>
                      <strong>{module.name}</strong>
                      <p>{module.description}</p>
                    </div>
                    <div className="moduleActivationControl">
                      <small>{setting ? "Definido aquí" : inherited ? "Heredado activo" : "No activo"}</small>
                      <button
                        aria-pressed={setting?.enabled ?? inherited}
                        className={
                          (setting?.enabled ?? inherited) ? "configurationToggle active" : "configurationToggle"
                        }
                        disabled={!canConfigure || action !== null || !selectedWorkspace}
                        onClick={() => {
                          if (!selectedWorkspace) return;
                          void runAction(
                            `module-${module.code}`,
                            () =>
                              adminConfiguration.setWorkspaceModule(token, selectedWorkspace.id, module.code, {
                                enabled: !(setting?.enabled ?? inherited),
                                expected_version: setting?.version,
                              }),
                            "Activación de módulo actualizada."
                          );
                        }}
                        type="button"
                      >
                        {(setting?.enabled ?? inherited) ? "Activo" : "Activar"}
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>
        </>
      ) : null}

      {page.kind && view !== "module-catalog-activation" ? (
        <ConfigurationCatalog
          action={action}
          canConfigure={canConfigure}
          configurations={currentConfigurations}
          draft={configurationDraft}
          onClone={(record) =>
            void runAction(
              "clone",
              () => adminConfiguration.cloneConfiguration(token, record.id),
              "Nueva revisión creada."
            )
          }
          onDraftChange={setConfigurationDraft}
          onPublish={(record) =>
            void runAction(
              "publish",
              () => adminConfiguration.publishConfiguration(token, record.id),
              "Versión publicada e inmutable."
            )
          }
          onSubmit={createConfiguration}
        />
      ) : null}

      {view === "numbering-rules" ? (
        <section className="numberingWorkbench">
          <div>
            <span>Alcance de secuencia</span>
            <input onChange={(event) => setNumberingScope(event.target.value)} value={numberingScope} />
          </div>
          <button
            className="workflowAction"
            disabled={action !== null}
            onClick={() => void runNumbering(false)}
            type="button"
          >
            <RefreshCw size={15} /> Previsualizar
          </button>
          <button
            className="workflowAction primary"
            disabled={!canConfigure || action !== null}
            onClick={() => void runNumbering(true)}
            type="button"
          >
            <Send size={15} /> Emitir consecutivo
          </button>
          <strong>{numberingResult?.value ?? "—"}</strong>
          <small>{numberingResult?.committed ? "Consecutivo confirmado" : "Vista previa sin consumo"}</small>
        </section>
      ) : null}
    </section>
  );
}

function ConfigurationCatalog({
  action,
  canConfigure,
  configurations,
  draft,
  onClone,
  onDraftChange,
  onPublish,
  onSubmit,
}: {
  action: string | null;
  canConfigure: boolean;
  configurations: AdminConfigurationRecord[];
  draft: { code: string; name: string; description: string; content: string };
  onClone: (record: AdminConfigurationRecord) => void;
  onDraftChange: (value: { code: string; name: string; description: string; content: string }) => void;
  onPublish: (record: AdminConfigurationRecord) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <div className="adminConfigurationGrid configurationCatalogLayout">
      <form className="securityFormCard" onSubmit={onSubmit}>
        <div className="panelHeader compactHeader">
          <h3>
            <CopyPlus size={18} /> Nuevo borrador
          </h3>
          <span>JSON declarativo</span>
        </div>
        <div className="formColumns">
          <label>
            <span>Código</span>
            <input
              disabled={!canConfigure || action !== null}
              onChange={(event) => onDraftChange({ ...draft, code: event.target.value })}
              required
              value={draft.code}
            />
          </label>
          <label>
            <span>Nombre</span>
            <input
              disabled={!canConfigure || action !== null}
              onChange={(event) => onDraftChange({ ...draft, name: event.target.value })}
              required
              value={draft.name}
            />
          </label>
        </div>
        <label>
          <span>Descripción</span>
          <textarea
            disabled={!canConfigure || action !== null}
            onChange={(event) => onDraftChange({ ...draft, description: event.target.value })}
            value={draft.description}
          />
        </label>
        <label>
          <span>Definición</span>
          <textarea
            className="configurationJsonEditor"
            disabled={!canConfigure || action !== null}
            onChange={(event) => onDraftChange({ ...draft, content: event.target.value })}
            spellCheck={false}
            value={draft.content}
          />
        </label>
        <button className="workflowAction primary" disabled={!canConfigure || action !== null} type="submit">
          Crear borrador
        </button>
      </form>
      <section className="securityListCard configurationVersionList">
        <div className="panelHeader compactHeader">
          <h3>Versiones</h3>
          <span>{configurations.length} registros</span>
        </div>
        {configurations.map((record) => (
          <article key={record.id}>
            <div>
              <span>
                {record.code} / rev. {record.revision}
              </span>
              <strong>{record.name}</strong>
              <p>{record.description}</p>
            </div>
            <div className="configurationVersionActions">
              <em className={record.status}>{record.status}</em>
              {record.status === "draft" ? (
                <button disabled={!canConfigure || action !== null} onClick={() => onPublish(record)} type="button">
                  <Send size={14} /> Publicar
                </button>
              ) : (
                <button disabled={!canConfigure || action !== null} onClick={() => onClone(record)} type="button">
                  <CopyPlus size={14} /> Clonar
                </button>
              )}
            </div>
          </article>
        ))}
      </section>
    </div>
  );
}

function WorkspaceTree({ rows }: { rows: Array<{ workspace: EnterpriseWorkspace; depth: number }> }) {
  return (
    <section className="securityListCard enterpriseWorkspaceTree">
      <div className="panelHeader compactHeader">
        <h3>
          <GitBranch size={18} /> Estructura empresarial
        </h3>
        <span>Sin ciclos</span>
      </div>
      <div role="tree">
        {rows.map(({ workspace, depth }) => (
          <article aria-level={depth + 1} key={workspace.id} role="treeitem" style={{ marginLeft: `${depth * 22}px` }}>
            <span>{workspace.workspace_type_code}</span>
            <strong>{workspace.name}</strong>
            <small>
              {workspace.code} / {workspace.status}
            </small>
          </article>
        ))}
      </div>
    </section>
  );
}

function WorkspaceSelect({
  disabled,
  onChange,
  rows,
  value,
}: {
  disabled: boolean;
  onChange: (value: string) => void;
  rows: Array<{ workspace: EnterpriseWorkspace; depth: number }>;
  value: string;
}) {
  return (
    <label className="workspaceConfigurationSelect">
      <span>Workspace</span>
      <select disabled={disabled} onChange={(event) => onChange(event.target.value)} value={value}>
        {rows.map(({ workspace, depth }) => (
          <option key={workspace.id} value={workspace.id}>{`${"— ".repeat(depth)}${workspace.name}`}</option>
        ))}
      </select>
    </label>
  );
}

function workspaceTreeRows(workspaces: EnterpriseWorkspace[]) {
  const children = new Map<number | null, EnterpriseWorkspace[]>();
  workspaces.forEach((workspace) =>
    children.set(workspace.parent_id, [...(children.get(workspace.parent_id) ?? []), workspace])
  );
  const rows: Array<{ workspace: EnterpriseWorkspace; depth: number }> = [];
  const walk = (parentId: number | null, depth: number) => {
    (children.get(parentId) ?? [])
      .sort((left, right) => left.sort_order - right.sort_order || left.name.localeCompare(right.name))
      .forEach((workspace) => {
        rows.push({ workspace, depth });
        walk(workspace.id, depth + 1);
      });
  };
  walk(null, 0);
  return rows;
}

function emptyConfigurationDraft(kind: AdminConfigurationKind) {
  return {
    code: "",
    name: "",
    description: "",
    content: JSON.stringify(contentExamples[kind], null, 2),
  };
}

function errorDetail(error: unknown) {
  if (error instanceof Error) return error.message;
  return "No fue posible completar la operación.";
}
