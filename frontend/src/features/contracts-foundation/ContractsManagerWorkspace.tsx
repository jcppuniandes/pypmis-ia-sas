import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { Evidence, Facts, Input, ReasonCodes, Records, Select } from "../progress-foundation/Fields";
import "../progress-foundation/progressFoundation.css";
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
import { CommandForm, ReadState } from "./ContractForms";
import { entities, statuses, tabs, type Entity, type Tab } from "./views";
import "./contractsFoundation.css";

function useCollection(scope: Scope, path: string | null, afterId: string) {
  return useRead(
    scope.token,
    scope.base,
    path === null ? null : query(path, { limit: 50, after_id: afterId }),
    scope.revision
  );
}

function Paging({
  afterId,
  setAfterId,
  next,
}: {
  afterId: string;
  setAfterId: (value: string) => void;
  next: unknown;
}) {
  return afterId || positiveId(next) ? (
    <div className="contractActions">
      {afterId ? (
        <button type="button" onClick={() => setAfterId("")}>
          Primera página
        </button>
      ) : null}
      {positiveId(next) ? (
        <button type="button" onClick={() => setAfterId(text(next))}>
          Página siguiente
        </button>
      ) : null}
    </div>
  ) : null;
}

function useDetails(scope: Scope, path: string | null) {
  return useRead(scope.token, scope.base, path, scope.revision);
}

function RecordDetail({
  label,
  row,
  columns,
  workspaceId,
}: {
  label: string;
  row: Row;
  columns: Entity["columns"];
  workspaceId: number;
}) {
  const details = Object.fromEntries(Object.entries(row).filter(([, value]) => value !== null && value !== undefined));
  return (
    <section className="contractDetail" aria-label="Detalle contractual">
      <h3>
        {label} · #{text(row.id)}
      </h3>
      <Facts
        values={[
          ["ID", row.id],
          ["Revisión", row.version],
          ...columns.filter(([key]) => key !== "id").map(([key, name]): [string, unknown] => [name, row[key]]),
        ]}
      />
      {label === "Commercial Commitments" && row.status === "APPROVED" && positiveId(row.id) ? (
        <Link to={`/workspaces/${workspaceId}/cost?commercial_commitment_id=${text(row.id)}`}>
          Consultar adopción comercial en Cost
        </Link>
      ) : null}
      {label === "Contracts" || label === "Contract Packages" ? (
        <Link to={`/workspaces/${workspaceId}/procurement`}>Consultar fuente en Procurement</Link>
      ) : null}
      {rows(row.lines).length ? (
        <Records
          label="Líneas y trazabilidad"
          items={rows(row.lines)}
          columns={[
            ["id", "ID"],
            ["line_number", "Línea"],
            ["description", "Descripción"],
            ["quantity", "Cantidad"],
            ["sov_line_id", "SOV (ID)"],
            ["application_line_id", "Solicitud (línea)"],
            ["net_amount", "Importe neto"],
          ]}
        />
      ) : null}
      <ReasonCodes codes={row.reason_codes ?? row.blockers} />
      <Evidence title="Evidencia, huellas y referencias versionadas" value={details} />
    </section>
  );
}

function ContractTrace({ scope, identity }: { scope: Scope; identity: string }) {
  const [open, setOpen] = useState(false);
  const trace = useDetails(scope, open ? `/trace/${identity}` : null);
  return (
    <section className="contractDetail" aria-label="Trazabilidad contractual">
      <button aria-expanded={open} type="button" onClick={() => setOpen(!open)}>
        {open ? "Cerrar trazabilidad" : "Consultar trazabilidad contractual"}
      </button>
      <ReadState {...trace} retry={scope.reload} />
      {trace.data ? (
        <>
          <Facts
            values={[
              ["Versiones", rows(trace.data.versions).length],
              ["Compromisos", rows(trace.data.commitments).length],
              ["Valorizaciones", rows(trace.data.sovs).length],
              ["Solicitudes", rows(trace.data.applications).length],
              ["Certificados", rows(trace.data.certificates).length],
            ]}
          />
          <Evidence title="Cadena contractual, referencias de origen y decisiones" value={trace.data} />
        </>
      ) : null}
    </section>
  );
}

