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

function simplifiedStep(step: GuidedFlowStep) {
  const descriptor = `${step.key} ${step.label}`.toLowerCase();

  if (descriptor.includes("tenant")) {
    return {
      label: "Project access",
      summary: "Confirm the user is working in an assigned project.",
    };
  }

  if (descriptor.includes("project_setup") || descriptor.includes("setup") || descriptor.includes("project setup")) {
    return {
      label: "Project and WBS",
      summary: "Define project identity, roles and WBS controls.",
    };
  }

  if (descriptor.includes("schedule")) {
    return {
      label: "Load schedule",
      summary: "Import P6 XML/XER and Activity Sheet data.",
    };
  }

  if (descriptor.includes("cost_currency") || descriptor.includes("currency") || descriptor.includes("cost and")) {
    return {
      label: "Baseline gate",
      summary: "Confirm cost, currency and schedule quality before approval.",
    };
  }

  if (descriptor.includes("wbs") || descriptor.includes("cbs") || descriptor.includes("fbs")) {
    return {
      label: "CBS/FBS and CostCodes",
      summary: "Reconcile WBS, CBS, FBS, CostCode and commitments.",
    };
  }

  if (descriptor.includes("baseline")) {
    return {
      label: "Baseline approval",
      summary: "Freeze the controlled schedule and cost baseline.",
    };
  }

  if (descriptor.includes("progress")) {
    return {
      label: "Progress and EVM",
      summary: "Capture progress and calculate earned value.",
    };
  }

  if (descriptor.includes("integrated_control") || descriptor.includes("integrated control")) {
    return {
      label: "Business processes",
      summary: "Control approvals, versions, exports and recost history.",
    };
  }

  if (descriptor.includes("awp") || descriptor.includes("package")) {
    return {
      label: "AWP packages",
      summary: "Release packages through constraints and POC readiness.",
    };
  }

  if (descriptor.includes("evidence") || descriptor.includes("closeout")) {
    return {
      label: "Closeout evidence",
      summary: "Keep approvals, documents and audit evidence controlled.",
    };
  }

  switch (step.key) {
    case "setup":
      return {
        label: "Project and WBS",
        summary: "Define project identity, roles and WBS controls.",
      };
    case "schedule":
      return {
        label: "Load schedule",
        summary: "Import P6 XML/XER and Activity Sheet data.",
      };
    case "cost_currency":
      return {
        label: "Baseline gate",
        summary: "Confirm cost, currency and schedule quality before approval.",
      };
    case "baseline":
      return {
        label: "Baseline approval",
        summary: "Freeze the controlled schedule and cost baseline.",
      };
    case "progress":
      return {
        label: "Progress and EVM",
        summary: "Capture progress and calculate earned value.",
      };
    case "integrated_control":
      return {
        label: "CBS/FBS control",
        summary: "Reconcile WBS, CBS, FBS, CostCode and commitments.",
      };
    case "awp":
      return {
        label: "AWP packages",
        summary: "Release packages through constraints and POC readiness.",
      };
    case "evidence":
      return {
        label: "Closeout evidence",
        summary: "Keep approvals, documents and audit evidence controlled.",
      };
    default:
      return {
        label: step.label,
        summary: step.summary,
      };
  }
}

export default function GuidedProcessRail({ activeKey, steps, onNavigate }: Props) {
  const operationalSteps = steps.filter((step) => step.key !== "tenant");

  return (
    <aside className="guidedProcessRail" aria-label="Project information flow">
      <div className="navigatorHeader">
        <strong>Project Information Flow</strong>
        <span>Follow the project data</span>
      </div>
      {operationalSteps.map((step) => {
        const display = simplifiedStep(step);
        return (
          <button
            aria-label={`Open ${display.label}`}
            aria-current={activeKey === step.target_view ? "page" : undefined}
            className={`guidedRailItem ${step.state} ${activeKey === step.target_view ? "active" : ""}`}
            key={step.key}
            onClick={() => onNavigate(step.target_view)}
            type="button"
          >
            {stateIcon(step.state)}
            <span>
              <strong>{display.label}</strong>
              <small>{display.summary}</small>
            </span>
            <em>{step.blocking_count}</em>
          </button>
        );
      })}
    </aside>
  );
}
