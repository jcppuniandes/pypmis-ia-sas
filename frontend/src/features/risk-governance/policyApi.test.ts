import { beforeEach, describe, expect, it, vi } from "vitest";
import { basicDataApi } from "../basic-data/api";
import { governancePolicyApi, riskGovernanceApi, type GovernanceConfiguration } from "./policyApi";
const fetchMock = vi.fn();
const item = {
  id: 1,
  version: 4,
  name: "Policy",
  description: "Governed",
  content_json: {},
} as GovernanceConfiguration;
beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({ id: 1 }), headers: new Headers() });
});
describe("Wave 2B API boundaries", () => {
  it("preserves clone scope unless an explicit target Workspace is selected", async () => {
    const api = governancePolicyApi("/api/v1/basic-data");
    await api.clone("token", item, null);
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/basic-data/admin/configurations/1/clone",
      expect.objectContaining({ body: "{}" })
    );
    await api.clone("token", item, 45);
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/basic-data/admin/configurations/1/clone",
      expect.objectContaining({ body: JSON.stringify({ target_workspace_id: 45 }) })
    );
  });
  it("sends configuration version and idempotency headers, no executable formula", async () => {
    await governancePolicyApi("/api/v1/risk-governance").update("token", item, { thresholds: [] });
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/risk-governance/admin/configurations/1",
      expect.objectContaining({
        method: "PUT",
        headers: expect.objectContaining({
          "If-Match": '"4"',
          "Idempotency-Key": expect.any(String),
          Authorization: "Bearer token",
        }),
        body: JSON.stringify({ name: "Policy", description: "Governed", content_json: { thresholds: [] } }),
      })
    );
  });
  it("propagates 412 without automatic overwrite or retry", async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, status: 412, text: async () => "ETAG_MISMATCH" });
    await expect(governancePolicyApi("/api/v1/basic-data").publish("token", item)).rejects.toThrow("ETAG_MISMATCH");
  });
  it("USER reads Risk context without any configuration mutation", async () => {
    await riskGovernanceApi.effective("token", 41);
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/risk-governance/effective?workspace_id=41",
      expect.objectContaining({ headers: { Authorization: "Bearer token" } })
    );
  });
  it("uses canonical Project identity and server-side pagination", async () => {
    await basicDataApi.items("token", 41, 3);
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/basic-data/projects/41/items?page=3&page_size=25",
      expect.anything()
    );
  });
});
