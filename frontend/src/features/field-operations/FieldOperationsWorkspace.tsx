import { useState, type FormEvent } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { Evidence, Facts, Input, ReasonCodes, Records, Select } from "../progress-foundation/Fields";
import {
  isRow,
  permits,
  positiveId,
  projectRoot,
  query,
  rows,
  text,
  useCommands,
  useRead,
  versionOf,
  type Row,
  type Scope,
} from "./api";
import { FieldCommandForm, ReadState } from "./FieldForms";
import FieldConsumerPanel from "./FieldConsumerPanel";
import { entities, tabs, type Entity } from "./views";
import "../progress-foundation/progressFoundation.css";
import "./fieldOperations.css";

function Paging({ after, setAfter, next }: { after: string; setAfter: (value: string) => void; next: unknown }) {
  return after || positiveId(next) ? (
    <div className="fieldActions">
      {after ? (
        <button type="button" onClick={() => setAfter("")}>
          Primera página
        </button>
      ) : null}
      {positiveId(next) ? (
        <button type="button" onClick={() => setAfter(text(next))}>
          Página siguiente
        </button>
      ) : null}
    </div>
  ) : null;
}

function EntityPanel({ label, entity, scope }: { label: string; entity: Entity; scope: Scope }) {
  const [after, setAfter] = useState("");
  const [selection, setSelection] = useState("");
  const [editor, setEditor] = useState("");
  const register = useRead(scope.token, scope.base, query(entity.path, { limit: 50, after_id: after }), scope.revision);
  const detail = useRead(
    scope.token,
    scope.base,
    selection && entity.details !== false ? `${entity.path}/${selection}` : null,
    scope.revision
  );
  const current =
    detail.data ?? (entity.details === false ? rows(register.data).find((row) => text(row.id) === selection) : null);
  const version = versionOf(current?.version);
  const status = text(current?.status).toUpperCase();
  const actions = (entity.actions ?? []).filter(
    (item) => scope.can(item.duty) && item.states.includes(status) && version !== undefined
  );
  const create = entity.create && scope.can(entity.create.duty) ? entity.create : null;
  const show = (row: Row) => {
    setSelection(text(row.id));
    setEditor("");
  };
  return (
    <section className="progressPanel" aria-label={label}>
      <h2>{label}</h2>
      {label === "Equipment References" ? (
        <p>Referencias operacionales al equipo maestro externo; no administra inventario ni activos contables.</p>
      ) : null}
      {label === "Installed Quantity Evidence" ? (
        <p>Es la misma producción instalada verificada, no una medición Progress ni una certificación contractual.</p>
      ) : null}
      {label === "Labor" || label === "Equipment Usage" ? (
        <p>El uso registra horas operacionales; no calcula nómina ni reconoce Actual Cost.</p>
      ) : null}
      <ReadState {...register} retry={scope.reload} />
      {register.data ? (
        <>
          <Records
            label={label}
            items={rows(register.data)}
            columns={[["id", "ID"], ...entity.columns]}
            select={show}
          />
          <Paging
            after={after}
            setAfter={(value) => {
              setAfter(value);
              setSelection("");
            }}
            next={register.data.next_after_id ?? register.data.next_cursor}
          />
        </>
      ) : null}
      {create ? (
        <div className="fieldActions">
          <button
            type="button"
            aria-expanded={editor === "create"}
            onClick={() => setEditor(editor === "create" ? "" : "create")}
          >
            Nuevo registro
          </button>
        </div>
      ) : null}
      {create && editor === "create" ? (
        <FieldCommandForm
          key={`new-${entity.path}`}
          label={create.name}
          spec={create.spec}
          environment={scope}
          busy={scope.busy || register.loading}
          submit={async (body) => {
            const row = await scope.command(entity.path, body);
            if (row) {
              setAfter("");
              show(row);
            }
            return row;
          }}
        />
      ) : null}
      <ReadState {...detail} retry={scope.reload} />
      {current ? (
        <section className="fieldDetail" aria-label="Hecho de campo seleccionado">
          <h3>
            {label} #{text(current.id)}
          </h3>
          <Facts
            values={[
              ["ID", current.id],
              ["Versión", current.version],
              ...entity.columns.map(([key, title]): [string, unknown] => [title, current[key]]),
            ]}
          />
          <ReasonCodes codes={current.reason_codes ?? current.blockers} />
          <Evidence title="Evidencia operacional y referencias fijadas" value={current} />
          <div className="fieldActions">
            {actions.map((item) => (
              <button
                key={item.name}
                type="button"
                disabled={scope.busy || detail.loading}
                aria-expanded={editor === item.name}
                onClick={() => setEditor(editor === item.name ? "" : item.name)}
              >
                {item.name}…
              </button>
            ))}
          </div>
          {actions
            .filter((item) => item.name === editor)
            .map((item) => (
              <FieldCommandForm
                key={item.name}
                label={item.name}
                spec={item.spec ?? {}}
                environment={scope}
                busy={scope.busy || detail.loading}
                submit={async (body) => {
                  const row = await scope.command(
                    `${entity.path}/${selection}${item.endpoint ?? "/actions"}`,
                    { ...body, ...item.body },
                    version
                  );
                  if (row) setEditor("");
                  return row;
                }}
              />
            ))}
        </section>
      ) : null}
    </section>
  );
}

