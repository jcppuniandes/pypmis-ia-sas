import { beforeEach, describe, expect, it, vi } from "vitest";
import { portfolioReviewApi } from "./api";
import type { PortfolioReviewAction, PortfolioReviewConfiguration, PortfolioReviewSession } from "./types";

const mocks = vi.hoisted(() => ({ apiFetch: vi.fn(), apiFetchWithResponse: vi.fn() }));

vi.mock("../../api/client", () => mocks);
vi.mock("../capital-planning/api", () => ({ createIdempotencyKey: () => "generated-review-key" }));

const rawSession = {
  id: 41,
  review_number: "PRV-000041",
  portfolio_workspace_id: 71,
  portfolio_workspace_name: "Capital Portfolio",
  planning_cycle_id: 7,
  allocation_plan_id: 51,
  review_type: "QUARTERLY",
  planned_review_date: "2026-10-05",
  review_period_start: "2026-07-01",
  review_period_end: "2026-09-30",
  next_planned_review_date: "2027-01-05",
  status: "PREPARING",
  agenda: [{ code: "CAPITAL_ALLOCATION_BALANCE", title: "Capital Allocation Balance", status: "READY" }],
  conclusions: [],
  current_snapshot: {
    id: 91,
    hash: "s".repeat(64),
    source_current: true,
    source_references: {
      allocation: { record_id: 51, version: 4, hash: "a".repeat(64), current: true },
    },
  },
  review_readiness: {
    status: "ATTENTION",
    components: { SNAPSHOT_READINESS: "READY", OVERALL_REVIEW_READINESS: "ATTENTION" },
    blocking_issues: ["AGENDA_INCOMPLETE"],
  },
  portfolio_summary: { project_count: 3 },
  actions: [],
  source_current: true,
  revision_version: 4,
  allowed_actions: ["snapshot_preview", "freeze_snapshot"],
};

