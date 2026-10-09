import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import PortfolioEvaluationAdminView from "./PortfolioEvaluationAdminView";
import PortfolioEvaluationWorkspace from "./PortfolioEvaluationWorkspace";

const queueItem = {
  portfolio_workspace_id: 8,
  project_workspace_id: 14,
  project_number: "PRJ-0014",
  project_name: "Controlled expansion",
  membership_id: 31,
  queue: "TO_EVALUATE",
  eligible: true,
  blocking_issues: [],
  allowed_actions: ["read", "start"],
  latest_evaluation: null,
};

describe("PortfolioEvaluationWorkspace", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders backend-derived evaluation queues without a candidate entity", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input: RequestInfo | URL) => {
      const path = String(input);
      const body = path.includes("/portfolio-options")
        ? [{ id: 8, name: "Capital Portfolio", record_code: "01.02" }]
        : [queueItem];
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
    });

    render(<PortfolioEvaluationWorkspace token="token" />);

    expect(await screen.findByRole("heading", { name: "Portfolio Evaluation" })).toBeInTheDocument();
    expect(await screen.findByText("Controlled expansion")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Start/ })).toBeEnabled();
    expect(screen.getByText(/No global candidate/)).toBeInTheDocument();
  });

  it("renders contextual ranking and Gate 07F handoff readiness only", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input: RequestInfo | URL) => {
      const path = String(input);
      const body = path.includes("/prioritization/readiness")
        ? {
            portfolio_workspace_id: 8,
            status: "READY",
            eligible_project_count: 1,
            completed_evaluation_count: 1,
            in_progress_evaluation_count: 0,
            blocked_project_count: 0,
            coverage_percent: "100.00",
            blocking_issues: [],
            readiness_hash: "r".repeat(64),
            can_enter_portfolio_analysis: true,
            final_output: "READY_FOR_PORTFOLIO_ANALYSIS",
          }
        : path.includes("/prioritization")
          ? {
              portfolio_workspace_id: 8,
              generated_at: "2026-08-20T12:00:00Z",
              ranking_rules: { manual_override: false },
              matrix_hash: "m".repeat(64),
              items: [
                {
                  rank: 1,
                  portfolio_workspace_id: 8,
                  project_workspace_id: 14,
                  project_number: "PRJ-0014",
                  project_name: "Controlled expansion",
                  evaluation_id: 71,
                  evaluation_version: 1,
                  normalized_score: "82.5000",
                  strategic_alignment_score: "100.0000",
                  risk_score: "2.0000",
                  proposal_score: "91.0000",
                  strategic_objectives: [{ code: "GROWTH", name: "Growth" }],
                  rom_cost: "2500000.0000",
                  evaluation_status: "COMPLETED",
                  completed_at: "2026-08-20T11:00:00Z",
                  planned_finish: "2028-01-01",
                },
              ],
            }
          : [{ id: 8, name: "Capital Portfolio", record_code: "01.02" }];
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
    });

    render(<PortfolioEvaluationWorkspace token="token" view="prioritization" />);

    expect(await screen.findByRole("heading", { name: "Prioritization Matrix" })).toBeInTheDocument();
    expect(await screen.findByText("READY_FOR_PORTFOLIO_ANALYSIS")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Portfolio prioritization ranking" })).toHaveTextContent("PRJ-0014");
    expect(screen.queryByText(/FID/i)).not.toBeInTheDocument();
  });
});

describe("PortfolioEvaluationAdminView", () => {
  afterEach(() => vi.restoreAllMocks());

  it("keeps the starter matrix in draft until explicit publication", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input: RequestInfo | URL) => {
      const path = String(input);
      const body = path.endsWith("/preview")
        ? { effective: { applicable_governance_models: ["CAPITAL_OWNER"] }, publishable: true }
        : [
            {
              id: 91,
              kind: "portfolio_evaluation_configuration",
              code: "gate07e-default",
              name: "Default Portfolio Evaluation Matrix",
              description: "Explicit publication required",
              status: "draft",
              revision: 1,
              version: 1,
              content_json: { applicable_governance_models: ["CAPITAL_OWNER"] },
              content_hash: "c".repeat(64),
            },
          ];
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
    });

    render(<PortfolioEvaluationAdminView token="token" />);

    expect(await screen.findByRole("heading", { name: "Portfolio Evaluation & Prioritization" })).toBeInTheDocument();
    expect(await screen.findByText(/draft · rev 1/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Publish/ })).toBeEnabled();
  });
});
