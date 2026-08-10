import type { Classification, EnterpriseNode } from "../types";

function compareRecordCodes(left: string, right: string) {
  const leftParts = left.split(".").map(Number);
  const rightParts = right.split(".").map(Number);
  const length = Math.max(leftParts.length, rightParts.length);
  for (let index = 0; index < length; index += 1) {
    const difference = (leftParts[index] ?? -1) - (rightParts[index] ?? -1);
    if (difference) return difference;
  }
  return 0;
}

export default function EnterpriseTable({
  nodes,
  allNodes = nodes,
  classifications = [],
  admin = false,
  onSelect,
}: {
  nodes: EnterpriseNode[];
  allNodes?: EnterpriseNode[];
  classifications?: Classification[];
  admin?: boolean;
  onSelect: (nodeId: number) => void;
}) {
  const byId = new Map(allNodes.map((node) => [node.id, node]));
  const orderedNodes = [...nodes].sort((left, right) => compareRecordCodes(left.record_code, right.record_code));
  return (
    <div className="enterpriseTableWrap">
      <table className="enterpriseTable">
        <thead>
          <tr>
            <th>Record Code</th>
            <th>Nombre</th>
            <th>Tipo</th>
            <th>Parent</th>
            <th>Estado</th>
            <th>Responsible Area</th>
            {admin ? <th>Actions</th> : null}
          </tr>
        </thead>
        <tbody>
          {orderedNodes.map((node) => {
            const responsibleArea = classifications.find(
              (item) => item.workspace_id === node.id && item.category_set_code === "responsible-area"
            );
            return (
              <tr
                key={node.id}
                onClick={() => onSelect(node.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") onSelect(node.id);
                }}
                tabIndex={0}
              >
                <td>
                  <code className="enterpriseRecordCode">{node.record_code}</code>
                </td>
                <td>{node.name}</td>
                <td>{node.workspace_type_code}</td>
                <td>{node.parent_id ? (byId.get(node.parent_id)?.name ?? "—") : "Raíz"}</td>
                <td>
                  <span className={`enterpriseStatus ${node.status}`}>{node.status}</span>
                </td>
                <td>{responsibleArea?.category_item_code ?? "—"}</td>
                {admin ? (
                  <td>
                    <button className="enterpriseTableAction" onClick={() => onSelect(node.id)} type="button">
                      Editar
                    </button>
                  </td>
                ) : null}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
