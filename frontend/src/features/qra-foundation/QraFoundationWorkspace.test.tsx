import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import QraFoundationWorkspace from "./QraFoundationWorkspace";
const mocks = vi.hoisted(() => ({
  options: vi.fn(),
  requirements: vi.fn(),
  contexts: vi.fn(),
  sourceOptions: vi.fn(),
  records: vi.fn(),
  record: vi.fn(),
  recordItems: vi.fn(),
  readiness: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  updateModelMetadata: vi.fn(),
  updateModelInputs: vi.fn(),
  action: vi.fn(),
  refreshPreview: vi.fn(),
}));
vi.mock("./api", () => ({ qraFoundationApi: mocks }));
const draft = {
  id: 2,
  project_id: 41,
  title: "Foundation",
  number: "CSR-000002",
  version: 1,
  status: "DRAFT",
  revision_version: 3,
  hash: null,
  snapshot_json: {},
  aggregate_json: {
    items: [],
    gaps: [],
    source_refs: [],
    basis: {},
    analysis_scope: { type: "ENTIRE_PROJECT", refs: [] },
    quality: "UNVERIFIED",
    confidence: "PRELIMINARY",
  },
  allowed_actions: ["edit", "submit"],
};
const rules = {
  configuration: { id: 8, revision: 1, hash: "methodology-hash" },
  context: { governance_model: "CAPITAL_OWNER", fel_stage: "FEL-3" },
  policy: {
    range_policies: [{ code: "MIN_MOST_LIKELY_MAX" }],
    distribution_families: [{ code: "TRIANGULAR" }],
    correlation_methods: ["NO_CORRELATION"],
    separation_of_duties: { preparer_cannot_approve: true },
  },
  cost_requirements: [{ code: "CONTINGENCY_BASIS", field: "contingency_basis", blocking: true }],
  schedule_requirements: [{ code: "DATA_DATE", field: "data_date", blocking: true }],
  allowed_actions: ["cost_create", "schedule_create", "model_create"],
};
beforeEach(() => {
  vi.clearAllMocks();
  mocks.options.mockResolvedValue({
    projects: [{ id: 41, code: "MIN", name: "Mining fixture" }],
    allowed_actions: ["cost_create", "schedule_create", "model_create"],
    analysis_types: ["COST_QRA", "SCHEDULE_QRA", "INTEGRATED_COST_SCHEDULE_QRA"],
    quality_values: ["UNVERIFIED", "VERIFIED"],
    confidence_values: ["PRELIMINARY", "HIGH"],
  });
  mocks.requirements.mockResolvedValue(rules);
  mocks.contexts.mockResolvedValue({
    risk_readiness: { hash: "risk-hash", status: "READY" },
    owner_capability: { hash: "owner-hash", status: "READY" },
  });
  mocks.sourceOptions.mockResolvedValue({
    items: [{ kind: "SCHEDULE_IMPORT", id: 9, reference: "P6-XML-9", version: 9, hash: "schedule-hash" }],
  });
  mocks.records.mockResolvedValue({ items: [draft], total: 1, page: 1, page_size: 25 });
  mocks.record.mockImplementation(async (_token: string, _kind: string, id: number) => {
    const page = await mocks.records.mock.results.slice(-1)[0].value;
    return page.items.find((item: { id: number }) => item.id === id);
  });
  mocks.recordItems.mockImplementation(async (_token: string, kind: string, id: number, page = 1) => {
    const result = await mocks.records.mock.results.slice(-1)[0].value;
    const item = result.items.find((candidate: { id: number }) => candidate.id === id);
    const all =
      kind === "model"
        ? (item.aggregate_json.inputs ?? [])
        : (item.snapshot_json.population ?? item.aggregate_json.items ?? []);
    return { items: all.slice((page - 1) * 25, page * 25), total: all.length, page, page_size: 25 };
  });
  mocks.readiness.mockResolvedValue({
    readiness_status: "BLOCKED",
    coverage: { required: 10, covered: 9 },
    blockers: ["MISSING_DATA_DATE"],
  });
  mocks.create.mockResolvedValue(draft);
  mocks.update.mockResolvedValue(draft);
  mocks.updateModelMetadata.mockResolvedValue(draft);
  mocks.updateModelInputs.mockResolvedValue(draft);
  mocks.action.mockResolvedValue({ persisted: false, readiness_status: "READY_FOR_QRA_ANALYSIS" });
  mocks.refreshPreview.mockResolvedValue({ persisted: false, changes: ["SOURCE_CHANGED"] });
});
describe("QRA Foundation USER workspace", () => {
  it("loads the initial context under React StrictMode without abandoning the active request", async () => {
    render(
      <StrictMode>
        <QraFoundationWorkspace token="user" />
      </StrictMode>
    );
    await screen.findByText("Cost source readiness · BLOCKED");
    expect(screen.getByRole("button", { name: "Edit cost source assessment" })).toBeEnabled();
  });
  it("loads summary metadata and one server item page, retrieving an aggregate only for editing", async () => {
    const user = userEvent.setup();
    mocks.record.mockImplementation(async (_token: string, _kind: string, _id: number, summary = false) =>
      summary ? { ...draft, aggregate_json: undefined } : draft
    );
    render(<QraFoundationWorkspace token="user" />);
    await screen.findByText("Cost source readiness · BLOCKED");
    expect(mocks.record).toHaveBeenCalledWith("user", "cost", 2, true);
    expect(mocks.recordItems).toHaveBeenCalledWith("user", "cost", 2);
    await user.click(screen.getByRole("button", { name: "Edit cost source assessment" }));
    expect(mocks.record).toHaveBeenLastCalledWith("user", "cost", 2, false);
    expect(screen.getByLabelText("Record title")).toHaveValue("Foundation");
  });
  it("displays a stable model identity independently of successor record numbering", async () => {
    mocks.records.mockResolvedValue({
      items: [{ ...draft, number: "QRM-000009", model_number: "QRM-000001", version: 3 }],
      total: 1,
      page: 1,
      page_size: 25,
    });
    render(<QraFoundationWorkspace token="user" initialView="qra-model-definition" />);
    await screen.findByText("Model definition readiness · BLOCKED");
    expect(screen.getByRole("option", { name: "QRM-000001 · v3 · DRAFT" })).toBeInTheDocument();
    expect(screen.getByText("Model number")).toBeInTheDocument();
  });
  it("displays backend current readiness and exact denominator, no ADMIN or simulation controls", async () => {
    render(<QraFoundationWorkspace token="user" />);
    await screen.findByText("Cost source readiness · BLOCKED");
    expect(screen.getByText(/9 satisfied \/ 10 required/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Publish|Clone|Run simulation|P80/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve for analysis" })).not.toBeInTheDocument();
    expect(mocks.requirements).toHaveBeenCalledTimes(1);
    expect(mocks.sourceOptions).toHaveBeenCalledTimes(2);
    expect(mocks.records).toHaveBeenCalledTimes(1);
  });
  it("does not turn a successful non-persisted preview into governed evidence", async () => {
    const user = userEvent.setup();
    render(<QraFoundationWorkspace token="user" />);
    await screen.findByText("Cost source readiness · BLOCKED");
    await user.click(screen.getByRole("button", { name: "Preview readiness" }));
    await screen.findByText("persisted=false");
    expect(screen.getByText("Cost source readiness · BLOCKED")).toBeInTheDocument();
    expect(mocks.action).toHaveBeenCalledWith("user", "cost", draft, "preview", "");
  });
  it("captures selected canonical source lineage and source basis without calculating anything", async () => {
    const user = userEvent.setup();
    render(<QraFoundationWorkspace token="user" initialView="qra-schedule-source-readiness" />);
    await screen.findByText("Schedule source readiness · BLOCKED");
    await user.click(screen.getByRole("button", { name: "Source Snapshot" }));
    expect(screen.getByText("Draft source snapshot — not completed evidence")).toBeInTheDocument();
    expect(screen.queryByText("Frozen source snapshot — immutable evidence")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Edit schedule source assessment" }));
    await user.selectOptions(screen.getByLabelText("Select governed source"), "0");
    await user.selectOptions(screen.getByLabelText("Source evidence quality"), "VERIFIED");
    await user.selectOptions(screen.getByLabelText("Source confidence"), "HIGH");
    await user.clear(screen.getByLabelText("basis JSON"));
    fireEvent.change(screen.getByLabelText("basis JSON"), {
      target: { value: '{"data_date":"2026-10-09","schedule_type":"CURRENT"}' },
    });
    await user.click(screen.getByRole("button", { name: "Save schedule source assessment" }));
    await waitFor(() =>
      expect(mocks.update).toHaveBeenCalledWith(
        "user",
        "schedule",
        draft,
        expect.objectContaining({
          source_refs: [{ kind: "SCHEDULE_IMPORT", id: 9, reference: "P6-XML-9", version: 9, hash: "schedule-hash" }],
          quality: "VERIFIED",
          confidence: "HIGH",
          basis: { data_date: "2026-10-09", schedule_type: "CURRENT" },
        })
      )
    );
  });
  it("preserves input on stale ETag instead of silently overwriting or retrying", async () => {
    mocks.update.mockRejectedValue(new Error("412 ETAG_MISMATCH"));
    const user = userEvent.setup();
    render(<QraFoundationWorkspace token="user" />);
    await screen.findByText("Cost source readiness · BLOCKED");
    await user.click(screen.getByRole("button", { name: "Edit cost source assessment" }));
    await user.clear(screen.getByLabelText("Record title"));
    await user.type(screen.getByLabelText("Record title"), "Unsaved source title");
    await user.click(screen.getByRole("button", { name: "Save cost source assessment" }));
    await screen.findByText("412 ETAG_MISMATCH");
    expect(screen.getByLabelText("Record title")).toHaveValue("Unsaved source title");
    expect(mocks.update).toHaveBeenCalledTimes(1);
  });
  it("validates JSON syntax/shape only, leaving readiness and policy decisions on server", async () => {
    const user = userEvent.setup();
    render(<QraFoundationWorkspace token="user" />);
    await screen.findByText("Cost source readiness · BLOCKED");
    await user.click(screen.getByRole("button", { name: "Edit cost source assessment" }));
    await user.clear(screen.getByLabelText("items JSON"));
    await user.type(screen.getByLabelText("items JSON"), "invalid");
    await user.click(screen.getByRole("button", { name: "Save cost source assessment" }));
    await screen.findByText(/items must contain valid JSON/);
    expect(mocks.update).not.toHaveBeenCalled();
    expect(screen.getByLabelText("items JSON")).toHaveValue("invalid");
  });
  it("stores model input definitions, deterministic exclusions and correlation rules without a run", async () => {
    const model = {
      ...draft,
      number: "QRM-000002",
      aggregate_json: {
        analysis_type: "COST_QRA",
        purpose: "",
        inputs: [],
        correlations: { method: "NO_CORRELATION", pairs: [], groups: [], matrix: [] },
      },
    };
    mocks.records.mockResolvedValue({ items: [model], total: 1, page: 1, page_size: 25 });
    const user = userEvent.setup();
    render(<QraFoundationWorkspace token="user" initialView="qra-model-definition" />);
    await screen.findByText("Model definition readiness · BLOCKED");
    await user.click(screen.getByRole("button", { name: "Edit model definition" }));
    await user.type(screen.getByLabelText("Model purpose"), "Governed future analysis");
    await user.type(screen.getByLabelText("Cost assessment ID"), "11");
    const inputs = [
      {
        source_kind: "COST",
        source_item_ref: "WBS-01",
        mode: "DETERMINISTIC",
        rationale: "Fixed commitment",
        evidence_refs: [{ reference: "Contract-01" }],
      },
    ];
    await user.click(screen.getByRole("button", { name: "Save model definition" }));
    await waitFor(() =>
      expect(mocks.updateModelMetadata).toHaveBeenCalledWith(
        "user",
        model,
        expect.objectContaining({
          purpose: "Governed future analysis",
          cost_source_assessment_id: 11,
          correlations: { method: "NO_CORRELATION", pairs: [], groups: [], matrix: [] },
        })
      )
    );
    await user.click(screen.getByRole("button", { name: "Edit input page" }));
    fireEvent.change(screen.getByLabelText("Input page JSON"), { target: { value: JSON.stringify(inputs) } });
    await user.click(screen.getByRole("button", { name: "Save input page" }));
    await waitFor(() =>
      expect(mocks.updateModelInputs).toHaveBeenCalledWith("user", expect.objectContaining({ id: model.id }), inputs)
    );
  });
  it("shows approval only when allowed by backend and sends independent review notes", async () => {
    const reviewed = { ...draft, status: "IN_REVIEW", allowed_actions: ["approve"] };
    mocks.records.mockResolvedValue({ items: [reviewed], total: 1, page: 1, page_size: 25 });
    const user = userEvent.setup();
    render(<QraFoundationWorkspace token="approver" initialView="qra-model-definition" />);
    await screen.findByText("Model definition readiness · BLOCKED");
    expect(screen.queryByRole("button", { name: "Edit model definition" })).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Review / approval comments"), "Independent review completed");
    await user.click(screen.getByRole("button", { name: "Approve for analysis" }));
    await waitFor(() =>
      expect(mocks.action).toHaveBeenCalledWith(
        "approver",
        "model",
        reviewed,
        "approve",
        "Independent review completed"
      )
    );
  });
  it("keeps immutable history hashes and uses read-only refresh preview", async () => {
    const completed = {
      ...draft,
      status: "COMPLETED",
      hash: "frozen-history-hash",
      snapshot_json: { data_date: "2026-10-08" },
      allowed_actions: ["refresh_apply"],
    };
    mocks.records.mockResolvedValue({ items: [completed], total: 1, page: 1, page_size: 25 });
    const user = userEvent.setup();
    render(<QraFoundationWorkspace token="user" initialView="qra-foundation-history" />);
    await screen.findByRole("article", { name: "QRA immutable history" });
    expect(screen.queryByRole("button", { name: "Edit cost source assessment" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Refresh Preview" }));
    await screen.findByText("persisted=false");
    expect(mocks.refreshPreview).toHaveBeenCalledWith("user", "cost", 2);
    expect(screen.getByRole("article", { name: "QRA immutable history" })).toHaveTextContent("frozen-history-hash");
    expect(mocks.action).not.toHaveBeenCalled();
  });
  it("keeps full immutable snapshots when changing the selected history record or page", async () => {
    const completed = {
      ...draft,
      status: "COMPLETED",
      hash: "frozen-history-hash",
      snapshot_json: { data_date: "2026-10-08" },
      allowed_actions: [],
    };
    const other = { ...completed, id: 3, number: "CSR-000003", hash: "second-frozen-hash" };
    mocks.records.mockResolvedValue({ items: [completed, other], total: 60, page: 1, page_size: 25 });
    mocks.record.mockImplementation(async (_token: string, _kind: string, id: number, summary = false) => {
      const item = id === 3 ? other : completed;
      return summary ? { ...item, snapshot_json: {}, aggregate_json: {} } : item;
    });
    const user = userEvent.setup();
    render(<QraFoundationWorkspace token="user" initialView="qra-foundation-history" />);
    await screen.findByRole("option", { name: "CSR-000003 · v1 · COMPLETED" });
    await user.selectOptions(screen.getByLabelText("Selected governed record"), "3");
    await waitFor(() => expect(mocks.record).toHaveBeenLastCalledWith("user", "cost", 3, false));
    expect(screen.getByRole("article", { name: "QRA immutable history" })).toHaveTextContent("2026-10-08");
    await user.click(screen.getByRole("button", { name: "Next governed records page" }));
    await waitFor(() => expect(mocks.records).toHaveBeenLastCalledWith("user", 41, "cost", 2));
    expect(mocks.record).toHaveBeenLastCalledWith("user", "cost", 3, false);
    expect(screen.getByRole("article", { name: "QRA immutable history" })).toHaveTextContent("second-frozen-hash");
    expect(screen.getByRole("article", { name: "QRA immutable history" })).toHaveTextContent("2026-10-08");
  });
  it("exposes frozen schedule source, constraints/lags and open-end findings without recalculating logic", async () => {
    const completed = {
      ...draft,
      status: "COMPLETED",
      hash: "frozen-schedule-hash",
      snapshot_json: {
        source_refs: [{ reference: "P6-XML-9", hash: "frozen-import-hash" }],
        schedule_summary: {
          constraints: ["A-CONSTRAINED"],
          negative_lags: ["A-1:A-2"],
          excessive_lags: ["A-2:A-3"],
          open_ends: ["A-OPEN"],
          missing_predecessors: ["A-OPEN"],
          missing_successors: [],
        },
      },
      allowed_actions: [],
    };
    mocks.records.mockResolvedValue({ items: [completed], total: 1, page: 1, page_size: 25 });
    const user = userEvent.setup();
    render(<QraFoundationWorkspace token="user" initialView="qra-schedule-source-readiness" />);
    await screen.findByText("Schedule source readiness · BLOCKED");
    for (const label of ["Source Snapshot", "Logic Quality", "Constraints / Lags", "Open Ends"])
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Source Snapshot" }));
    expect(screen.getByRole("article", { name: "QRA source lineage" })).toHaveTextContent("frozen-import-hash");
    await user.click(screen.getByRole("button", { name: "Constraints / Lags" }));
    expect(screen.getByRole("article", { name: "QRA Constraints / Lags" })).toHaveTextContent("A-CONSTRAINED");
    expect(screen.getByRole("article", { name: "QRA Constraints / Lags" })).toHaveTextContent("A-1:A-2");
    await user.click(screen.getByRole("button", { name: "Open Ends" }));
    expect(screen.getByRole("article", { name: "QRA Open Ends" })).toHaveTextContent("A-OPEN");
    expect(mocks.action).not.toHaveBeenCalled();
    expect(mocks.update).not.toHaveBeenCalled();
  });
  it("clears the previous Project when a new authorized search has no results", async () => {
    const user = userEvent.setup();
    render(<QraFoundationWorkspace token="user" />);
    await screen.findByText("Cost source readiness · BLOCKED");
    mocks.options.mockResolvedValue({ projects: [], allowed_actions: [], analysis_types: [] });
    await user.type(screen.getByLabelText("Find authorized Projects"), "No matching Project");
    await user.click(screen.getByRole("button", { name: "Search Projects" }));
    await screen.findByText("No governed records for this Project and domain.");
    expect(screen.queryByRole("button", { name: "Create cost source assessment" })).not.toBeInTheDocument();
    expect(screen.queryByText("Cost source readiness · BLOCKED")).not.toBeInTheDocument();
    expect(mocks.create).not.toHaveBeenCalled();
  });
  it("requires saving or cancelling an edit before changing Project or domain", async () => {
    const user = userEvent.setup();
    render(<QraFoundationWorkspace token="user" />);
    await screen.findByText("Cost source readiness · BLOCKED");
    await user.click(screen.getByRole("button", { name: "Edit cost source assessment" }));
    expect(screen.getByLabelText("Project Workspace")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Search Projects" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Schedule Source Readiness" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Create cost source assessment" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Cancel edit" }));
    expect(screen.getByLabelText("Project Workspace")).toBeEnabled();
    expect(screen.getByRole("button", { name: "Schedule Source Readiness" })).toBeEnabled();
  });
  it("changes the empty-domain view when a sidebar route supplies a new initialView", async () => {
    mocks.options.mockResolvedValue({ projects: [], allowed_actions: [], analysis_types: [] });
    const { rerender } = render(<QraFoundationWorkspace token="user" />);
    await screen.findByText("Cost source readiness · NOT_STARTED");
    rerender(<QraFoundationWorkspace token="user" initialView="qra-schedule-source-readiness" />);
    await screen.findByText("Schedule source readiness · NOT_STARTED");
    expect(screen.getByRole("navigation", { name: "Schedule Source Readiness sections" })).toBeInTheDocument();
    rerender(<QraFoundationWorkspace token="user" initialView="qra-model-definition" />);
    await screen.findByText("Model definition readiness · NOT_STARTED");
    expect(screen.getByRole("navigation", { name: "Model Definition sections" })).toBeInTheDocument();
  });
  it("defers sidebar route changes until the pending editor is explicitly cancelled", async () => {
    const user = userEvent.setup();
    const { rerender } = render(<QraFoundationWorkspace token="user" />);
    await screen.findByText("Cost source readiness · BLOCKED");
    await user.click(screen.getByRole("button", { name: "Edit cost source assessment" }));
    await user.clear(screen.getByLabelText("Record title"));
    await user.type(screen.getByLabelText("Record title"), "Pending source evidence");
    rerender(<QraFoundationWorkspace token="user" initialView="qra-model-definition" />);
    expect(screen.getByLabelText("Record title")).toHaveValue("Pending source evidence");
    expect(screen.getByRole("article", { name: "QRA definition editor" })).toBeInTheDocument();
    expect(mocks.options).toHaveBeenCalledTimes(1);
    expect(mocks.records).toHaveBeenCalledTimes(1);
    expect(mocks.update).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Cancel edit" }));
    await screen.findByText("Model definition readiness · BLOCKED");
    expect(mocks.records).toHaveBeenLastCalledWith("user", 41, "model", 1);
    expect(screen.queryByRole("article", { name: "QRA definition editor" })).not.toBeInTheDocument();
  });
  it("uses server record pagination and displays only a bounded input page", async () => {
    mocks.records.mockResolvedValue({
      items: [
        {
          ...draft,
          aggregate_json: {
            ...draft.aggregate_json,
            items: Array.from({ length: 1000 }, (_, index) => ({ ref: `ACT-${index}`, mode: "UNCERTAIN" })),
          },
        },
      ],
      total: 60,
      page: 1,
      page_size: 25,
    });
    const user = userEvent.setup();
    render(<QraFoundationWorkspace token="user" />);
    await screen.findByText("Cost source readiness · BLOCKED");
    await user.click(screen.getByRole("button", { name: "Uncertainty Input Readiness" }));
    expect(screen.getAllByRole("row")).toHaveLength(26);
    await user.click(screen.getByRole("button", { name: "Next source inputs page" }));
    await waitFor(() => expect(mocks.recordItems).toHaveBeenLastCalledWith("user", "cost", 2, 2));
    expect(screen.getByRole("cell", { name: "ACT-25" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Next governed records page" }));
    await waitFor(() => expect(mocks.records).toHaveBeenCalledWith("user", 41, "cost", 2));
  });
  it("creates only a DRAFT record and switches source views through bounded server loads", async () => {
    const user = userEvent.setup();
    render(<QraFoundationWorkspace token="user" />);
    await screen.findByText("Cost source readiness · BLOCKED");
    await user.click(screen.getByRole("button", { name: "Create cost source assessment" }));
    await waitFor(() =>
      expect(mocks.create).toHaveBeenCalledWith("user", 41, "cost", { title: "Cost source assessment", comments: "" })
    );
    await user.click(screen.getByRole("button", { name: "Schedule Source Readiness" }));
    await screen.findByText("Schedule source readiness · BLOCKED");
    expect(mocks.records).toHaveBeenLastCalledWith("user", 41, "schedule", 1);
  });
});
