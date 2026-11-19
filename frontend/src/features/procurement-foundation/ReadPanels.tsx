import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Evidence, Facts, Input, ReasonCodes, Records, Select } from "../progress-foundation/Fields";
import { isRow, query, rows, text, useProcurementRead, version, type ProcurementRow } from "./api";
import { CommandForm, Pager, ReadState, type ProcurementScope } from "./Panels";

const columnLabels: Record<string, string> = {
  id: "ID",
  code: "Código",
  package_code: "Código",
  package_id: "Paquete",
  title: "Título",
  status: "Estado",
  version: "Versión",
  due_date: "Vencimiento",
  date: "Fecha",
  event_type: "Evento",
  vendor_id: "Proveedor",
  action: "Acción",
  entity_type: "Entidad",
  entity_id: "ID entidad",
  reason: "Motivo",
  actor_id: "Actor",
  created_at: "Registro",
  required_quantity: "Requerida",
  ordered_quantity: "Ordenada",
  shipped_quantity: "Expedida",
  received_quantity: "Recibida",
  accepted_quantity: "Aceptada",
  reserved_quantity: "Reservada",
  allocated_quantity: "Asignada",
  available_quantity: "Disponible",
  uom: "UOM",
  required_on_site_date: "Necesario en sitio",
  material_requirement_id: "Requisito físico",
  target_id: "ID destino",
  target_kind: "Tipo destino",
  source_kind: "Tipo de origen",
  source_id: "ID origen",
  effective_date: "Vigencia",
};
const displayKey = (key: string) => columnLabels[key] ?? key.replace(/_/g, " ");
const scalar = (value: unknown) => typeof value === "number" || typeof value === "string" || typeof value === "boolean";

function ProjectionTable({ label, items }: { label: string; items: ProcurementRow[] }) {
  const keys = [...new Set(items.flatMap((row) => Object.keys(row).filter((key) => scalar(row[key]))))].slice(0, 14);
  return (
    <Records
      label={label}
      items={items}
      columns={(keys.length ? keys : ["id", "status"]).map((key) => [key, displayKey(key)])}
    />
  );
}

function Projection({ data, title }: { data: ProcurementRow; title: string }) {
  const summaries = Object.entries(data)
    .filter(([key, value]) => scalar(value) && !["next_cursor", "next_after_id"].includes(key))
    .slice(0, 24);
  const nested = Object.entries(data).filter(([key, value]) => isRow(value) && !["filters"].includes(key));
  return (
    <>
      {summaries.length ? <Facts values={summaries.map(([key, value]) => [displayKey(key), value])} /> : null}
      {Object.entries(data)
        .filter(([key, value]) => key !== "allowed_actions" && Array.isArray(value) && value.some(isRow))
        .map(([key, value]) => (
          <div key={key}>
            <h4>{key === "items" ? title : displayKey(key)}</h4>
            <ProjectionTable label={key === "items" ? title : displayKey(key)} items={rows(value)} />
          </div>
        ))}
      {nested.map(([key, value]) => {
        const facts = Object.entries(value as ProcurementRow)
          .filter(([, item]) => scalar(item))
          .slice(0, 18);
        const tables = Object.entries(value as ProcurementRow).filter(
          ([, item]) => Array.isArray(item) && item.some(isRow)
        );
        return facts.length || tables.length ? (
          <div key={key}>
            <h4>{displayKey(key)}</h4>
            {facts.length ? <Facts values={facts.map(([name, item]) => [displayKey(name), item])} /> : null}
            {tables.map(([label, items]) => (
              <ProjectionTable key={label} label={displayKey(label)} items={rows(items)} />
            ))}
          </div>
        ) : null;
      })}
      <ReasonCodes codes={data.reason_codes ?? data.reasons} />
      <Evidence title="Fuentes, referencias y huellas de esta lectura" value={data} />
    </>
  );
}

