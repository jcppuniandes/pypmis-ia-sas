import { useState, type FormEvent } from "react";
import { policyContent, type JsonRecord, type ScheduleOverview, type WorkspaceProps } from "./types";

export default function MappingPanel({
  data,
  selected,
  busy,
  can,
  command,
  targetKind,
  targetId,
}: WorkspaceProps & { targetKind: "WBS" | "ACTIVITY"; targetId: string }) {
  const mappings = (selected?.mappings ?? data.mappings).filter(
    (mapping) =>
      mapping.target_kind === targetKind &&
      mapping.target_external_id === targetId &&
      (!mapping.schedule_version_id || mapping.schedule_version_id === selected?.id)
  );
  const currentMapping = mappings.filter((row) => row.status !== "REMOVED").slice(-1)[0];
  const [plans, setPlans] = useState<number[]>(currentMapping?.plan_item_ids ?? []);
  const [scopes, setScopes] = useState<number[]>(currentMapping?.scope_item_ids ?? []);
  const [reason, setReason] = useState("");
  if (!selected || !targetId) return <p>Selecciona un objeto de la versión para consultar o preparar su mapeo.</p>;
  const policy = (policyContent(data.configuration).mapping_policy ?? {}) as JsonRecord;
  const publishedPlanRequired = policy.published_plan_required !== false;
  const currentScopeIds = data.current_scope_item_ids;
  const currentScope = (id: number) =>
    currentScopeIds
      ? currentScopeIds.includes(id)
      : data.scope_items.some((row) => row.id === id && row.status === "APPROVED");
  const eligiblePlan = (plan: ScheduleOverview["plan_items"][number]) =>
    plan.status !== "SUPERSEDED" &&
    (!publishedPlanRequired || plan.status === "PUBLISHED") &&
    (plan.allocations ?? []).every((link) => currentScope(link.scope_item_id));
  function toggle(values: number[], id: number) {
    return values.includes(id) ? values.filter((value) => value !== id) : [...values, id];
  }
  function save(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    void command(
      `/versions/${selected.id}/mappings`,
      { target_kind: targetKind, target_external_id: targetId, plan_item_ids: plans, scope_item_ids: scopes, reason },
      selected.version
    ).catch(() => undefined);
  }
  const editable = can("mapping.edit") && ["DRAFT", "STAGED", "VALIDATED", "UNDER_REVIEW"].includes(selected.status);
  return (
    <section aria-label={`Mapeo ${targetKind} ${targetId}`}>
      <h4>
        {targetKind} {targetId} · trazabilidad M:N
      </h4>
      {mappings.length ? (
        mappings.map((mapping, index) => (
          <p key={mapping.id ?? index}>
            Estado {mapping.status ?? "REQUIRES_REVIEW"} · Plan Items{" "}
            {mapping.plan_item_ids.join(", ") || "sin vínculo"} · Scope directo{" "}
            {mapping.scope_item_ids.join(", ") || "sin vínculo directo"}
          </p>
        ))
      ) : (
        <p>UNMAPPED · no se promueve una versión sin satisfacer la política de mapeo.</p>
      )}
      <p>
        Plan Items conserva la descomposición de ejecución; Scope conserva entregables y cantidades. Un vínculo directo
        no puede contradecir los Plan Items.
      </p>
      {editable ? (
        <form onSubmit={save}>
          <fieldset disabled={busy}>
            <legend>Plan Items vinculados</legend>
            <div className="scheduleCheckGrid">
              {data.plan_items.map((plan) => (
                <label key={plan.id}>
                  <input
                    aria-label={`Mapear Plan Item ${plan.code}`}
                    type="checkbox"
                    checked={plans.includes(plan.id)}
                    disabled={!eligiblePlan(plan) && !plans.includes(plan.id)}
                    onChange={() => setPlans(toggle(plans, plan.id))}
                  />
                  <span>
                    {plan.code} · {plan.name} · {plan.status ?? "UNKNOWN"}
                    {!eligiblePlan(plan) ? " · no elegible según política/Scope vigente" : ""}
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
          {policy.allow_direct_scope !== false ? (
            <fieldset disabled={busy}>
              <legend>Scope Items directos según política</legend>
              <div className="scheduleCheckGrid">
                {data.scope_items
                  .filter((item) => currentScope(item.id) || scopes.includes(item.id))
                  .map((item) => (
                    <label key={item.id}>
                      <input
                        aria-label={`Mapear Scope Item ${item.scope_code}`}
                        type="checkbox"
                        checked={scopes.includes(item.id)}
                        disabled={!currentScope(item.id) && !scopes.includes(item.id)}
                        onChange={() => setScopes(toggle(scopes, item.id))}
                      />
                      <span>
                        {item.scope_code} · {item.name} · {item.scope_nature}
                        {!currentScope(item.id) ? " · fuera de Scope Baseline vigente" : ""}
                      </span>
                    </label>
                  ))}
              </div>
            </fieldset>
          ) : (
            <p>El Schedule Profile no admite vínculos directos; usa Plan Items publicados.</p>
          )}
          <div className="scheduleActions">
            <label className="scheduleControl">
              Motivo mapping
              <input required minLength={8} value={reason} onChange={(event) => setReason(event.target.value)} />
            </label>
            <button type="submit" disabled={busy || (!plans.length && !scopes.length)}>
              Guardar mapping Schedule M:N
            </button>
            {currentMapping ? (
              <button
                type="button"
                disabled={busy || reason.trim().length < 8}
                onClick={() =>
                  void command(
                    `/versions/${selected.id}/mappings`,
                    {
                      target_kind: targetKind,
                      target_external_id: targetId,
                      plan_item_ids: [],
                      scope_item_ids: [],
                      action: "REMOVE",
                      reason,
                    },
                    selected.version
                  ).catch(() => undefined)
                }
              >
                Retirar mapping Schedule con trazabilidad
              </button>
            ) : null}
          </div>
        </form>
      ) : (
        <p>Los vínculos de esta versión son de solo lectura. Una corrección requiere una nueva versión.</p>
      )}
    </section>
  );
}
