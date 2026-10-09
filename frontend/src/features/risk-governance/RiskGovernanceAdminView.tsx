import GovernedPolicyEditor, { type PolicySection } from "./GovernedPolicyEditor";

const RISK_POLICY_SECTIONS: readonly PolicySection[] = [
  ["General", "scope"],
  ["Risk Capacity", "capacity_statements"],
  ["Risk Appetite", "appetite_statements"],
  ["Risk Thresholds", "thresholds"],
  ["Threshold Types / Operators", "thresholds"],
  ["Risk Dimensions", "dimensions"],
  ["Applicability", "applicability"],
  ["Strategic Theme Overrides", "applicability.strategic_themes"],
  ["Project Type Overrides", "applicability.project_types"],
  ["Governance Model Overrides", "applicability.governance_models"],
  ["Portfolio Overrides", "scope"],
  ["Escalation Rules", "escalation_rules"],
  ["Effective From", "effective_from"],
  ["Effective To", "effective_to"],
  ["Inheritance", "inherit_to_descendants"],
  ["Review / SoD", "separation_of_duties"],
  ["Preview", null],
  ["History", null],
];
export default function RiskGovernanceAdminView({ token }: { token: string }) {
  return (
    <GovernedPolicyEditor
      token={token}
      root="/api/v1/risk-governance"
      title="Risk Governance Configuration"
      eyebrow="ADMIN MODE / Enterprise Strategy Foundation / Risk Governance"
      boundary="ADMIN configures Risk Capacity, Appetite and Threshold policy only. This is not a Risk Register, Risk Readiness, QRA or Gate decision. USER consumes published policy read-only."
      sections={RISK_POLICY_SECTIONS}
    />
  );
}