function QueryPanel({ kind, scope }: { kind: string; scope: Scope }) {
  const [workfront, setWorkfront] = useState("");
  const [horizon, setHorizon] = useState(text(scope.profile?.lookahead_days) || "14");
  const [entityType, setEntityType] = useState("");
  const [entityId, setEntityId] = useState("");
  const [after, setAfter] = useState("");
  const readiness = kind === "Field Readiness";
  const history = kind === "History";
  const dashboard = kind === "Field Dashboard";
  const trace = kind === "Trace";
  const [path, setPath] = useState<string | null>(
    readiness || trace ? null : history ? "/history" : dashboard ? "/dashboard" : "/lookahead"
  );
  const result = useRead(
    scope.token,
    scope.base,
    path === null ? null : query(path, { after_id: after, limit: 50 }),
    scope.revision
  );
  const submit = (event: FormEvent) => {
    event.preventDefault();
    setAfter("");
    const next = readiness
      ? positiveId(workfront)
        ? query("/readiness", { workfront_id: workfront })
        : null
      : trace
        ? positiveId(entityId) && entityType
          ? query("/trace", { entity_type: entityType, entity_id: entityId })
          : null
        : history
          ? query("/history", { entity_type: entityType, entity_id: positiveId(entityId) ? entityId : undefined })
          : dashboard
            ? "/dashboard"
            : query("/lookahead", { horizon_days: horizon });
    if (next === path) scope.reload();
    setPath(next);
  };
  const scalarValues = Object.entries(result.data ?? {}).filter(([, value]) =>
    ["string", "number", "boolean"].includes(typeof value)
  );
  return (
    <section className="progressPanel" aria-label={kind}>
      <h2>{kind}</h2>
      {dashboard ? (
        <p>Hechos de ejecución y disponibilidad. No representa avance aprobado, costo reconocido ni liberación AWP.</p>
      ) : null}
      {!dashboard ? (
        <form className="progressForm" onSubmit={submit}>
          {history || trace ? (
            <>
              {trace ? (
                <Select
                  label="Tipo de entidad de campo"
                  value={entityType}
                  onChange={setEntityType}
                  values={["WORKFRONT", "PRODUCTION", "EVENT", "INSTRUCTION", "CONSTRAINT"]}
                  required
                />
              ) : (
                <Input label="Tipo de entidad de campo" value={entityType} onChange={setEntityType} />
              )}
              <Input
                label="ID de entidad de campo"
                value={entityId}
                type="number"
                onChange={setEntityId}
                required={trace}
              />
            </>
          ) : readiness ? (
            <Input label="Frente de trabajo ID" value={workfront} type="number" onChange={setWorkfront} required />
          ) : null}
          {!history && !readiness && !trace ? (
            <Input label="Horizonte de campo días" value={horizon} type="number" onChange={setHorizon} required />
          ) : null}
          <button type="submit">Consultar {kind}</button>
        </form>
      ) : null}
      <ReadState {...result} retry={scope.reload} />
      {result.data ? (
        <>
          <Facts values={scalarValues} />
          {dashboard && isRow(result.data.counts) ? <Facts values={Object.entries(result.data.counts)} /> : null}
          {dashboard && isRow(result.data.verified_production_by_uom) ? (
            <Records
              label="Producción verificada por unidad"
              items={Object.entries(result.data.verified_production_by_uom).map(([uom, quantity]) => ({
                uom,
                quantity,
              }))}
              columns={[
                ["uom", "Unidad"],
                ["quantity", "Cantidad verificada"],
              ]}
            />
          ) : null}
          <ReasonCodes codes={result.data.reason_codes ?? result.data.blockers ?? result.data.missing} />
          {history || readiness ? (
            <Records
              label={kind}
              items={rows(result.data.checks ?? result.data)}
              columns={
                history
                  ? [
                      ["entity_type", "Entidad"],
                      ["entity_id", "ID"],
                      ["entity_version", "Versión"],
                      ["event_type", "Acción"],
                      ["created_by", "Actor"],
                      ["reason", "Motivo"],
                      ["created_at", "Fecha"],
                    ]
                  : readiness
                    ? [
                        ["check", "Comprobación"],
                        ["ready", "Disponible"],
                        ["required", "Requerida"],
                        ["detail", "Detalle"],
                      ]
                    : [
                        ["workfront_id", "Frente"],
                        ["event_type", "Tipo"],
                        ["date", "Fecha"],
                        ["title", "Descripción"],
                        ["status", "Estado"],
                      ]
              }
            />
          ) : null}
          {!history && !readiness && !dashboard && !trace ? (
            <>
              <Records
                label="Frentes del horizonte"
                items={rows(result.data.workfronts)}
                columns={[
                  ["id", "ID"],
                  ["title", "Frente"],
                  ["planned_start", "Inicio previsto"],
                  ["planned_finish", "Fin previsto"],
                  ["status", "Estado"],
                ]}
              />
              <Records
                label="Turnos del horizonte"
                items={rows(result.data.shifts)}
                columns={[
                  ["id", "ID"],
                  ["shift_code", "Turno"],
                  ["shift_date", "Fecha"],
                  ["workfront_id", "Frente"],
                  ["status", "Estado"],
                ]}
              />
              <Records
                label="Eventos del horizonte"
                items={rows(result.data.events)}
                columns={[
                  ["id", "ID"],
                  ["event_code", "Código"],
                  ["event_type", "Tipo"],
                  ["title", "Evento"],
                  ["status", "Estado"],
                ]}
              />
            </>
          ) : null}
          {trace ? (
            <Records
              label="Historial del hecho"
              items={rows(result.data.history)}
              columns={[
                ["entity_type", "Entidad"],
                ["entity_id", "ID"],
                ["entity_version", "Versión"],
                ["event_type", "Acción"],
                ["reason", "Motivo"],
              ]}
            />
          ) : null}
          <Evidence title="Fuentes de la consulta operacional" value={result.data} />
          <Paging after={after} setAfter={setAfter} next={result.data.next_after_id ?? result.data.next_cursor} />
        </>
      ) : null}
    </section>
  );
}

