import { useEffect, useState, type FormEvent } from "react";
import { Evidence, Input, Records, Select } from "./Fields";
import { collection, display, moneyDisplay, text, type CostPanelProps, type CostRow } from "./types";
import { operationalError } from "../operational-context/commands";

export function ActualsPanel({ data, busy, reason, command, can }: CostPanelProps) {
  const [draft, setDraft] = useState({
    source_system: "CONTROLLED_MANUAL",
    source_reference: "",
    source_type: "CONTROLLED_MANUAL",
    posting_date: "",
    recognition_date: "",
    period_id: "",
    amount: "",
    currency: "USD",
    cbs_id: "",
    cost_code_id: "",
    control_account_id: "",
    evidence_ref: "",
    description: "",
    fx_rate_id: "",
  });
  const [selectedId, setSelectedId] = useState("");
  const [adjustment, setAdjustment] = useState(false);
  const selected = data.actuals.find((row) => String(row.id) === selectedId);
  function set(key: keyof typeof draft, value: string) {
    setDraft({ ...draft, [key]: value });
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    await command(
      adjustment && selected ? `/actuals/${selected.id}/adjustments` : "/actuals",
      {
        ...draft,
        period_id: Number(draft.period_id),
        cbs_id: draft.cbs_id ? Number(draft.cbs_id) : null,
        cost_code_id: draft.cost_code_id ? Number(draft.cost_code_id) : null,
        control_account_id: draft.control_account_id ? Number(draft.control_account_id) : null,
        fx_rate_id: draft.fx_rate_id ? Number(draft.fx_rate_id) : null,
        reason,
      },
      adjustment && selected ? selected.version : undefined
    );
  }
  return (
    <section className="costPanel">
      <h3>Actual Cost · costo incurrido reconocido</h3>
      <p>
        Importar no equivale a reconocer. Requiere fuente única, evidencia, período abierto y aprobación independiente.
        No es aprobación de factura, pago ni contabilidad.
      </p>
      <Records
        label="Actual Cost"
        rows={data.actuals}
        columns={[
          ["source_reference", "Fuente"],
          ["source_system", "Sistema"],
          ["posting_date", "Contabilización fuente"],
          ["recognition_date", "Reconocimiento"],
          ["period_id", "Período"],
          ["amount", "Importe"],
          ["currency", "Moneda"],
          ["status", "Estado"],
          ["adjusts_entry_id", "Ajusta"],
          ["approved_by", "Reconocido por"],
        ]}
        select={(row) => setSelectedId(String(row.id))}
      />
      {selected ? (
        <>
          <div className="costLifecycle">
            {can("actual.approve") && selected.status === "IMPORTED" ? (
              <button
                type="button"
                disabled={busy || reason.trim().length < 8}
                onClick={() =>
                  void command(
                    `/actuals/${selected.id}/decision`,
                    { status: "RECOGNIZED", reason },
                    selected.version
                  ).catch(() => undefined)
                }
              >
                Reconocer Actual independiente
              </button>
            ) : null}
            {can("actual.adjust") && selected.status === "RECOGNIZED" ? (
              <button
                type="button"
                onClick={() => {
                  setAdjustment(true);
                  setDraft({
                    ...draft,
                    source_system: text(selected, "source_system"),
                    source_reference: "",
                    period_id: text(selected, "period_id"),
                    currency: text(selected, "currency"),
                    cbs_id: text(selected, "cbs_id"),
                    cost_code_id: text(selected, "cost_code_id"),
                    control_account_id: text(selected, "control_account_id"),
                  });
                }}
              >
                Preparar ajuste Actual
              </button>
            ) : null}
          </div>
          <Evidence label="Linaje y reconocimiento Actual" value={selected} />
        </>
      ) : null}
      {can("actual.import") || (adjustment && can("actual.adjust")) ? (
        <form className="costForm" onSubmit={(event) => void save(event).catch(() => undefined)}>
          <h4 className="costWide">
            {adjustment ? `Ajuste explícito de Actual #${selected?.id}` : "Importar candidato Actual"}
          </h4>
          {(
            [
              "source_system",
              "source_reference",
              "source_type",
              "posting_date",
              "recognition_date",
              "amount",
              "currency",
              "evidence_ref",
              "description",
            ] as const
          ).map((key) => (
            <Input
              key={key}
              label={`Actual ${key}`}
              required={key !== "description"}
              type={key.endsWith("_date") ? "date" : key === "amount" ? "number" : "text"}
              value={draft[key]}
              onChange={(value) => set(key, value)}
            />
          ))}
          <Select
            label="Actual Period"
            required
            value={draft.period_id}
            onChange={(value) => set("period_id", value)}
            rows={data.periods.filter((row) => ["OPEN", "REVIEW"].includes(text(row, "status")))}
          />
          <Select label="Actual CBS" rows={data.cbs} value={draft.cbs_id} onChange={(value) => set("cbs_id", value)} />
          <Select
            label="Actual Cost Code"
            rows={data.cost_codes}
            value={draft.cost_code_id}
            onChange={(value) => set("cost_code_id", value)}
          />
          <Select
            label="Actual Control Account"
            rows={data.control_accounts}
            value={draft.control_account_id}
            onChange={(value) => set("control_account_id", value)}
          />
          <Select
            label="Actual FX Rate"
            rows={data.fx_rates?.filter((row) => row.status === "PUBLISHED") ?? []}
            value={draft.fx_rate_id}
            onChange={(value) => set("fx_rate_id", value)}
          />
          <button type="submit" disabled={busy || reason.trim().length < 8}>
            {adjustment ? "Registrar ajuste Actual" : "Importar Actual candidato"}
          </button>
          {adjustment ? (
            <button type="button" onClick={() => setAdjustment(false)}>
              Cancelar ajuste
            </button>
          ) : null}
        </form>
      ) : null}
    </section>
  );
}

