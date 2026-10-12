import { beforeEach, describe, expect, it, vi } from "vitest";
import { qraEngineApi, type QraRun } from "./api";
const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("../../api/client", () => ({ apiFetch: fetchMock }));
vi.mock("../capital-planning/api", () => ({ createIdempotencyKey: () => "qra-run-action-key" }));
beforeEach(() => {
  vi.clearAllMocks();
  fetchMock.mockResolvedValue({});
});
describe("QRA run API", () => {
  it("creates only under an approved model with a caller-retained idempotency key", async () => {
    await qraEngineApi.create("user", 8, { seed: 19, iterations: 1000 }, "retained-key");
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/qra-engine/models/8/runs",
      expect.objectContaining({
        method: "POST",
        token: "user",
        headers: { "Idempotency-Key": "retained-key" },
        body: '{"seed":19,"iterations":1000}',
      })
    );
  });
  it.each(["execute", "cancel", "review", "accept"] as const)("uses ETag and idempotency for %s", async (action) => {
    await qraEngineApi.action("user", { id: 3, revision_version: 5 } as QraRun, action, "Governed action");
    expect(fetchMock).toHaveBeenLastCalledWith(
      `/api/v1/qra-engine/runs/3/${action}`,
      expect.objectContaining({
        headers: { "If-Match": '"5"', "Idempotency-Key": "qra-run-action-key" },
        body: '{"comments":"Governed action"}',
      })
    );
  });
  it("keeps run/history/models page reads bounded and propagates polling cancellation", async () => {
    const controller = new AbortController();
    await qraEngineApi.runs("user", 41, 2, controller.signal);
    expect(fetchMock).toHaveBeenLastCalledWith("/api/v1/qra-engine/projects/41/runs?page=2&page_size=25", {
      token: "user",
      signal: controller.signal,
    });
    await qraEngineApi.models("user", 41, 2, controller.signal);
    expect(fetchMock).toHaveBeenLastCalledWith("/api/v1/qra-engine/projects/41/approved-models?page=2&page_size=25", {
      token: "user",
      signal: controller.signal,
    });
    await qraEngineApi.status("user", 3, controller.signal);
    expect(fetchMock).toHaveBeenLastCalledWith("/api/v1/qra-engine/runs/3/status", {
      token: "user",
      signal: controller.signal,
    });
  });
  it("delegates comparison and pre-run validation to the backend", async () => {
    await qraEngineApi.compare("user", 3, 4);
    expect(fetchMock).toHaveBeenLastCalledWith("/api/v1/qra-engine/runs/compare?left_id=3&right_id=4", {
      token: "user",
    });
    await qraEngineApi.preflight("user", 8);
    expect(fetchMock).toHaveBeenLastCalledWith("/api/v1/qra-engine/models/8/preflight", { token: "user" });
  });
});
