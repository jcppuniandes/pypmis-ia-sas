import { useState, type FormEvent } from "react";
import { Evidence, Input, Records, Select } from "./Fields";
import { text, type CostPanelProps, type CostRow } from "./types";

const resourceTypes = ["LABOR", "MATERIAL", "EQUIPMENT", "SUBCONTRACT", "OTHER"];
export default function ApuRatesPanel({ data, busy, reason, command, can }: CostPanelProps) {
  const [rate, setRate] = useState({
    code: "",
    name: "",
    resource_type: "LABOR",
    unit: "h",
    amount: "",
    currency: "USD",
    effective_from: "",
    effective_to: "",
    source_reference: "",
    supersedes_id: "",
  });
  const [apu, setApu] = useState({
    code: "",
    name: "",
    unit: "m2",
    currency: "USD",
    effective_from: "",
    effective_to: "",
    source_reference: "",
    supersedes_id: "",
  });
  const [components, setComponents] = useState<
    { rate_id: string; category: string; quantity_per_unit: string; unit: string }[]
  >([{ rate_id: "", category: "LABOR", quantity_per_unit: "1", unit: "h" }]);
  const [factor, setFactor] = useState({ name: "", percentage: "" });
  const [selected, setSelected] = useState<CostRow | null>(null);
  async function saveRate(event: FormEvent) {
    event.preventDefault();
    await command("/rates", {
      ...rate,
      effective_to: rate.effective_to || null,
      supersedes_id: rate.supersedes_id ? Number(rate.supersedes_id) : null,
      reason,
    });
  }
  async function saveApu(event: FormEvent) {
    event.preventDefault();
    await command("/apus", {
      ...apu,
      effective_to: apu.effective_to || null,
      supersedes_id: apu.supersedes_id ? Number(apu.supersedes_id) : null,
      components: components.map((item) => ({ ...item, rate_id: Number(item.rate_id) })),
      factors: factor.name && factor.percentage ? [{ ...factor, basis: "DIRECT_COST" }] : [],
      reason,
    });
  }
  const rateColumns: [string, string][] = [
    ["code", "Código"],
    ["resource_type", "Tipo"],
    ["unit", "Unidad"],
    ["amount", "Tarifa"],
    ["currency", "Moneda"],
    ["effective_from", "Desde"],
    ["effective_to", "Hasta"],
    ["revision", "Revisión"],
    ["status", "Estado"],
  ];
  return (
    <section className="costPanel">
      <h3>APU / Rates</h3>
      <p>
        Tarifas y APU versionados y con vigencia. Publicación independiente; una tarifa histórica no se sobrescribe.
      </p>
      <Records label="Cost Rates" rows={data.rates} columns={rateColumns} select={setSelected} />
      {can("rate.edit") ? (
        <form className="costForm" onSubmit={(event) => void saveRate(event).catch(() => undefined)}>
          {(
            [
              "code",
              "name",
              "unit",
              "amount",
              "currency",
              "effective_from",
              "effective_to",
              "source_reference",
            ] as const
          ).map((key) => (
            <Input
              key={key}
              label={`Rate ${key}`}
              value={rate[key]}
              type={key.startsWith("effective_") ? "date" : key === "amount" ? "number" : "text"}
              required={key !== "effective_to"}
              onChange={(value) => setRate({ ...rate, [key]: value })}
            />
          ))}
          <Select
            label="Rate Resource Type"
            required
            value={rate.resource_type}
            values={resourceTypes}
            onChange={(resource_type) => setRate({ ...rate, resource_type })}
          />
          <Select
            label="Rate Supersedes"
            value={rate.supersedes_id}
            rows={data.rates.filter((row) => row.status === "PUBLISHED")}
            onChange={(supersedes_id) => setRate({ ...rate, supersedes_id })}
          />
          <button type="submit" disabled={busy || reason.trim().length < 8}>
            Crear Rate DRAFT
          </button>
        </form>
      ) : null}
      <Records
        label="Cost APU"
        rows={data.apus}
        columns={[
          ["code", "Código"],
          ["unit", "Unidad"],
          ["unit_amount", "Costo unitario"],
          ["currency", "Moneda"],
          ["effective_from", "Desde"],
          ["revision", "Revisión"],
          ["status", "Estado"],
        ]}
        select={setSelected}
      />
      {can("apu.edit") ? (
        <form className="costForm" onSubmit={(event) => void saveApu(event).catch(() => undefined)}>
          {(["code", "name", "unit", "currency", "effective_from", "effective_to", "source_reference"] as const).map(
            (key) => (
              <Input
                key={key}
                label={`APU ${key}`}
                value={apu[key]}
                type={key.startsWith("effective_") ? "date" : "text"}
                required={key !== "effective_to"}
                onChange={(value) => setApu({ ...apu, [key]: value })}
              />
            )
          )}
          <Select
            label="APU Supersedes"
            value={apu.supersedes_id}
            rows={data.apus.filter((row) => row.status === "PUBLISHED")}
            onChange={(supersedes_id) => setApu({ ...apu, supersedes_id })}
          />
          {components.map((item, index) => (
            <div className="costForm costWide" key={index}>
              <Select
                label={`APU Component ${index + 1} Rate`}
                required
                rows={data.rates.filter((row) => row.status === "PUBLISHED")}
                value={item.rate_id}
                onChange={(rate_id) => {
                  const source = data.rates.find((row) => String(row.id) === rate_id);
                  setComponents(
                    components.map((row, position) =>
                      position === index
                        ? {
                            ...row,
                            rate_id,
                            category: text(source, "resource_type", "OTHER"),
                            unit: text(source, "unit"),
                          }
                        : row
                    )
                  );
                }}
              />
              <Select
                label={`APU Component ${index + 1} Category`}
                required
                values={resourceTypes}
                value={item.category}
                onChange={(category) =>
                  setComponents(components.map((row, position) => (position === index ? { ...row, category } : row)))
                }
              />
              <Input
                label={`APU Component ${index + 1} Quantity`}
                type="number"
                required
                value={item.quantity_per_unit}
                onChange={(quantity_per_unit) =>
                  setComponents(
                    components.map((row, position) => (position === index ? { ...row, quantity_per_unit } : row))
                  )
                }
              />
              <Input
                label={`APU Component ${index + 1} Unit`}
                required
                value={item.unit}
                onChange={(unit) =>
                  setComponents(components.map((row, position) => (position === index ? { ...row, unit } : row)))
                }
              />
              {components.length > 1 ? (
                <button
                  type="button"
                  onClick={() => setComponents(components.filter((_, position) => position !== index))}
                >
                  Quitar componente {index + 1}
                </button>
              ) : null}
            </div>
          ))}
          <button
            type="button"
            onClick={() =>
              setComponents([...components, { rate_id: "", category: "OTHER", quantity_per_unit: "1", unit: "" }])
            }
          >
            Agregar componente APU
          </button>
          <Input label="APU Factor Name" value={factor.name} onChange={(name) => setFactor({ ...factor, name })} />
          <Input
            label="APU Factor Percentage"
            type="number"
            value={factor.percentage}
            onChange={(percentage) => setFactor({ ...factor, percentage })}
          />
          <button type="submit" disabled={busy || reason.trim().length < 8}>
            Crear APU DRAFT
          </button>
        </form>
      ) : null}
      {selected ? (
        <>
          <h4>
            {text(selected, "code")} · {text(selected, "status")} · r{text(selected, "revision")}
          </h4>
          <Evidence label="Fuente y composición de APU / Rate" value={selected} />
          {selected.status === "DRAFT" && can(selected.components_json ? "apu.publish" : "rate.publish") ? (
            <button
              type="button"
              disabled={busy || reason.trim().length < 8}
              onClick={() =>
                void command(
                  `/${selected.components_json ? "apus" : "rates"}/${selected.id}/publish`,
                  { reason },
                  Number(selected.version)
                )
                  .then(setSelected)
                  .catch(() => undefined)
              }
            >
              Publicar {selected.components_json ? "APU" : "Rate"} independiente
            </button>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
