import { useState, type FormEvent } from "react";
import { Field, NamedSelect } from "./Fields";
import type { AwpPanelProps, AwpRecord } from "./types";
import { policyValues } from "../schedule-foundation/types";

export default function DependenciesPanel({ data, busy, reason, can, command }: AwpPanelProps) {
  const [selectedId, setSelectedId] = useState(0);
  const [predecessor, setPredecessor] = useState("");
  const [successor, setSuccessor] = useState("");
  const [type, setType] = useState("DELIVERABLE");
  const [blocking, setBlocking] = useState(true);
  const [evidence, setEvidence] = useState("");
  const [status, setStatus] = useState("ACTIVE");
  const selected = data.dependencies.find((row) => row.id === selectedId);
  function select(row?: AwpRecord) {
    setSelectedId(row?.id ?? 0);
    setPredecessor(String(row?.predecessor_package_id ?? ""));
    setSuccessor(String(row?.successor_package_id ?? ""));
    setType(String(row?.dependency_type ?? "DELIVERABLE"));
    setBlocking(row ? Boolean(row.blocking) : true);
    setEvidence(String(row?.evidence_reference ?? ""));
    setStatus(row?.status ?? "ACTIVE");
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    await command(
      `/dependencies${selected ? `/${selected.id}` : ""}`,
      {
        predecessor_package_id: Number(predecessor),
        successor_package_id: Number(successor),
        dependency_type: type,
        blocking,
        evidence_reference: evidence,
        status,
        reason,
      },
      selected?.version,
      selected ? "PUT" : "POST"
    );
  }
  const options = data.packages.map((row) => ({ value: row.id, label: `${row.package_code} · ${row.package_type}` }));
  return (
    <section className="awpPanel">
      <h3>Package Dependencies</h3>
      <p>Dependencias tipificadas entre paquetes, sin una jerarquía EWP/PWP/CWP impuesta. No son relaciones CPM.</p>
      <div className="awpTable">
        <table aria-label="Package dependencies">
          <thead>
            <tr>
              <th>Predecesor</th>
              <th>Sucesor</th>
              <th>Tipo</th>
              <th>Bloquea</th>
              <th>Estado</th>
              <th>Detalle</th>
            </tr>
          </thead>
          <tbody>
            {data.dependencies.map((row) => (
              <tr key={row.id}>
                <td>{data.packages.find((item) => item.id === row.predecessor_package_id)?.package_code}</td>
                <td>{data.packages.find((item) => item.id === row.successor_package_id)?.package_code}</td>
                <td>{String(row.dependency_type)}</td>
                <td>{row.blocking ? "Sí" : "No"}</td>
                <td>{row.status}</td>
                <td>
                  <button type="button" onClick={() => select(row)}>
                    Editar dependencia #{row.id}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {can("dependency.edit") ? (
        <>
          <button type="button" onClick={() => select()}>
            Nueva dependencia
          </button>
          <form className="awpForm" onSubmit={(e) => void save(e).catch(() => undefined)}>
            <NamedSelect
              label="Dependency predecessor"
              value={predecessor}
              onChange={setPredecessor}
              optional={false}
              options={options}
            />
            <NamedSelect
              label="Dependency successor"
              value={successor}
              onChange={setSuccessor}
              optional={false}
              options={options.filter((row) => String(row.value) !== predecessor)}
            />
            <NamedSelect
              label="Dependency type"
              value={type}
              onChange={setType}
              optional={false}
              options={policyValues(data.configuration, "dependency_types", [
                "DELIVERABLE",
                "MATERIAL",
                "WORKFRONT",
                "INTERFACE",
                "SUPPORT",
              ]).map((value) => ({ value, label: value }))}
            />
            <Field label="Dependency blocking">
              <input type="checkbox" checked={blocking} onChange={(e) => setBlocking(e.target.checked)} />
            </Field>
            <Field label="Dependency evidence">
              <input aria-label="Dependency evidence" value={evidence} onChange={(e) => setEvidence(e.target.value)} />
            </Field>
            <NamedSelect
              label="Dependency status"
              value={status}
              onChange={setStatus}
              optional={false}
              options={["ACTIVE", "CLEARED", "CANCELLED"].map((value) => ({ value, label: value }))}
            />
            <button disabled={busy || reason.trim().length < 8} type="submit">
              Guardar dependencia Package
            </button>
          </form>
        </>
      ) : null}
    </section>
  );
}
