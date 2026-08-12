import { Archive, CheckCircle2, CopyPlus, Eye, FileStack, Hash, Layers3, Save, Send, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError } from "../../../api/client";
import { enterpriseStructureApi } from "../api";
import type { ConfigurationVersion, ProjectConfiguration, ProjectPreview, ProjectTemplatePayload } from "../types";

type ProjectView = "templates" | "numbering" | "policy";

const EMPTY_TEMPLATE: ProjectTemplatePayload = {
  code: "",
  name: "",
  description: "",
  applicable_parent_types: ["portfolio", "program"],
  default_classifications: [],
  enabled_modules: [],
  default_role_codes: [],
  default_group_codes: [],
  numbering_rule_code: "project-workspace",
  default_attributes: { currency: "COP", country: "CO" },
  creation_policy_code: "project-creation",
};

function messageFrom(error: unknown) {
  if (!(error instanceof ApiError)) {
    return error instanceof Error ? error.message : "No fue posible completar la operacion.";
  }
  try {
    const body = JSON.parse(error.message) as {
      detail?: string | { message?: string; issues?: string[] };
    };
    if (typeof body.detail === "string") return body.detail;
    return [body.detail?.message, ...(body.detail?.issues ?? [])].filter(Boolean).join(" · ") || error.message;
  } catch {
    return error.message;
  }
}

function templatePayload(template: ConfigurationVersion): ProjectTemplatePayload {
  const content = template.content_json;
  return {
    code: template.code,
    name: template.name,
    description: template.description,
    applicable_parent_types: (content.applicable_parent_types as string[]) ?? [],
    default_classifications:
      (content.default_classifications as ProjectTemplatePayload["default_classifications"]) ?? [],
    enabled_modules: (content.enabled_modules as string[]) ?? [],
    default_role_codes: (content.default_role_codes as string[]) ?? [],
    default_group_codes: (content.default_group_codes as string[]) ?? [],
    numbering_rule_code: String(content.numbering_rule_code ?? "project-workspace"),
    default_attributes: (content.default_attributes as Record<string, unknown>) ?? {},
    creation_policy_code: String(content.creation_policy_code ?? "project-creation"),
  };
}

