import { afterEach, describe, expect, it, vi } from "vitest";
import { capitalPlanningApi, createIdempotencyKey } from "./api";
import type { CapitalDemandFilters, StrategicCapitalDemand } from "./types";

const filters: CapitalDemandFilters = {
  search: "north",
  planning_cycle_id: "7",
  status: "SUBMITTED,IN_REVIEW",
  theme: "reliability",
  strategic_objective: "asset-integrity",
  bucket_code: "",
  driver: "compliance",
  sponsor_user_id: "3",
  owning_workspace_id: "11",
  urgency: "high",
  target_horizon: "near",
  potential_portfolio_id: "21",
  uncertainty_level: "medium",
  mine: "true",
};

const demand = {
  id: 41,
  revision_version: 6,
} as StrategicCapitalDemand;

describe("capitalPlanningApi", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("creates an RFC 4122 key when randomUUID is unavailable on an insecure HTTP origin", () => {
    vi.stubGlobal("crypto", {
      getRandomValues: (bytes: Uint8Array) => {
        bytes.fill(0xab);
        return bytes;
      },
    });

    expect(createIdempotencyKey()).toBe("abababab-abab-4bab-abab-abababababab");
  });

  it("sends the complete governed server filter contract", async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(
          JSON.stringify({
            cycle_id: 7,
            demand_count: 0,
            status_counts: {},
            theme_counts: {},
            driver_counts: {},
            horizon_counts: {},
            uncertainty_counts: {},
            indicative_capital_totals_by_currency: {},
            unpriced_demand_count: 0,
            normalization_warning: null,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
    );
    vi.stubGlobal("fetch", fetchMock);

    await capitalPlanningApi.demandSummary("token", filters);

    const [url, request] = fetchMock.mock.calls[0];
    const query = new URL(String(url), "http://local.test").searchParams;
    expect(query.get("status")).toBe("SUBMITTED,IN_REVIEW");
    expect(query.get("strategic_objective")).toBe("asset-integrity");
    expect(query.get("owning_workspace_id")).toBe("11");
    expect(query.get("mine")).toBe("true");
    expect((request as RequestInit).headers).toMatchObject({ Authorization: "Bearer token" });
  });

  it("always protects Demand commands with ETag and Idempotency-Key", async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(JSON.stringify({ ...demand, status: "SUBMITTED" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
    );
    vi.stubGlobal("fetch", fetchMock);

    await capitalPlanningApi.actionDemand("token", demand, "submit", undefined, "submit-demand-41-v6");

    const [url, request] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/v1/capital-planning/demands/41/submit");
    expect((request as RequestInit).headers).toMatchObject({
      Authorization: "Bearer token",
      "If-Match": '"6"',
      "Idempotency-Key": "submit-demand-41-v6",
    });
  });

  it("uses versioned and idempotent commands for the full Planning Cycle lifecycle", async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(JSON.stringify({ id: 9, revision_version: 2 }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
    );
    vi.stubGlobal("fetch", fetchMock);
    const cycle = { id: 9, revision_version: 2 } as never;

    await capitalPlanningApi.openCycle("token", cycle, "cycle-open-key");
    await capitalPlanningApi.startCycleReview("token", cycle, "cycle-review-key");
    await capitalPlanningApi.closeCycle("token", cycle, "cycle-close-key");

    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
      "/api/v1/capital-planning/cycles/9/open",
      "/api/v1/capital-planning/cycles/9/review/start",
      "/api/v1/capital-planning/cycles/9/close",
    ]);
    expect(fetchMock.mock.calls.map(([, request]) => (request as RequestInit).headers)).toEqual([
      expect.objectContaining({ "If-Match": '"2"', "Idempotency-Key": "cycle-open-key" }),
      expect.objectContaining({ "If-Match": '"2"', "Idempotency-Key": "cycle-review-key" }),
      expect.objectContaining({ "If-Match": '"2"', "Idempotency-Key": "cycle-close-key" }),
    ]);
  });
});