function EntityPanel({ entity, label, scope }: { entity: Entity; label: string; scope: Scope }) {
  const [selected, setSelected] = useState("");
  const [afterId, setAfterId] = useState("");
  const [editor, setEditor] = useState("");
  const [contractFilter, setContractFilter] = useState("");
  const collectionPath =
    label === "Contract Versions" ? query(entity.path, { contract_id: contractFilter }) : entity.path;
  const register = useCollection(scope, collectionPath, afterId);
  const hasDetail = entity.details !== false && Boolean(selected);
  const detail = useDetails(scope, hasDetail ? `${entity.path}/${selected}` : null);
  const current =
    detail.data ?? (!hasDetail ? rows(register.data).find((item) => text(item.id) === selected) : undefined);
  const currentVersion = versionOf(current?.version);
  const commands = (entity.actions ?? []).filter(
    (action) =>
      currentVersion !== undefined &&
      action.states.includes(text(current?.status).toUpperCase()) &&
      scope.can(action.duty) &&
      (!Array.isArray(current?.allowed_actions) ||
        permits(current.allowed_actions, action.duty) ||
        current.allowed_actions.includes(action.body?.action))
  );
  const create = entity.create;
  const mayCreate = create && scope.can(create.duty);
  const choose = (row: Row) => {
    setEditor("");
    setSelected(positiveId(row.id) ? text(row.id) : "");
  };
  return (
    <section className="progressPanel" aria-label={label}>
      <h2>{label}</h2>
      {label === "Finance References" ? (
        <p>Solo referencias externas; no crea facturas, pagos ni contabilizaciones.</p>
      ) : null}
      {label === "Contract Versions" ? (
        <Input
          label="Filtrar por contrato (ID)"
          type="number"
          value={contractFilter}
          onChange={(value) => {
            setContractFilter(value);
            setAfterId("");
            setSelected("");
          }}
        />
      ) : null}
      <ReadState {...register} retry={scope.reload} />
      {register.data && !register.error ? (
        <>
          <Records
            label={label}
            items={rows(register.data)}
            columns={[["id", "ID"], ...entity.columns]}
            select={choose}
          />
          <Paging afterId={afterId} setAfterId={setAfterId} next={register.data.next_after_id} />
        </>
      ) : null}
      {mayCreate ? (
        <div className="contractActions">
          <button
            type="button"
            aria-expanded={editor === "create"}
            onClick={() => setEditor(editor === "create" ? "" : "create")}
          >
            Nuevo registro
          </button>
        </div>
      ) : null}
      {mayCreate && editor === "create" ? (
        <CommandForm
          label={create.name}
          spec={create.spec}
          environment={scope}
          busy={scope.busy || register.loading}
          submit={async (body) => {
            const result = await scope.command(entity.path, body, create.initialVersion);
            if (result) {
              setAfterId("");
              choose(result);
            }
            return result;
          }}
        />
      ) : null}
      <ReadState {...detail} retry={scope.reload} />
      {current ? (
        <RecordDetail label={label} row={current} columns={entity.columns} workspaceId={scope.workspaceId} />
      ) : null}
      {current && label === "Contracts" ? <ContractTrace key={selected} scope={scope} identity={selected} /> : null}
      {commands.length ? (
        <div className="contractActions">
          {commands.map((item) => (
            <button
              key={item.name}
              type="button"
              aria-expanded={editor === item.name}
              disabled={scope.busy || detail.loading}
              onClick={() => setEditor(editor === item.name ? "" : item.name)}
            >
              {item.name}…
            </button>
          ))}
        </div>
      ) : null}
      {commands
        .filter((item) => item.name === editor)
        .map((item) => (
          <CommandForm
            key={item.name}
            label={item.name}
            spec={item.spec ?? {}}
            environment={scope}
            busy={scope.busy || detail.loading}
            submit={async (body) => {
              const result = await scope.command(
                `${entity.path}/${selected}${item.endpoint ?? "/actions"}`,
                { ...body, ...item.body },
                currentVersion
              );
              if (result) setEditor("");
              return result;
            }}
          />
        ))}
    </section>
  );
}

