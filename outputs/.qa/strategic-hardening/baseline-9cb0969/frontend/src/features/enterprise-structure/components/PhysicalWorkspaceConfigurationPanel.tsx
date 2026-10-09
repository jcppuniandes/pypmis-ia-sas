import { Building2, Eye, Factory, Hash, Map, MapPin, PackageOpen, Save, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError } from "../../../api/client";
import { enterpriseStructureApi } from "../api";
import type { PhysicalConfiguration, PhysicalPreview } from "../types";

const DISPLAY_TYPES = ["region", "district", "site", "property", "facility", "warehouse", "linear-asset"];
const ACTIVE_PHYSICAL_TYPES = ["region", "district", "site", "property", "facility", "warehouse"];
const COMPOSITION_CAPABILITIES: Record<string, string[]> = {
  region: ACTIVE_PHYSICAL_TYPES,
  district: ["site", "property", "facility", "warehouse"],
  site: ["property", "facility", "warehouse"],
  property: ["facility", "warehouse"],
  facility: ["warehouse"],
  warehouse: [],
};

function messageFrom(error: unknown) {
  if (!(error instanceof ApiError))
    return error instanceof Error ? error.message : "No fue posible completar la operacion.";
  try {
    return String((JSON.parse(error.message) as { detail?: string }).detail ?? error.message);
  } catch {
    return error.message;
  }
}

function iconFor(code: string) {
  if (code === "region" || code === "district") return <Map size={18} />;
  if (code === "site") return <MapPin size={18} />;
  if (code === "property") return <Building2 size={18} />;
  if (code === "facility") return <Factory size={18} />;
  return <PackageOpen size={18} />;
}