function MappingPanel({ scope }: { scope: Scope }) {
  const [kind, setKind] = useState("");
  const [identity, setIdentity] = useState("");
  const [selection, setSelection] = useState<{ kind: string; id: string } | null>(null);
  const path = query("/mappings", { source_kind: selection?.kind, source_id: selection?.id });
  const result = useRead(scope.token, scope.base, path, scope.revision);
  const version = versionOf(result.data?.version, true);
  return (
    <section className="progressPanel" aria-label="Mappings">
      <h2>Mappings</h2>
      <p>Conserve las identidades canónicas. Un vínculo no modifica el destino.</p>
      <form
        className="progressForm"
        onSubmit={(event) => {
          event.preventDefault();
          if (kind && positiveId(identity)) {
            if (selection?.kind === kind && selection.id === identity) scope.reload();
            setSelection({ kind, id: identity });
          }
        }}
      >
        <Select
          label="Clase de origen del vínculo"
          value={kind}
          onChange={setKind}
          values={["WORKFRONT", "PRODUCTION", "EVENT", "INSTRUCTION", "CONSTRAINT"]}
          required
        />
        <Input label="Origen del vínculo ID" type="number" value={identity} onChange={setIdentity} required />
        <button type="submit">Consultar vínculos de campo</button>
      </form>
      <ReadState {...result} retry={scope.reload} />
      {result.data ? (
        <>
          <Records
            label="Mappings"
            items={rows(result.data)}
            columns={[
              ["id", "ID"],
              ["source_kind", "Origen"],
              ["source_id", "Hecho"],
              ["action", "Decisión"],
              ["version", "Revisión"],
            ]}
          />
          <Evidence title="Referencias canónicas de campo" value={result.data} />
        </>
      ) : null}
      {selection && version !== undefined && scope.can("mapping.edit") ? (
        <FieldCommandForm
          label="Registrar vínculo de campo"
          spec={{
            fields: entities.Mappings.create?.spec.fields?.filter(
              (field) => !["source_kind", "source_id"].includes(field.key)
            ),
          }}
          environment={scope}
          busy={scope.busy || result.loading}
          submit={async (body) =>
            scope.command(
              "/mappings",
              { ...body, source_kind: selection.kind, source_id: Number(selection.id) },
              version
            )
          }
        />
      ) : null}
    </section>
  );
}

