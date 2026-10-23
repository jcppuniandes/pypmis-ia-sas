import { useCallback, useEffect, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { operationalError, useOperationalCommandKeys } from "../operational-context/commands";
import { costApi } from "./api";
import RegistryPanel from "./RegistryPanel";
import CostMappingsPanel from "./CostMappingsPanel";
import ApuRatesPanel from "./ApuRatesPanel";
import BudgetsPanel from "./BudgetsPanel";
import BaselinesPanel from "./BaselinesPanel";
import PhasingPanel from "./PhasingPanel";
import { ActualsPanel, CommitmentsPanel, CurrencyPanel, OverviewPanel } from "./FinancialPanels";
import { Records } from "./Fields";
import type { CostCommand, CostOverview } from "./types";
import "./costFoundation.css";

const tabs = [
  "CBS",
  "Cost Codes",
  "Control Accounts",
  "APU / Rates",
  "Budget",
  "Cost Baseline",
  "Cost Phasing",
  "Commitments",
  "Actuals",
  "Accruals",
  "Cost Overview",
] as const;
export default function CostManagerWorkspace({
  token,
  workspaceId,
  readOnly = false,
}: {
  token: string;
  workspaceId: number;
  readOnly?: boolean;
}) {
  const [tab, setTab] = useState<(typeof tabs)[number]>("CBS");
  const [data, setData] = useState<CostOverview | null>(null);
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const keys = useOperationalCommandKeys();
  const load = useCallback(async () => setData(await costApi.overview(token, workspaceId)), [token, workspaceId]);
  const query = useCallback((path: string) => costApi.query(token, workspaceId, path), [token, workspaceId]);
  useEffect(() => {
    let active = true;
    costApi
      .overview(token, workspaceId)
      .then((result) => active && setData(result))
      .catch((caught) => active && setError(operationalError(caught)));
    return () => {
      active = false;
    };
  }, [token, workspaceId]);
  const command: CostCommand = async (path, payload, version, method) => {
    setBusy(true);
    setError("");
    setMessage("");
    const fingerprint = { workspaceId, path, payload, version, method };
    try {
      const result = await costApi.command(
        token,
        workspaceId,
        path,
        payload,
        keys.key(path, fingerprint),
        version,
        method
      );
      keys.complete(path, fingerprint);
      await load();
      setMessage(
        "Operación Cost registrada. Scope, Schedule y las fuentes aprobadas permanecen bajo su autoridad original."
      );
      return result;
    } catch (caught) {
      setError(operationalError(caught));
      throw caught;
    } finally {
      setBusy(false);
    }
  };
  const props = data
    ? {
        data,
        busy,
        reason,
        command,
        query,
        can: (action: string) =>
          (!readOnly || action === "read") &&
          data.allowed_actions.some((value) => [action, `cost.${action}`, `cost_foundation.${action}`].includes(value)),
      }
    : null;
  return (
    <section className="costFoundation" aria-label="Cost Manager" aria-busy={busy}>
      <CompactModuleHeader
        title="Cost Manager"
        eyebrow="USER MODE · CANONICAL PROJECT · O1B-C"
        tone="user"
        description="Scope-first Cost Foundation: CBS, APU, Budget y baseline de costo gobernado, sin duplicar Contract, Funding ni Accounting."
        metrics={[
          { label: "CBS", value: data?.cbs.length ?? 0 },
          { label: "Budgets", value: data?.budgets.length ?? 0 },
          { label: "Baselines", value: data?.baselines.filter((row) => row.status === "APPROVED").length ?? 0 },
        ]}
        actions={
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              setError("");
              void load().catch((caught) => setError(operationalError(caught)));
            }}
          >
            Actualizar Cost
          </button>
        }
      />
      {error ? (
        <p role="alert" className="costError">
          {error}
        </p>
      ) : null}
      {message ? (
        <p role="status" className="costNotice">
          {message}
        </p>
      ) : null}
      {!data && !error ? <p role="status">Cargando Cost canónico…</p> : null}
      {props ? (
        <>
          {readOnly ? (
            <p className="costDeferred">Workspace archivado · Cost de solo lectura. No se exponen mutaciones.</p>
          ) : null}
          <p className="costBoundary">
            Scope = WHAT · Schedule = WHEN · CBS = HOW cost is structured. Cost no redefine cantidad, fecha, compromiso
            legal ni avance ganado.
          </p>
          <InputReason reason={reason} setReason={setReason} />
          <nav className="costTabs" aria-label="Cost Manager submodules">
            {tabs.map((label) => (
              <button type="button" aria-pressed={tab === label} key={label} onClick={() => setTab(label)}>
                {label}
              </button>
            ))}
          </nav>
          {tab === "CBS" || tab === "Cost Codes" || tab === "Control Accounts" ? (
            <>
              <RegistryPanel key={tab} {...props} kind={tab} />
              <CostMappingsPanel {...props} />
            </>
          ) : null}
          {tab === "APU / Rates" ? (
            <>
              <ApuRatesPanel {...props} />
              <CurrencyPanel {...props} />
            </>
          ) : null}
          {tab === "Budget" ? <BudgetsPanel {...props} /> : null}
          {tab === "Cost Baseline" ? <BaselinesPanel {...props} /> : null}
          {tab === "Cost Phasing" ? <PhasingPanel {...props} /> : null}
          {tab === "Commitments" ? <CommitmentsPanel {...props} /> : null}
          {tab === "Actuals" ? <ActualsPanel {...props} /> : null}
          {tab === "Accruals" ? (
            <section className="costPanel">
              <h3>Accrual foundation</h3>
              <p className="costDeferred">DEFERRED_WITH_CONTRACT</p>
              <p>
                Contrato de integración explícito: costo incurrido aún no reconocido, reversión y reemplazo por Actual.
                No hay autoridad de Accrual operativa en esta entrega ni importes sumados a Actual.
              </p>
            </section>
          ) : null}
          {tab === "Cost Overview" ? <OverviewPanel {...props} /> : null}
          <details className="costEvidence">
            <summary>Historial Cost · fuentes y aprobaciones</summary>
            <Records
              label="Cost History"
              rows={data!.history}
              columns={[
                ["entity_type", "Entidad"],
                ["entity_id", "ID"],
                ["event_type", "Evento"],
                ["revision", "Revisión"],
                ["reason", "Motivo"],
                ["created_by", "Actor"],
                ["created_at", "Fecha"],
              ]}
            />
          </details>
        </>
      ) : null}
    </section>
  );
}
function InputReason({ reason, setReason }: { reason: string; setReason: (value: string) => void }) {
  return (
    <label className="costField">
      <span>Motivo Cost</span>
      <input
        aria-label="Motivo Cost"
        minLength={8}
        value={reason}
        onChange={(event) => setReason(event.target.value)}
      />
    </label>
  );
}
