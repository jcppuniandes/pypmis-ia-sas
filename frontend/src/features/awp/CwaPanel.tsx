import { useState } from "react";
import type { FormEvent } from "react";
import { Field, NamedSelect } from "./Fields";
import type { AwpPanelProps, Cwa } from "./types";

export default function CwaPanel({ data, busy, reason, can, command }: AwpPanelProps) {
  const [selected, setSelected] = useState<Cwa | null>(null);
  const [draft, setDraft] = useState({
    code: "",
    name: "",
    description: "",
    area: "",
    zone: "",
    location: "",
    parent_cwa_id: "",
    status: "ACTIVE",
  });
  function select(row: Cwa | null) {
    setSelected(row);
    setDraft({
      code: row?.code ?? "",
      name: row?.name ?? "",
      description: row?.description ?? "",
      area: row?.area ?? "",
      zone: row?.zone ?? "",
      location: row?.location ?? "",
      parent_cwa_id: row?.parent_cwa_id ? String(row.parent_cwa_id) : "",
      status: row?.status ?? "ACTIVE",
    });
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    const result = await command(
      `/cwas${selected ? `/${selected.id}` : ""}`,
      { ...draft, parent_cwa_id: draft.parent_cwa_id ? Number(draft.parent_cwa_id) : null, reason },
      selected?.version,
      selected ? "PUT" : "POST"
    );
    select(result as Cwa);
  }
  const current = data.cwas.find((row) => row.id === selected?.id) ?? selected;
  return (
    <section className="awpPanel">
      <h3>Construction Work Areas</h3>
      <p>CWA define un área o contenedor jerárquico. No es un Work Package y no genera fechas CPM.</p>
      <div className="awpTable">
        <table aria-label="Construction Work Areas">
          <thead>
            <tr>
              <th>Código</th>
              <th>Nombre</th>
              <th>Padre</th>
              <th>Área / zona</th>
              <th>Estado</th>
              <th>Revisión</th>
              <th>Detalle</th>
            </tr>
          </thead>
          <tbody>
            {data.cwas.map((row) => (
              <tr key={row.id}>
                <td>{row.code}</td>
                <td>{row.name}</td>
                <td>{data.cwas.find((parent) => parent.id === row.parent_cwa_id)?.code ?? "Raíz"}</td>
                <td>
                  {row.area} / {row.zone}
                </td>
                <td>{row.status}</td>
                <td>{row.version}</td>
                <td>
                  <button onClick={() => select(row)} type="button">
                    Editar CWA {row.code}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {can("cwa.manage") ? (
        <>
          <button type="button" onClick={() => select(null)}>
            Nueva CWA
          </button>
          <form className="awpForm" onSubmit={(e) => void save(e).catch(() => undefined)}>
            {(["code", "name", "description", "area", "zone", "location"] as const).map((key) => (
              <Field key={key} label={`CWA ${key}`}>
                <input
                  aria-label={`CWA ${key}`}
                  required={key === "code" || key === "name"}
                  value={draft[key]}
                  onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
                />
              </Field>
            ))}
            <NamedSelect
              label="CWA padre"
              value={draft.parent_cwa_id}
              onChange={(value) => setDraft({ ...draft, parent_cwa_id: value })}
              options={data.cwas
                .filter((row) => row.id !== selected?.id)
                .map((row) => ({ value: row.id, label: `${row.code} · ${row.name}` }))}
            />
            <NamedSelect
              label="CWA status"
              value={draft.status}
              onChange={(value) => setDraft({ ...draft, status: value })}
              optional={false}
              options={["ACTIVE", "INACTIVE"].map((value) => ({ value, label: value }))}
            />
            <button disabled={busy || reason.trim().length < 8} type="submit">
              {current ? "Guardar CWA" : "Crear CWA"}
            </button>
          </form>
        </>
      ) : (
        <p>Sin permiso para administrar CWA.</p>
      )}
    </section>
  );
}
