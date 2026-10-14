import { ExternalLink } from "lucide-react";
import { strategicRouteForView } from "../enterprise-strategy/navigation/strategicNavigationBlueprint";
import { qraEvidenceSourceHref } from "./qraSourceLink";
import "./qraEvidence.css";

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}
function text(value: unknown): string {
  if (value == null || value === "") return "NOT CAPTURED";
  if (typeof value === "boolean") return value ? "YES" : "NO";
  if (Array.isArray(value)) return value.map(text).join(" · ") || "None";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** Compact, read-only provider reference. This component never fetches or executes QRA. */
export default function QraEvidenceSummary({
  summary,
  applicability,
  onView,
}: {
  summary?: Record<string, unknown> | null;
  applicability?: Record<string, unknown> | null;
  onView?: () => void;
}) {
  const source = summary || {};
  const context = applicability || {};
  const current = source.source_current ?? source.current;
  const analysis = source.analysis_type || context.analysis_type;
  const review = record(source.accepted_review || source.review);
  const percentiles = source.selected_percentiles || source.percentiles;
  const probability = source.target_probabilities || source.target_probability;
  const warnings = source.warnings || [];
  const blockers = source.blockers || [];
  const sourceRoute = strategicRouteForView("qra-run-overview", "user");
  const directSource = qraEvidenceSourceHref(source);
  const sourceHref = directSource || sourceRoute || undefined;
  return (
    <section aria-label={`${text(analysis)} evidence summary`} className="qraEvidenceSummary">
      <dl>
        {[
          [
            "Applicability",
            context.outcome || context.applicability || context.requirement_status || source.applicability,
          ],
          ["Applicability reason", context.reason || context.reasons || context.applicability_reason],
          [
            "Engine capability fit",
            context.engine_capability_fit ||
              context.capability_fit ||
              source.capability_fit ||
              source.engine_capability_fit,
          ],
          ["Provider", source.provider_key || "QRA_RESULT_PROVIDER"],
          ["Provider status", source.provider_status || source.status],
          ["Evidence class", source.classification],
          ["Analysis type", analysis],
          ["Run", source.run_number || source.qra_run_number || source.run_id || source.qra_run_id || source.id],
          [
            "Model",
            source.model_number ||
              source.model_definition_id ||
              source.model_id ||
              source.qra_model_definition_id ||
              record(source.model).id,
          ],
          [
            "Accepted",
            source.accepted_status ??
              source.acceptance_status ??
              source.review_status ??
              review.status ??
              source.accepted,
          ],
          ["Current", current === true ? "CURRENT" : current === false ? "STALE" : "NOT EVALUATED"],
          ["Analytical readiness", source.analytical_readiness || source.readiness || source.readiness_status],
          ["Convergence", source.convergence_status || record(source.convergence).status || source.convergence],
          ["Scope", source.analysis_scope || source.scope || source.scope_type],
          [
            "Currency / unit",
            source.currency ||
              source.currency_code ||
              source.unit ||
              record(source.result_semantics).currency ||
              record(source.result_semantics).unit,
          ],
          ["As-of", source.as_of || source.as_of_date],
        ].map(([label, value]) => (
          <div key={String(label)}>
            <dt>{String(label)}</dt>
            <dd>{text(value)}</dd>
          </div>
        ))}
      </dl>
      <div className="qraEvidenceNumbers">
        <div>
          <strong>Selected percentiles</strong>
          <span>{text(percentiles)}</span>
        </div>
        <div>
          <strong>Target probabilities</strong>
          <span>{text(probability)}</span>
        </div>
      </div>
      <p className="qraCapabilityNotice">
        Tail-convergence limitation: CONVERGED certifies mean stability only; P90/P95 and tail convergence are not
        certified.
      </p>
      {analysis === "SCHEDULE_QRA" ? (
        <p className="qraCapabilityNotice">
          Schedule uses normalized elapsed time (HOURS/DAYS), not detailed P6 work calendars. Actual progress and
          non-source remaining durations are not supported.
        </p>
      ) : null}
      <p>
        <strong>Warnings:</strong> {text(warnings)}
      </p>
      <p>
        <strong>Blockers:</strong> {text(blockers)}
      </p>
      <details>
        <summary>Governed QRA reference</summary>
        <dl>
          {[
            ["Run hash", source.run_hash],
            ["Model version / hash", `${text(source.model_version)} / ${text(source.model_hash)}`],
            ["Engine version", source.engine_version],
            ["Methodology revision / hash", `${text(source.methodology_revision)} / ${text(source.methodology_hash)}`],
            [
              "Accepted review / hash",
              `${text(source.accepted_review_id || source.review_id)} / ${text(source.acceptance_hash || source.evidence_hash)}`,
            ],
            ["Provider contract", source.provider_contract_version],
          ].map(([label, value]) => (
            <div key={String(label)}>
              <dt>{String(label)}</dt>
              <dd>{text(value)}</dd>
            </div>
          ))}
        </dl>
      </details>
      {onView && !directSource ? (
        <button onClick={onView} type="button">
          <ExternalLink size={13} /> View QRA
        </button>
      ) : (
        <a href={sourceHref}>
          <ExternalLink size={13} /> View QRA
        </a>
      )}
      <small>Reference only: no approved contingency, Budget, schedule date or automatic Gate/FID decision.</small>
    </section>
  );
}
