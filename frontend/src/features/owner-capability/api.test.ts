import { beforeEach, describe, expect, it, vi } from "vitest";
import { ownerCapabilityApi, type OwnerCapabilityAssessment } from "./api";
const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("../../api/client", () => ({ apiFetch: fetchMock }));
vi.mock("../capital-planning/api", () => ({ createIdempotencyKey: () => "owner-command-key" }));
beforeEach(() => {
  vi.clearAllMocks();
  fetchMock.mockResolvedValue({});
});
const assessment = { id: 17, revision_version: 4 } as OwnerCapabilityAssessment;
describe("Owner Capability API", () => {
  it("sends server ETag and idempotency for immutable version commands", async () => {
    await ownerCapabilityApi.assessmentAction("actor", assessment, "complete");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/owner-capability/assessments/17/complete",
      expect.objectContaining({
        method: "POST",
        token: "actor",
        headers: { "If-Match": '"4"', "Idempotency-Key": "owner-command-key" },
      })
    );
  });
  it("preserves the server assessment version for mitigation edits", async () => {
    await ownerCapabilityApi.updateMitigation("actor", assessment, "2", { description: "External support" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/owner-capability/assessments/17/mitigations/2",
      expect.objectContaining({
        method: "PUT",
        headers: { "If-Match": '"4"', "Idempotency-Key": "owner-command-key" },
        body: '{"description":"External support"}',
      })
    );
  });
  it("uses scoped server pagination and encoded search", async () => {
    await ownerCapabilityApi.options("actor", "Mine & Plant", 2);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/owner-capability/options?page=2&page_size=100&search=Mine%20%26%20Plant",
      { token: "actor" }
    );
    await ownerCapabilityApi.assessments("actor", 41, 3);
    expect(fetchMock).toHaveBeenLastCalledWith("/api/v1/owner-capability/projects/41/assessments?page=3&page_size=25", {
      token: "actor",
    });
  });
  it("context and refresh preview are read-only requests without command writes", async () => {
    await ownerCapabilityApi.contexts("actor", 41);
    await ownerCapabilityApi.refreshPreview("actor", 17);
    expect(fetchMock).toHaveBeenLastCalledWith("/api/v1/owner-capability/assessments/17/refresh-preview", {
      token: "actor",
    });
    for (const call of fetchMock.mock.calls) expect(call[1]).not.toHaveProperty("method");
  });
});