type QueryView = "Procurement Register" | "Procurement Look-Ahead" | "History";
const projections: Record<QueryView, string> = {
  "Procurement Register": "/status",
  "Procurement Look-Ahead": "/lookahead",
  History: "/history",
};
const utcDate = () => new Date().toISOString().slice(0, 10);
export function QueryPanel({ scope, view }: { scope: ProcurementScope; view: QueryView }) {
  const lookahead = view === "Procurement Look-Ahead";
  const history = view === "History";
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [applied, setApplied] = useState<Record<string, string>>({});
  const [cursors, setCursors] = useState<string[]>([]);
  const [traceId, setTraceId] = useState("");
  const [selectedTrace, setSelectedTrace] = useState("");
  const values = (key: string) => filters[key] ?? "";
  const update = (key: string) => (value: string) => setFilters((current) => ({ ...current, [key]: value }));
  const request = useProcurementRead(
    scope.token,
    scope.base,
    query(projections[view], {
      ...applied,
      limit: 50,
      after_id: cursors[cursors.length - 1],
    }),
    scope.revision
  );
  const trace = useProcurementRead(
    scope.token,
    scope.base,
    selectedTrace ? query("/trace", { package_id: selectedTrace }) : null,
    scope.revision
  );
  function filter(event: FormEvent) {
    event.preventDefault();
    setApplied(filters);
    setCursors([]);
  }
  return (
    <section className="progressPanel" aria-label={`Consulta ${view}`}>
      <h3>{view}</h3>
      <p>
        {history
          ? "Historial de comandos, versiones y referencias de fuente."
          : "Proyección del estado real, de solo lectura."}
      </p>
      <form className="progressForm" onSubmit={filter}>
        <Input
          label="ID de paquete Procurement"
          value={values("package_id")}
          onChange={update("package_id")}
          type="number"
        />
        {lookahead ? (
          <>
            <Input
              label="Horizonte (días)"
              value={values("horizon_days")}
              onChange={update("horizon_days")}
              type="number"
            />
            <Input label="Desde" value={values("start")} onChange={update("start")} type="date" />
            <Input label="Hasta" value={values("end")} onChange={update("end")} type="date" />
            <Select
              label="Tipo de paquete AWP"
              value={values("target_kind")}
              onChange={update("target_kind")}
              values={["PWP", "CWP", "IWP"]}
              required={Boolean(values("target_id"))}
            />
            <Input
              label="ID del paquete AWP"
              value={values("target_id")}
              onChange={update("target_id")}
              type="number"
              required={Boolean(values("target_kind"))}
            />
            <Input label="ID de proveedor" value={values("vendor_id")} onChange={update("vendor_id")} type="number" />
            <Input
              label="ID del responsable"
              value={values("responsible_id")}
              onChange={update("responsible_id")}
              type="number"
            />
            <Input label="Categoría" value={values("category")} onChange={update("category")} />
            <Input label="Disciplina" value={values("discipline")} onChange={update("discipline")} />
            <Input label="Estado" value={values("status")} onChange={update("status")} />
          </>
        ) : null}
        <button type="submit" disabled={request.loading}>
          Aplicar filtros
        </button>
      </form>
      <ReadState {...request} reload={scope.reload} />
      {request.value && !request.error ? (
        <>
          <Projection data={request.value} title={view} />
          <Pager
            cursors={cursors}
            setCursors={setCursors}
            next={text(request.value.next_after_id ?? request.value.next_cursor)}
            disabled={request.loading}
          />
        </>
      ) : null}
      {view === "Procurement Register" ? (
        <>
          <h4>Trazabilidad de un paquete</h4>
          <form
            className="progressForm"
            onSubmit={(event) => {
              event.preventDefault();
              setSelectedTrace(traceId);
            }}
          >
            <Input label="Paquete para trazabilidad" value={traceId} onChange={setTraceId} type="number" required />
            <button type="submit">Consultar trazabilidad</button>
          </form>
          <ReadState {...trace} reload={scope.reload} />
          {trace.value && !trace.error ? <Projection data={trace.value} title="Trazabilidad Procurement" /> : null}
        </>
      ) : null}
    </section>
  );
}

export function AvailabilityPanel({ scope, workspaceId }: { scope: ProcurementScope; workspaceId: number }) {
  const [workPackageId, setWorkPackageId] = useState("");
  const [packageId, setPackageId] = useState("");
  const [asOf, setAsOf] = useState(utcDate);
  const [availabilityQuery, setAvailabilityQuery] = useState<string | null>(null);
  const [readinessQuery, setReadinessQuery] = useState<string | null>(null);
  const availability = useProcurementRead(scope.token, scope.base, availabilityQuery, scope.revision);
  const readiness = useProcurementRead(scope.token, scope.base, readinessQuery, scope.revision);
  return (
    <section className="progressPanel" aria-label="Disponibilidad y Readiness">
      <h3>Material Availability</h3>
      <p>Evalúa cantidades físicas por destino y fecha de corte. No emite una liberación AWP.</p>
      <form
        className="progressForm"
        onSubmit={(e) => {
          e.preventDefault();
          setAvailabilityQuery(query("/material-availability", { work_package_id: workPackageId, as_of: asOf }));
        }}
      >
        <Input
          label="ID del CWP o IWP para disponibilidad"
          value={workPackageId}
          onChange={setWorkPackageId}
          type="number"
          required
        />
        <Input label="Fecha de corte de disponibilidad" value={asOf} onChange={setAsOf} type="date" required />
        <button type="submit" disabled={availability.loading}>
          Consultar disponibilidad
        </button>
      </form>
      <ReadState {...availability} reload={scope.reload} />
      {availability.value && !availability.error ? (
        <Projection data={availability.value} title="Disponibilidad de materiales" />
      ) : null}
      <h4>Procurement Readiness</h4>
      <form
        className="progressForm"
        onSubmit={(e) => {
          e.preventDefault();
          setReadinessQuery(query("/readiness", { package_id: packageId }));
        }}
      >
        <Input
          label="ID del paquete para Procurement Readiness"
          value={packageId}
          onChange={setPackageId}
          type="number"
          required
        />
        <button type="submit" disabled={readiness.loading}>
          Consultar preparación de Procurement
        </button>
      </form>
      <ReadState {...readiness} reload={scope.reload} />
      {readiness.value && !readiness.error ? <Projection data={readiness.value} title="Procurement Readiness" /> : null}
      <Link to={`/workspaces/${workspaceId}/awp`}>Consultar AWP Readiness y liberación independiente</Link>
    </section>
  );
}

