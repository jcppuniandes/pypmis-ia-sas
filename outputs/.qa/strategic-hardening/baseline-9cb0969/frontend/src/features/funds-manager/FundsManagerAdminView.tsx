/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { Copy, Eye, Save, Send } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { portfolioPlanningApi } from "../portfolio-planning/api";
import { fundsManagerApi } from "./api";
import "./fundsManager.css";
import type { FundsConfiguration } from "./types";

function parse(value: string) {
  try {
    return JSON.parse(value) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export default function FundsManagerAdminView({ token }: { token: string }) {
  const [records, setRecords] = useState<FundsConfiguration[]>([]);
  const [selected, setSelected] = useState<FundsConfiguration | null>(null);
  const [content, setContent] = useState("");
  const [portfolios, setPortfolios] = useState<Array<Record<string, unknown>>>([]);
  const [portfolioId, setPortfolioId] = useState(0);
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [message, setMessage] = useState("");
  const parsed = useMemo(() => parse(content), [content]);

  async function load(preferredId?: number) {
    const [items, portfolioItems] = await Promise.all([
      fundsManagerApi.configurations(token),
      portfolioPlanningApi.portfolioOptions(token),
    ]);
    setRecords(items);
    setPortfolios(portfolioItems);
    setPortfolioId((current) => current || Number(portfolioItems[0]?.id || 0));
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
      setMessage(error instanceof Error ? error.message : "Unable to load Funds configuration")
    );
  }, [token]);

  function patchPolicy(key: string, value: unknown) {
    if (!parsed) return;
    setContent(JSON.stringify({ ...parsed, [key]: value }, null, 2));
  }

  async function execute(action: "clone" | "save" | "publish") {
    if (!selected) return;
    try {
      let result = selected;
      if (action === "clone") result = await fundsManagerApi.cloneConfiguration(token, selected);
      if (action === "save") {
        if (!parsed) throw new Error("Configuration JSON is invalid.");
        result = await fundsManagerApi.updateConfiguration(token, selected, parsed);
      }
      if (action === "publish") result = await fundsManagerApi.publishConfiguration(token, selected);
      await load(result.id);
      setMessage(`Funds Manager configuration ${action} completed.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Unable to ${action} configuration`);
    }
  }

  async function previewDraft() {
    if (!selected || !parsed) return;
    try {
      setPreview(await fundsManagerApi.previewConfiguration(token, portfolioId || null, selected.id, parsed));
      setMessage("Dry-run completed: persisted=false; no Fund, Assignment or Readiness Snapshot was created.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to preview Funds configuration");
    }
  }

  return (
    <section aria-label="Funds Manager Configuration" className="fundsManager fundsManagerAdmin">
      <CompactModuleHeader
        description="Controls funding source types, Fund and Assignment lifecycle, coverage thresholds, common currency, periods, restrictions, conditions, inheritance and Gate 07J compatibility. No arbitrary formulas or financial execution."
        eyebrow="ADMIN MODE · ENTERPRISE STRATEGY MANAGER · GATE 07J-FUND"
        metrics={[
          { label: "Revisions", value: records.length },
          { label: "Confirmed threshold", value: `${Number(parsed?.minimum_confirmed_coverage_percent ?? 0)}%` },
          { label: "Reserved counts", value: parsed?.reserved_counts_toward_readiness ? "YES" : "NO" },
        ]}
        title="Funds Manager Configuration"
        tone="admin"
      />
      {message ? (
        <div className="fundsMessage" role="status">
          {message}
        </div>
      ) : null}
      <div className="fundsAdminGrid">
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
        <article className="fundsSurface">
          <header>
            <div>
              <span>Controlled funding policy</span>
              <h3>{selected?.name || "No configuration"}</h3>
            </div>
            <strong>{selected?.status}</strong>
          </header>
          <section className="fundsPolicyGrid">
            <label>
              Minimum confirmed coverage %
              <input
                disabled={selected?.status !== "draft"}
                min={0}
                max={100}
                type="number"
                value={Number(parsed?.minimum_confirmed_coverage_percent ?? 100)}
                onChange={(event) => patchPolicy("minimum_confirmed_coverage_percent", Number(event.target.value))}
              />
            </label>
            <label>
              Minimum potential coverage %
              <input
                disabled={selected?.status !== "draft"}
                min={0}
                max={100}
                type="number"
                value={Number(parsed?.minimum_potential_coverage_percent ?? 100)}
                onChange={(event) => patchPolicy("minimum_potential_coverage_percent", Number(event.target.value))}
              />
            </label>
            <label>
              <input
                checked={Boolean(parsed?.reserved_counts_toward_readiness)}
                disabled={selected?.status !== "draft"}
                onChange={(event) => patchPolicy("reserved_counts_toward_readiness", event.target.checked)}
                type="checkbox"
              />{" "}
              Reserved counts toward readiness
            </label>
            <label>
              <input
                checked={Boolean(parsed?.conditional_funds_count_toward_readiness)}
                disabled={selected?.status !== "draft"}
                onChange={(event) => patchPolicy("conditional_funds_count_toward_readiness", event.target.checked)}
                type="checkbox"
              />{" "}
              Conditional funding may count
            </label>
            <label>
              <input
                checked={Boolean(parsed?.require_each_project_coverage)}
                disabled={selected?.status !== "draft"}
                onChange={(event) => patchPolicy("require_each_project_coverage", event.target.checked)}
                type="checkbox"
              />{" "}
              Require each Project coverage
            </label>
            <label>
              <input
                checked={Boolean(parsed?.require_period_coverage)}
                disabled={selected?.status !== "draft"}
                onChange={(event) => patchPolicy("require_period_coverage", event.target.checked)}
                type="checkbox"
              />{" "}
              Require period coverage
            </label>
            <label>
              <input
                checked={Boolean(parsed?.open_condition_is_blocker)}
                disabled={selected?.status !== "draft"}
                onChange={(event) => patchPolicy("open_condition_is_blocker", event.target.checked)}
                type="checkbox"
              />{" "}
              Open condition is blocker
            </label>
            <label>
              <input
                checked={Boolean(parsed?.fund_creator_cannot_authorize)}
                disabled={selected?.status !== "draft"}
                onChange={(event) => patchPolicy("fund_creator_cannot_authorize", event.target.checked)}
                type="checkbox"
              />{" "}
              Fund creator ≠ authorizer
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
          <details className="fundsJson">
            <summary>Advanced controlled JSON</summary>
            <textarea
              aria-label="Funds Manager configuration JSON"
              disabled={selected?.status !== "draft"}
              onChange={(event) => setContent(event.target.value)}
              rows={28}
              value={content}
            />
          </details>
          <div className="fundsActions">
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
              <summary>Effective policy and Gate 07J evidence preview</summary>
              <pre>{JSON.stringify(preview, null, 2)}</pre>
            </details>
          ) : null}
        </article>
      </div>
      <p className="fundsGuardrail">
        ADMIN Preview is non-persistent and cannot create Funds, Assignments, readiness snapshots, FID decisions,
        payments or Project activation.
      </p>
    </section>
  );
}