export default function ProjectWorkspaceConfigurationPanel({
  token,
  canConfigure,
  view,
}: {
  token: string;
  canConfigure: boolean;
  view: ProjectView;
}) {
  const [data, setData] = useState<ProjectConfiguration | null>(null);
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null);
  const [draft, setDraft] = useState<ProjectTemplatePayload>(EMPTY_TEMPLATE);
  const [parentId, setParentId] = useState(0);
  const [templateId, setTemplateId] = useState(0);
  const [preview, setPreview] = useState<ProjectPreview | null>(null);
  const [prefix, setPrefix] = useState("PYP-PRJ");
  const [padding, setPadding] = useState(5);
  const [policy, setPolicy] = useState<Record<string, unknown>>({});
  const [busy, setBusy] = useState(true);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const response = await enterpriseStructureApi.projectConfiguration(token);
    setData(response);
    setSelectedTemplateId((current) => current ?? response.templates[0]?.id ?? null);
    setParentId((current) => current || response.parent_options[0]?.id || 0);
    setTemplateId((current) => current || response.templates[0]?.id || 0);
    setPrefix(String(response.numbering_rule.content_json.prefix ?? "PYP-PRJ"));
    setPadding(Number(response.numbering_rule.content_json.padding ?? 5));
    setPolicy(response.creation_policy.content_json);
  }, [token]);

  useEffect(() => {
    // Initial synchronization is intentional on panel entry.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load()
      .catch((caught) => setError(messageFrom(caught)))
      .finally(() => setBusy(false));
  }, [load]);

  const selectedTemplate = useMemo(
    () => data?.templates.find((item) => item.id === selectedTemplateId) ?? null,
    [data, selectedTemplateId]
  );

  useEffect(() => {
    if (!selectedTemplate) return;
    // The form intentionally mirrors the selected persisted revision.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDraft(templatePayload(selectedTemplate));
  }, [selectedTemplate]);

  async function run(action: () => Promise<unknown>, success: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      await load();
      setNotice(success);
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(false);
    }
  }

  async function saveTemplate() {
    if (!selectedTemplate) {
      await run(
        () => enterpriseStructureApi.createProjectTemplate(token, draft),
        "Project Template creada como borrador."
      );
      return;
    }
    await run(
      () =>
        enterpriseStructureApi.updateProjectTemplate(token, selectedTemplate.id, {
          ...draft,
          expected_version: selectedTemplate.version,
        }),
      "Project Template guardada como borrador."
    );
  }

  async function publishTemplate() {
    if (!selectedTemplate) return;
    setBusy(true);
    setError("");
    try {
      const validation = await enterpriseStructureApi.validateProjectTemplate(token, selectedTemplate.id);
      if (!validation.valid) throw new Error(validation.issues.join(" · "));
      await enterpriseStructureApi.publishProjectTemplate(token, selectedTemplate.id, validation.content_hash);
      await load();
      setNotice("Project Template validada y publicada.");
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(false);
    }
  }

  const projectContent = data?.project_type.content_json ?? {};
  const projectAttributes = (projectContent.project_attributes as Array<Record<string, unknown>>) ?? [];

  return (
    <div className="projectConfigurationWorkspace">
      {error ? <div className="enterpriseAlert error">{error}</div> : null}
      {notice ? <div className="enterpriseAlert success">{notice}</div> : null}
      {data ? (
        <section className="projectGateStrip" aria-label="Estado Gate 05A">
          <ShieldCheck size={20} />
          <div>
            <strong>{data.gate_status}</strong>
            <span>Configuracion ADMIN lista; el Project Creation Process permanece fuera de este gate.</span>
          </div>
          <em>0 Project Workspaces creados por esta pantalla</em>
        </section>
      ) : null}

      {view === "templates" && data ? (
        <>
          <section className="projectSummaryGrid">
            <article>
              <Layers3 />
              <span>Workspace Type</span>
              <strong>PROJECT</strong>
              <small>Repetible · USER MODE · configurable</small>
            </article>
            <article>
              <FileStack />
              <span>Project Templates</span>
              <strong>{data.summary.templates}</strong>
              <small>{data.summary.draft_templates} borradores controlados</small>
            </article>
            <article>
              <CheckCircle2 />
              <span>Padres permitidos</span>
              <strong>Portfolio / Program</strong>
              <small>Backend source of truth</small>
            </article>
            <article>
              <Hash />
              <span>Identificadores</span>
              <strong>Separados</strong>
              <small>id · external_key · Record Code · Project Number</small>
            </article>
          </section>

          <section className="projectDefinitionGrid">
            <article className="enterprisePanel">
              <header>
                <div>
                  <span>General</span>
                  <h3>Comportamiento PROJECT</h3>
                </div>
              </header>
              <dl className="projectFacts">
                {[
                  "repeatable",
                  "user_mode_enabled",
                  "admin_configurable",
                  "template_supported",
                  "creation_process_supported",
                ].map((key) => (
                  <div key={key}>
                    <dt>{key.replace(/_/g, " ")}</dt>
                    <dd>{projectContent[key] ? "Si" : "No"}</dd>
                  </div>
                ))}
              </dl>
            </article>
            <article className="enterprisePanel">
              <header>
                <div>
                  <span>Atributos</span>
                  <h3>Formulario de Project Workspace</h3>
                </div>
              </header>
              <div className="projectAttributeList">
                {projectAttributes.map((attribute) => (
                  <span key={String(attribute.code)}>
                    <strong>{String(attribute.label)}</strong>
                    <small>
                      {String(attribute.type)}
                      {attribute.required ? " · requerido" : ""}
                    </small>
                  </span>
                ))}
              </div>
            </article>
          </section>

          <section className="projectTemplateLayout">
            <aside className="enterprisePanel projectTemplateList">
              <header>
                <div>
                  <span>Project Templates</span>
                  <h3>Revisiones configuradas</h3>
                </div>
              </header>
              {data.templates.map((item) => (
                <button
                  className={item.id === selectedTemplateId ? "active" : ""}
                  key={item.id}
                  onClick={() => setSelectedTemplateId(item.id)}
                  type="button"
                >
                  <strong>{item.name}</strong>
                  <span>{item.code}</span>
                  <em>
                    {item.status} · r{item.revision}
                  </em>
                </button>
              ))}
              <button
                className="enterpriseButton"
                disabled={!canConfigure || busy}
                onClick={() => {
                  setSelectedTemplateId(null);
                  setDraft({ ...EMPTY_TEMPLATE });
                }}
                type="button"
              >
                <FileStack size={15} /> Nueva plantilla
              </button>
            </aside>
            <section className="enterprisePanel projectTemplateEditor">
              <header>
                <div>
                  <span>Configuracion reutilizable</span>
                  <h3>{selectedTemplate?.name ?? "Nueva Project Template"}</h3>
                </div>
                {selectedTemplate?.status === "published" ? (
                  <button
                    className="enterpriseButton"
                    disabled={!canConfigure || busy}
                    onClick={() =>
                      run(
                        () => enterpriseStructureApi.cloneProjectTemplate(token, selectedTemplate.id),
                        "Borrador clonado."
                      )
                    }
                    type="button"
                  >
                    <CopyPlus size={15} /> Clonar
                  </button>
                ) : null}
              </header>
              <div className="projectTemplateForm">
                <label>
                  <span>Codigo</span>
                  <input
                    disabled={!canConfigure || Boolean(selectedTemplate)}
                    value={draft.code}
                    onChange={(event) => setDraft({ ...draft, code: event.target.value })}
                  />
                </label>
                <label>
                  <span>Nombre</span>
                  <input
                    disabled={!canConfigure || Boolean(selectedTemplate && selectedTemplate.status !== "draft")}
                    value={draft.name}
                    onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                  />
                </label>
                <label className="wide">
                  <span>Descripcion</span>
                  <textarea
                    disabled={!canConfigure || Boolean(selectedTemplate && selectedTemplate.status !== "draft")}
                    value={draft.description}
                    onChange={(event) => setDraft({ ...draft, description: event.target.value })}
                  />
                </label>
                <fieldset>
                  <legend>Padres aplicables</legend>
                  {data.allowed_parent_types.map((code) => (
                    <label key={code}>
                      <input
                        checked={draft.applicable_parent_types.includes(code)}
                        disabled={!canConfigure || Boolean(selectedTemplate && selectedTemplate.status !== "draft")}
                        onChange={(event) =>
                          setDraft({
                            ...draft,
                            applicable_parent_types: event.target.checked
                              ? [...draft.applicable_parent_types, code]
                              : draft.applicable_parent_types.filter((item) => item !== code),
                          })
                        }
                        type="checkbox"
                      />{" "}
                      {code.toUpperCase()}
                    </label>
                  ))}
                </fieldset>
                <fieldset>
                  <legend>Modulos existentes habilitados</legend>
                  {data.available_modules.map((module) => (
                    <label key={module.code}>
                      <input
                        checked={draft.enabled_modules.includes(module.code)}
                        disabled={!canConfigure || Boolean(selectedTemplate && selectedTemplate.status !== "draft")}
                        onChange={(event) =>
                          setDraft({
                            ...draft,
                            enabled_modules: event.target.checked
                              ? [...draft.enabled_modules, module.code]
                              : draft.enabled_modules.filter((item) => item !== module.code),
                          })
                        }
                        type="checkbox"
                      />{" "}
                      {module.name}
                    </label>
                  ))}
                </fieldset>
              </div>
              <div className="publicationActions">
                {selectedTemplate?.status === "draft" || !selectedTemplate ? (
                  <button
                    className="enterpriseButton"
                    disabled={!canConfigure || busy}
                    onClick={saveTemplate}
                    type="button"
                  >
                    <Save size={15} /> Guardar
                  </button>
                ) : null}
                {selectedTemplate?.status === "draft" ? (
                  <button
                    className="enterpriseButton primary"
                    disabled={!canConfigure || busy}
                    onClick={publishTemplate}
                    type="button"
                  >
                    <Send size={15} /> Validar y publicar
                  </button>
                ) : null}
                {selectedTemplate ? (
                  <button
                    className="enterpriseButton danger"
                    disabled={!canConfigure || busy}
                    onClick={() =>
                      run(
                        () => enterpriseStructureApi.archiveProjectTemplate(token, selectedTemplate.id),
                        "Plantilla archivada logicamente."
                      )
                    }
                    type="button"
                  >
                    <Archive size={15} /> Archivar
                  </button>
                ) : null}
              </div>
            </section>
          </section>

          <section className="enterprisePanel projectPreviewPanel">
            <header>
              <div>
                <span>Dry run</span>
                <h3>Preview del futuro Project Workspace</h3>
              </div>
              <Eye />
            </header>
            <div className="projectPreviewControls">
              <label>
                <span>Workspace padre</span>
                <select value={parentId} onChange={(event) => setParentId(Number(event.target.value))}>
                  {data.parent_options.map((parent) => (
                    <option key={parent.id} value={parent.id}>
                      {parent.record_code} · {parent.name} ({parent.workspace_type_code})
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Project Template</span>
                <select value={templateId} onChange={(event) => setTemplateId(Number(event.target.value))}>
                  {data.templates
                    .filter((item) => item.status !== "archived")
                    .map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.code} · {item.status}
                      </option>
                    ))}
                </select>
              </label>
              <button
                className="enterpriseButton primary"
                disabled={busy || !parentId || !templateId}
                onClick={async () => {
                  setBusy(true);
                  setError("");
                  try {
                    setPreview(await enterpriseStructureApi.previewProject(token, parentId, templateId));
                  } catch (caught) {
                    setError(messageFrom(caught));
                  } finally {
                    setBusy(false);
                  }
                }}
                type="button"
              >
                <Eye size={15} /> Previsualizar
              </button>
            </div>
            {preview ? (
              <div className={`projectPreviewResult ${preview.allowed ? "allowed" : "blocked"}`}>
                <article>
                  <span>Record Code</span>
                  <strong>{preview.projected_record_code}</strong>
                </article>
                <article>
                  <span>Project Number</span>
                  <strong>{preview.projected_project_number}</strong>
                </article>
                <article>
                  <span>Estado inicial</span>
                  <strong>{preview.initial_status}</strong>
                </article>
                <article>
                  <span>Persistencia</span>
                  <strong>{preview.persisted ? "Si" : "No (preview)"}</strong>
                </article>
                {preview.issues.length ? (
                  <ul>
                    {preview.issues.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p>Padre, plantilla, clasificaciones y modulos validados por backend.</p>
                )}
              </div>
            ) : null}
          </section>
        </>
      ) : null}

      {view === "numbering" && data ? (
        <section className="enterprisePanel projectFocusedPanel">
          <header>
            <div>
              <span>Numbering Rules</span>
              <h3>Project Number</h3>
            </div>
            <Hash />
          </header>
          <p>Identificador de negocio independiente del id tecnico, external key y Record Code jerarquico.</p>
          <div className="projectNumberExample">
            {prefix}-{String(1).padStart(padding, "0")}
          </div>
          <div className="projectPreviewControls">
            <label>
              <span>Prefijo</span>
              <input disabled={!canConfigure} value={prefix} onChange={(event) => setPrefix(event.target.value)} />
            </label>
            <label>
              <span>Digitos</span>
              <input
                disabled={!canConfigure}
                min="3"
                max="12"
                type="number"
                value={padding}
                onChange={(event) => setPadding(Number(event.target.value))}
              />
            </label>
            <button
              className="enterpriseButton primary"
              disabled={!canConfigure || busy}
              onClick={() =>
                run(
                  () => enterpriseStructureApi.updateProjectNumbering(token, prefix, padding),
                  "Regla de numeracion versionada."
                )
              }
              type="button"
            >
              <Save size={15} /> Guardar revision
            </button>
          </div>
          <dl className="projectFacts">
            <div>
              <dt>Unicidad</dt>
              <dd>Por tenant</dd>
            </div>
            <div>
              <dt>Reutilizacion</dt>
              <dd>No</dd>
            </div>
            <div>
              <dt>Preview</dt>
              <dd>No consume secuencia</dd>
            </div>
            <div>
              <dt>Record Code</dt>
              <dd>Motor existente</dd>
            </div>
          </dl>
        </section>
      ) : null}

      {view === "policy" && data ? (
        <section className="enterprisePanel projectFocusedPanel">
          <header>
            <div>
              <span>Creation Policies</span>
              <h3>Project Creation Process</h3>
            </div>
            <ShieldCheck />
          </header>
          <p>Configuracion declarativa para Gate 05B. Este panel no crea, aprueba ni materializa Project Workspaces.</p>
          <div className="projectPolicyGrid">
            {[
              ["template_required", "Project Template requerida"],
              ["project_manager_required", "Project Manager requerido"],
              ["strategic_objective_required", "Objetivo estrategico requerido"],
              ["approval_required", "Aprobacion requerida"],
              ["auto_project_number", "Project Number automatico"],
              ["auto_record_code", "Record Code automatico"],
              ["activation_after_approval", "Activacion posterior a aprobacion"],
              ["materialization_after_approval", "Materializacion posterior a aprobacion"],
            ].map(([key, label]) => (
              <label key={key}>
                <input
                  checked={Boolean(policy[key])}
                  disabled={!canConfigure}
                  onChange={(event) => setPolicy({ ...policy, [key]: event.target.checked })}
                  type="checkbox"
                />
                <span>{label}</span>
              </label>
            ))}
          </div>
          <div className="publicationActions">
            <button
              className="enterpriseButton primary"
              disabled={!canConfigure || busy}
              onClick={() =>
                run(
                  () => enterpriseStructureApi.updateProjectCreationPolicy(token, policy),
                  "Politica de creacion versionada."
                )
              }
              type="button"
            >
              <Save size={15} /> Guardar revision
            </button>
          </div>
        </section>
      ) : null}
    </div>
  );
}