export function CommitmentsPanel({ data, busy, reason, command, can, query }: CostPanelProps) {
  const [draft, setDraft] = useState({
    source_system: "CONTRACT_ADMIN",
    source_type: "CONTRACT",
    source_reference: "",
    source_revision: "1",
    source_hash: "",
    source_record_id: "",
    source_document: "",
    source_approval_status: "APPROVED",
    economic_origin: "",
    parent_economic_origin: "",
    inclusion_mode: "ADDITIVE",
    amount: "",
    currency: "USD",
    effective_date: "",
    cbs_id: "",
    cost_code_id: "",
    control_account_id: "",
    fx_rate_id: "",
    supersedes_id: "",
  });
  const [selectedId, setSelectedId] = useState("");
  const [reconciliation, setReconciliation] = useState<CostRow | null>(null);
  const [error, setError] = useState("");
  const selected = data.commitment_references.find((row) => String(row.id) === selectedId);
  const refresh = () =>
    query("/commitments/reconciliation")
      .then(setReconciliation)
      .catch((caught) => setError(operationalError(caught)));
  useEffect(() => {
    let active = true;
    query("/commitments/reconciliation")
      .then((result) => active && setReconciliation(result))
      .catch((caught) => active && setError(operationalError(caught)));
    return () => {
      active = false;
    };
  }, [query, data.commitment_references]);
  function set(key: keyof typeof draft, value: string) {
    setDraft({ ...draft, [key]: value });
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    await command("/commitments", {
      ...draft,
      source_record_id: draft.source_record_id ? Number(draft.source_record_id) : null,
      parent_economic_origin: draft.parent_economic_origin || null,
      cbs_id: draft.cbs_id ? Number(draft.cbs_id) : null,
      cost_code_id: draft.cost_code_id ? Number(draft.cost_code_id) : null,
      control_account_id: draft.control_account_id ? Number(draft.control_account_id) : null,
      fx_rate_id: draft.fx_rate_id ? Number(draft.fx_rate_id) : null,
      supersedes_id: draft.supersedes_id ? Number(draft.supersedes_id) : null,
      reason,
    });
    await refresh();
  }
  return (
    <section className="costPanel">
      <h3>Commitment projection / reconciliation</h3>
      <p>
        Vista de costo, no autoridad contractual. INCLUDED y CALL_OFF no vuelven a sumar el padre; ADDITIVE exige origen
        incremental; REFERENCE_ONLY aporta cero.
      </p>
      {error ? (
        <p role="alert" className="costError">
          {error}
        </p>
      ) : null}
      <Records
        label="Commitment References"
        rows={data.commitment_references}
        columns={[
          ["source_type", "Tipo"],
          ["source_reference", "Fuente"],
          ["economic_origin", "Origen económico"],
          ["parent_economic_origin", "Origen padre"],
          ["inclusion_mode", "Inclusión"],
          ["amount", "Importe fuente"],
          ["currency", "Moneda"],
          ["status", "Verificación"],
        ]}
        select={(row) => setSelectedId(String(row.id))}
      />
      {reconciliation ? (
        <>
          <div className="costFacts">
            <div>
              <span>Net Commitment</span>
              <strong>{display(reconciliation.net_commitment ?? reconciliation.amount ?? reconciliation.total)}</strong>
            </div>
            <div>
              <span>Agregación</span>
              <strong>{display(reconciliation.aggregation_status ?? reconciliation.status)}</strong>
            </div>
          </div>
          <Evidence label="Reconciliación por obligación y moneda" value={reconciliation} />
        </>
      ) : null}
      {selected && selected.status === "PROPOSED" && can("commitment.verify") ? (
        <button
          type="button"
          disabled={busy || reason.trim().length < 8}
          onClick={() =>
            void command(`/commitments/${selected.id}/verify`, { status: "VERIFIED", reason }, selected.version).catch(
              () => undefined
            )
          }
        >
          Verificar Commitment independiente
        </button>
      ) : null}
      {selected ? <Evidence label="Commitment source revision y proyección" value={selected} /> : null}
      {can("commitment.reconcile") ? (
        <form className="costForm" onSubmit={(event) => void save(event).catch(() => undefined)}>
          <Select
            label="Commitment Supersedes Reference"
            rows={data.commitment_references.filter((row) => row.status === "VERIFIED")}
            value={draft.supersedes_id}
            onChange={(value) => set("supersedes_id", value)}
          />
          {(
            [
              "source_system",
              "source_reference",
              "source_revision",
              "source_hash",
              "source_record_id",
              "source_document",
              "source_approval_status",
              "economic_origin",
              "parent_economic_origin",
              "amount",
              "currency",
              "effective_date",
            ] as const
          ).map((key) => (
            <Input
              key={key}
              label={`Commitment ${key}`}
              required={!["source_record_id", "parent_economic_origin"].includes(key)}
              value={draft[key]}
              type={
                key === "effective_date" ? "date" : ["amount", "source_record_id"].includes(key) ? "number" : "text"
              }
              onChange={(value) => set(key, value)}
            />
          ))}
          <Select
            label="Commitment Source Type"
            required
            values={["CONTRACT", "PO", "SUBCONTRACT", "CONTRACT_CHANGE_ORDER"]}
            value={draft.source_type}
            onChange={(value) => set("source_type", value)}
          />
          <Select
            label="Commitment Inclusion Mode"
            required
            values={["INCLUDED", "CALL_OFF", "ADDITIVE", "REFERENCE_ONLY"]}
            value={draft.inclusion_mode}
            onChange={(value) => set("inclusion_mode", value)}
          />
          <Select
            label="Commitment CBS"
            rows={data.cbs}
            value={draft.cbs_id}
            onChange={(value) => set("cbs_id", value)}
          />
          <Select
            label="Commitment Cost Code"
            rows={data.cost_codes}
            value={draft.cost_code_id}
            onChange={(value) => set("cost_code_id", value)}
          />
          <Select
            label="Commitment Control Account"
            rows={data.control_accounts}
            value={draft.control_account_id}
            onChange={(value) => set("control_account_id", value)}
          />
          <Select
            label="Commitment FX Rate"
            rows={data.fx_rates?.filter((row) => row.status === "PUBLISHED") ?? []}
            value={draft.fx_rate_id}
            onChange={(value) => set("fx_rate_id", value)}
          />
          <button type="submit" disabled={busy || reason.trim().length < 8}>
            Registrar Commitment reference
          </button>
        </form>
      ) : null}
    </section>
  );
}