export default function FieldOperationsWorkspace({
  token,
  workspaceId,
  readOnly = false,
}: {
  token: string;
  workspaceId: number;
  readOnly?: boolean;
}) {
  const [tab, setTab] = useState<string>("Field Dashboard");
  const base = projectRoot(workspaceId);
  const commands = useCommands(token, base, readOnly);
  const configuration = useRead(token, base, "/configuration", commands.revision);
  const profileRow = isRow(configuration.data?.profile) ? configuration.data.profile : null;
  const profile = isRow(profileRow?.content_json) ? profileRow.content_json : null;
  const allowed = configuration.data?.allowed_actions;
  const canRead = permits(allowed, "read");
  const scope: Scope = {
    ...commands,
    token,
    base,
    workspaceId,
    profile,
    can: (duty) => !readOnly && permits(allowed, duty),
  };
  return (
    <section
      className="progressFoundation fieldOperations"
      aria-label="Field Operations Manager"
      aria-busy={commands.busy}
    >
      <CompactModuleHeader
        title="Field Operations Manager"
        eyebrow="USER MODE · CANONICAL PROJECT · O3A"
        tone="user"
        description="Hechos de ejecución, recursos y evidencia de campo. Progress, AWP, Cost y Contracts mantienen sus decisiones independientes."
        metrics={[
          { label: "Perfil", value: text(profileRow?.code) || "Sin perfil publicado" },
          { label: "Workspace", value: workspaceId },
        ]}
        actions={
          <button type="button" disabled={commands.busy} onClick={commands.reload}>
            Actualizar campo
          </button>
        }
      />
      {readOnly ? <p className="progressNotice">Workspace archivado · hechos de campo de solo lectura.</p> : null}
      <ReadState {...configuration} retry={commands.reload} />
      {commands.error ? (
        <p role="alert" className="progressError">
          {commands.error}
        </p>
      ) : null}
      {commands.message ? <p role="status">{commands.message}</p> : null}
      {configuration.data && !canRead ? <p role="status">La función no está habilitada para este contexto.</p> : null}
      {canRead ? (
        <>
          <p className="fieldBoundary">
            IWP liberado no significa trabajo ejecutado. Producción registrada no significa avance aprobado. Las horas y
            materiales usados no crean costos ni pagos.
          </p>
          <nav className="progressTabs" aria-label="Field Operations Manager submodules">
            {tabs.map((name) => (
              <button type="button" key={name} aria-pressed={name === tab} onClick={() => setTab(name)}>
                {name}
              </button>
            ))}
          </nav>
          {tab === "Consumers" ? (
            <FieldConsumerPanel token={token} workspaceId={workspaceId} readOnly={readOnly} />
          ) : tab === "Mappings" ? (
            <MappingPanel scope={scope} />
          ) : entities[tab] ? (
            <EntityPanel key={tab} label={tab} entity={entities[tab]} scope={scope} />
          ) : (
            <QueryPanel key={tab} kind={tab} scope={scope} />
          )}
        </>
      ) : null}
    </section>
  );
}
