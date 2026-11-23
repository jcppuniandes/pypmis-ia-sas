import { useState, type FormEvent } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { Evidence, Facts, Input, Records, ReasonCodes, Select } from "../progress-foundation/Fields";
import { FieldCommandForm, ReadState } from "../field-operations/FieldForms";
import QualityCommandForm, { SourceControl } from "./QualityForms";
import QualityConsumerPanel from "./QualityConsumerPanel";
import { LotLinksPanel, ReadinessAssessmentPanel } from "./QualitySupportPanels";
import { entities, tabs, type Entity } from "./views";
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
import "../progress-foundation/progressFoundation.css";
import "./quality.css";

function Paging({ next, after, setAfter }: { next: unknown; after: string; setAfter: (value: string) => void }) {
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
  const [selected, setSelected] = useState("");
  const [editor, setEditor] = useState("");
  const list = useRead(scope.token, scope.base, query(entity.path, { limit: 50, after_id: after }), scope.revision);
  const detail = useRead(
    scope.token,
    scope.base,
    selected && entity.details !== false ? `${entity.path}/${selected}` : null,
    scope.revision
  );
  const record = detail.data ?? rows(list.data).find((row) => text(row.id) === selected);
  const records = rows(list.data).filter((row) => !entity.reinspectionOnly || positiveId(row.reinspection_of_id));
  const version = versionOf(record?.version);
  const status = text(record?.status).toUpperCase();
  const actions = (entity.actions ?? []).filter(
    (action) => scope.can(action.duty) && action.states.includes(status) && version !== undefined
  );
  const create = entity.create && scope.can(entity.create.duty) ? entity.create : null;
  const show = (row: Row) => {
    setSelected(text(row.id));
    setEditor("");
  };
  return (
    <section className="progressPanel" aria-label={label}>
      <h2>{label}</h2>
      <ReadState {...list} retry={scope.reload} />
      {list.data ? (
        <>
          <Records label={label} items={records} columns={[["id", "ID"], ...entity.columns]} select={show} />
          <Paging
            next={list.data.next_cursor ?? list.data.next_after_id}
            after={after}
            setAfter={(value) => {
              setAfter(value);
              setSelected("");
            }}
          />
        </>
      ) : null}
      {create ? (
        <button
          type="button"
          aria-expanded={editor === "create"}
          onClick={() => setEditor(editor === "create" ? "" : "create")}
        >
          Nuevo registro Quality
        </button>
      ) : null}
      {create && editor === "create" ? (
        <QualityCommandForm
          key={`new-${entity.path}`}
          label={create.name}
          spec={create.spec}
          environment={scope}
          busy={scope.busy || list.loading}
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
      {record ? (
        <section className="qualityDetail" aria-label="Registro Quality seleccionado">
          <h3>
            {label} #{text(record.id)}
          </h3>
          <Facts
            values={[
              ["ID", record.id],
              ["Versión", record.version],
              ...entity.columns.map(([key, title]): [string, unknown] => [title, record[key]]),
            ]}
          />
          <ReasonCodes codes={record.reason_codes ?? record.blockers} />
          <Evidence title="Quality fuentes y linaje inmutables" value={record} />
          <div className="fieldActions">
            {actions.map((action) => (
              <button
                type="button"
                key={action.name}
                disabled={scope.busy || detail.loading}
                aria-expanded={editor === action.name}
                onClick={() => setEditor(editor === action.name ? "" : action.name)}
              >
                {action.name}…
              </button>
            ))}
          </div>
          {actions
            .filter((action) => action.name === editor)
            .map((action) => (
              <QualityCommandForm
                key={action.name}
                label={action.name}
                spec={action.spec ?? {}}
                environment={scope}
                busy={scope.busy || detail.loading}
                submit={async (body) => {
                  const row = await scope.command(
                    `${entity.path}/${selected}${action.endpoint ?? "/actions"}`,
                    { ...body, ...action.body },
                    version
                  );
                  if (row) {
                    setEditor("");
                    if (action.endpoint === "/successor") show(row);
                  }
                  return row;
                }}
              />
            ))}
        </section>
      ) : null}
    </section>
  );
}

const subjectTypes = [
  "FIELD_PRODUCTION",
  "FIELD_REWORK",
  "FIELD_WORKFRONT",
  "MATERIAL_RECEIPT_LINE",
  "MATERIAL_ACCEPTANCE",
  "MATERIAL_ALLOCATION",
];
function HoldPanel({ scope }: { scope: Scope }) {
  const [item, setItem] = useState("");
  const [pin, setPin] = useState<Row | undefined>();
  const [meta, setMeta] = useState<Row | null>(null);
  const result = useRead(
    scope.token,
    scope.base,
    positiveId(item) && text(meta?.subject_key)
      ? query("/control-point-decisions", { itp_item_id: item, subject_key: text(meta?.subject_key) })
      : null,
    scope.revision
  );
  const version = versionOf(result.data?.version, true);
  return (
    <section className="progressPanel" aria-label="Hold and Witness Decisions">
      <h2>Hold and Witness Decisions</h2>
      <p>La decisión libera el punto ITP; no libera IWP ni cierra restricciones AWP.</p>
      <Input
        label="Punto ITP ID"
        type="number"
        value={item}
        onChange={(value) => {
          setItem(value);
        }}
        required
      />
      <SourceControl
        field={{ key: "subject_reference", label: "Objeto del punto ITP", types: subjectTypes, required: true }}
        value={pin}
        change={(value) => {
          setPin(value);
          setMeta(null);
        }}
        resolved={setMeta}
        environment={scope}
        asOf=""
      />
      <ReadState {...result} retry={scope.reload} />
      {result.data ? (
        <Records
          label="Decisiones de puntos de control"
          items={rows(result.data)}
          columns={[
            ["id", "ID"],
            ["itp_item_id", "Punto"],
            ["decision", "Decisión"],
            ["version", "Versión"],
            ["created_by", "Actor"],
          ]}
        />
      ) : null}
      {pin && positiveId(item) && version !== undefined && scope.can("control.release") ? (
        <FieldCommandForm
          label="Decidir punto de control"
          spec={{
            fields: [
              { key: "decision", label: "Decisión del punto", choices: ["RELEASED", "WAIVED"], required: true },
              { key: "inspection_record_id", label: "Inspección cerrada ID", kind: "id", collection: "/inspections" },
              { key: "test_record_id", label: "Ensayo cerrado ID", kind: "id", collection: "/tests" },
              { key: "document_references", label: "Evidencia CDE", kind: "document", multiple: true, required: true },
            ],
          }}
          environment={scope}
          busy={scope.busy || result.loading}
          submit={(body) =>
            scope.command(
              "/control-point-decisions",
              { ...body, itp_item_id: Number(item), subject_reference: pin },
              version
            )
          }
        />
      ) : null}
    </section>
  );
}

function QueryPanel({ kind, scope }: { kind: string; scope: Scope }) {
  const dashboard = kind === "Quality Dashboard";
  const readiness = kind === "Quality Readiness";
  const trace = kind === "Trace";
  const history = kind === "History";
  const [item, setItem] = useState("");
  const [sourceKind, setSourceKind] = useState(subjectTypes[0]);
  const [sourceId, setSourceId] = useState("");
  const [entityType, setEntityType] = useState("INSPECTION");
  const [identity, setIdentity] = useState("");
  const [horizon, setHorizon] = useState("14");
  const [after, setAfter] = useState("");
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [path, setPath] = useState<string | null>(
    dashboard ? "/dashboard" : history ? "/history" : readiness || trace ? null : "/lookahead"
  );
  const result = useRead(
    scope.token,
    scope.base,
    path === null ? null : query(path, { limit: 50, after_id: after }),
    scope.revision
  );
  const submit = (event: FormEvent) => {
    event.preventDefault();
    setAfter("");
    const next = readiness
      ? query("/readiness", { itp_id: item, source_type: sourceKind, source_id: sourceId })
      : trace
        ? query("/trace", { entity_type: entityType, entity_id: identity })
        : history
          ? query("/history", { entity_type: entityType, entity_id: identity })
          : query("/lookahead", { horizon_days: horizon, ...filters });
    if (next === path) scope.reload();
    setPath(next);
  };
  return (
    <section className="progressPanel" aria-label={kind}>
      <h2>{kind}</h2>
      {!dashboard ? (
        <form className="progressForm" onSubmit={submit}>
          {readiness ? (
            <>
              <Input label="ITP aplicable ID" type="number" value={item} onChange={setItem} required />
              <Select
                label="Tipo de objeto Quality"
                value={sourceKind}
                values={subjectTypes}
                onChange={setSourceKind}
                required
              />
              <Input label="Objeto Quality ID" type="number" value={sourceId} onChange={setSourceId} required />
            </>
          ) : trace || history ? (
            <>
              <Select
                label="Tipo de entidad Quality"
                value={entityType}
                values={[
                  "PLAN",
                  "ITP",
                  "ITP_ITEM",
                  "INSPECTION_REQUEST",
                  "INSPECTION",
                  "TEST_REQUEST",
                  "TEST",
                  "NCR",
                  "DISPOSITION",
                  "CORRECTIVE_ACTION",
                  "ACCEPTANCE",
                  "PUNCH",
                ]}
                onChange={setEntityType}
              />
              <Input
                label="Entidad Quality ID"
                type="number"
                value={identity}
                onChange={setIdentity}
                required={trace}
              />
            </>
          ) : (
            <>
              <Input label="Horizonte Quality días" type="number" value={horizon} onChange={setHorizon} />
              {[
                ["iwp_id", "IWP ID"],
                ["cwp_id", "CWP ID"],
                ["workfront_id", "Workfront ID"],
                ["discipline", "Disciplina"],
                ["vendor_id", "Vendor ID"],
                ["inspector_user_id", "Inspector ID"],
                ["status", "Estado"],
                ["date_from", "Desde fecha"],
                ["date_to", "Hasta fecha"],
                ["location", "Ubicación"],
              ].map(([key, label]) => (
                <Input
                  key={key}
                  label={label}
                  type={key.startsWith("date_") ? "date" : "text"}
                  value={filters[key] ?? ""}
                  onChange={(value) => setFilters((old) => ({ ...old, [key]: value }))}
                />
              ))}
            </>
          )}
          <button type="submit">Consultar {kind}</button>
        </form>
      ) : null}
      <ReadState {...result} retry={scope.reload} />
      {result.data ? (
        <>
          <Facts
            values={Object.entries(result.data).filter(([, value]) =>
              ["string", "number", "boolean"].includes(typeof value)
            )}
          />
          <ReasonCodes codes={result.data.reason_codes ?? result.data.blockers} />
          {readiness ? (
            <Records
              label="Controles Quality"
              items={rows(result.data.items).map((item) => ({
                ...item,
                state: Array.isArray(item.issues) && item.issues.length ? "PENDIENTE" : "CUMPLE",
              }))}
              columns={[
                ["itp_item_id", "Punto ITP"],
                ["state", "Estado"],
                ["required", "Requerido"],
                ["control_type", "Control"],
              ]}
            />
          ) : history || trace ? (
            <Records
              label="Historial Quality"
              items={rows(history ? result.data : result.data.history)}
              columns={[
                ["entity_type", "Entidad"],
                ["entity_id", "ID"],
                ["entity_version", "Versión"],
                ["event_type", "Acción"],
                ["created_by", "Actor"],
                ["reason", "Motivo"],
              ]}
            />
          ) : (
            Object.entries(result.data)
              .filter(([, value]) => Array.isArray(value))
              .map(([key, value]) => (
                <Records
                  key={key}
                  label={key}
                  items={rows(value)}
                  columns={[
                    ["id", "ID"],
                    ["request_number", "Solicitud"],
                    ["title", "Título"],
                    ["status", "Estado"],
                    ["due_date", "Vencimiento"],
                  ]}
                />
              ))
          )}
          <Evidence title="Fuentes Quality de la consulta" value={result.data} />
          <Paging next={result.data.next_cursor ?? result.data.next_after_id} after={after} setAfter={setAfter} />
        </>
      ) : null}
    </section>
  );
}

export default function QualityManagerWorkspace({
  token,
  workspaceId,
  readOnly = false,
}: {
  token: string;
  workspaceId: number;
  readOnly?: boolean;
}) {
  const [tab, setTab] = useState("Quality Dashboard");
  const base = projectRoot(workspaceId);
  const commands = useCommands(token, base, readOnly);
  const configuration = useRead(token, base, "/configuration", commands.revision);
  const record = isRow(configuration.data?.profile) ? configuration.data.profile : null;
  const profile = isRow(record?.content_json) ? record.content_json : null;
  const allowed = configuration.data?.allowed_actions;
  const scope: Scope = {
    ...commands,
    token,
    base,
    workspaceId,
    profile,
    can: (duty) => !readOnly && permits(allowed, duty),
  };
  return (
    <section className="progressFoundation qualityManager" aria-label="Quality Manager">
      <CompactModuleHeader
        title="Quality Manager"
        eyebrow="USER MODE · CANONICAL PROJECT · O3B"
        description="Inspecciones, ensayos, no conformidades y aceptación de calidad. Cada dominio conserva su autoridad."
        tone="user"
        metrics={[
          { label: "Perfil", value: text(record?.code) || "Sin perfil publicado" },
          { label: "Workspace", value: workspaceId },
        ]}
        actions={
          <button type="button" disabled={commands.busy} onClick={commands.reload}>
            Actualizar Quality
          </button>
        }
      />
      {readOnly ? <p>Workspace archivado · Quality de solo lectura.</p> : null}
      <ReadState {...configuration} retry={commands.reload} />
      {commands.error ? (
        <p role="alert" className="progressError">
          {commands.error}
        </p>
      ) : null}
      {commands.message ? <p role="status">{commands.message}</p> : null}
      {permits(allowed, "read") ? (
        <>
          <p className="qualityBoundary">
            Trabajo ejecutado no significa calidad aceptada. PASS no aprueba Progress, no libera AWP y no crea
            certificados ni costos.
          </p>
          <nav className="progressTabs" aria-label="Quality Manager submodules">
            {tabs.map((name) => (
              <button type="button" key={name} aria-pressed={name === tab} onClick={() => setTab(name)}>
                {name}
              </button>
            ))}
          </nav>
          {entities[tab] ? (
            <EntityPanel key={tab} label={tab} entity={entities[tab]} scope={scope} />
          ) : tab === "Consumers" ? (
            <QualityConsumerPanel token={token} workspaceId={workspaceId} readOnly={readOnly} />
          ) : tab === "Hold and Witness Decisions" ? (
            <HoldPanel scope={scope} />
          ) : tab === "Material Lot Traceability" ? (
            <LotLinksPanel scope={scope} />
          ) : tab === "Readiness Evidence Assessments" ? (
            <ReadinessAssessmentPanel scope={scope} />
          ) : (
            <QueryPanel key={tab} kind={tab} scope={scope} />
          )}
        </>
      ) : null}
    </section>
  );
}