const sourceKinds = ["PACKAGE", "REQUIREMENT", "MATERIAL_REQUIREMENT", "MATERIAL_ITEM", "RECEIPT", "ALLOCATION"];
const targetKinds = [
  "PWP",
  "CWP",
  "IWP",
  "EWP",
  "CWA",
  "SCOPE",
  "PLAN",
  "CBS",
  "COST_CODE",
  "CONTROL_ACCOUNT",
  "WBS",
  "ACTIVITY",
  "MILESTONE",
  "ENGINEERING_DELIVERABLE",
  "ENGINEERING_REVISION",
  "IFC_RELEASE",
  "DESIGN_PACKAGE",
];
export function MappingsPanel({ scope }: { scope: ProcurementScope }) {
  const [sourceKind, setSourceKind] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [targetKind, setTargetKind] = useState("");
  const [scheduleVersion, setScheduleVersion] = useState("");
  const [source, setSource] = useState<{ kind: string; id: string } | null>(null);
  const [target, setTarget] = useState<{ kind: string; schedule: string } | null>(null);
  const [cursors, setCursors] = useState<string[]>([]);
  const mappings = useProcurementRead(
    scope.token,
    scope.base,
    query("/mappings", {
      source_kind: source?.kind,
      source_id: source?.id,
      limit: 50,
      after_id: cursors[cursors.length - 1],
    }),
    scope.revision
  );
  const targets = useProcurementRead(
    scope.token,
    scope.base,
    target
      ? query("/mapping-targets", {
          target_kind: target.kind,
          schedule_version_id: target.schedule,
        })
      : null,
    scope.revision
  );
  const mappingVersion = version(mappings.value);
  const canMap = scope.can("mapping.manage") || scope.can("mapping.edit");
  return (
    <section className="progressPanel" aria-label="Relaciones de Procurement">
      <h3>Mappings</h3>
      <p>Los vínculos registran identidades exactas, nunca nombres. Una baja conserva el historial.</p>
      <form
        className="progressForm"
        onSubmit={(e) => {
          e.preventDefault();
          setSource({ kind: sourceKind, id: sourceId });
          setCursors([]);
        }}
      >
        <Select label="Tipo de origen" value={sourceKind} onChange={setSourceKind} values={sourceKinds} required />
        <Input label="ID de origen" value={sourceId} onChange={setSourceId} type="number" required />
        <button type="submit" disabled={mappings.loading}>
          Consultar vínculos del origen
        </button>
      </form>
      <ReadState {...mappings} reload={scope.reload} />
      {mappings.value && !mappings.error ? (
        <Projection data={mappings.value} title="Relaciones de Procurement" />
      ) : null}
      <Pager
        cursors={cursors}
        setCursors={setCursors}
        next={text(mappings.value?.next_after_id ?? mappings.value?.next_cursor)}
        disabled={mappings.loading}
      />
      <form
        className="progressForm"
        onSubmit={(e) => {
          e.preventDefault();
          setTarget({ kind: targetKind, schedule: scheduleVersion });
        }}
      >
        <Select
          label="Consultar tipo de destino"
          value={targetKind}
          onChange={setTargetKind}
          values={targetKinds}
          required
        />
        <Input
          label="Versión P6 aceptada del destino"
          value={scheduleVersion}
          onChange={setScheduleVersion}
          type="number"
        />
        <button type="submit" disabled={targets.loading}>
          Consultar destinos válidos
        </button>
      </form>
      <ReadState {...targets} reload={scope.reload} />
      {targets.value && !targets.error ? <Projection data={targets.value} title="Destinos autorizados" /> : null}
      {source && canMap && mappingVersion !== undefined && !mappings.error ? (
        <CommandForm
          key={`${source.kind}-${source.id}-${mappingVersion}`}
          label="Registrar vínculo"
          busy={scope.busy || mappings.loading}
          profile={scope.profile}
          spec={{
            fields: [
              { key: "target_kind", label: "Tipo de destino del vínculo", choices: targetKinds, required: true },
              { key: "target_id", label: "ID de destino del vínculo", type: "number" },
              { key: "schedule_version_id", label: "Versión P6 aceptada", type: "number" },
              { key: "external_id", label: "ID externo P6" },
              { key: "source_hash", label: "Hash de la fuente" },
              { key: "action", label: "Acción del vínculo", choices: ["SET", "REMOVE"], required: true },
              {
                key: "effective_date",
                label: "Fecha efectiva del vínculo",
                type: "date",
                required: true,
                initial: utcDate(),
              },
            ],
          }}
          submit={(body) =>
            scope.command(
              "/mappings",
              { ...body, source_kind: source.kind, source_id: Number(source.id) },
              mappingVersion
            )
          }
        />
      ) : null}
    </section>
  );
}
