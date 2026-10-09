import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import BasicDataAdminView from "../basic-data/BasicDataAdminView";
import RiskGovernanceAdminView from "./RiskGovernanceAdminView";

const mocks = vi.hoisted(() => ({
  configurations: vi.fn(),
  clone: vi.fn(),
  update: vi.fn(),
  publish: vi.fn(),
  archive: vi.fn(),
  preview: vi.fn(),
}));
vi.mock("./policyApi", () => ({ governancePolicyApi: () => mocks }));
const published = {
  id: 1,
  code: "RG",
  name: "Governed policy",
  description: "Baseline",
  status: "published",
  revision: 1,
  version: 2,
  content_hash: "abc",
  content_json: {
    scope: { type: "tenant", workspace_id: null },
    capacity_statements: [],
    separation_of_duties: { preparer_cannot_publish: true },
  },
};
const draft = { ...published, id: 2, status: "draft", revision: 2, version: 1 };
beforeEach(() => {
  vi.clearAllMocks();
  mocks.configurations.mockResolvedValue([published, draft]);
  mocks.update.mockResolvedValue({ ...draft, version: 2 });
  mocks.clone.mockResolvedValue(draft);
  mocks.preview.mockResolvedValue({ persisted: false, status: "AVAILABLE", source: { revision: 1 } });
});
describe("Wave 2B reusable ADMIN policy", () => {
  it("hides policy mutation controls when backend action metadata denies them", async () => {
    mocks.configurations.mockResolvedValue([
      { ...published, allowed_actions: [] },
      { ...draft, allowed_actions: [] },
    ]);
    render(<RiskGovernanceAdminView token="scoped-reader" />);
    await screen.findAllByText("Governed policy", { selector: "h3" });
    expect(
      screen.queryByRole("button", { name: /Clone to DRAFT|Archive|Edit policy|Publish/ })
    ).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Inspect revision" })).toHaveLength(2);
  });
  it("allows draft preparation but hides independent publish when SoD disallows it", async () => {
    mocks.configurations.mockResolvedValue([{ ...draft, allowed_actions: ["edit"] }]);
    render(<BasicDataAdminView token="policy-author" />);
    expect(await screen.findByRole("button", { name: "Edit policy" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Publish" })).not.toBeInTheDocument();
  });
  it("exposes Risk governance groups without live Risk/BasicData transactions", async () => {
    render(<RiskGovernanceAdminView token="admin" />);
    await screen.findAllByText("Governed policy", { selector: "h3" });
    expect(screen.getByText("Risk Capacity", { selector: "span" })).toBeInTheDocument();
    expect(screen.getByText("Risk Appetite", { selector: "span" })).toBeInTheDocument();
    expect(screen.getByText("Risk Thresholds", { selector: "span" })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Create readiness assessment|Add Basic Data item/ })
    ).not.toBeInTheDocument();
  });
  it("stages a real section and preserves input on an ETag error", async () => {
    const user = userEvent.setup();
    mocks.update.mockRejectedValue(new Error("412 ETAG_MISMATCH"));
    render(<RiskGovernanceAdminView token="admin" />);
    await user.click(await screen.findByRole("button", { name: "Edit policy" }));
    await user.click(
      within(screen.getByLabelText("Policy section editor")).getByRole("button", { name: "Risk Capacity" })
    );
    const input = screen.getByRole("textbox", { name: "Governed policy section JSON" });
    fireEvent.change(input, {
      target: { value: '[{"code":"CAPACITY","dimension_code":"financial","statement":"Controlled limit"}]' },
    });
    await user.click(screen.getByRole("button", { name: "Save DRAFT revision" }));
    await screen.findByText("412 ETAG_MISMATCH");
    expect(mocks.update).toHaveBeenCalledWith(
      "admin",
      draft,
      expect.objectContaining({
        capacity_statements: [{ code: "CAPACITY", dimension_code: "financial", statement: "Controlled limit" }],
      })
    );
    expect(input).toHaveValue('[{"code":"CAPACITY","dimension_code":"financial","statement":"Controlled limit"}]');
  });
  it("resolves backend preview persisted=false and does not implement UI precedence", async () => {
    const user = userEvent.setup();
    render(<RiskGovernanceAdminView token="admin" />);
    await user.click(await screen.findByRole("button", { name: "Preview persisted=false" }));
    await screen.findByText("persisted=false", { selector: "strong" });
    await waitFor(() =>
      expect(mocks.preview).toHaveBeenCalledWith("admin", expect.objectContaining({ configuration_id: 1 }))
    );
    expect(mocks.publish).not.toHaveBeenCalled();
  });
  it("uses the same lifecycle for Basic Data categories, tailoring, quality and freshness", async () => {
    render(<BasicDataAdminView token="admin" />);
    await screen.findByRole("heading", { name: "Basic Data Readiness Configuration" });
    for (const label of [
      "Data Categories",
      "Requirements",
      "FEL Stage Rules",
      "Gate Profile Rules",
      "Quality Rules",
      "Confidence Rules",
      "Freshness Rules",
      "Coverage Rules",
      "Review / SoD",
    ])
      expect(screen.getByText(label, { selector: "span" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Complete assessment" })).not.toBeInTheDocument();
  });
});
