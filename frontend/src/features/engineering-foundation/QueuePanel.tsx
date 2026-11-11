import { useState } from "react";
import { engineeringQuery, items, text } from "./api";
import { DateFilters, ReadState, Records } from "./controls";
import { useEngineeringData } from "./hooks";
import type { EngineeringPanel } from "./types";

export default function QueuePanel({ scope, kind }: { scope: EngineeringPanel; kind: "review" | "ifc" }) {
  const [asOf, setAsOf] = useState("");
  const status = useEngineeringData(
    scope.token,
    scope.base,
    engineeringQuery("/status", { as_of: asOf }),
    scope.refreshKey
  );
  const title = kind === "review" ? "Cola de revisión Engineering" : "Cola de liberación IFC";
  const queue = items(status.value)
    .filter((row) =>
      kind === "review"
        ? ["UNDER_REVIEW", "CHANGES_REQUESTED"].includes(text(row.status))
        : row.status === "APPROVED" && row.effective_ifc_revision_id !== row.revision_id
    )
    .map((row) => ({ ...row, code: row.deliverable_code, id: row.revision_id }));
  return (
    <section className="progressPanel" aria-label={title}>
      <h3>{title}</h3>
      <p>Vista técnica al corte. Las decisiones se registran sobre la revisión vigente con permisos propios.</p>
      <DateFilters asOf={asOf} setAsOf={setAsOf} />
      <ReadState {...status} reload={scope.reload} />
      {status.value ? (
        <Records
          label={title}
          items={queue}
          columns={[
            ["deliverable_code", "Código"],
            ["title", "Entregable"],
            ["revision_code", "Revisión"],
            ["discipline", "Disciplina"],
            ["status", "Estado técnico"],
            ["forecast_issue_date", "Emisión prevista"],
          ]}
          select={(row) => {
            scope.setDeliverableId(text(row.deliverable_id));
            scope.setRevisionId(text(row.revision_id));
          }}
        />
      ) : null}
    </section>
  );
}
