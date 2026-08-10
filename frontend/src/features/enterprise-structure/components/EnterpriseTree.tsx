import {
  Boxes,
  BriefcaseBusiness,
  Building2,
  ChevronDown,
  ChevronRight,
  Factory,
  FolderKanban,
  HardHat,
  House,
} from "lucide-react";
import { useState } from "react";
import type { EnterpriseTreeNode } from "../types";

type Props = {
  nodes: EnterpriseTreeNode[];
  onSelect: (nodeId: number) => void;
  selectedNodeId: number | null;
};

export default function EnterpriseTree({ nodes, onSelect, selectedNodeId }: Props) {
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());

  function nodeIcon(type: string) {
    if (type === "business-unit") return <BriefcaseBusiness size={15} />;
    if (type === "portfolio") return <FolderKanban size={15} />;
    if (type === "program") return <Boxes size={15} />;
    if (type === "project") return <HardHat size={15} />;
    if (type === "property") return <House size={15} />;
    if (type === "facility") return <Factory size={15} />;
    return <Building2 size={15} />;
  }

  function renderNodes(items: EnterpriseTreeNode[]) {
    return items.map((node) => {
      const hasChildren = node.children.length > 0;
      const isCollapsed = collapsed.has(node.id);
      return (
        <div key={node.id} role="treeitem" aria-expanded={hasChildren ? !isCollapsed : undefined}>
          <div
            className={node.id === selectedNodeId ? "enterpriseTreeRow selected" : "enterpriseTreeRow"}
            style={{ paddingLeft: `${12 + node.depth * 18}px` }}
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
              {nodeIcon(node.workspace_type_code)}
              <span className="enterpriseTreeCopy">
                <strong>{node.name}</strong>
                <small>
                  <code className="enterpriseRecordCode">{node.record_code}</code>
                  <span>
                    {node.code} · {node.workspace_type_code}
                  </span>
                  <em className={node.status}>{node.status}</em>
                </small>
              </span>
            </button>
          </div>
          {hasChildren && !isCollapsed ? renderNodes(node.children) : null}
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