describe("portfolioReviewApi", () => {
  beforeEach(() => vi.clearAllMocks());

  it("normalizes the governed Session, snapshot lineage and backend readiness", async () => {
    mocks.apiFetch.mockResolvedValue(rawSession);

    const value = await portfolioReviewApi.readSession("token", 41);

    expect(mocks.apiFetch).toHaveBeenCalledWith("/api/v1/portfolio-reviews/41", { token: "token" });
    expect(value).toEqual(
      expect.objectContaining({
        portfolio_id: 71,
        portfolio_name: "Capital Portfolio",
        review_date: "2026-10-05",
        revision_version: 4,
        readiness: expect.objectContaining({ overall: "ATTENTION", blockers: ["AGENDA_INCOMPLETE"] }),
        snapshot: expect.objectContaining({ snapshot_hash: "s".repeat(64), source_current: true }),
      })
    );
    expect(value.snapshot?.sources[0]).toEqual(
      expect.objectContaining({ source_type: "allocation", source_id: 51, source_version: 4, source_current: true })
    );
    expect(value.agenda[0].label).toBe("Capital Allocation Balance");
    expect(value.readiness.dimensions).toEqual({ SNAPSHOT_READINESS: "READY", OVERALL_REVIEW_READINESS: "ATTENTION" });
  });

  it("maps the frozen backend detail without fetching or stitching any live source authority", async () => {
    mocks.apiFetch.mockResolvedValue({
      ...rawSession,
      status: "COMPLETED",
      current_snapshot: undefined,
      snapshot: {
        id: 91,
        snapshot_hash: "s".repeat(64),
        snapshot_json: { source_as_of: "2026-10-05T09:00:00Z", portfolio_summary: { portfolio_size: 3 } },
        source_index_json: { BUDGET_SCENARIO: { record_id: 19, version: 2, hash: "b".repeat(64) } },
        warnings_json: [],
        blockers_json: [],
      },
      summary: { portfolio_size: 3 },
      actions: [{ id: 501, owner_user_id: 17, action_type: "HOLD_FOR_CAPACITY", status: "OPEN" }],
    });
    const value = await portfolioReviewApi.readSession("token", 41);
    expect(mocks.apiFetch).toHaveBeenCalledTimes(1);
    expect(value.snapshot?.source_as_of).toBe("2026-10-05T09:00:00Z");
    expect(value.snapshot?.sources[0]).toMatchObject({
      source_type: "BUDGET_SCENARIO",
      source_id: 19,
      source_version: 2,
    });
    expect(value.summary).toEqual({ portfolio_size: 3 });
    expect(value.actions[0]).toMatchObject({ id: 501, owner_user_id: 17, status: "OPEN" });
  });

  it("preserves backend Project identity, approved currency and every governance action in one matrix page", async () => {
    mocks.apiFetchWithResponse.mockResolvedValue({
      data: {
        items: [
          {
            project_workspace_id: 1001,
            project_code: "PRJ-1001",
            project_name: "Terminal Expansion",
            allocation_variance_contribution: { bucket_status: "UNDER_TARGET" },
            approved_amount_context: { amount: "600000000", currency: "COP" },
            review_actions: [
              { id: 501, action_type: "HOLD_FOR_CAPACITY", owner_user_id: 17 },
              { id: 502, action_type: "REQUEST_REASSESSMENT", owner_user_id: 18 },
            ],
          },
        ],
        total: 201,
        page: 2,
        page_size: 100,
      },
      response: new Response(),
    });
    const matrix = await portfolioReviewApi.projectMatrix("token", 41, { page: 2, fid_status: "FID_GRANTED" });
    expect(mocks.apiFetchWithResponse).toHaveBeenCalledTimes(1);
    expect(matrix.items[0]).toMatchObject({
      project_id: 1001,
      project_number: "PRJ-1001",
      approved_amounts_by_currency: { COP: "600000000" },
    });
    expect(matrix.items[0].review_actions).toHaveLength(2);
    expect(matrix.page).toBe(2);
    expect(matrix.total).toBe(201);
  });

  it("uses the Wave 2A allocation plan number and preserves grouped currency positions", async () => {
    mocks.apiFetch.mockResolvedValue({
      allocation_plan: { id: 51, allocation_plan_number: "SCA-000051", revision_version: 4 },
      comparison: {
        positions: [
          {
            bucket_code: "GROWTH",
            target_percentage: "40",
            target_amount: "700",
            target_currency: "USD",
            current_portfolio: { amount_by_currency: { USD: "600", COP: "800" }, evaluable: false },
          },
        ],
        multi_currency: true,
        normalization_warning: "NOT_EVALUABLE",
        unclassified: { amount_by_currency: { COP: "50" }, item_count: 1 },
      },
    });
    const context = await portfolioReviewApi.allocation("token", 41);
    expect(context.allocation_plan_number).toBe("SCA-000051");
    expect(context.buckets[0].target.amounts_by_currency).toEqual({ USD: "700" });
    expect(context.buckets[0].current_portfolio).toMatchObject({
      amounts_by_currency: { USD: "600", COP: "800" },
      evaluable: false,
    });
    expect(context.unclassified.count).toBe(1);
  });

  it("uses Idempotency-Key for Session creation and combines it with If-Match for snapshot freeze", async () => {
    mocks.apiFetch.mockResolvedValue(rawSession);
    const draft = {
      portfolio_id: 71,
      portfolio_workspace_id: 71,
      planning_cycle_id: 7,
      allocation_plan_id: 51,
      review_type: "QUARTERLY",
      review_date: "2026-10-05",
      planned_review_date: "2026-10-05",
      review_period_start: "2026-07-01",
      review_period_end: "2026-09-30",
      next_planned_review_date: "2027-01-05",
    };

    const created = await portfolioReviewApi.createSession("token", draft, "create-41");
    await portfolioReviewApi.freezeSnapshot("token", created, "freeze-41");

    expect(mocks.apiFetch).toHaveBeenNthCalledWith(1, "/api/v1/portfolio-reviews", {
      method: "POST",
      token: "token",
      headers: { "Idempotency-Key": "create-41" },
      body: JSON.stringify(draft),
    });
    expect(mocks.apiFetch).toHaveBeenNthCalledWith(2, "/api/v1/portfolio-reviews/41/freeze-snapshot", {
      method: "POST",
      token: "token",
      headers: { "If-Match": '"4"', "Idempotency-Key": "freeze-41" },
      body: JSON.stringify({ reason: "Periodic Portfolio Review governed freeze" }),
    });
    expect(mocks.apiFetch).toHaveBeenNthCalledWith(3, "/api/v1/portfolio-reviews/41", { token: "token" });
  });

  it.each(["HOLD_FOR_CAPACITY", "REQUEST_REASSESSMENT", "REBALANCE_CAPITAL", "MOVE_BETWEEN_BUCKETS"])(
    "creates %s only through the Portfolio Review Action endpoint",
    async (actionType) => {
      const normalized = {
        ...rawSession,
        portfolio_id: 71,
        review_date: "2026-10-05",
        readiness: { overall: "READY", ready: true, dimensions: {}, blockers: [], warnings: [] },
        summary: {},
        snapshot: null,
      } as unknown as PortfolioReviewSession;
      mocks.apiFetch.mockResolvedValue({
        id: 501,
        review_session_id: 41,
        subject_type: "PROJECT",
        subject_id: 1001,
        action_type: actionType,
        rationale: "Governance request",
        priority: "HIGH",
        status: "OPEN",
        revision_version: 1,
        allowed_actions: [],
      });

      await portfolioReviewApi.createAction(
        "token",
        normalized,
        {
          subject_type: "PROJECT",
          subject_id: 1001,
          action_type: actionType,
          rationale: "Governance request",
          priority: "HIGH",
          owner: "Portfolio PMO",
          due_date: null,
        },
        "action-501"
      );

      expect(mocks.apiFetch).toHaveBeenCalledTimes(1);
      expect(mocks.apiFetch).toHaveBeenCalledWith("/api/v1/portfolio-reviews/41/actions", {
        method: "POST",
        token: "token",
        headers: { "If-Match": '"4"', "Idempotency-Key": "action-501" },
        body: expect.stringContaining(`"action_type":"${actionType}"`),
      });
    }
  );

  it("guards action approval and dispatch with ETag plus independent idempotency keys", async () => {
    const action = {
      id: 501,
      review_session_id: 41,
      subject_type: "PROJECT",
      subject_id: 1001,
      action_type: "REQUEST_GATE_REVALIDATION",
      rationale: "Refresh evidence",
      priority: "HIGH",
      due_date: null,
      status: "OPEN",
      revision_version: 2,
      allowed_actions: ["approve", "dispatch"],
    } as PortfolioReviewAction;
    mocks.apiFetch.mockResolvedValue(action);

    await portfolioReviewApi.approveAction("token", action, "approve-501");
    await portfolioReviewApi.dispatchAction("token", action, "dispatch-501");

    expect(mocks.apiFetch).toHaveBeenNthCalledWith(1, "/api/v1/portfolio-review-actions/501/approve", {
      method: "POST",
      token: "token",
      headers: { "If-Match": '"2"', "Idempotency-Key": "approve-501" },
    });
    expect(mocks.apiFetch).toHaveBeenNthCalledWith(2, "/api/v1/portfolio-review-actions/501/dispatch", {
      method: "POST",
      token: "token",
      headers: { "If-Match": '"2"', "Idempotency-Key": "dispatch-501" },
    });
  });

  it("keeps ADMIN operations under the configuration boundary", async () => {
    const item = {
      id: 801,
      name: "Quarterly Review",
      description: "Policy",
      status: "draft",
      revision: 2,
      version: 5,
      content_json: { cadence: { QUARTERLY: 90 } },
    } as PortfolioReviewConfiguration;
    mocks.apiFetch.mockResolvedValue(item);

    await portfolioReviewApi.updateConfiguration("token", item, item.content_json);
    await portfolioReviewApi.publishConfiguration("token", item);
    await portfolioReviewApi.archiveConfiguration("token", item);

    expect(mocks.apiFetch).toHaveBeenNthCalledWith(1, "/api/v1/portfolio-reviews/admin/configurations/801", {
      method: "PUT",
      token: "token",
      headers: { "If-Match": '"5"' },
      body: JSON.stringify({ name: item.name, description: item.description, content_json: item.content_json }),
    });
    expect(mocks.apiFetch).toHaveBeenNthCalledWith(
      2,
      "/api/v1/portfolio-reviews/admin/configurations/801/publish",
      expect.objectContaining({ method: "POST", headers: { "If-Match": '"5"' } })
    );
    expect(mocks.apiFetch).toHaveBeenNthCalledWith(
      3,
      "/api/v1/portfolio-reviews/admin/configurations/801/archive",
      expect.objectContaining({ method: "POST", headers: { "If-Match": '"5"' } })
    );
  });
});
