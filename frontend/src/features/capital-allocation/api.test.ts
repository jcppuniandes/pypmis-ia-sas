import { beforeEach, describe, expect, it, vi } from "vitest";
import { strategicAllocationApi } from "./api";
import type { StrategicAllocationPlan } from "./types";

const mocks = vi.hoisted(() => ({ apiFetch: vi.fn(), apiFetchWithResponse: vi.fn() }));

vi.mock("../../api/client", () => mocks);
vi.mock("../capital-planning/api", () => ({ createIdempotencyKey: () => "generated-idempotency-key" }));

const rawPlan = {
  id: 51,
  allocation_plan_number: "SCA-00051",
  logical_code: "SCA-00051",
  plan_revision: 1,
  name: "FY27 allocation",
  description: "Governed intent",
  planning_cycle_id: 7,
  planning_cycle_number: "CPC-00007",
  planning_cycle_name: "FY27",
  scope_workspace_id: 11,
  scope_workspace_name: "P&P Enterprise",
  scope_type: "business-unit",
  portfolio_workspace_id: null,
  portfolio_workspace_name: null,
  base_currency: "COP",
  allocation_basis: "PERCENTAGE",
  status: "DRAFT",
  assumptions: [],
  constraints: [],
  configuration_revision: 4,
  configuration_hash: "a".repeat(64),
  plan_hash: "b".repeat(64),
  endorsed_snapshot_hash: null,
  lines: [],
  readiness: { status: "BLOCKED", blocking_issues: ["TARGET_ALLOCATION"] },
  source_current: true,
  created_by_user_id: 1,
  reviewer_user_id: null,
  endorser_user_id: null,
  created_at: "2026-10-01T10:00:00Z",
  updated_at: "2026-10-01T10:00:00Z",
  submitted_at: null,
  review_started_at: null,
  endorsed_at: null,
  revision_version: 3,
  allowed_actions: ["edit", "classify", "submit"],
};

