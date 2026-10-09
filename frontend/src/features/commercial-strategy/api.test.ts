import { afterEach, describe, expect, it, vi } from "vitest";
import { commercialStrategyApi } from "./api";

const strategy = {
  id: 1,
  strategy_number: "CCS-000001",
  project_workspace_id: 10,
  current_version: null,
  allowed_actions: {},
  revision_version: 2,
  created_at: "2026-09-15T00:00:00Z",
  updated_at: "2026-09-15T00:00:00Z",
};

function response(data: unknown, headers: Record<string, string> = {}) {
  return {
    ok: true,
    status: 200,
    headers: new Headers(headers),
    json: async () => data,
  } as Response;
}

describe("Commercial Strategy API client", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("resolves effective USER catalogs for the selected Project Workspace", async () => {
    const fetchMock = vi.fn(async () => response({ procurement_approaches: ["EPC"] }));
    vi.stubGlobal("fetch", fetchMock);

    await commercialStrategyApi.options("token", 101);

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/commercial-strategies/options?project_workspace_id=101"),
      expect.objectContaining({ headers: expect.objectContaining({ Authorization: "Bearer token" }) })
    );
  });

  it("reads a bounded cursor page from response headers", async () => {
    const fetchMock = vi.fn(async () =>
      response([strategy], {
        "X-Next-Cursor": "cursor-2",
        "X-Page-Limit": "50",
        "X-Result-Count": "1",
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    const page = await commercialStrategyApi.listPage("token", {
      queue: "in_review",
      search: "capital works",
      cursor: "cursor-1",
    });

    expect(page).toEqual({ items: [strategy], nextCursor: "cursor-2", pageLimit: 50, resultCount: 1 });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining(
        "/api/v1/commercial-strategies?queue=in_review&search=capital+works&cursor=cursor-1&limit=50"
      ),
      expect.objectContaining({ headers: expect.objectContaining({ Authorization: "Bearer token" }) })
    );
  });

  it("sends ETag and idempotency controls on governed lifecycle actions", async () => {
    const fetchMock = vi.fn(async () => response({}));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "fixed-idempotency-key" });
    const version = {
      id: 11,
      commercial_strategy_id: 1,
      version_number: 1,
      version_purpose: "INITIAL_COMMERCIAL_ASSESSMENT",
      status: "IN_REVIEW" as const,
      fel_stage_code: "FEL-2",
      content_json: {} as never,
      readiness_json: {},
      readiness_warnings_json: [],
      readiness_blockers_json: [],
      source_references_json: {},
      source_hashes_json: {},
      source_bundle_hash: "source",
      source_current: true,
      configuration_id: 2,
      configuration_revision: 1,
      configuration_hash: "config",
      content_hash: "content",
      commercial_strategy_hash: "strategy",
      preparer_user_id: 1,
      reviewer_user_id: 2,
      created_at: "2026-09-15T00:00:00Z",
      updated_at: "2026-09-15T00:00:00Z",
      completed_at: null,
      revision_version: 7,
      allowed_actions: { can_complete: true },
    };

    await commercialStrategyApi.lifecycle("token", strategy, version, "complete");

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/commercial-strategies/1/versions/11/complete"),
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "If-Match": '"7"',
          "Idempotency-Key": "fixed-idempotency-key",
        }),
      })
    );
  });

  it("uses the strategy ETag when applying a refresh as a new revision", async () => {
    const fetchMock = vi.fn(async () => response({}));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "fixed-idempotency-key" });

    await commercialStrategyApi.refreshApply("token", strategy);

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/commercial-strategies/1/refresh-apply"),
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "If-Match": '"2"',
          "Idempotency-Key": "fixed-idempotency-key",
        }),
      })
    );
  });

  it("keeps ADMIN effective preview non-transactional", async () => {
    const fetchMock = vi.fn(async () => response({ persisted: false }));
    vi.stubGlobal("fetch", fetchMock);

    await commercialStrategyApi.effectivePreview("admin-token", 101, 8);

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/commercial-strategies/admin/configurations/effective-preview"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ project_workspace_id: 101, configuration_id: 8, content_json: null }),
      })
    );
  });
});
