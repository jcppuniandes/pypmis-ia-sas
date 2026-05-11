import { describe, it, expect, vi, beforeEach } from "vitest";
import { apiFetch, ApiError } from "../src/api/client";

describe("apiFetch", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("throws ApiError on 401", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      text: () => Promise.resolve("Unauthorized"),
      statusText: "Unauthorized",
    }));

    await expect(apiFetch("/api/v1/auth/me", { token: "bad" })).rejects.toThrow(ApiError);
  });

  it("returns parsed JSON on success", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ status: "ok" }),
    }));

    const result = await apiFetch<{ status: string }>("/api/v1/health");
    expect(result.status).toBe("ok");
  });

  it("returns undefined on 204", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
    }));

    const result = await apiFetch("/api/v1/something");
    expect(result).toBeUndefined();
  });
});
