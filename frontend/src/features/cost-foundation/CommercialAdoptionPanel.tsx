import { useState, type FormEvent } from "react";
import { Evidence, Input, Records, Select } from "./Fields";
import { costProjectRoot } from "./api";
import { positiveId, query, text, useCommands, useRead, versionOf } from "../contracts-foundation/api";
import { ReadState } from "../contracts-foundation/ContractForms";
import { type CostPanelProps, type CostRow } from "./types";

const root = "/commercial-commitment-adoptions";

export default function CommercialAdoptionPanel({
  token,
  workspaceId,
  initialId,
  props,
}: {
  token: string;
  workspaceId: number;
  initialId: string;
  props: CostPanelProps;
}) {
  const [identity, setIdentity] = useState(initialId);
  const [lookupId, setLookupId] = useState(positiveId(initialId) ? initialId : "");
  const [beforeId, setBeforeId] = useState("");
  const [status, setStatus] = useState("");
  const [cbs, setCbs] = useState("");
  const [costCode, setCostCode] = useState("");
  const [account, setAccount] = useState("");
  const [effective, setEffective] = useState("");
  const canAdopt = props.can("mapping.edit");
  const base = costProjectRoot(workspaceId);
  const command = useCommands(token, base, !canAdopt);
  const source = useRead(
    token,
    base,
    lookupId ? query(root + "/lookup", { source_entity_id: lookupId }) : null,
    command.revision
  );
  const register = useRead(token, base, query(root, { before_id: beforeId }), command.revision);
  const version = versionOf(source.data?.version, true);
  const pinnedVersion = versionOf(source.data?.source_version);
  const hash = text(source.data?.source_hash);
  const observed = text(source.data?.observed_at);
  const sourceEffective = text(source.data?.effective_at);
  const validSource =
    source.data &&
    version !== undefined &&
    pinnedVersion !== undefined &&
    /^[a-f0-9]{64}$/.test(hash) &&
    observed &&
    sourceEffective;
  async function decide(event: FormEvent) {
    event.preventDefault();
    if (
      !canAdopt ||
      !validSource ||
      source.loading ||
      identity !== lookupId ||
      ![cbs, costCode, account].every(positiveId) ||
      !["ADOPTED", "NOT_ADOPTED"].includes(status)
    )
      return;
    const result = await command.command(
      root,
      {
        source_entity_id: Number(lookupId),
        source_version: pinnedVersion,
        source_hash: hash,
        observed_at: observed,
        effective_at: effective || sourceEffective,
        cbs_id: Number(cbs),
        cost_code_id: Number(costCode),
        control_account_id: Number(account),
        consumer_status: status,
        reason: props.reason.trim(),
      },
      version
    );
    if (result) setStatus("");
  }
  const active = (items: CostRow[]) => items.filter((row) => row.status === "ACTIVE");
  const records = Array.isArray(register.data?.items) ? (register.data.items as CostRow[]) : [];
  return (
    <section className="costPanel" aria-label="Commercial Adoption">
      <h3>Commercial Adoption</h3>
      <p className="costBoundary">
        Cost decide si consume una referencia contractual aprobada. No crea ni altera el compromiso legal, un Actual,
        una factura o un pago.
      </p>
      {command.error ? (
        <p className="costError" role="alert">
          {command.error}
        </p>
      ) : null}
      {command.message ? (
        <p className="costNotice" role="status">
          Decisión Cost registrada.
        </p>
      ) : null}
      <form
        className="costForm"
        onSubmit={(event) => {
          event.preventDefault();
          if (!positiveId(identity)) return;
          if (lookupId === identity) command.reload();
          setLookupId(identity);
        }}
      >
        <Input
          label="Compromiso comercial (ID)"
          value={identity}
          onChange={(value) => {
            setIdentity(value);
            setStatus("");
            setEffective("");
          }}
          type="number"
          required
        />
        <button type="submit" disabled={command.busy}>
          Consultar compromiso aprobado
        </button>
      </form>
      <ReadState {...source} retry={command.reload} />
      {validSource && identity === lookupId ? (
        <>
          <p>
            Compromiso <strong>{text(source.data?.commitment_code)}</strong> · {text(source.data?.currency)}{" "}
            {text(source.data?.committed_amount)} · <strong>{text(source.data?.consumer_status)}</strong>
          </p>
          <Evidence label="Referencia contractual y huella verificada" value={source.data} />
          {canAdopt ? (
            <form className="costForm" aria-label="Registrar decisión Cost" onSubmit={(event) => void decide(event)}>
              <Select
                label="Decisión Cost"
                values={["ADOPTED", "NOT_ADOPTED"]}
                value={status}
                onChange={setStatus}
                required
              />
              <Select label="CBS de adopción" rows={active(props.data.cbs)} value={cbs} onChange={setCbs} required />
              <Select
                label="Código de costo de adopción"
                rows={active(props.data.cost_codes)}
                value={costCode}
                onChange={setCostCode}
                required
              />
              <Select
                label="Cuenta de control de adopción"
                rows={active(props.data.control_accounts)}
                value={account}
                onChange={setAccount}
                required
              />
              <Input
                label="Fecha efectiva Cost"
                value={effective || sourceEffective}
                onChange={setEffective}
                type="date"
                required
              />
              <button type="submit" disabled={command.busy || source.loading || props.reason.trim().length < 8}>
                Registrar decisión Cost
              </button>
            </form>
          ) : null}
        </>
      ) : null}
      <ReadState {...register} retry={command.reload} />
      {register.data ? (
        <>
          <Records
            label="Decisiones de adopción comercial"
            rows={records}
            columns={[
              ["source_entity_id", "Compromiso (ID)"],
              ["source_version", "Versión de origen"],
              ["source_hash", "Huella"],
              ["consumer_status", "Decisión"],
              ["version", "Revisión Cost"],
              ["effective_at", "Fecha efectiva"],
              ["reason", "Motivo"],
            ]}
          />
          {beforeId ? (
            <button type="button" onClick={() => setBeforeId("")}>
              Primera página
            </button>
          ) : null}
          {positiveId(register.data.next_cursor) ? (
            <button type="button" onClick={() => setBeforeId(text(register.data?.next_cursor))}>
              Página siguiente
            </button>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
