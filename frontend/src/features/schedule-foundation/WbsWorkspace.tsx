import { useState } from "react";
import MappingPanel from "./MappingPanel";
import { display, type ScheduleObject, type WorkspaceProps } from "./types";
import { wbsHierarchy } from "./wbsTree";

export default function WbsWorkspace(props: WorkspaceProps) {
  const [target, setTarget] = useState("");
  const rows = props.selected?.snapshot_json.wbs ?? [];
  const tree = wbsHierarchy(rows);
  const branches = (nodes: ScheduleObject[], ancestors: string[] = []) =>
    nodes.map((row) => (
      <li key={row.external_id} role="treeitem">
        <button
          type="button"
          aria-label={`Inspeccionar WBS ${row.code ?? row.external_id}`}
          onClick={() => setTarget(row.external_id)}
        >
          {row.code ?? row.external_id} · {row.name ?? "WBS"}
        </button>
        <small>
          {" "}
          P6 {row.external_id} · {display(row.path)}
        </small>
        {!ancestors.includes(row.external_id) && tree.children(row.external_id).length ? (
          <ul role="group">{branches(tree.children(row.external_id), [...ancestors, row.external_id])}</ul>
        ) : null}
      </li>
    ));
  return (
    <section className="schedulePanel">
      <h3>WBS · organización del cronograma</h3>
      <p>
        El árbol WBS no equivale a la jerarquía Scope. Los movimientos y cambios se preparan en una versión sucesora.
      </p>
      {rows.length ? (
        <ul className="scheduleWbsTree" role="tree" aria-label="WBS hierarchy">
          {branches(tree.roots)}
        </ul>
      ) : (
        <p>Sin WBS en la versión seleccionada.</p>
      )}
      {rows.length && !tree.roots.length ? (
        <p role="alert">Estructura sin raíz válida; consulta la validación antes de aceptar.</p>
      ) : null}
      <MappingPanel key={`${props.selected?.id}:${target}`} {...props} targetKind="WBS" targetId={target} />
    </section>
  );
}
