import type { EnterpriseNode } from "../types";

export default function EnterpriseTable({
  nodes,
  onSelect,
}: {
  nodes: EnterpriseNode[];
  onSelect: (nodeId: number) => void;
}) {
  return (
    <div className="enterpriseTableWrap">
      <table className="enterpriseTable">
        <thead>
          <tr>
            <th>Código</th>
            <th>Nombre</th>
            <th>Tipo</th>
            <th>Región</th>
            <th>Estado</th>
            <th>Versión</th>
          </tr>
        </thead>
        <tbody>
          {nodes.map((node) => (
            <tr
              key={node.id}
              onClick={() => onSelect(node.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") onSelect(node.id);
              }}
              tabIndex={0}
            >
              <td>{node.code}</td>
              <td>{node.name}</td>
              <td>{node.workspace_type_code}</td>
              <td>{node.region_code || "—"}</td>
              <td>
                <span className={`enterpriseStatus ${node.status}`}>{node.status}</span>
              </td>
              <td>{node.version}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
