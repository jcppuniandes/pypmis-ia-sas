import { CheckCircle2, CircleAlert, CircleDot } from "lucide-react";
import type { GuidedFlowStep } from "../types";

type Props = {
  activeKey: string;
  steps: GuidedFlowStep[];
  onNavigate: (targetView: string) => void;
};

function stateIcon(state: string) {
  if (state === "complete") return <CheckCircle2 size={16} />;
  if (state === "blocked") return <CircleAlert size={16} />;
  return <CircleDot size={16} />;
}

export default function GuidedProcessRail({ activeKey, steps, onNavigate }: Props) {
  return (
    <aside className="guidedProcessRail" aria-label="Guided control flow">
      <div className="navigatorHeader">
        <strong>Guided Flow</strong>
        <span>Next controlled steps</span>
      </div>
      {steps.map((step) => (
        <button
          aria-label={`Open ${step.label}`}
          aria-current={activeKey === step.target_view ? "page" : undefined}
          className={`guidedRailItem ${step.state} ${activeKey === step.target_view ? "active" : ""}`}
          key={step.key}
          onClick={() => onNavigate(step.target_view)}
          type="button"
        >
          {stateIcon(step.state)}
          <span>
            <strong>{step.label}</strong>
            <small>{step.summary}</small>
          </span>
          <em>{step.blocking_count}</em>
        </button>
      ))}
    </aside>
  );
}
