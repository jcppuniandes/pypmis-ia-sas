import { Building2, ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";
import type { EnterpriseTreeNode } from "../types";

type Props = {
  nodes: EnterpriseTreeNode[];
  onSelect: (nodeId: number) => void;
  selectedNodeId: number | null;
};

export default function EnterpriseTree({ nodes, onSelect, selectedNodeId }: Props) {
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());

  function renderNodes(items: EnterpriseTreeNode[], depth = 0) {
    return items.map((node) => {
      const hasChildren = node.children.length > 0;
      const isCollapsed = collapsed.has(node.id);
      return (
        <div key={node.id} role="treeitem" aria-expanded={hasChildren ? !isCollapsed : undefined}>
          <div
            className={node.id === selectedNodeId ? "enterpriseTreeRow selected" : "enterpriseTreeRow"}
            style={{ paddingLeft: `${12 + depth * 18}px` }}
          >
            <button
              aria-label={`${isCollapsed ? "Expandir" : "Contraer"} ${node.name}`}
              className="enterpriseTreeToggle"
              disabled={!hasChildren}
              onClick={() =>
                setCollapsed((current) => {
                  const next = new Set(current);
                  if (next.has(node.id)) next.delete(node.id);
                  else next.add(node.id);
                  return next;
                })
              }
              type="button"
            >
              {hasChildren ? isCollapsed ? <ChevronRight size={15} /> : <ChevronDown size={15} /> : <span />}
            </button>
            <button className="enterpriseTreeSelect" onClick={() => onSelect(node.id)} type="button">
              <Building2 size={15} />
              <span>
                <strong>{node.name}</strong>
                <small>
                  {node.code} · {node.workspace_type_code}
                </small>
              </span>
              <em className={node.status}>{node.status}</em>
            </button>
          </div>
          {hasChildren && !isCollapsed ? renderNodes(node.children, depth + 1) : null}
        </div>
      );
    });
  }

  return (
    <div className="enterpriseTree" role="tree" aria-label="Enterprise hierarchy">
      {nodes.length ? renderNodes(nodes) : <p>No hay nodos que coincidan con los filtros.</p>}
    </div>
  );
}
