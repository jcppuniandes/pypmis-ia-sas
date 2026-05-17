import { ArrowRight } from "lucide-react";
import type { GuidedFlowStep, GuidedNextAction } from "../types";

type Props = {
  action: GuidedNextAction;
  step: GuidedFlowStep;
  onNavigate: (targetView: string) => void;
};

export default function NextActionPanel({ action, step, onNavigate }: Props) {
  return (
    <aside className="nextActionPanel" aria-label="Next action">
      <span>{step.owner_role}</span>
      <strong>{action.label}</strong>
      <p>{action.reason || step.summary}</p>
      <button className="workflowAction primary" disabled={action.disabled} onClick={() => onNavigate(action.target_view)} type="button">
        <ArrowRight size={16} />
        <span>Go</span>
      </button>
    </aside>
  );
}
