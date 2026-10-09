import type { ReactNode } from "react";

export type CompactHeaderMetric = {
  label: string;
  value: number | string;
};

export default function CompactModuleHeader({
  eyebrow,
  title,
  description,
  metrics,
  actions,
  tone = "admin",
}: {
  eyebrow: string;
  title: string;
  description: string;
  metrics: CompactHeaderMetric[];
  actions?: ReactNode;
  tone?: "admin" | "user";
}) {
  return (
    <header className={`compactModuleHeader ${tone}`}>
      <div className="compactHeaderCopy">
        <span className="compactHeaderEyebrow">{eyebrow}</span>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
      <div className="compactHeaderSide">
        <div className="compactHeaderMetrics" aria-label={`Métricas de ${title}`}>
          {metrics.map((metric) => (
            <article key={metric.label}>
              <strong>{metric.value}</strong>
              <span>{metric.label}</span>
            </article>
          ))}
        </div>
        {actions ? <div className="compactHeaderActions">{actions}</div> : null}
      </div>
    </header>
  );
}