export function CurrencyPanel({ data, busy, reason, command, can }: CostPanelProps) {
  const [draft, setDraft] = useState({
    code: "",
    from_currency: "COP",
    to_currency: "USD",
    rate: "",
    effective_from: "",
    effective_to: "",
    conversion_basis: "",
    source_reference: "",
    supersedes_id: "",
  });
  const [selectedId, setSelectedId] = useState("");
  const selected = data.fx_rates?.find((row) => String(row.id) === selectedId);
  async function save(event: FormEvent) {
    event.preventDefault();
    await command("/fx-rates", {
      ...draft,
      effective_to: draft.effective_to || null,
      supersedes_id: draft.supersedes_id ? Number(draft.supersedes_id) : null,
      reason,
    });
  }
  return (
    <section className="costPanel">
      <h3>Currency / FX governance</h3>
      <p>
        Cada importe conserva moneda y procedencia. Sin FX publicado aplicable: NO_AGGREGATION. Editar y publicar son
        deberes independientes.
      </p>
      <Records
        label="FX Rates"
        rows={data.fx_rates ?? []}
        columns={[
          ["code", "Código"],
          ["from_currency", "Desde"],
          ["to_currency", "Hacia"],
          ["rate", "Tasa"],
          ["effective_from", "Vigencia"],
          ["revision", "Revisión"],
          ["status", "Estado"],
          ["source_reference", "Fuente"],
        ]}
        select={(row) => setSelectedId(String(row.id))}
      />
      {can("fx.edit") ? (
        <form className="costForm" onSubmit={(event) => void save(event).catch(() => undefined)}>
          {(
            [
              "code",
              "from_currency",
              "to_currency",
              "rate",
              "effective_from",
              "effective_to",
              "conversion_basis",
              "source_reference",
            ] as const
          ).map((key) => (
            <Input
              key={key}
              label={`FX ${key}`}
              required={key !== "effective_to"}
              value={draft[key]}
              type={key.startsWith("effective_") ? "date" : key === "rate" ? "number" : "text"}
              onChange={(value) => setDraft({ ...draft, [key]: value })}
            />
          ))}
          <Select
            label="FX Supersedes"
            rows={data.fx_rates?.filter((row) => row.status === "PUBLISHED") ?? []}
            value={draft.supersedes_id}
            onChange={(supersedes_id) => setDraft({ ...draft, supersedes_id })}
          />
          <button type="submit" disabled={busy || reason.trim().length < 8}>
            Crear FX DRAFT
          </button>
        </form>
      ) : null}
      {selected && selected.status === "DRAFT" && can("fx.publish") ? (
        <button
          type="button"
          disabled={busy || reason.trim().length < 8}
          onClick={() =>
            void command(`/fx-rates/${selected.id}/publish`, { reason }, selected.version).catch(() => undefined)
          }
        >
          Publicar FX independiente
        </button>
      ) : null}
    </section>
  );
}

