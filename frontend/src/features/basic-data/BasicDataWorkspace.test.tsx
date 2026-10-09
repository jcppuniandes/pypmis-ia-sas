import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import BasicDataWorkspace from "./BasicDataWorkspace";
const mocks = vi.hoisted(() => ({
  options: vi.fn(),
  requirements: vi.fn(),
  items: vi.fn(),
  assessments: vi.fn(),
  currentReadiness: vi.fn(),
  createItem: vi.fn(),
  updateItem: vi.fn(),
  validateItem: vi.fn(),
  createAssessment: vi.fn(),
  assessmentAction: vi.fn(),
  refreshPreview: vi.fn(),
  effective: vi.fn(),
}));
vi.mock("./api", () => ({ basicDataApi: mocks }));
vi.mock("../risk-governance/policyApi", () => ({ riskGovernanceApi: { effective: mocks.effective } }));
const item = {
  id: 1,
  requirement_code: "GEOTECH",
  availability: "AVAILABLE",
  validation_state: "NOT_VALIDATED",
  quality: "ACCEPTABLE",
  confidence: "HIGH",
  revision_version: 3,
  source_reference: "STUDY-01",
};
const draft = {
  id: 2,
  assessment_number: "BDA-000002",
  assessment_version: 1,
  status: "DRAFT",
  revision_version: 1,
  snapshot_json: {},
  assessment_hash: null,
};
beforeEach(() => {
  vi.clearAllMocks();
  mocks.options.mockResolvedValue({
    projects: [{ id: 41, code: "MIN", name: "Mining fixture" }],
    quality_values: ["PRELIMINARY", "ACCEPTABLE"],
    confidence_values: ["PRELIMINARY", "HIGH"],
    availability_values: ["NOT_AVAILABLE", "AVAILABLE"],
    validation_values: ["NOT_VALIDATED", "VALIDATED"],
    allowed_actions: [
      "item_create",
      "item_edit",
      "item_validate",
      "assessment_create",
      "assessment_submit",
      "assessment_complete",
    ],
  });
  mocks.requirements.mockResolvedValue({
    configuration: { revision: 1 },
    context: { fel_stage: "FEL-2", definition_assessment: { score: 320, hash: "pdri-hash" } },
    requirements: [
      {
        requirement_code: "GEOTECH",
        name: "Geotechnical",
        category: "site",
        blocking: true,
        minimum_quality: "PRELIMINARY",
        minimum_confidence: "PRELIMINARY",
        minimum_validation_state: "VALIDATED",
      },
    ],
  });
  mocks.items.mockResolvedValue({ items: [item], total: 1, page: 1, page_size: 25 });
  mocks.assessments.mockResolvedValue({ items: [draft], total: 1, page: 1, page_size: 25 });
  mocks.currentReadiness.mockResolvedValue({
    status: "BLOCKED",
    source_current: false,
    coverage: { required: 10, satisfied: 9, partial: 0, missing: 1, percentage: 90 },
    critical_gaps: ["GEOTECH_MISSING"],
    blockers: ["GEOTECH_MISSING"],
  });
  mocks.effective.mockResolvedValue({
    status: "AVAILABLE",
    source: { content_hash: "risk-hash", revision: 1 },
    thresholds: [],
  });
  mocks.createItem.mockResolvedValue(item);
  mocks.assessmentAction.mockResolvedValue({ persisted: false, status: "READY" });
});
describe("Basic Data USER workspace", () => {
  it("renders exact denominator and contextual FEL/PDRI without ADMIN controls", async () => {
    const user = userEvent.setup();
    render(<BasicDataWorkspace token="user" />);
    await screen.findByText(/9 satisfied \/ 10 required/);
    expect(screen.queryByRole("button", { name: /Publish|Clone to DRAFT/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "FEL / PDRI Context" }));
    expect(screen.getByText(/"score": 320/)).toBeInTheDocument();
    expect(screen.getByText(/pdri-hash/)).toBeInTheDocument();
    expect(mocks.effective).toHaveBeenCalledWith("user", 41);
  });
  it("creates reference metadata separately from validation", async () => {
    const user = userEvent.setup();
    render(<BasicDataWorkspace token="user" />);
    await screen.findByText(/9 satisfied/);
    await user.click(screen.getByRole("button", { name: "Basic Data Register" }));
    await user.click(screen.getByRole("button", { name: "Add Basic Data item" }));
    await user.type(screen.getByLabelText("Evidence reference"), "SURVEY-02");
    await user.selectOptions(screen.getByLabelText("Quality"), "ACCEPTABLE");
    await user.click(screen.getByRole("button", { name: "Save Basic Data item" }));
    await waitFor(() =>
      expect(mocks.createItem).toHaveBeenCalledWith(
        "user",
        41,
        expect.objectContaining({
          source_reference: "SURVEY-02",
          quality: "ACCEPTABLE",
          evidence_refs: [expect.objectContaining({ source_reference: "SURVEY-02" })],
        })
      )
    );
    expect(mocks.createItem.mock.calls[0][2]).not.toHaveProperty("validation_state");
    expect(mocks.validateItem).not.toHaveBeenCalled();
  });
  it("offers preview and submit but completion only after IN_REVIEW", async () => {
    const user = userEvent.setup();
    render(<BasicDataWorkspace token="user" />);
    await screen.findByText(/BDA-000002 · DRAFT/, { selector: "strong" });
    expect(screen.queryByRole("button", { name: "Complete assessment" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Preview assessment" }));
    await screen.findByText("persisted=false", { selector: "strong" });
    expect(mocks.assessmentAction).toHaveBeenCalledWith("user", draft, "preview");
  });
  it("hides action controls for read-only actors, while backend remains authoritative", async () => {
    mocks.options.mockResolvedValueOnce({ ...(await mocks.options()), allowed_actions: [] });
    const user = userEvent.setup();
    render(<BasicDataWorkspace token="readonly" />);
    await screen.findByText(/9 satisfied/);
    expect(screen.queryByRole("button", { name: "Create readiness assessment" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Validation" }));
    expect(screen.queryByRole("button", { name: "Validate GEOTECH" })).not.toBeInTheDocument();
  });
  it("uses Project-scoped action metadata rather than tenant-wide option permissions", async () => {
    mocks.requirements.mockResolvedValueOnce({ ...(await mocks.requirements()), allowed_actions: [] });
    const user = userEvent.setup();
    render(<BasicDataWorkspace token="scoped" />);
    await screen.findByText(/9 satisfied/);
    expect(screen.queryByRole("button", { name: "Create readiness assessment" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Basic Data Register" }));
    expect(screen.queryByRole("button", { name: "Add Basic Data item" })).not.toBeInTheDocument();
  });
  it("honors entity-level validation authority supplied by the backend", async () => {
    mocks.items.mockResolvedValueOnce({
      items: [{ ...item, allowed_actions: ["item_edit"] }],
      total: 1,
      page: 1,
      page_size: 25,
    });
    const user = userEvent.setup();
    render(<BasicDataWorkspace token="editor" />);
    await screen.findByText(/9 satisfied/);
    await user.click(screen.getByRole("button", { name: "Validation" }));
    expect(screen.getByRole("button", { name: "Edit GEOTECH" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Validate GEOTECH" })).not.toBeInTheDocument();
  });
  it("searches authorized Projects on the server instead of loading all tenant identities", async () => {
    const user = userEvent.setup();
    render(<BasicDataWorkspace token="scoped" />);
    await screen.findByText(/9 satisfied/);
    await user.type(screen.getByRole("textbox", { name: "Find authorized Projects" }), "Mining");
    await user.click(screen.getByRole("button", { name: "Search Projects" }));
    await waitFor(() => expect(mocks.options).toHaveBeenCalledWith("scoped", "Mining"));
  });
});
