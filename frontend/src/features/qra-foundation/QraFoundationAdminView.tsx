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
      boundary="Configure source requirements, methodology, uncertainty ranges, distributions, correlations, applicability, independent review and validity. ADMIN never approves live Project models. Reserved engine settings do not execute simulation or calculate contingency."
      sections={QRA_POLICY_SECTIONS}
    />
  );
}
