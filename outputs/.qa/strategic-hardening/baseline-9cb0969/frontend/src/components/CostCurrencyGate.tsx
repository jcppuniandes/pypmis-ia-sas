import { ShieldCheck } from "lucide-react";
import type { CostCurrencyGate as CostCurrencyGateType } from "../types";

type Props = {
  gate: CostCurrencyGateType;
  projectCurrency: string;
  pending?: boolean;
  onConfirm: (currency: string) => void;
};

export default function CostCurrencyGate({ gate, projectCurrency, pending = false, onConfirm }: Props) {
  const currency = gate.detected_currency || projectCurrency;
  return (
    <section className={`costCurrencyGate ${gate.state}`} aria-label="Cost and currency gate">
      <div>
        <span>Cost and currency gate</span>
        <strong>{gate.message}</strong>
      </div>
      <div className="gateFacts compact">
        <div>
          <span>Currency</span>
          <strong>{currency || "Select"}</strong>
        </div>
        <div>
          <span>Cost loaded</span>
          <strong>{gate.cost_loaded_activity_percent.toFixed(0)}%</strong>
        </div>
        <div>
          <span>Total cost</span>
          <strong>{gate.total_imported_cost.toLocaleString()}</strong>
        </div>
        <div>
          <span>Missing cost</span>
          <strong>{gate.missing_cost_activity_count}</strong>
        </div>
      </div>
      <button
        className="workflowAction"
        disabled={pending || !gate.schedule_import_id || gate.currency_confirmed}
        onClick={() => onConfirm(currency)}
        type="button"
      >
        <ShieldCheck size={16} />
        <span>{gate.currency_confirmed ? "Confirmed" : "Confirm Currency"}</span>
      </button>
    </section>
  );
}