export default function PhysicalWorkspaceConfigurationPanel({
  token,
  canConfigure,
}: {
  token: string;
  canConfigure: boolean;
}) {
  const [data, setData] = useState<PhysicalConfiguration | null>(null);
  const [selectedType, setSelectedType] = useState("property");
  const [section, setSection] = useState<
    "general" | "attributes" | "composition" | "templates" | "numbering" | "policy" | "preview"
  >("general");
  const [parentId, setParentId] = useState(0);
  const [templateId, setTemplateId] = useState(0);
  const [name, setName] = useState("Workspace de prueba");
  const [preview, setPreview] = useState<PhysicalPreview | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [compositionChildren, setCompositionChildren] = useState<string[]>([]);
  const [numberingPrefix, setNumberingPrefix] = useState("");
  const [numberingPadding, setNumberingPadding] = useState(5);

  const load = useCallback(async () => {
    const response = await enterpriseStructureApi.physicalConfiguration(token);
    setData(response);
    setParentId((current) => current || response.parent_options[0]?.id || 0);
  }, [token]);

  useEffect(() => {
    // Remote synchronization is intentional on panel entry.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load()
      .catch((caught) => setError(messageFrom(caught)))
      .finally(() => setBusy(false));
  }, [load]);

  const workspaceType = data?.workspace_types.find((item) => item.code === selectedType) ?? null;
  const content = workspaceType?.content_json ?? {};
  const templates = useMemo(
    () =>
      data?.templates.filter(
        (item) => item.content_json.workspace_type_code === selectedType && item.status !== "archived"
      ) ?? [],
    [data, selectedType]
  );
  const numbering =
    data?.numbering_rules.find((item) => item.content_json.configuration_version && item.code.endsWith(selectedType)) ??
    null;
  const policy = data?.creation_policies.find((item) => item.content_json.workspace_type_code === selectedType) ?? null;

  useEffect(() => {
    // Local editor values intentionally follow the selected server revision.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCompositionChildren(data?.composition_rules[selectedType] ?? []);
    setNumberingPrefix(String(numbering?.content_json.prefix ?? ""));
    setNumberingPadding(Number(numbering?.content_json.padding ?? 5));
    setNotice("");
  }, [data, numbering, selectedType]);

  const mutate = async (operation: () => Promise<unknown>, success: string) => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await operation();
      await load();
      setNotice(success);
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    // Keep preview controls aligned with the parametrized type.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setTemplateId(templates[0]?.id ?? 0);
    setPreview(null);
  }, [templates]);

  if (busy && !data) return <p>Cargando configuracion fisica y geografica…</p>;

  return (
    <div className="physicalConfigurationWorkspace">
      {error ? <div className="enterpriseAlert error">{error}</div> : null}
      {notice ? <div className="enterpriseAlert success">{notice}</div> : null}
      {data ? (
        <section className="projectGateStrip physicalGateStrip" aria-label="Estado Gate 06A">
          <ShieldCheck size={20} />
          <div>
            <strong>{data.gate_status}</strong>
            <span>Configuracion gobernada; sin instancias reales ni procesos de creacion.</span>
          </div>
          <em>{data.summary.real_instances} instancias fisicas reales creadas por Gate 06A</em>
        </section>
      ) : null}

      <div className="physicalTypeCards">
        {DISPLAY_TYPES.map((code) => {
          const item = data?.workspace_types.find((type) => type.code === code);
          if (!item) return null;
          const reserved = Boolean(item.content_json.reserved);
          return (
            <button
              className={selectedType === code ? "active" : ""}
              key={code}
              onClick={() => setSelectedType(code)}
              type="button"
            >
              {iconFor(code)}
              <span>{code.replace("-", "_").toUpperCase()}</span>
              <small>{reserved ? "Reservado · no creable" : code === "property" ? "Real Estate" : "Activo"}</small>
            </button>
          );
        })}
      </div>

      <nav className="physicalSubtabs" aria-label="Configuracion por Workspace Type">
        {(["general", "attributes", "composition", "templates", "numbering", "policy", "preview"] as const).map(
          (item) => (
            <button
              className={section === item ? "active" : ""}
              key={item}
              onClick={() => setSection(item)}
              type="button"
            >
              {item === "composition" ? "Allowed Parents / Children" : item.charAt(0).toUpperCase() + item.slice(1)}
            </button>
          )
        )}
      </nav>

      {workspaceType && section === "general" ? (
        <section className="enterprisePanel physicalDetailPanel">
          <header>
            <div>
              <span>Workspace Type</span>
              <h3>{workspaceType.name}</h3>
            </div>
            {iconFor(selectedType)}
          </header>
          <p>{workspaceType.description}</p>
          <dl className="projectFacts">
            {[
              "repeatable",
              "hierarchical_record_code",
              "business_numbering",
              "admin_configurable",
              "user_mode_enabled",
              "template_supported",
              "creation_process_supported",
              "reserved",
            ].map((key) => (
              <div key={key}>
                <dt>{key.replace(/_/g, " ")}</dt>
                <dd>{content[key] ? "Si" : "No"}</dd>
              </div>
            ))}
          </dl>
          {selectedType === "property" ? (
            <div className="physicalDecision">
              <strong>PROPERTY = Real Estate</strong>
              <span>No se renombra ni se confunde con FACILITY.</span>
            </div>
          ) : null}
          {selectedType === "linear-asset" ? (
            <div className="physicalDecision warning">
              <strong>LINEAR_ASSET reservado</strong>
              <span>No disponible para creacion u operacion.</span>
            </div>
          ) : null}
        </section>
      ) : null}

      {section === "attributes" ? (
        <section className="enterprisePanel physicalDetailPanel">
          <header>
            <div>
              <span>Attributes</span>
              <h3>Formulario parametrizado</h3>
            </div>
          </header>
          <div className="projectAttributeList">
            {((content.workspace_attributes as string[]) ?? []).map((attribute) => (
              <span key={attribute}>
                <strong>{attribute}</strong>
                <small>Workspace attribute</small>
              </span>
            ))}
          </div>
        </section>
      ) : null}

      {section === "composition" && data ? (
        <section className="enterprisePanel physicalDetailPanel">
          <header>
            <div>
              <span>Composition Rules</span>
              <h3>Matriz flexible</h3>
            </div>
          </header>
          <p>Capacidades permitidas; los niveles REGION, DISTRICT y SITE no son obligatorios.</p>
          <div className="physicalCompositionMatrix">
            {Object.entries(data.composition_rules).map(([parent, children]) => (
              <article key={parent}>
                <strong>{parent.toUpperCase()}</strong>
                <span>{children.length ? children.map((child) => child.toUpperCase()).join(" · ") : "Sin hijos"}</span>
              </article>
            ))}
          </div>
          {canConfigure && selectedType !== "linear-asset" ? (
            <div className="physicalEditor">
              <strong>Hijos fisicos permitidos desde {selectedType.toUpperCase()}</strong>
              <div className="physicalCheckGrid">
                {(COMPOSITION_CAPABILITIES[selectedType] ?? [])
                  .filter((code) => code !== selectedType)
                  .map((code) => (
                    <label key={code}>
                      <input
                        checked={compositionChildren.includes(code)}
                        disabled={selectedType === "warehouse"}
                        onChange={(event) =>
                          setCompositionChildren((current) =>
                            event.target.checked ? [...current, code] : current.filter((item) => item !== code)
                          )
                        }
                        type="checkbox"
                      />
                      <span>{code.toUpperCase()}</span>
                    </label>
                  ))}
              </div>
              <button
                className="enterpriseButton primary"
                disabled={busy || selectedType === "warehouse"}
                onClick={() =>
                  mutate(
                    () =>
                      enterpriseStructureApi.updatePhysicalComposition(
                        token,
                        selectedType,
                        workspaceType?.version ?? 0,
                        compositionChildren
                      ),
                    "Composition Rule guardada con revision y auditoria."
                  )
                }
                type="button"
              >
                <Save size={15} /> Guardar composicion
              </button>
            </div>
          ) : null}
        </section>
      ) : null}

      {section === "templates" ? (
        <section className="enterprisePanel physicalDetailPanel">
          <header>
            <div>
              <span>Templates</span>
              <h3>Revisiones controladas</h3>
            </div>
          </header>
          {templates.length ? (
            <div className="physicalConfigRows">
              {templates.map((item) => (
                <article key={item.id}>
                  <strong>{item.code}</strong>
                  <span>{item.name}</span>
                  <em>{item.status}</em>
                </article>
              ))}
            </div>
          ) : (
            <p>Este tipo no tiene plantillas configurables en Gate 06A.</p>
          )}
        </section>
      ) : null}

      {section === "numbering" ? (
        <section className="enterprisePanel physicalDetailPanel">
          <header>
            <div>
              <span>Numbering Rules</span>
              <h3>Business Number separado del Record Code</h3>
            </div>
            <Hash />
          </header>
          {numbering ? (
            <>
              <div className="projectNumberExample">
                {String(numbering.content_json.prefix)}-
                {String(1).padStart(Number(numbering.content_json.padding), "0")}
              </div>
              <p>Preview no consume secuencia · tenant-scoped · no reuse.</p>
              {canConfigure ? (
                <div className="physicalEditor inline">
                  <label>
                    <span>Prefijo</span>
                    <input value={numberingPrefix} onChange={(event) => setNumberingPrefix(event.target.value)} />
                  </label>
                  <label>
                    <span>Digitos</span>
                    <input
                      min={3}
                      max={10}
                      type="number"
                      value={numberingPadding}
                      onChange={(event) => setNumberingPadding(Number(event.target.value))}
                    />
                  </label>
                  <button
                    className="enterpriseButton primary"
                    disabled={busy || !numberingPrefix.trim()}
                    onClick={() =>
                      mutate(
                        () =>
                          enterpriseStructureApi.updatePhysicalNumbering(
                            token,
                            selectedType,
                            numbering.version,
                            numberingPrefix,
                            numberingPadding
                          ),
                        "Numbering Rule guardada sin consumir la secuencia."
                      )
                    }
                    type="button"
                  >
                    <Save size={15} /> Guardar numeracion
                  </button>
                </div>
              ) : null}
            </>
          ) : (
            <p>Numeracion reservada no disponible.</p>
          )}
        </section>
      ) : null}

      {section === "policy" ? (
        <section className="enterprisePanel physicalDetailPanel">
          <header>
            <div>
              <span>Creation Policy</span>
              <h3>Contrato DRAFT</h3>
            </div>
          </header>
          {policy ? (
            <>
              <div className="physicalConfigRows">
                {Object.entries(policy.content_json)
                  .filter(([, value]) => typeof value !== "object")
                  .map(([key, value]) => (
                    <article key={key}>
                      <strong>{key.replace(/_/g, " ")}</strong>
                      <span>{String(value)}</span>
                    </article>
                  ))}
              </div>
              <p>Gate 06A no ejecuta Creation Processes.</p>
              {canConfigure ? (
                <button
                  className="enterpriseButton primary"
                  disabled={busy}
                  onClick={() =>
                    mutate(
                      () =>
                        enterpriseStructureApi.updatePhysicalCreationPolicy(token, selectedType, policy.version, {
                          allowed_parent_types: policy.content_json.allowed_parent_types,
                          template_required: policy.content_json.template_required,
                          responsible_required: policy.content_json.responsible_required,
                          approval_required: policy.content_json.approval_required,
                          auto_business_number: policy.content_json.auto_business_number,
                          auto_record_code: policy.content_json.auto_record_code,
                          initial_workspace_status: policy.content_json.initial_workspace_status,
                          activation_rule: policy.content_json.activation_rule,
                        }),
                      "Creation Policy DRAFT guardada con control de concurrencia."
                    )
                  }
                  type="button"
                >
                  <Save size={15} /> Confirmar policy DRAFT
                </button>
              ) : null}
            </>
          ) : (
            <p>No aplica: tipo geografico o reservado.</p>
          )}
        </section>
      ) : null}

      {section === "preview" && data ? (
        <section className="enterprisePanel projectPreviewPanel physicalDetailPanel">
          <header>
            <div>
              <span>Dry run</span>
              <h3>Workspace Preview</h3>
            </div>
            <Eye />
          </header>
          <div className="projectPreviewControls">
            <label>
              <span>Parent Workspace</span>
              <select value={parentId} onChange={(event) => setParentId(Number(event.target.value))}>
                {data.parent_options.map((parent) => (
                  <option key={parent.id} value={parent.id}>
                    {parent.record_code} · {parent.name} ({parent.workspace_type_code})
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Template</span>
              <select
                disabled={!templates.length}
                value={templateId}
                onChange={(event) => setTemplateId(Number(event.target.value))}
              >
                <option value={0}>Sin template</option>
                {templates.map((template) => (
                  <option key={template.id} value={template.id}>
                    {template.code} · {template.status}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Name</span>
              <input value={name} onChange={(event) => setName(event.target.value)} />
            </label>
            <button
              className="enterpriseButton primary"
              disabled={busy || !parentId || selectedType === "linear-asset"}
              onClick={async () => {
                setBusy(true);
                setError("");
                try {
                  setPreview(
                    await enterpriseStructureApi.previewPhysicalWorkspace(token, {
                      workspace_type_code: selectedType,
                      parent_id: parentId,
                      template_id: templateId || null,
                      minimal_attributes: { name },
                    })
                  );
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
                <span>Allowed</span>
                <strong>{preview.allowed ? "YES" : "NO"}</strong>
              </article>
              <article>
                <span>Record Code</span>
                <strong>{preview.projected_record_code}</strong>
              </article>
              <article>
                <span>Business Number</span>
                <strong>{preview.projected_business_number ?? "N/A"}</strong>
              </article>
              <article>
                <span>Persisted</span>
                <strong>{preview.persisted ? "YES" : "NO"}</strong>
              </article>
              {preview.issues.length ? (
                <ul>
                  {preview.issues.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              ) : (
                <p>Parent, tipo, template, clasificaciones y numeracion validados por backend.</p>
              )}
            </div>
          ) : null}
        </section>
      ) : null}

      {!canConfigure ? (
        <div className="enterpriseAlert">Vista de consulta: configuracion protegida por RBAC.</div>
      ) : null}
      <div className="physicalDecision">
        <strong>ASSET != Workspace Type</strong>
        <span>Los Assets seran registros operacionales de Asset Manager en un gate futuro.</span>
      </div>
    </div>
  );
}
