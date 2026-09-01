/* eslint-disable react-hooks/exhaustive-deps */
import { Copy, Eye, Save, Send } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { portfolioPlanningApi } from "../portfolio-planning/api";
import "../portfolio-planning/portfolioPlanning.css";
import { portfolioBudgetApi } from "./api";
import type { BudgetConfiguration } from "./types";
import "./portfolioBudget.css";

const sections = [
  "General",
  "Budget Currency",
  "Budget Target Rules",
  "Cost Source",
  "Time Phasing",
  "Scenario States",
  "Forced In / Forced Out",
  "Constraints",
  "Readiness",
  "Waterline",
  "Project Dependencies",
  "Dependency Types",
  "Dependency Policies",
  "CAPEX / EXPENSE",
  "Target Breakdown",
  "Warnings / Blockers",
  "Inheritance",
  "Permissions",
  "Preview",
];

function parse(value: string) {
  try {
    return JSON.parse(value) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export default function PortfolioBudgetAdminView({ token }: { token: string }) {
  const [records, setRecords] = useState<BudgetConfiguration[]>([]);
  const [selected, setSelected] = useState<BudgetConfiguration | null>(null);
  const [content, setContent] = useState("");
  const [portfolios, setPortfolios] = useState<Array<Record<string, unknown>>>([]);
  const [portfolioId, setPortfolioId] = useState(0);
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [message, setMessage] = useState("");
  const sequence = useRef(0);
  const parsed = useMemo(() => parse(content), [content]);

  async function load(preferredId?: number) {
    const current = ++sequence.current;
    const [items, portfolioItems] = await Promise.all([
      portfolioBudgetApi.configurations(token),
      portfolioPlanningApi.portfolioOptions(token),
    ]);
    if (current !== sequence.current) return;
    setRecords(items);
    setPortfolios(portfolioItems);
    setPortfolioId((value) => value || Number(portfolioItems[0]?.id || 0));
    const next =
      items.find((item) => item.id === preferredId) ||
      items.find((item) => item.status === "draft") ||
      items[0] ||
      null;
    setSelected(next);
    setContent(next ? JSON.stringify(next.content_json, null, 2) : "");
  }

  useEffect(() => {
    void load().catch((error) =>
      setMessage(error instanceof Error ? error.message : "Unable to load Gate 07G configuration")
    );
  }, [token]);

  function patch(mutator: (next: Record<string, unknown>) => void) {
    if (!parsed) {
      setMessage("Configuration JSON must be valid.");
      return;
    }
    const next = structuredClone(parsed);
    mutator(next);
    setContent(JSON.stringify(next, null, 2));
  }

  async function execute(action: "clone" | "save" | "publish") {
    if (!selected) return;
    try {
      let result = selected;
      if (action === "clone") result = await portfolioBudgetApi.cloneConfiguration(token, selected);
      if (action === "save") {
        if (!parsed) throw new Error("Configuration JSON is invalid.");
        result = await portfolioBudgetApi.updateConfiguration(token, selected, parsed);
      }
      if (action === "publish") result = await portfolioBudgetApi.publishConfiguration(token, selected);
      setSelected(result);
      setContent(JSON.stringify(result.content_json, null, 2));
      setMessage(`Gate 07G configuration ${action} completed.`);
      await load(result.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Unable to ${action} configuration`);
    }
  }

  async function previewDraft() {
    if (!selected || !parsed) return;
    try {
      setPreview(await portfolioBudgetApi.previewConfiguration(token, portfolioId || undefined, selected.id, parsed));
      setMessage("Preview completed; persisted=false and no Target or Scenario was created.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to preview configuration");
    }
  }

  const policy = (parsed?.budget_currency_policy as Record<string, unknown> | undefined) || {};
  const methods = (parsed?.allowed_time_phasing_methods as string[] | undefined) || [];
  const constraints = (parsed?.controlled_constraints as string[] | undefined) || [];
  const waterline = (parsed?.waterline as Record<string, unknown> | undefined) || {};
  const dependencies = (parsed?.dependencies as Record<string, unknown> | undefined) || {};
  const breakdown = (parsed?.capex_expense as Record<string, unknown> | undefined) || {};

  return (
    <section aria-label="Portfolio Budget Planning Configuration" className="portfolioBudget portfolioBudgetAdmin">
      <CompactModuleHeader
        description="Governed currency, Target rules, cost source hierarchy, explicit time phasing, scenario states, forced governance, controlled constraints, readiness and inheritance. No formulas, Funds, Resources, scenario winner or FID."
        eyebrow="ADMIN MODE · ENTERPRISE STRATEGY MANAGER · PORTFOLIO MANAGER · GATE 07G"
        metrics={[
          { label: "Revisions", value: records.length },
          { label: "Starter", value: "DRAFT" },
          { label: "Scope", value: "CAPITAL_OWNER" },
        ]}
        title="Portfolio Budget Planning Configuration"
        tone="admin"
      />
      <nav aria-label="Portfolio Budget configuration sections" className="planningAdminSections">
        {sections.map((item) => (
          <button key={item} type="button">
            {item}
          </button>
        ))}
      </nav>
      {message ? (
        <div className="planningMessage" role="status">
          {message}
        </div>
      ) : null}
      <div className="planningAdminGrid budgetAdminGrid">
        <aside>
          {records.map((item) => (
            <button
              className={selected?.id === item.id ? "active" : ""}
              key={item.id}
              onClick={() => {
                setSelected(item);
                setContent(JSON.stringify(item.content_json, null, 2));
                setPreview(null);
              }}
              type="button"
            >
              <strong>{item.name}</strong>
              <span>
                {item.status} · rev {item.revision}
              </span>
            </button>
          ))}
        </aside>
        <article className="budgetSurface">
          <header className="budgetSectionHeader">
            <div>
              <span>Controlled policy</span>
              <h3>{selected?.name || "No configuration"}</h3>
            </div>
            <strong>{selected?.status || ""}</strong>
          </header>
          <section aria-label="Structured Budget policy" className="budgetPolicyGrid">
            <label>
              Budget Currency
              <input
                disabled={selected?.status !== "draft"}
                value={String(policy.budget_currency || "")}
                onChange={(event) =>
                  patch((next) => {
                    next.budget_currency_policy = {
                      ...((next.budget_currency_policy as object) || {}),
                      budget_currency: event.target.value.toUpperCase(),
                      fx_conversion: false,
                    };
                  })
                }
              />
            </label>
            <label>
              Scenario max count
              <input
                disabled={selected?.status !== "draft"}
                max="20"
                min="1"
                type="number"
                value={String(parsed?.scenario_max_count || 20)}
                onChange={(event) =>
                  patch((next) => {
                    next.scenario_max_count = Number(event.target.value);
                  })
                }
              />
            </label>
            <label>
              Required cost coverage %
              <input
                disabled={selected?.status !== "draft"}
                max="100"
                min="0"
                type="number"
                value={String(parsed?.required_cost_coverage_percent || 100)}
                onChange={(event) =>
                  patch((next) => {
                    next.required_cost_coverage_percent = Number(event.target.value);
                  })
                }
              />
            </label>
            <label>
              Period granularity
              <select
                disabled={selected?.status !== "draft"}
                value={String(parsed?.period_granularity || "YEAR")}
                onChange={(event) =>
                  patch((next) => {
                    next.period_granularity = event.target.value;
                  })
                }
              >
                <option>YEAR</option>
                <option>QUARTER</option>
                <option>MONTH</option>
              </select>
            </label>
            <label className="wide">
              Allowed time phasing
              <input
                disabled={selected?.status !== "draft"}
                value={methods.join(", ")}
                onChange={(event) =>
                  patch((next) => {
                    next.allowed_time_phasing_methods = event.target.value
                      .split(",")
                      .map((item) => item.trim())
                      .filter(Boolean);
                  })
                }
              />
            </label>
            <label className="wide">
              Controlled constraints
              <input
                disabled={selected?.status !== "draft"}
                value={constraints.join(", ")}
                onChange={(event) =>
                  patch((next) => {
                    next.controlled_constraints = event.target.value
                      .split(",")
                      .map((item) => item.trim())
                      .filter(Boolean);
                  })
                }
              />
            </label>
            <label>
              Waterline visible
              <input
                checked={Boolean(waterline.show_waterline ?? true)}
                disabled={selected?.status !== "draft"}
                onChange={(event) =>
                  patch((next) => {
                    next.waterline = { ...((next.waterline as object) || {}), show_waterline: event.target.checked };
                  })
                }
                type="checkbox"
              />
            </label>
            <label>
              Dependency evaluation
              <input
                checked={Boolean(dependencies.enabled ?? true)}
                disabled={selected?.status !== "draft"}
                onChange={(event) =>
                  patch((next) => {
                    next.dependencies = { ...((next.dependencies as object) || {}), enabled: event.target.checked };
                  })
                }
                type="checkbox"
              />
            </label>
            <label>
              Mandatory unmet policy
              <select
                disabled={selected?.status !== "draft"}
                value={String(dependencies.mandatory_unmet_policy || "BLOCK_FREEZE")}
                onChange={(event) =>
                  patch((next) => {
                    next.dependencies = {
                      ...((next.dependencies as object) || {}),
                      mandatory_unmet_policy: event.target.value,
                    };
                  })
                }
              >
                <option>BLOCK_FREEZE</option>
                <option>WARN</option>
              </select>
            </label>
            <label>
              CAPEX / EXPENSE view
              <input
                checked={Boolean(breakdown.enabled ?? true)}
                disabled={selected?.status !== "draft"}
                onChange={(event) =>
                  patch((next) => {
                    next.capex_expense = { ...((next.capex_expense as object) || {}), enabled: event.target.checked };
                  })
                }
                type="checkbox"
              />
            </label>
            <label>
              Require target breakdown
              <input
                checked={Boolean(breakdown.require_target_breakdown ?? false)}
                disabled={selected?.status !== "draft"}
                onChange={(event) =>
                  patch((next) => {
                    next.capex_expense = {
                      ...((next.capex_expense as object) || {}),
                      require_target_breakdown: event.target.checked,
                    };
                  })
                }
                type="checkbox"
              />
            </label>
            <label className="wide">
              Preview Portfolio
              <select value={portfolioId} onChange={(event) => setPortfolioId(Number(event.target.value))}>
                <option value={0}>Configuration only</option>
                {portfolios.map((item) => (
                  <option key={Number(item.id)} value={Number(item.id)}>
                    {String(item.name)}
                  </option>
                ))}
              </select>
            </label>
          </section>
          <details className="budgetJson">
            <summary>Advanced controlled JSON</summary>
            <textarea
              aria-label="Portfolio Budget configuration JSON"
              disabled={selected?.status !== "draft"}
              onChange={(event) => setContent(event.target.value)}
              rows={28}
              value={content}
            />
          </details>
          <div aria-label="Portfolio Budget configuration actions" className="planningActions">
            <button
              disabled={!selected || selected.status !== "published"}
              onClick={() => void execute("clone")}
              type="button"
            >
              <Copy size={14} /> Clone
            </button>
            <button disabled={!selected || !parsed} onClick={() => void previewDraft()} type="button">
              <Eye size={14} /> Preview
            </button>
            <button
              disabled={!selected || selected.status !== "draft" || !parsed}
              onClick={() => void execute("save")}
              type="button"
            >
              <Save size={14} /> Save
            </button>
            <button
              disabled={!selected || selected.status !== "draft" || !parsed}
              onClick={() => void execute("publish")}
              type="button"
            >
              <Send size={14} /> Publish
            </button>
          </div>
          {preview ? (
            <details open>
              <summary>Effective policy Preview</summary>
              <pre>{JSON.stringify(preview, null, 2)}</pre>
            </details>
          ) : null}
        </article>
      </div>
    </section>
  );
}