describe("strategicAllocationApi", () => {
  beforeEach(() => vi.clearAllMocks());

  it("normalizes the backend workspace, Bucket and scope catalog without inventing authority", async () => {
    mocks.apiFetch.mockResolvedValue({
      planning_cycles: [],
      scope_workspaces: [{ id: 11, name: "Operations", type: "business-unit" }],
      portfolios: [],
      strategic_capital_buckets: [{ code: "sustaining", name: "Sustaining Capital", active: true }],
      allocation_basis_options: ["PERCENTAGE"],
      scope_types: ["enterprise", "business-unit", "portfolio"],
      effective_configuration: { allocation_policy: { percentage_total_required: "100" } },
    });

    const value = await strategicAllocationApi.options("token", 11);

    expect(mocks.apiFetch).toHaveBeenCalledWith("/api/v1/capital-planning/allocation-options?scope_workspace_id=11", {
      token: "token",
    });
    expect(value.workspaces[0]).toEqual(expect.objectContaining({ id: 11, workspace_type_code: "BUSINESS_UNIT" }));
    expect(value.buckets[0]).toEqual(
      expect.objectContaining({ bucket_code: "sustaining", bucket_name: "Sustaining Capital" })
    );
    expect(value.scope_options).toEqual(["ENTERPRISE", "BUSINESS_UNIT", "PORTFOLIO"]);
  });

  it("normalizes plans and backend readiness while retaining the ETag revision", async () => {
    mocks.apiFetch.mockResolvedValue(rawPlan);

    const value = await strategicAllocationApi.readPlan("token", 51);

    expect(value.scope_type).toBe("BUSINESS_UNIT");
    expect(value.revision_version).toBe(3);
    expect(value.readiness).toEqual(expect.objectContaining({ overall: "BLOCKED", blockers: ["TARGET_ALLOCATION"] }));
  });

  it("sends If-Match and idempotency for one-primary-Bucket batch replacement", async () => {
    mocks.apiFetch.mockResolvedValue({ allocation_plan: rawPlan, classifications: [] });
    const plan = { ...rawPlan, scope_type: "BUSINESS_UNIT" } as unknown as StrategicAllocationPlan;

    await strategicAllocationApi.replaceClassifications(
      "token",
      plan,
      [
        {
          demand_id: 91,
          target_type: "DEMAND",
          target_id: 91,
          bucket_code: "growth",
          rationale: "Explicit sponsor decision",
        },
        { demand_id: 92, target_type: "DEMAND", target_id: 92, bucket_code: null },
      ],
      "idem-51"
    );

    expect(mocks.apiFetch).toHaveBeenCalledWith("/api/v1/capital-planning/allocation-plans/51/classifications", {
      method: "PUT",
      token: "token",
      headers: { "If-Match": '"3"', "Idempotency-Key": "idem-51" },
      body: JSON.stringify({
        classifications: [
          {
            target_type: "DEMAND",
            target_id: 91,
            bucket_code: "growth",
            rationale: "Explicit sponsor decision",
          },
        ],
      }),
    });
  });

  it("keeps currencies separate and exposes unclassified Demand from the backend comparison", async () => {
    mocks.apiFetch.mockResolvedValue({
      allocation_plan_id: 51,
      allocation_plan_version: 3,
      population_definition: { statuses: ["SUBMITTED", "IN_REVIEW", "ENDORSED"] },
      classification_precedence: ["EXPLICIT", "DEMAND", "THEME_DEFAULT", "UNCLASSIFIED"],
      positions: [
        {
          bucket_code: "growth",
          bucket_name: "Growth Capital",
          target_percentage: "40",
          current_demand: {
            amount_by_currency: { COP: "500000000" },
            percentage: null,
            item_count: 1,
            evaluable: false,
            source: "CAPITAL_DEMAND",
            drilldown: [
              {
                id: 91,
                number: "CD-00091",
                name: "Actual backend Demand payload",
                classification_source: "THEME_DEFAULT",
              },
            ],
          },
          current_portfolio: { amount_by_currency: {}, item_count: 0, source: "PORTFOLIO_MEMBERSHIP" },
          recommended: { amount_by_currency: {}, item_count: 0, source: "PORTFOLIO_RECOMMENDATION" },
          approved: { amount_by_currency: {}, item_count: 0, source: "FID_PYP_FFA" },
          status: "NOT_EVALUABLE",
        },
      ],
      unclassified: {
        demand: {
          amount_by_currency: { USD: "250000" },
          item_count: 1,
          evaluable: false,
          source: "UNCLASSIFIED",
          drilldown: [
            {
              capital_demand_id: 92,
              demand_number: "CD-00092",
              amount: "250000",
              currency: "USD",
            },
          ],
        },
      },
      classification_coverage_percentage: "50",
      multi_currency: true,
      normalization_warning: "COP and USD are not normalized.",
      generated_at: "2026-10-01T10:00:00Z",
    });

    const value = await strategicAllocationApi.comparison("token", 51);

    expect(value.evaluable).toBe(false);
    expect(value.unclassified).toEqual(expect.objectContaining({ amount_by_currency: { USD: "250000" }, count: 1 }));
    expect(value.classifications?.[0]).toEqual(
      expect.objectContaining({ demand_id: 91, target_type: "DEMAND", target_id: 91, bucket_code: "growth" })
    );
    expect(value.classifications?.[1]).toEqual(
      expect.objectContaining({ demand_id: 92, bucket_code: null, resolution_source: "UNCLASSIFIED" })
    );
    expect(value.warnings).toEqual(["COP and USD are not normalized."]);
  });

  it("normalizes immutable audit metadata for the History surface", async () => {
    mocks.apiFetch.mockResolvedValue([
      {
        event_type: "capital_planning.allocation_plan.endorse",
        outcome: "SUCCESS",
        actor_user_id: 7,
        metadata: { from: ["IN_REVIEW"], to: "ENDORSED" },
        occurred_at: "2026-10-01T10:00:00Z",
      },
    ]);

    const events = await strategicAllocationApi.history("token", 51);

    expect(events[0]).toEqual(
      expect.objectContaining({
        actor_name: "User 7",
        from_status: "IN_REVIEW",
        to_status: "ENDORSED",
        detail: expect.objectContaining({ outcome: "SUCCESS" }),
      })
    );
  });
});