function LookupPanel({
  kind,
  scope,
}: {
  kind: "Contract Readiness" | "Commercial Look-Ahead" | "History";
  scope: Scope;
}) {
  const [contractId, setContractId] = useState("");
  const [horizon, setHorizon] = useState("30");
  const [status, setStatus] = useState("");
  const [entityType, setEntityType] = useState("");
  const [entityId, setEntityId] = useState("");
  const [path, setPath] = useState<string | null>(
    kind === "Contract Readiness" ? null : kind === "History" ? "/history" : "/lookahead"
  );
  const [afterId, setAfterId] = useState("");
  const result = useCollection(scope, path, afterId);
  const isReadiness = kind === "Contract Readiness";
  const isHistory = kind === "History";
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const next = isReadiness
      ? positiveId(contractId)
        ? `/readiness/${contractId}`
        : null
      : isHistory
        ? query("/history", { entity_type: entityType, entity_id: positiveId(entityId) ? entityId : undefined })
        : query("/lookahead", {
            horizon_days: horizon,
            status,
            contract_id: positiveId(contractId) ? contractId : undefined,
          });
    setAfterId("");
    if (path === next) scope.reload();
    setPath(next);
  };
  return (
    <section className="progressPanel" aria-label={kind}>
      <h2>{kind}</h2>
      <form className="progressForm" onSubmit={submit}>
        {isHistory ? (
          <>
            <Input label="Tipo de entidad" value={entityType} onChange={setEntityType} />
            <Input label="Entidad (ID)" value={entityId} onChange={setEntityId} type="number" />
          </>
        ) : (
          <Input
            label="Contrato (ID)"
            type="number"
            value={contractId}
            onChange={setContractId}
            required={isReadiness}
          />
        )}
        {!isReadiness && !isHistory ? (
          <>
            <Input label="Horizonte (días)" type="number" value={horizon} onChange={setHorizon} required />
            <Input label="Estado de evento" value={status} onChange={setStatus} />
          </>
        ) : null}
        <button type="submit">Consultar {kind}</button>
      </form>
      <ReadState {...result} retry={scope.reload} />
      {result.data && !result.error ? (
        isReadiness ? (
          <>
            <Facts
              values={[
                ["Contrato", result.data.contract_id],
                ["Preparación", result.data.readiness_status ?? result.data.status],
                ["Versión", result.data.contract_version_id],
              ]}
            />
            <ReasonCodes codes={result.data.reason_codes ?? result.data.blockers} />
            <Records
              label="Comprobaciones de preparación"
              items={rows(result.data.checks)}
              columns={[
                ["code", "Comprobación"],
                ["status", "Estado"],
                ["required", "Requerida"],
              ]}
            />
            <Evidence title="Evidencia de preparación contractual" value={result.data} />
          </>
        ) : (
          <>
            <Records
              label={kind}
              items={rows(result.data)}
              columns={
                isHistory
                  ? [
                      ["entity_type", "Entidad"],
                      ["entity_id", "ID"],
                      ["event_type", "Evento"],
                      ["entity_version", "Revisión"],
                      ["reason", "Motivo"],
                      ["created_by", "Actor"],
                      ["created_at", "Fecha"],
                    ]
                  : [
                      ["event_type", "Tipo"],
                      ["contract_id", "Contrato"],
                      ["due_date", "Fecha prevista"],
                      ["title", "Evento"],
                      statuses,
                    ]
              }
            />
            <Evidence
              title={isHistory ? "Evidencia de auditoría" : "Fuentes de fechas y alertas"}
              value={result.data}
            />
            <Paging afterId={afterId} setAfterId={setAfterId} next={result.data.next_after_id} />
          </>
        )
      ) : null}
    </section>
  );
}

