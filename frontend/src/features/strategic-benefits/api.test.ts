import { afterEach, describe, expect, it, vi } from "vitest";
import { strategicBenefitsApi } from "./api";
import type { BenefitsPlanVersion, StrategicBenefit, StrategicBenefitsPlan } from "./types";

function response(data: unknown, headers: Record<string, string> = {}) {
  return { ok: true, status: 200, headers: new Headers(headers), json: async () => data } as Response;
}

const version = {
  id: 21,
  benefits_plan_id: 7,
  version_number: 1,
  version_purpose: "INITIAL_BENEFITS_PLAN",
  status: "DRAFT",
  fel_stage_code: "FEL-2",
  overview_json: {},
  outputs_json: [],
  outcomes_json: [],
  assumptions_json: [],
  constraints_json: [],
  benefits: [],
  readiness_json: {},
  readiness_status: "BLOCKED",
  readiness_warnings_json: [],
  readiness_blockers_json: [],
  coverage: {},
  source_references_json: {},
  source_hashes_json: {},
  source_current: true,
  configuration_id: 3,
  configuration_revision: 1,
  configuration_hash: "configuration",
  source_bundle_hash: "source",
  preparer_user_id: 1,
  reviewer_user_id: 2,
  revision_version: 9,
  allowed_actions: { can_edit_benefit: true },
  created_at: "2026-09-16T00:00:00Z",
  updated_at: "2026-09-16T00:00:00Z",
} satisfies BenefitsPlanVersion;

const plan = {
  id: 7,
  plan_number: "BPL-000007",
  project_workspace_id: 101,
  status: "DRAFT",
  current_version_id: 21,
  current_version: version,
  configuration_id: 3,
  configuration_revision: 1,
  configuration_hash: "configuration",
  revision_version: 4,
  allowed_actions: { can_edit: true },
  created_at: "2026-09-16T00:00:00Z",
  updated_at: "2026-09-16T00:00:00Z",
} as StrategicBenefitsPlan;

const benefit = {
  id: 31,
  benefit_number: "BEN-000031",
  status: "ACTIVE",
  benefit_name: "Reduced downtime",
  revision_version: 44,
} as StrategicBenefit;

describe("Strategic Benefits API client", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("reads cursor-paginated queues from response headers", async () => {
    const fetchMock = vi.fn(async () =>
      response([plan], { "X-Next-Cursor": "cursor-2", "X-Page-Limit": "50", "X-Result-Count": "1" })
    );
    vi.stubGlobal("fetch", fetchMock);
    const page = await strategicBenefitsApi.listPage("token", {
      queue: "in_review",
      cursor: "cursor-1",
      search: "value",
    });
    expect(page).toEqual({ items: [plan], nextCursor: "cursor-2", pageLimit: 50, resultCount: 1 });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("queue=in_review&search=value&cursor=cursor-1&limit=50"),
      expect.objectContaining({ headers: expect.objectContaining({ Authorization: "Bearer token" }) })
    );
  });

  it("uses the PlanVersion ETag and an idempotency key for governed Benefit mutations", async () => {
    const fetchMock = vi.fn(async () => response({}));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "fixed-key" });
    await strategicBenefitsApi.updateBenefit("token", plan, version, benefit, {
      benefit_name: "Reduced downtime",
      benefit_description: "",
      benefit_direction: "BENEFIT",
      benefit_type: "OPERATIONAL",
      benefit_category: "RELIABILITY",
      strategic_objective_refs: [],
      source_need_reference: {},
      source_business_analysis_reference: {},
      source_project_proposal_reference: {},
      source_business_case_reference: {},
      expected_outputs: [],
      expected_outcomes: [],
      benefit_statement: "",
      owner: {
        owner_type: null,
        owner_user_id: null,
        owner_organization_unit_id: null,
        owner_security_role_id: null,
        owner_reference: null,
        effective_from: null,
        effective_to: null,
        accountability_statement: "",
        acceptance_status: null,
      },
      expected_value: {},
      monetizable_flag: false,
      dependencies: [],
      assumptions: [],
      constraints: [],
      risk_references: [],
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/versions/21/benefits/31"),
      expect.objectContaining({ method: "PUT", headers: expect.objectContaining({ "If-Match": '"9"' }) })
    );

    await strategicBenefitsApi.addBenefit("token", plan, version, {} as never);
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining("/versions/21/benefits"),
      expect.objectContaining({ headers: expect.objectContaining({ "Idempotency-Key": "fixed-key" }) })
    );
  });

  it("loads traceability through one optimized paginated endpoint", async () => {
    const fetchMock = vi.fn(async () => response([{ benefit_id: "BEN-000001" }], { "X-Next-Cursor": "next" }));
    vi.stubGlobal("fetch", fetchMock);
    const page = await strategicBenefitsApi.traceabilityPage("token", 7, null, 25);
    expect(page.nextCursor).toBe("next");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/strategic-benefits-plans/7/traceability?limit=25"),
      expect.anything()
    );
  });

  it("keeps effective ADMIN preview non-transactional", async () => {
    const fetchMock = vi.fn(async () => response({ persisted: false }));
    vi.stubGlobal("fetch", fetchMock);
    await strategicBenefitsApi.effectivePreview("admin", 101, 3, { readiness_rules: {} });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/admin/configurations/effective-preview"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ project_workspace_id: 101, configuration_id: 3, content_json: { readiness_rules: {} } }),
      })
    );
  });
});
