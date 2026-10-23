import type { ReactNode } from "react";
import { text, type CostRow } from "./types";

export default function CbsTree({ rows, select }: { rows: CostRow[]; select: (row: CostRow) => void }) {
  const children = (parent: CostRow | null, visited: Set<string>): ReactNode => {
    const parentId = parent?.id ?? null;
    const items = rows
      .filter((row) => (row.parent_id ?? null) === parentId && !visited.has(String(row.id)))
      .sort(
        (left, right) =>
          Number(left.sort_order ?? 0) - Number(right.sort_order ?? 0) ||
          text(left, "code").localeCompare(text(right, "code"))
      );
    if (!items.length) return null;
    return (
      <ul>
        {items.map((row) => {
          const descendants = children(row, new Set([...visited, String(row.id)]));
          const button = (
            <button type="button" onClick={() => select(row)}>
              {text(row, "code")} · {text(row, "name")}
            </button>
          );
          return (
            <li key={String(row.id)}>
              {descendants ? (
                <details open>
                  <summary>{button}</summary>
                  {descendants}
                </details>
              ) : (
                button
              )}
            </li>
          );
        })}
      </ul>
    );
  };
  return (
    <section className="costCbsTree" aria-label="CBS hierarchy">
      <h4>Árbol CBS · independiente de WBS</h4>
      {rows.length ? children(null, new Set()) : <p>Sin nodos CBS.</p>}
    </section>
  );
}
