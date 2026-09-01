/* eslint-disable react-hooks/exhaustive-deps */
import { Copy, Eye, Save, Send } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { portfolioPlanningApi } from "../portfolio-planning/api";
import "../portfolio-planning/portfolioPlanning.css";
import { portfolioResourceApi } from "./api";
import type { ResourceConfiguration } from "./types";
import "./portfolioResource.css";

const sections = [
  "General",
  "Resource Roles",
  "Capacity",
  "Demand",
  "Units",
  "Timing",
  "Overload",
  "Scenarios",
  "Readiness",
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

export default function PortfolioResourceAdminView({ token }: { token: string }) {
  const [records, setRecords] = useState<ResourceConfiguration[]>([]);
  const [selected, setSelected] = useState<ResourceConfiguration | null>(null);
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
      portfolioResourceApi.configurations(token),
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
      setMessage(error instanceof Error ? error.message : "Unable to load Gate 07H configuration")
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
      if (action === "clone") result = await portfolioResourceApi.cloneConfiguration(token, selected);
      if (action === "save") {
        if (!parsed) throw new Error("Configuration JSON is invalid.");
        result = await portfolioResourceApi.updateConfiguration(token, selected, parsed);
      }
      if (action === "publish") result = await portfolioResourceApi.publishConfiguration(token, selected);
      setMessage(`Gate 07H configuration ${action} completed.`);
      await load(result.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Unable to ${action} configuration`);
    }
  }

  async function previewDraft() {
    if (!selected || !parsed) return;
    try {
      setPreview(await portfolioResourceApi.previewConfiguration(token, portfolioId || undefined, selected.id, parsed));
      setMessage("Preview completed; persisted=false and no capacity, demand or scenario record was created.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to preview configuration");
    }
  }

  const roles = (parsed?.resource_roles as Array<Record<string, unknown>> | undefined) || [];
  const units = (parsed?.allowed_units as string[] | undefined) || [];
  const timing = (parsed?.allowed_timing_methods as string[] | undefined) || [];
  const constraints = (parsed?.controlled_constraints as string[] | undefined) || [];

  return (
    <section
      aria-label="Portfolio Resource Planning Configuration"
      className="portfolioResource portfolioResourceAdmin"
    >
      <CompactModuleHeader
        description="Governed strategic resource roles, capacity/demand sources, explicit units, timing, overload policy, scenarios, readiness and inheritance. No named-person allocation, silent unit conversion, schedule leveling, winner, Funds or FID."
        eyebrow="ADMIN MODE · ENTERPRISE STRATEGY MANAGER · PORTFOLIO MANAGER · GATE 07H"
        metrics={[
          { label: "Revisions", value: records.length },
          { label: "Roles", value: roles.length },
          { label: "Scope", value: "CAPITAL_OWNER" },
        ]}
        title="Portfolio Resource Planning Configuration"
        tone="admin"
      />
      <nav aria-label="Portfolio Resource configuration sections" className="planningAdminSections">
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
      <div className="planningAdminGrid resourceAdminGrid">
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
        <article className="resourceSurface">
          <header className="resourceSectionHeader">
            <div>
              <span>Controlled strategic resource policy</span>
              <h3>{selected?.name || "No configuration"}</h3>
            </div>
            <strong>{selected?.status || ""}</strong>
          </header>
          <section aria-label="Structured Resource policy" className="resourcePolicyGrid">
            <label>
              Default Unit
              <select
                aria-label="Default Unit"
                disabled={selected?.status !== "draft"}
                value={String(parsed?.default_unit || "FTE")}
                onChange={(event) =>
                  patch((next) => {
                    next.default_unit = event.target.value;
                  })
                }
              >
                {units.map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </label>
            <label>
              Period Granularity
              <select
                aria-label="Period Granularity"
                disabled={selected?.status !== "draft"}
                value={String(parsed?.period_granularity || "MONTH")}
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
            <label>
              Demand coverage %
              <input
                aria-label="Demand coverage percentage"
                disabled={selected?.status !== "draft"}
                max="100"
                min="0"
                type="number"
                value={String(parsed?.required_demand_coverage_percent || 100)}
                onChange={(event) =>
                  patch((next) => {
                    next.required_demand_coverage_percent = Number(event.target.value);
                  })
                }
              />
            </label>
            <label>
              Scenario max count
              <input
                aria-label="Scenario max count"
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
              Overload Policy
              <select
                aria-label="Overload Policy"
                disabled={selected?.status !== "draft"}
                value={String(parsed?.overload_policy || "ALLOW_WITH_WARNING")}
                onChange={(event) =>
                  patch((next) => {
                    next.overload_policy = event.target.value;
                  })
                }
              >
                <option>ALLOW_WITH_WARNING</option>
                <option>BLOCK_READY_STATE</option>
              </select>
            </label>
            <label>
              Maximum utilization %
              <input
                aria-label="Maximum utilization percentage"
                disabled={selected?.status !== "draft"}
                min="1"
                type="number"
                value={String(parsed?.maximum_utilization_percent || 100)}
                onChange={(event) =>
                  patch((next) => {
                    next.maximum_utilization_percent = Number(event.target.value);
                  })
                }
              />
            </label>
            <label className="wide">
              Allowed units
              <input
                aria-label="Allowed units"
                disabled={selected?.status !== "draft"}
                value={units.join(", ")}
                onChange={(event) =>
                  patch((next) => {
                    next.allowed_units = event.target.value
                      .split(",")
                      .map((item) => item.trim())
                      .filter(Boolean);
                  })
                }
              />
            </label>
            <label className="wide">
              Allowed timing methods
              <input
                aria-label="Allowed timing methods"
                disabled={selected?.status !== "draft"}
                value={timing.join(", ")}
                onChange={(event) =>
                  patch((next) => {
                    next.allowed_timing_methods = event.target.value
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
                aria-label="Controlled constraints"
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
            <label className="wide">
              Preview Portfolio
              <select
                aria-label="Preview Portfolio"
                value={portfolioId}
                onChange={(event) => setPortfolioId(Number(event.target.value))}
              >
                <option value={0}>Configuration only</option>
                {portfolios.map((item) => (
                  <option key={Number(item.id)} value={Number(item.id)}>
                    {String(item.name)}
                  </option>
                ))}
              </select>
            </label>
          </section>
          <section aria-label="Strategic Resource Roles" className="resourceRoles">
            <h4>Strategic Resource Roles</h4>
            {roles.map((role) => (
              <article key={String(role.role_key)}>
                <strong>{String(role.name)}</strong>
                <span>
                  {String(role.role_key)} · {String(role.category)} · {String(role.unit)}
                </span>
              </article>
            ))}
          </section>
          <details className="resourceJson">
            <summary>Advanced controlled JSON</summary>
            <textarea
              aria-label="Portfolio Resource configuration JSON"
              disabled={selected?.status !== "draft"}
              onChange={(event) => setContent(event.target.value)}
              rows={28}
              value={content}
            />
          </details>
          <div aria-label="Portfolio Resource configuration actions" className="planningActions">
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
