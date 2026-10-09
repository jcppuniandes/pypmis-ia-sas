import GovernedPolicyEditor, { type PolicySection } from "../risk-governance/GovernedPolicyEditor";

const BASIC_DATA_POLICY_SECTIONS: readonly PolicySection[] = [
  ["General", "scope"],
  ["Data Categories", "categories"],
  ["Requirements", "requirements"],
  ["Applicability", "applicability"],
  ["FEL Stage Rules", "requirements"],
  ["Gate Profile Rules", "requirements"],
  ["Project Type Rules", "applicability.project_types"],
  ["Governance Model Rules", "applicability.governance_models"],
  ["Industry / Sector Rules", "requirements"],
  ["Availability Rules", "requirements"],
  ["Validation Rules", "requirements"],
  ["Quality Rules", "requirements"],
  ["Confidence Rules", "requirements"],
  ["Freshness Rules", "requirements"],
  ["Blocking Rules", "requirements"],
  ["Coverage Rules", "coverage_rules"],
  ["Numbering", "numbering"],
  ["Inheritance", "inherit_to_descendants"],
  ["Review / SoD", "separation_of_duties"],
  ["Preview", null],
  ["History", null],
];
export default function BasicDataAdminView({ token }: { token: string }) {
  return (
    <GovernedPolicyEditor
      token={token}
      root="/api/v1/basic-data"
      title="Basic Data Readiness Configuration"
      eyebrow="ADMIN MODE / Project Definition & Investment Case Configuration"
      boundary="ADMIN owns reusable categories, requirements, applicability, quality, confidence, freshness and blocking policy. This surface never creates or completes live Project Basic Data items or assessments."
      sections={BASIC_DATA_POLICY_SECTIONS}
    />
  );
}
