import { useState, type FormEvent } from "react";
import { Evidence, Input, Records, Select } from "./Fields";
import type { CostPanelProps } from "./types";

export default function BudgetsPanel({ data, busy, reason, command, can }: CostPanelProps) {
  const [budgetId, setBudgetId] = useState("");
  const [draft, setDraft] = useState({
    code: "",
    name: "",
    currency: "USD",
    budget_type: "ORIGINAL",
    pricing_date: "",
    predecessor_id: "",
  });
  const [line, setLine] = useState({
    line_code: "",
    description: "",
    quantity: "",
    unit: "",
    rate: "",
    currency: "USD",
    cost_class: "DIRECT",
    cbs_id: "",
    cost_code_id: "",
    control_account_id: "",
    scope_item_id: "",
    plan_item_id: "",
    work_package_id: "",
    apu_id: "",
  });
  const [candidate, setCandidate] = useState({
    line_code: "",
    scope_item_id: "",
    apu_id: "",
    cbs_id: "",
    cost_code_id: "",
    control_account_id: "",
    plan_item_id: "",
    work_package_id: "",
  });
  const selected = data.budgets.find((row) => String(row.id) === budgetId) ?? data.budgets[data.budgets.length - 1];
  const lines = data.budget_lines.filter((row) => row.budget_version_id === selected?.id);
  async function create(event: FormEvent) {
    event.preventDefault();
    const { pricing_date, ...fields } = draft;
    const result = await command("/budgets", {
      ...fields,
      predecessor_id: draft.budget_type !== "ORIGINAL" && draft.predecessor_id ? Number(draft.predecessor_id) : null,
      source_references: { pricing_date },
      reason,
    });
    setBudgetId(String(result.id));
  }
  async function addLine(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    const dimensions = Object.fromEntries(
      [
        "cbs_id",
        "cost_code_id",
        "control_account_id",
        "scope_item_id",
        "plan_item_id",
        "work_package_id",
        "apu_id",
      ].map((key) => [key, line[key as keyof typeof line] ? Number(line[key as keyof typeof line]) : null])
    );
    await command(`/budgets/${selected.id}/lines`, { ...line, ...dimensions, reason }, selected.version);
  }
  async function fromScope(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    const payload = Object.fromEntries(
      Object.entries(candidate).map(([key, value]) => [key, key === "line_code" ? value : value ? Number(value) : null])
    );
    await command(`/budgets/${selected.id}/candidate-from-scope`, { ...payload, reason }, selected.version);
  }
  const selectors = [
    ["cbs_id", "CBS", data.cbs],
    ["cost_code_id", "Cost Code", data.cost_codes],
    ["control_account_id", "Control Account", data.control_accounts],
    ["scope_item_id", "Scope", data.scope_items],
    ["plan_item_id", "Plan", data.plan_items],
    ["work_package_id", "Work Package", data.packages],
    ["apu_id", "APU", data.apus.filter((row) => row.status === "PUBLISHED")],
  ] as const;
  return (
    <section className="costPanel">
      <h3>Budget · Original / Approved / Current</h3>
      <p>
        Original es el primer presupuesto aprobado; Approved preserva cada aprobación; Current es el único extremo
        aprobado de la cadena de sucesores. Un candidato Scope × APU no aprueba Budget automáticamente.
      </p>
      <Records
        label="Budget Versions"
        rows={data.budgets}
        columns={[
          ["code", "Código"],
          ["name", "Nombre"],
          ["budget_type", "Tipo"],
          ["revision", "Revisión"],
          ["status", "Estado"],
          ["currency", "Moneda"],
          ["content_hash", "Hash"],
          ["approved_by", "Aprobador"],
        ]}
        select={(row) => setBudgetId(String(row.id))}
      />
      {can("budget.prepare") ? (
        <form className="costForm" onSubmit={(event) => void create(event).catch(() => undefined)}>
          {(["code", "name", "currency"] as const).map((key) => (
            <Input
              key={key}
              label={`Budget ${key}`}
              required
              value={draft[key]}
              onChange={(value) => setDraft({ ...draft, [key]: value })}
            />
          ))}
          <Input
            label="Budget Pricing Date"
            required
            type="date"
            value={draft.pricing_date}
            onChange={(pricing_date) => setDraft({ ...draft, pricing_date })}
          />
          <Select
            label="Budget Type"
            required
            values={["ORIGINAL", "CURRENT", "APPROVED_CHANGE"]}
            value={draft.budget_type}
            onChange={(budget_type) => setDraft({ ...draft, budget_type })}
          />
          {draft.budget_type !== "ORIGINAL" ? (
            <Select
              label="Budget Approved Predecessor"
              required
              rows={data.budgets.filter((row) => row.status === "APPROVED")}
              value={draft.predecessor_id}
              onChange={(predecessor_id) => setDraft({ ...draft, predecessor_id })}
            />
          ) : null}
          <button type="submit" disabled={busy || reason.trim().length < 8}>
            Crear Budget DRAFT
          </button>
        </form>
      ) : null}
      <Select
        label="Selected Budget"
        rows={data.budgets}
        value={String(selected?.id ?? "")}
        onChange={setBudgetId}
        required
      />
      {selected ? (
        <>
          <p>
            Budget #{selected.id} · {selected.status}. Aprobados e históricos son inmutables; los cambios requieren
            sucesor.
          </p>
          <Records
            label="Budget Lines"
            rows={lines}
            columns={[
              ["line_code", "Línea"],
              ["description", "Descripción"],
              ["scope_item_id", "Scope"],
              ["apu_id", "APU"],
              ["quantity", "Cantidad"],
              ["unit", "Unidad"],
              ["rate", "Tarifa"],
              ["amount", "Importe"],
              ["currency", "Moneda"],
              ["cost_class", "Clase"],
            ]}
          />
          {selected.status === "DRAFT" && can("budget.prepare") ? (
            <>
              <form className="costForm" onSubmit={(event) => void fromScope(event).catch(() => undefined)}>
                <h4 className="costWide">Scope aprobado × APU publicado → línea candidata</h4>
                <Input
                  label="Budget Candidate Line Code"
                  required
                  value={candidate.line_code}
                  onChange={(line_code) => setCandidate({ ...candidate, line_code })}
                />
                {selectors.map(([key, label, rows]) => (
                  <Select
                    key={key}
                    label={`Budget Candidate ${label}`}
                    rows={[...rows]}
                    required={key === "scope_item_id" || key === "apu_id"}
                    value={candidate[key as keyof typeof candidate] ?? ""}
                    onChange={(value) => setCandidate({ ...candidate, [key]: value })}
                  />
                ))}
                <button type="submit" disabled={busy || reason.trim().length < 8}>
                  Construir Budget Candidate desde Scope
                </button>
              </form>
              <details>
                <summary>Agregar línea de Budget con base explícita</summary>
                <form className="costForm" onSubmit={(event) => void addLine(event).catch(() => undefined)}>
                  {(["line_code", "description", "quantity", "unit", "rate", "currency"] as const).map((key) => (
                    <Input
                      key={key}
                      label={`Budget Line ${key}`}
                      required
                      value={line[key]}
                      type={key === "quantity" || key === "rate" ? "number" : "text"}
                      onChange={(value) => setLine({ ...line, [key]: value })}
                    />
                  ))}
                  {selectors.map(([key, label, rows]) => (
                    <Select
                      key={key}
                      label={`Budget Line ${label}`}
                      rows={[...rows]}
                      value={line[key]}
                      onChange={(value) => setLine({ ...line, [key]: value })}
                    />
                  ))}
                  <Select
                    label="Budget Line Cost Class"
                    required
                    values={["DIRECT", "INDIRECT", "CONTINGENCY", "MANAGEMENT_RESERVE"]}
                    value={line.cost_class}
                    onChange={(cost_class) => setLine({ ...line, cost_class })}
                  />
                  <button type="submit" disabled={busy || reason.trim().length < 8}>
                    Agregar Budget Line
                  </button>
                </form>
              </details>
            </>
          ) : null}
          <div className="costLifecycle">
            {(
              [
                ["DRAFT", "SUBMITTED", "budget.submit", "Enviar Budget"],
                ["SUBMITTED", "UNDER_REVIEW", "budget.review", "Revisar Budget"],
                ["UNDER_REVIEW", "APPROVED", "budget.approve", "Aprobar Budget independiente"],
                ["UNDER_REVIEW", "REJECTED", "budget.approve", "Rechazar Budget"],
              ] as const
            )
              .filter(([source, , action]) => selected.status === source && can(action))
              .map(([, status, , label]) => (
                <button
                  key={status}
                  type="button"
                  disabled={busy || reason.trim().length < 8}
                  onClick={() =>
                    void command(`/budgets/${selected.id}/transition`, { status, reason }, selected.version).catch(
                      () => undefined
                    )
                  }
                >
                  {label}
                </button>
              ))}
            {selected.status === "APPROVED" && can("budget.prepare") ? (
              <button
                type="button"
                disabled={busy || reason.trim().length < 8}
                onClick={() =>
                  void command(`/budgets/${selected.id}/successor`, { reason }, selected.version)
                    .then((result) => setBudgetId(String(result.id)))
                    .catch(() => undefined)
                }
              >
                Crear Budget sucesor
              </button>
            ) : null}
          </div>
          <Evidence label="Budget snapshot y procedencia" value={selected} />
        </>
      ) : null}
    </section>
  );
}
