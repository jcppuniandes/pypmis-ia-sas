import { useState, type FormEvent } from "react";
import { Input, Records, Select } from "./Fields";
import CbsTree from "./CbsTree";
import { policyValues, text, type CostPanelProps, type CostRow } from "./types";

type Kind = "CBS" | "Cost Codes" | "Control Accounts";
const definitions = {
  CBS: { path: "/cbs", action: "cbs.edit", rows: "cbs" },
  "Cost Codes": { path: "/cost-codes", action: "code.edit", rows: "cost_codes" },
  "Control Accounts": { path: "/control-accounts", action: "account.edit", rows: "control_accounts" },
} as const;
export default function RegistryPanel({ kind, data, busy, reason, command, can }: CostPanelProps & { kind: Kind }) {
  const config = definitions[kind];
  const rows = data[config.rows];
  const [selected, setSelected] = useState<CostRow | null>(null);
  const [draft, setDraft] = useState({
    code: "",
    name: "",
    parent_id: "",
    sort_order: "0",
    category: "LABOR",
    owner_user_id: "",
    responsible_role: "cost_controller",
    status: "ACTIVE",
  });
  function select(row: CostRow | null) {
    setSelected(row);
    setDraft({
      code: text(row, "code"),
      name: text(row, "name"),
      parent_id: text(row, "parent_id"),
      sort_order: text(row, "sort_order", "0"),
      category: text(row, "category", "LABOR"),
      owner_user_id: text(row, "owner_user_id"),
      responsible_role: text(row, "responsible_role", "cost_controller"),
      status: text(row, "status", "ACTIVE"),
    });
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    const payload = {
      code: draft.code,
      name: draft.name,
      status: draft.status,
      reason,
      ...(kind === "CBS"
        ? { parent_id: draft.parent_id ? Number(draft.parent_id) : null, sort_order: Number(draft.sort_order) }
        : {}),
      ...(kind === "Cost Codes" ? { category: draft.category } : {}),
      ...(kind === "Control Accounts"
        ? { owner_user_id: Number(draft.owner_user_id), responsible_role: draft.responsible_role }
        : {}),
    };
    const result = await command(
      `${config.path}${selected ? `/${selected.id}` : ""}`,
      payload,
      selected ? Number(selected.version) : undefined,
      selected ? "PUT" : "POST"
    );
    select(result);
  }
  const columns: [string, string][] = [
    ["code", "Código"],
    ["name", "Nombre"],
  ];
  if (kind === "CBS") columns.push(["path", "Ruta CBS"], ["level", "Nivel"], ["parent_id", "Padre"]);
  if (kind === "Cost Codes") columns.push(["category", "Categoría"]);
  if (kind === "Control Accounts") columns.push(["owner_user_id", "Responsable"], ["responsible_role", "Rol"]);
  columns.push(["status", "Estado"], ["revision", "Revisión"]);
  return (
    <section className="costPanel">
      <h3>{kind}</h3>
      <p>
        {kind === "CBS"
          ? "CBS es jerárquica e independiente de WBS. Los vínculos con Scope, Plan, Package y Schedule son explícitos M:N."
          : kind === "Control Accounts"
            ? "Punto de responsabilidad integrado. No se crea una cuenta automáticamente por nodo CBS o WBS."
            : "Cost Code clasifica costo; no es CBS, recurso, APU ni Control Account."}
      </p>
      {kind === "CBS" ? <CbsTree rows={rows} select={select} /> : null}
      <Records label={kind} rows={rows} columns={columns} select={select} />
      {can(config.action) ? (
        <>
          <button type="button" onClick={() => select(null)}>
            Nuevo {kind}
          </button>
          <form className="costForm" onSubmit={(event) => void submit(event).catch(() => undefined)}>
            <Input
              label={`${kind} Code`}
              required
              value={draft.code}
              disabled={Boolean(selected)}
              onChange={(code) => setDraft({ ...draft, code })}
            />
            <Input
              label={`${kind} Name`}
              required
              value={draft.name}
              onChange={(name) => setDraft({ ...draft, name })}
            />
            {kind === "CBS" ? (
              <>
                <Select
                  label="CBS Parent"
                  value={draft.parent_id}
                  onChange={(parent_id) => setDraft({ ...draft, parent_id })}
                  rows={data.cbs.filter((row) => row.id !== selected?.id)}
                />
                <Input
                  label="CBS Sort Order"
                  type="number"
                  value={draft.sort_order}
                  onChange={(sort_order) => setDraft({ ...draft, sort_order })}
                />
              </>
            ) : null}
            {kind === "Cost Codes" ? (
              <Select
                label="Cost Code Category"
                required
                value={draft.category}
                onChange={(category) => setDraft({ ...draft, category })}
                values={policyValues(data, "cost_code_categories", [
                  "LABOR",
                  "MATERIAL",
                  "EQUIPMENT",
                  "SUBCONTRACT",
                  "ENGINEERING",
                  "PROCUREMENT",
                  "CONSTRUCTION",
                  "TEMPORARY_WORKS",
                  "LOGISTICS",
                  "INDIRECTS",
                  "OVERHEADS",
                  "CONTINGENCY",
                ])}
              />
            ) : null}
            {kind === "Control Accounts" ? (
              <>
                <Input
                  label="Control Account Owner User ID"
                  type="number"
                  required
                  value={draft.owner_user_id}
                  onChange={(owner_user_id) => setDraft({ ...draft, owner_user_id })}
                />
                <Input
                  label="Control Account Responsible Role"
                  required
                  value={draft.responsible_role}
                  onChange={(responsible_role) => setDraft({ ...draft, responsible_role })}
                />
              </>
            ) : null}
            <Select
              label={`${kind} Status`}
              required
              value={draft.status}
              onChange={(status) => setDraft({ ...draft, status })}
              values={["ACTIVE", "INACTIVE"]}
            />
            <button type="submit" disabled={busy || reason.trim().length < 8}>
              {selected ? `Guardar ${kind}` : `Crear ${kind}`}
            </button>
          </form>
        </>
      ) : (
        <p>Sin permiso de edición {kind}.</p>
      )}
    </section>
  );
}
