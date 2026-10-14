import { beforeEach, describe, expect, it, vi } from "vitest";
import { investmentGatePreparationApi } from "../investment-gate-preparation/api";
import type { InvestmentGatePreparation } from "../investment-gate-preparation/types";
import { investmentEvidencePolicyApi } from "./api";
import type { EvidencePolicyConfiguration } from "./types";

const mocks = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock("../../api/client", () => ({ apiFetch: mocks.fetch }));
describe("Existing evidence lifecycle request contracts", () => {
  beforeEach(() => mocks.fetch.mockReset());
  it("carries the explicit retry key and ETag for a policy clone without another API", async () => {
    const policy = { id: 8, version: 4 } as EvidencePolicyConfiguration;
    await investmentEvidencePolicyApi.clone("admin", policy, "stable-retry-key-123");
    expect(mocks.fetch).toHaveBeenCalledWith("/api/v1/investment-evidence-policy/configurations/8/clone", {
      method: "POST",
      token: "admin",
      headers: { "If-Match": '"4"', "Idempotency-Key": "stable-retry-key-123" },
    });
  });
  it("binds explicit Gate evidence refresh to the preview hash, ETag and idempotency key", async () => {
    const preparation = { id: 9, revision_version: 6 } as InvestmentGatePreparation;
    await investmentGatePreparationApi.refresh("preparer", preparation, "a".repeat(64), "stable-refresh-key");
    expect(mocks.fetch).toHaveBeenCalledWith("/api/v1/investment-gate-preparations/9/refresh", {
      method: "POST",
      token: "preparer",
      headers: { "If-Match": '"6"' },
      body: JSON.stringify({ expected_source_hash: "a".repeat(64), idempotency_key: "stable-refresh-key" }),
    });
  });
});
