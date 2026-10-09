import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import OwnerCapabilityWorkspace from "./OwnerCapabilityWorkspace";
const mocks = vi.hoisted(() => ({
  options: vi.fn(),
  requirements: vi.fn(),
  contexts: vi.fn(),
  assessments: vi.fn(),
  currentReadiness: vi.fn(),
  createAssessment: vi.fn(),
  updateAssessment: vi.fn(),
  assessmentAction: vi.fn(),
  refreshPreview: vi.fn(),
  createMitigation: vi.fn(),
  updateMitigation: vi.fn(),
}));
vi.mock("./api", () => ({ ownerCapabilityApi: mocks }));
const draft = {
  id: 2,
  title: "Capability",
  comments: "",
  assessment_number: "OCA-000002",
  assessment_version: 1,
  status: "DRAFT",
  revision_version: 3,
  aggregate_json: { items: [], gaps: [], mitigations: [] },
  snapshot_json: {},
  assessment_hash: null,
  allowed_actions: ["assessment_edit", "assessment_submit", "mitigation_edit"],
};
const rules = {
  configuration: { revision: 1, content_hash: "framework-hash" },
  context: { governance_model: "CAPITAL_OWNER", fel_stage: "FEL-3" },
  maturity_scale: [{ code: "INITIAL" }, { code: "DEFINED" }, { code: "IMPLEMENTED" }],
  quality_scale: [{ code: "NOT_AVAILABLE" }, { code: "VALIDATED" }],
  requirements: [
    {
      requirement_code: "SPONSOR",
      name: "Sponsor accountability",
      dimension: "GOVERNANCE",
      minimum_maturity: "IMPLEMENTED",
      minimum_evidence_quality: "VALIDATED",
      blocking: true,
    },
  ],
  allowed_actions: ["assessment_create"],
};
beforeEach(() => {
  vi.clearAllMocks();
  mocks.options.mockResolvedValue({
    projects: [{ id: 41, code: "MIN", name: "Mining fixture" }],
    confidence_values: ["PRELIMINARY", "MODERATE", "HIGH"],
    allowed_actions: ["assessment_create"],
  });
  mocks.requirements.mockResolvedValue(rules);
  mocks.contexts.mockResolvedValue({
    fel_pdri: { score: 320, hash: "pdri-hash" },
    commercial: { id: 9, version: 2, hash: "commercial-hash" },
    resources: { id: 12, hash: "resource-hash" },
    risk_governance: { revision: 1 },
    basic_data: { status: "READY" },
  });
  mocks.assessments.mockResolvedValue({ items: [draft], total: 1, page: 1, page_size: 25 });
  mocks.currentReadiness.mockResolvedValue({
    readiness_status: "BLOCKED",
    source_current: false,
    coverage: { required: 10, satisfied: 9, percentage: 90 },
    blockers: ["SPONSOR_MISSING"],
  });
  mocks.assessmentAction.mockResolvedValue({
    persisted: false,
    readiness_status: "READY",
    coverage: { required: 1, satisfied: 1, percentage: 100 },
  });
  mocks.createAssessment.mockResolvedValue(draft);
  mocks.updateAssessment.mockResolvedValue(draft);
  mocks.createMitigation.mockResolvedValue(draft);
});
describe("Owner Capability USER workspace", () => {
  it("renders backend readiness and exact denominator, never ADMIN controls", async () => {
    render(<OwnerCapabilityWorkspace token="user" />);
    await screen.findByText(/9 satisfied \/ 10 required/);
    expect(screen.getByText("OVERALL_OWNER_CAPABILITY_READINESS · BLOCKED")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Publish|Clone to DRAFT|Edit policy/ })).not.toBeInTheDocument();
    expect(screen.getByText(/SPONSOR_MISSING/)).toBeInTheDocument();
  });
  it("uses effective configurable scales and quality independent from confidence", async () => {
    const user = userEvent.setup();
    render(<OwnerCapabilityWorkspace token="user" />);
    await screen.findByText(/9 satisfied/);
    await user.click(screen.getByRole("button", { name: "Capability Assessment" }));
    await user.click(screen.getByRole("button", { name: "Add capability item" }));
    await user.selectOptions(screen.getByLabelText("Current maturity"), "IMPLEMENTED");
    await user.selectOptions(screen.getByLabelText("Evidence quality"), "VALIDATED");
    await user.selectOptions(screen.getByLabelText("Confidence"), "HIGH");
    await user.type(screen.getByLabelText("Evidence reference"), "CHARTER-001");
    await user.click(screen.getByRole("button", { name: "Save capability item" }));
    await waitFor(() =>
      expect(mocks.updateAssessment).toHaveBeenCalledWith(
        "user",
        draft,
        expect.objectContaining({
          items: [
            expect.objectContaining({
              requirement_code: "SPONSOR",
              current_maturity: "IMPLEMENTED",
              evidence_quality: "VALIDATED",
              confidence: "HIGH",
              evidence_refs: [expect.objectContaining({ source_reference: "CHARTER-001" })],
            }),
          ],
        })
      )
    );
    expect(screen.queryByText("OVERALL_OWNER_CAPABILITY_READINESS · READY")).not.toBeInTheDocument();
  });
  it("stores a blocking gap independently from capability evidence", async () => {
    const user = userEvent.setup();
    render(<OwnerCapabilityWorkspace token="user" />);
    await screen.findByText(/9 satisfied/);
    await user.click(screen.getByRole("button", { name: "Gaps" }));
    await user.click(screen.getByRole("button", { name: "Add capability gap" }));
    await user.type(screen.getByLabelText("Gap"), "Sponsor accountability missing");
    await user.click(screen.getByLabelText("Blocking gap"));
    await user.selectOptions(screen.getByLabelText("Severity"), "CRITICAL");
    await user.click(screen.getByRole("button", { name: "Save capability gap" }));
    await waitFor(() =>
      expect(mocks.updateAssessment).toHaveBeenCalledWith(
        "user",
        draft,
        expect.objectContaining({
          gaps: [
            expect.objectContaining({
              description: "Sponsor accountability missing",
              blocking: true,
              severity: "CRITICAL",
            }),
          ],
        })
      )
    );
  });
  it("honors configured scale labels, descriptions and order while preserving value codes", async () => {
    mocks.requirements.mockResolvedValue({
      ...rules,
      maturity_scale: [
        {
          code: "IMPLEMENTED",
          name: "Operationally established",
          description: "Implemented governance mechanisms",
          order: 2,
        },
        { code: "INITIAL", name: "Early governance", description: "Initial owner mechanisms", order: 1 },
      ],
      quality_scale: [
        { code: "VALIDATED", name: "Source verified", description: "Verified documentary evidence", order: 1 },
      ],
    });
    const user = userEvent.setup();
    render(<OwnerCapabilityWorkspace token="user" />);
    await screen.findByText(/9 satisfied/);
    await user.click(screen.getByRole("button", { name: "Capability Assessment" }));
    await user.click(screen.getByRole("button", { name: "Add capability item" }));
    expect(screen.getByRole("option", { name: "Operationally established (IMPLEMENTED)" })).toHaveAttribute(
      "title",
      "Implemented governance mechanisms"
    );
    expect(screen.getByLabelText("Current maturity")).toHaveValue("INITIAL");
    expect(screen.getByRole("option", { name: "Source verified (VALIDATED)" })).toHaveAttribute("value", "VALIDATED");
  });
  it("creates external support mitigation without computing readiness", async () => {
    const user = userEvent.setup();
    render(<OwnerCapabilityWorkspace token="user" />);
    await screen.findByText(/9 satisfied/);
    await user.click(screen.getByRole("button", { name: "Mitigation Plan" }));
    await user.click(screen.getByRole("button", { name: "Add mitigation" }));
    await user.type(screen.getByLabelText("Action"), "Independent Owner engineer support");
    await user.type(screen.getByLabelText("Approach"), "EXTERNAL_SPECIALIST");
    await user.type(screen.getByLabelText("Action owner"), "Assurance function");
    await user.click(screen.getByRole("button", { name: "Save mitigation" }));
    await waitFor(() =>
      expect(mocks.createMitigation).toHaveBeenCalledWith(
        "user",
        draft,
        expect.objectContaining({
          approach: "EXTERNAL_SPECIALIST",
          description: "Independent Owner engineer support",
          status: "PROPOSED",
          owner: "Assurance function",
        })
      )
    );
    expect(mocks.assessmentAction).not.toHaveBeenCalled();
  });
  it("exposes context references only and preserves historical snapshots", async () => {
    const user = userEvent.setup();
    mocks.assessments.mockResolvedValue({
      items: [
        {
          ...draft,
          status: "COMPLETED",
          assessment_hash: "frozen-hash",
          snapshot_json: { context: { commercial_hash: "old-hash" } },
          allowed_actions: ["assessment_create"],
        },
      ],
      total: 1,
      page: 1,
      page_size: 25,
    });
    render(<OwnerCapabilityWorkspace token="reviewer" />);
    await screen.findByText(/9 satisfied/);
    await user.click(screen.getByRole("button", { name: "Commercial Context" }));
    expect(screen.getByText(/commercial-hash/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add capability item" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "History" }));
    await user.click(screen.getByText("Frozen assessment snapshot and source lineage"));
    expect(screen.getByText(/old-hash/)).toBeInTheDocument();
    expect(screen.getByText(/"assessment_hash": "frozen-hash"/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply successor DRAFT" })).toBeInTheDocument();
  });
  it("honors explicit entity and Project action denial", async () => {
    mocks.requirements.mockResolvedValue({ ...rules, allowed_actions: [] });
    mocks.assessments.mockResolvedValue({
      items: [{ ...draft, allowed_actions: [] }],
      total: 1,
      page: 1,
      page_size: 25,
    });
    const user = userEvent.setup();
    render(<OwnerCapabilityWorkspace token="viewer" />);
    await screen.findByText(/9 satisfied/);
    expect(screen.queryByRole("button", { name: "Create capability assessment" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Submit assessment" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Capability Assessment" }));
    expect(screen.queryByRole("button", { name: "Add capability item" })).not.toBeInTheDocument();
  });
  it("shows independent review and complete only when backend allows IN_REVIEW", async () => {
    mocks.assessments.mockResolvedValue({
      items: [{ ...draft, status: "IN_REVIEW", allowed_actions: ["assessment_review", "assessment_complete"] }],
      total: 1,
      page: 1,
      page_size: 25,
    });
    render(<OwnerCapabilityWorkspace token="reviewer" />);
    await screen.findByText(/9 satisfied/);
    expect(screen.getByRole("button", { name: "Review assessment" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Complete assessment" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Submit assessment" })).not.toBeInTheDocument();
  });
  it("keeps preview READY separate from current governed readiness", async () => {
    const user = userEvent.setup();
    render(<OwnerCapabilityWorkspace token="user" />);
    await screen.findByText(/9 satisfied/);
    await user.click(screen.getByRole("button", { name: "Preview assessment" }));
    await screen.findByText("persisted=false", { selector: "strong" });
    expect(screen.getByText("OVERALL_OWNER_CAPABILITY_READINESS · BLOCKED")).toBeInTheDocument();
    expect(screen.queryByText("OVERALL_OWNER_CAPABILITY_READINESS · READY")).not.toBeInTheDocument();
  });
  it("keeps rejected draft edits visible on ETag conflict without retry", async () => {
    const user = userEvent.setup();
    mocks.updateAssessment.mockRejectedValue(new Error("412 ETAG_MISMATCH"));
    render(<OwnerCapabilityWorkspace token="user" />);
    await screen.findByText(/9 satisfied/);
    await user.click(screen.getByRole("button", { name: "Capability Assessment" }));
    await user.click(screen.getByRole("button", { name: "Add capability item" }));
    await user.type(screen.getByLabelText("Rationale"), "Keep unsaved rationale");
    await user.click(screen.getByRole("button", { name: "Save capability item" }));
    await screen.findByText("412 ETAG_MISMATCH");
    expect(screen.getByLabelText("Rationale")).toHaveValue("Keep unsaved rationale");
    expect(mocks.updateAssessment).toHaveBeenCalledTimes(1);
  });
  it("searches authorized Projects server-side rather than loading all identities", async () => {
    const user = userEvent.setup();
    render(<OwnerCapabilityWorkspace token="user" />);
    await screen.findByText(/9 satisfied/);
    await user.type(screen.getByLabelText("Find authorized Projects"), "Mining");
    await user.click(screen.getByRole("button", { name: "Search Projects" }));
    await waitFor(() => expect(mocks.options).toHaveBeenCalledWith("user", "Mining"));
  });
});
