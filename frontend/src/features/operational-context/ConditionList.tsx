import type { OperationalCondition } from "./types";

export function ConditionList({ title, items }: { title: string; items: OperationalCondition[] }) {
  return (
    <section className="operationalConditions" aria-label={title}>
      <h3>{title}</h3>
      {items.length ? (
        <ul>
          {items.map((item, index) => (
            <li key={index}>{typeof item === "string" ? item : JSON.stringify(item)}</li>
          ))}
        </ul>
      ) : (
        <p>No hay condiciones reportadas por la fuente.</p>
      )}
    </section>
  );
}
