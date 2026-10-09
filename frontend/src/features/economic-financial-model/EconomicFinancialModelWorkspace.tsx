/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect --
 * Route selection and API-backed detail state are intentionally synchronized by effects.
 */
import { Calculator, CheckCircle2, Send } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { economicFinancialModelApi } from "./api";
import type { FinancialInput, FinancialModel, FinancialReadiness } from "./types";
import "./economicFinancialModel.css";

const VIEWS = [
  "My Models",
  "Overview",
  "Current Version",
  "Assumptions",
  "Economic Case",
  "Financial Case",
  "CAPEX / OPEX",
  "Revenue / Benefits",
  "Capital Structure",
  "Funding Linkage",
  "Investors",
  "Debt",
  "Cash Flow",
  "Debt Service",
  "Indicators",
  "Covenants",
  "Scenarios",
  "Sensitivities",
  "Break-Even",
  "Readiness",
  "Source Lineage",
  "Compare Versions",
  "History / Audit",
] as const;

const ROUTE_LABEL: Record<string, (typeof VIEWS)[number]> = Object.fromEntries(
  VIEWS.map((label) => [`financial-model-${label.toLowerCase().replace(/ \/ /g, "-").replace(/ /g, "-")}`, label])
) as Record<string, (typeof VIEWS)[number]>;

