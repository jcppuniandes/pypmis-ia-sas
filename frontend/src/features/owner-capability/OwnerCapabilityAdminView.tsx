import GovernedPolicyEditor from "../risk-governance/GovernedPolicyEditor";
import { OWNER_CAPABILITY_POLICY_SECTIONS } from "./policySections";

export default function OwnerCapabilityAdminView({ token }: { token: string }) {
  return (
    <GovernedPolicyEditor
      token={token}
      root="/api/v1/owner-capability"
      title="Owner Capability Readiness Configuration"
      eyebrow="ADMIN MODE / Project Definition & Investment Case Configuration"
      boundary="Configure reusable Owner capability dimensions, requirements, maturity, evidence quality, tailoring, mitigation acceptance and review policy. ADMIN never creates or completes live Project assessments, assigns staff or changes Gate/FID policy."
      sections={OWNER_CAPABILITY_POLICY_SECTIONS}
    />
  );
}