function MappingPanel({ scope }: { scope: Scope }) {
  const entity: Entity = entities.Mappings;
  const [kind, setKind] = useState("");
  const [identity, setIdentity] = useState("");
  const [selected, setSelected] = useState<{ kind: string; id: string } | null>(null);
  const [afterId, setAfterId] = useState("");
  const lookup = useCollection(
    scope,
    query(entity.path, { source_kind: selected?.kind, source_id: selected?.id }),
    afterId
  );
  const version = versionOf(lookup.data?.version, true);
  return (
    <section className="progressPanel" aria-label="Mappings">
      <h2>Mappings</h2>
      <p>
        Consulte el origen antes de registrar un vínculo. Cada decisión mantiene su revisión y su referencia de origen.
      </p>
      <form
        className="progressForm"
        onSubmit={(event) => {
          event.preventDefault();
          if (!kind || !positiveId(identity)) return;
          setAfterId("");
          if (selected?.kind === kind && selected.id === identity) scope.reload();
          setSelected({ kind, id: identity });
        }}
      >
        <Select
          label="Clase de origen"
          value={kind}
          onChange={setKind}
          values={["CONTRACT_PACKAGE", "CONTRACT"]}
          required
        />
        <Input label="Origen (ID)" value={identity} onChange={setIdentity} type="number" required />
        <button type="submit">Consultar vínculos</button>
      </form>
      <ReadState {...lookup} retry={scope.reload} />
      {lookup.data ? (
        <>
          <Records
            label="Mappings"
            items={rows(lookup.data)}
            columns={[["id", "ID"], ...entity.columns, ["action", "Decisión"], ["version", "Revisión"]]}
          />
          <Evidence title="Fuentes de vínculos" value={lookup.data.items} />
          <Paging afterId={afterId} setAfterId={setAfterId} next={lookup.data.next_after_id} />
        </>
      ) : null}
      {entity.create &&
      scope.can("mapping.edit") &&
      selected &&
      selected.kind === kind &&
      selected.id === identity &&
      version !== undefined ? (
        <CommandForm
          key={`${selected.kind}:${selected.id}`}
          label={entity.create.name}
          spec={entity.create.spec}
          environment={scope}
          busy={scope.busy || lookup.loading}
          submit={(body) =>
            scope.command(entity.path, { ...body, source_kind: selected.kind, source_id: Number(selected.id) }, version)
          }
        />
      ) : null}
    </section>
  );
}

export default function ContractsManagerWorkspace({
  token,
  workspaceId,
  readOnly = false,
}: {
  token: string;
  workspaceId: number;
  readOnly?: boolean;
}) {
  const [tab, setTab] = useState<Tab>("Contract Packages");
  const base = projectRoot(workspaceId);
  const commands = useCommands(token, base, readOnly);
  const configuration = useRead(token, base, "/configuration", commands.revision);
  const configurationRow = isRow(configuration.data?.profile) ? configuration.data.profile : null;
  const profile = isRow(configurationRow?.content_json) ? configurationRow.content_json : null;
  const allowed = configuration.data?.allowed_actions;
  const scope: Scope = {
    ...commands,
    token,
    base,
    workspaceId,
    profile,
    can: (duty) => !readOnly && permits(allowed, duty),
  };
  const mayRead = permits(allowed, "read");
  return (
    <section
      className="progressFoundation contractsFoundation"
      aria-label="Contracts Manager"
      aria-busy={commands.busy}
    >
      <CompactModuleHeader
        title="Contracts Manager"
        eyebrow="USER MODE · CANONICAL PROJECT · O2C"
        tone="user"
        description="Contratos, obligaciones comerciales, valorización, avisos y reclamaciones del Project. La firma legal y el pago no se realizan aquí."
        metrics={[
          { label: "Perfil", value: text(configurationRow?.code) || "Sin perfil publicado" },
          { label: "Workspace", value: workspaceId },
        ]}
        actions={
          <button type="button" disabled={commands.busy} onClick={commands.reload}>
            Actualizar contratos
          </button>
        }
      />
      {readOnly ? <p className="progressNotice">Workspace archivado · contratos de solo lectura.</p> : null}
      <ReadState {...configuration} retry={commands.reload} />
      {commands.error ? (
        <p role="alert" className="progressError">
          {commands.error}
        </p>
      ) : null}
      {commands.message ? (
        <p role="status" className="progressNotice">
          {commands.message}
        </p>
      ) : null}
      {configuration.data && !mayRead ? <p role="status">La función no está habilitada para este contexto.</p> : null}
      {mayRead ? (
        <>
          <p className="contractBoundary">
            Procurement conserva adjudicación y PO; Progress conserva mediciones; Cost adopta por decisión propia;
            Finance conserva facturas y pagos.
          </p>
          <nav className="progressTabs" aria-label="Contracts Manager submodules">
            {tabs.map((label) => (
              <button key={label} type="button" aria-pressed={tab === label} onClick={() => setTab(label)}>
                {label}
              </button>
            ))}
          </nav>
          {tab === "Contract Readiness" || tab === "Commercial Look-Ahead" || tab === "History" ? (
            <LookupPanel key={tab} kind={tab} scope={scope} />
          ) : tab === "Mappings" ? (
            <MappingPanel scope={scope} />
          ) : (
            <EntityPanel key={tab} entity={entities[tab]} label={tab} scope={scope} />
          )}
        </>
      ) : null}
    </section>
  );
}