export default function EconomicFinancialModelWorkspace({
  token,
  initialView,
}: {
  token: string;
  initialView?: string;
}) {
  const [models, setModels] = useState<FinancialModel[]>([]);
  const [selectedId, setSelectedId] = useState(0);
  const [view, setView] = useState<(typeof VIEWS)[number]>(ROUTE_LABEL[initialView || ""] || "Overview");
  const [rows, setRows] = useState<FinancialInput[]>([]);
  const [readiness, setReadiness] = useState<FinancialReadiness | null>(null);
  const [projectId, setProjectId] = useState("");
  const [businessCaseId, setBusinessCaseId] = useState("");
  const [message, setMessage] = useState("");
  const selected = models.find((item) => item.id === selectedId) || models[0] || null;
  const version = selected?.current_version || null;

  const metrics = useMemo(
    () => [
      { label: "Version", value: version?.version_label || "—" },
      { label: "Model type", value: version?.model_type || "—" },
      { label: "Project NPV", value: version?.project_financial_npv || "—" },
      { label: "Minimum DSCR", value: version?.minimum_dscr || "—" },
      { label: "Readiness", value: version?.overall_readiness || "NOT_STARTED" },
    ],
    [version]
  );

  async function load(preferred?: number) {
    const output = await economicFinancialModelApi.list(token);
    setModels(output);
    setSelectedId(preferred || output[0]?.id || 0);
  }

  useEffect(() => setView(ROUTE_LABEL[initialView || ""] || "Overview"), [initialView]);
  useEffect(() => {
    void load().catch((error) => setMessage(error instanceof Error ? error.message : "Unable to load models"));
  }, [token]);
  useEffect(() => {
    if (!selected || !version) return;
    const source =
      view === "Assumptions"
        ? economicFinancialModelApi.assumptions
        : view === "Capital Structure" || view === "Debt" || view === "Funding Linkage"
          ? economicFinancialModelApi.instruments
          : view === "Investors"
            ? economicFinancialModelApi.investors
            : view === "Scenarios" || view === "Sensitivities"
              ? economicFinancialModelApi.scenarios
              : view === "Cash Flow" || view === "Debt Service"
                ? economicFinancialModelApi.cashFlows
                : view === "Indicators" ||
                    view === "Economic Case" ||
                    view === "Financial Case" ||
                    view === "Break-Even"
                  ? economicFinancialModelApi.metrics
                  : view === "CAPEX / OPEX" || view === "Revenue / Benefits"
                    ? economicFinancialModelApi.periods
                    : null;
    if (source)
      void source(token, version.id)
        .then(setRows)
        .catch(() => setRows([]));
    else setRows([]);
    void economicFinancialModelApi
      .readiness(token, selected.id)
      .then(setReadiness)
      .catch(() => setReadiness(null));
  }, [selected?.id, view]);

  async function create() {
    try {
      const item = await economicFinancialModelApi.create(token, Number(projectId), Number(businessCaseId));
      await load(item.id);
      setMessage(`${item.model_number} created with governed Business Case lineage.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Creation failed");
    }
  }

  async function act(action: "calculate" | "submit" | "complete") {
    if (!version) return;
    try {
      if (action === "calculate") await economicFinancialModelApi.calculate(token, version);
      if (action === "submit") await economicFinancialModelApi.submit(token, version);
      if (action === "complete") await economicFinancialModelApi.complete(token, version);
      await load(selected?.id);
      setMessage(`${action} completed with ETag and idempotency controls.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Unable to ${action}`);
    }
  }

  const detail =
    view === "Readiness"
      ? readiness
      : view === "Source Lineage"
        ? {
            references: version?.source_references_json,
            hashes: version?.source_hashes_json,
            source_current: version?.source_current,
          }
        : view === "Current Version" ||
            view === "Overview" ||
            view === "My Models" ||
            view === "Compare Versions" ||
            view === "History / Audit"
          ? version
          : null;

  return (
    <section aria-label="Economic & Financial Model" className="financialModel">
      <CompactModuleHeader
        description="Governed Project economics, capital structure, investors, debt, cash flow, metrics, scenarios and readiness with explicit Budget and Funding reconciliation."
        eyebrow="USER MODE · ENTERPRISE STRATEGY MANAGER · GATE 07M-FIN"
        metrics={metrics}
        title="Economic & Financial Model"
      />
      {message ? (
        <div className="financialModelMessage" role="status">
          {message}
        </div>
      ) : null}
      <nav aria-label="Economic and financial model views" className="financialModelTabs">
        {VIEWS.map((item) => (
          <button className={view === item ? "active" : ""} key={item} onClick={() => setView(item)} type="button">
            {item}
          </button>
        ))}
      </nav>
      <div className="financialModelControls">
        <label>
          Model
          <select onChange={(event) => setSelectedId(Number(event.target.value))} value={selected?.id || 0}>
            {!models.length ? <option value={0}>No governed models</option> : null}
            {models.map((item) => (
              <option key={item.id} value={item.id}>
                {item.model_number} · {item.current_version?.model_type}
              </option>
            ))}
          </select>
        </label>
        <button disabled={!version || version.status !== "DRAFT"} onClick={() => void act("calculate")} type="button">
          <Calculator size={15} /> Calculate
        </button>
        <button disabled={!version || version.status !== "DRAFT"} onClick={() => void act("submit")} type="button">
          <Send size={15} /> Submit
        </button>
        <button
          disabled={!version || version.status !== "IN_REVIEW"}
          onClick={() => void act("complete")}
          type="button"
        >
          <CheckCircle2 size={15} /> Complete
        </button>
      </div>
      {!models.length ? (
        <div className="financialModelCreate">
          <h3>Create the governed Project model</h3>
          <label>
            Project Workspace ID
            <input inputMode="numeric" onChange={(event) => setProjectId(event.target.value)} value={projectId} />
          </label>
          <label>
            Completed Business Case ID
            <input
              inputMode="numeric"
              onChange={(event) => setBusinessCaseId(event.target.value)}
              value={businessCaseId}
            />
          </label>
          <button disabled={!projectId || !businessCaseId} onClick={() => void create()} type="button">
            Create model
          </button>
        </div>
      ) : null}
      <article className="financialModelSurface">
        <header>
          <div>
            <span>{view}</span>
            <h3>{selected?.model_number || "Economic & Financial Model"}</h3>
          </div>
          <b>{version?.status || "NOT_STARTED"}</b>
        </header>
        {rows.length ? (
          <div className="financialModelTableWrap">
            <table>
              <thead>
                <tr>
                  {Object.keys(rows[0])
                    .slice(0, 9)
                    .map((key) => (
                      <th key={key}>{key.replace(/_/g, " ")}</th>
                    ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    {Object.keys(rows[0])
                      .slice(0, 9)
                      .map((key) => (
                        <td key={key}>
                          {typeof row[key] === "object" ? JSON.stringify(row[key]) : String(row[key] ?? "—")}
                        </td>
                      ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <pre>
            {JSON.stringify(
              detail || {
                view,
                status: "Configure governed inputs through the API or the corresponding controlled table.",
              },
              null,
              2
            )}
          </pre>
        )}
      </article>
    </section>
  );
}
