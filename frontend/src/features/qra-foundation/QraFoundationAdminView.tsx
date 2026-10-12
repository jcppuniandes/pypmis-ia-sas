import GovernedPolicyEditor from "../risk-governance/GovernedPolicyEditor";
import { QRA_API_ROOT } from "./api";
import { QRA_POLICY_SECTIONS } from "./policySections";

export default function QraFoundationAdminView({ token }: { token: string }) {
  return (
    <GovernedPolicyEditor
      token={token}
      root={QRA_API_ROOT}
      title="QRA Methodology & Source Readiness"
      eyebrow="ADMIN MODE / Project Definition & Investment Case Configuration"
      boundary="Configure source requirements, methodology, uncertainty ranges, distributions, correlations, applicability, independent review and validity. Distribution Rules edit the restrictions inside distribution_families; Review / Approval edits model_governance, with independence configured under SoD. Stage, Project Type, Governance Model and risk/complexity tailoring edit applicability; source-specific stage overrides belong inside each requirement's stage_rules. Execution Policy reuses reserved_engine_settings: engine_version, supported_analysis_types, iteration_policy (minimum/default/maximum/allow_override), seed_policy, percentiles, histogram_bins, chunk_size, max_correlation_dimension, convergence and independent result_review. Schedule execution requires explicit NORMALIZED_ELAPSED_TIME_V1, schedule_unit and schedule_unit_seconds; no inferred working calendar. Empty execution policy preserves existing Foundation validity but blocks execution. ADMIN never approves live Project models, executes simulation or approves contingency."
      sections={QRA_POLICY_SECTIONS}
    />
  );
}