export function OverviewPanel({ data, query }: CostPanelProps) {
  const [result, setResult] = useState<CostRow | null>(data.summary ?? null);
  const [cash, setCash] = useState<CostRow[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    Promise.all([query("/financial-overview"), query("/cash-flow")])
      .then(([summary, cashFlow]) => {
        if (active) {
          setResult(summary);
          setCash(collection(cashFlow.items ?? cashFlow.periods));
        }
      })
      .catch((caught) => active && setError(operationalError(caught)));
    return () => {
      active = false;
    };
  }, [query, data]);
  return (
    <section className="costPanel">
      <h3>Cost Overview</h3>
      <p>
        Cost controla el plan y el reconocimiento; no administra Funding/FIN, Treasury, pagos, avance ganado ni Forecast
        aprobado.
      </p>
      {error ? (
        <p role="alert" className="costError">
          {error}
        </p>
      ) : null}
      <div className="costFacts">
        {[
          ["Original Budget", "original_budget"],
          ["Current Budget", "current_budget"],
          ["Actual reconocido", "actual"],
          ["Net Commitment", "commitments"],
          ["ETC", "etc"],
          ["EAC", "eac"],
        ].map(([label, key]) => (
          <div key={key}>
            <span>{label}</span>
            <strong>{moneyDisplay(result?.[key])}</strong>
          </div>
        ))}
        <div>
          <span>Approved Budget</span>
          <strong>{data.budgets.filter((row) => row.status === "APPROVED").length} revisión(es) preservada(s)</strong>
        </div>
      </div>
      <Records
        label="Cost Cash Flow"
        rows={cash}
        columns={[
          ["period_code", "Período"],
          ["planned", "Planned"],
          ["current", "Current"],
          ["actual", "Actual"],
          ["commitment", "Commitment"],
          ["forecast_reference", "Forecast reference"],
        ]}
        format={(key, value) =>
          ["planned", "current", "actual", "commitment"].includes(key) ? moneyDisplay(value) : display(value)
        }
      />
      <Evidence label="Cost totals, límites y linaje" value={result} />
      <p className="costDeferred">
        ETC-ready ≠ Forecast gobernado. EAC = Actual reconocido + ETC aceptado; no se vuelve a añadir Commitment
        incluido en ETC. 4D no se convierte en 5D.
      </p>
    </section>
  );
}
