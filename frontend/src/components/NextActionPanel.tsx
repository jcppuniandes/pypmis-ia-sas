import { ArrowRight } from "lucide-react";
import type { GuidedFlowStep, GuidedNextAction } from "../types";

type Props = {
  action: GuidedNextAction;
  step: GuidedFlowStep;
  onNavigate: (targetView: string) => void;
};

function actionPhaseLabel(step: GuidedFlowStep) {
  const descriptor = `${step.key} ${step.label}`.toLowerCase();
  if (descriptor.includes("project_setup") || descriptor.includes("setup") || descriptor.includes("project setup")) {
    return "Project and WBS";
  }
  if (descriptor.includes("schedule")) return "Load schedule";
  if (descriptor.includes("cost_currency") || descriptor.includes("currency") || descriptor.includes("cost and")) {
    return "Baseline gate";
  }
  if (descriptor.includes("wbs") || descriptor.includes("cbs") || descriptor.includes("fbs")) {
    return "CBS/FBS and CostCodes";
  }
  if (descriptor.includes("baseline")) return "Baseline approval";
  if (descriptor.includes("progress")) return "Progress and EVM";
  if (descriptor.includes("integrated_control") || descriptor.includes("integrated control"))
    return "Business processes";
  if (descriptor.includes("awp") || descriptor.includes("package")) return "AWP packages";
  if (descriptor.includes("evidence") || descriptor.includes("closeout")) return "Closeout evidence";
  if (step.key === "cost_currency") return "Baseline gate";
  if (step.key === "integrated_control") return "CBS/FBS control";
  if (step.key === "awp") return "AWP packages";
  if (step.key === "evidence") return "Closeout evidence";
  if (step.key === "progress") return "Progress and EVM";
  if (step.key === "schedule") return "Load schedule";
  if (step.key === "setup") return "Project and WBS";
  return step.label;
}

export default function NextActionPanel({ action, step, onNavigate }: Props) {
  const label = actionPhaseLabel(step);
  return (
    <section className="nextActionPanel" aria-label="Next controlled action">
      <span>Next controlled action / {step.owner_role}</span>
      <strong>{label}</strong>
      <p>{action.reason || step.summary}</p>
      <button
        aria-label={`Open ${label}`}
        className="workflowAction primary"
        disabled={action.disabled}
        onClick={() => onNavigate(action.target_view)}
        type="button"
      >
        <ArrowRight size={16} />
        <span>Open {label}</span>
      </button>
    </section>
  );
}
