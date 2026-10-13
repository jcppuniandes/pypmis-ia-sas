import { beforeEach, describe, expect, it, vi } from "vitest";
import { qraFoundationApi, type QraRecord } from "./api";
const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("../../api/client", () => ({ apiFetch: fetchMock }));
vi.mock("../capital-planning/api", () => ({ createIdempotencyKey: () => "qra-command-key" }));
beforeEach(() => {
  vi.clearAllMocks();
  fetchMock.mockResolvedValue({});
});
const item = { id: 9, revision_version: 7 } as QraRecord;
describe("QRA Foundation API", () => {
  it("updates bounded input pages and metadata separately with concurrency and idempotency", async () => {
    await qraFoundationApi.updateModelInputs("actor", item, [
      { source_kind: "COST", source_item_ref: "A", mode: "DETERMINISTIC" },
    ]);
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/qra-foundation/models/9/inputs",
      expect.objectContaining({
        method: "PATCH",
        headers: { "If-Match": '"7"', "Idempotency-Key": "qra-command-key" },
        body: '{"inputs":[{"source_kind":"COST","source_item_ref":"A","mode":"DETERMINISTIC"}]}',
      })
    );
    await qraFoundationApi.updateModelMetadata("actor", item, { title: "Updated model metadata" });
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/qra-foundation/models/9/metadata",
      expect.objectContaining({
        method: "PATCH",
        headers: { "If-Match": '"7"', "Idempotency-Key": "qra-command-key" },
        body: '{"title":"Updated model metadata"}',
      })
    );
  });
  it("supports summary reads and server-paginated frozen item populations without writes", async () => {
    await qraFoundationApi.modelCorrelations("actor", 9);
    expect(fetchMock).toHaveBeenLastCalledWith("/api/v1/qra-foundation/models/9/correlations", { token: "actor" });
    await qraFoundationApi.record("actor", "model", 9, true);
    expect(fetchMock).toHaveBeenLastCalledWith("/api/v1/qra-foundation/models/9?summary=true", { token: "actor" });
    await qraFoundationApi.recordItems("actor", "schedule", 9, 3);
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/qra-foundation/schedule-assessments/9/items?page=3&page_size=25",
      { token: "actor" }
    );
    await qraFoundationApi.sourceOptions("actor", 41, "cost", 2);
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/qra-foundation/projects/41/cost-source-options?page=2&page_size=100",
      { token: "actor" }
    );
  });
  it("uses canonical scoped pagination and encoded Project search", async () => {
    await qraFoundationApi.options("actor", "Plant & Mine", 2);
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/qra-foundation/options?page=2&page_size=100&search=Plant%20%26%20Mine",
      { token: "actor" }
    );
    await qraFoundationApi.records("actor", 41, "schedule", 3);
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/qra-foundation/projects/41/schedule-assessments?page=3&page_size=25",
      { token: "actor" }
    );
  });
  it.each(["cost", "schedule", "model"] as const)(
    "uses server concurrency and idempotency for %s edits",
    async (kind) => {
      await qraFoundationApi.update("actor", kind, item, { title: "Source" });
      expect(fetchMock).toHaveBeenLastCalledWith(
        `/api/v1/qra-foundation/${kind === "model" ? "models" : `${kind}-assessments`}/9`,
        expect.objectContaining({
          method: "PUT",
          token: "actor",
          headers: { "If-Match": '"7"', "Idempotency-Key": "qra-command-key" },
          body: '{"title":"Source"}',
        })
      );
    }
  );
  it("creates only model definitions, never run or simulate requests", async () => {
    await qraFoundationApi.create("actor", 41, "model", { analysis_type: "COST_QRA" });
    await qraFoundationApi.action("actor", "model", item, "approve", "Independent approval");
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/qra-foundation/models/9/approve",
      expect.objectContaining({
        body: '{"comments":"Independent approval"}',
        headers: { "If-Match": '"7"', "Idempotency-Key": "qra-command-key" },
      })
    );
    expect(fetchMock.mock.calls.every(([path]) => !/\/run|\/simulate/.test(String(path)))).toBe(true);
  });
  it("retrieves contexts, current sources and refresh without commands", async () => {
    await qraFoundationApi.contexts("actor", 41);
    await qraFoundationApi.sourceOptions("actor", 41, "schedule");
    await qraFoundationApi.refreshPreview("actor", "cost", 9);
    expect(fetchMock).toHaveBeenLastCalledWith("/api/v1/qra-foundation/cost-assessments/9/refresh-preview", {
      token: "actor",
    });
    expect(fetchMock.mock.calls.every((call) => !call[1].method)).toBe(true);
  });
});
