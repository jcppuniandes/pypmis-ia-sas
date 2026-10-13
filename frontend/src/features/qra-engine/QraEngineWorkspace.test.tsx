import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import QraEngineWorkspace from "./QraEngineWorkspace";
import type { QraRun } from "./api";

const mocks = vi.hoisted(() => ({
  projects: vi.fn(),
  options: vi.fn(),
  models: vi.fn(),
  runs: vi.fn(),
  run: vi.fn(),
  status: vi.fn(),
  read: vi.fn(),
  preflight: vi.fn(),
  create: vi.fn(),
  action: vi.fn(),
  compare: vi.fn(),
}));
vi.mock("./api", () => ({ qraEngineApi: mocks }));
vi.mock("../qra-foundation/api", () => ({ qraFoundationApi: { options: mocks.projects } }));
const model = {
  id: 8,
  title: "Current cost model",
  model_number: "QRM-000008",
  version: 1,
  analysis_type: "COST_QRA",
  status: "APPROVED_FOR_ANALYSIS",
};
const completed: QraRun = {
  id: 2,
  project_id: 41,
  run_number: "QRR-000002",
  model_id: 8,
  analysis_type: "COST_QRA",
  status: "COMPLETED",
  review_status: "NOT_SUBMITTED",
  revision_version: 5,
  allowed_actions: ["review"],
  iterations_requested: 1000,
  iterations_completed: 1000,
  seed: 19,
  convergence_status: "CONVERGED",
  analytical_readiness: "READY",
  engine_version: "wave4-qra-v1",
  model_hash: "model-hash",
};
const queued = {
  ...completed,
  id: 3,
  run_number: "QRR-000003",
  status: "QUEUED",
  iterations_completed: 0,
  allowed_actions: ["execute", "cancel"],
};
beforeEach(() => {
  vi.clearAllMocks();
  mocks.projects.mockResolvedValue({
    projects: [{ id: 41, code: "MIN", name: "Canonical Mining Project" }],
    allowed_actions: [],
  });
  mocks.options.mockResolvedValue({
    approved_models: [model],
    allowed_actions: ["create"],
    engine_policy: {
      seed_policy: "USER_SPECIFIED",
      iteration_policy: { minimum: 100, default: 1000, maximum: 10000, allow_override: true },
    },
  });
  mocks.runs.mockResolvedValue({ items: [completed], total: 1, page: 1, page_size: 25 });
  mocks.run.mockImplementation(async (_token, id) => (id === 3 ? queued : completed));
  mocks.status.mockResolvedValue(queued);
  mocks.read.mockImplementation(async (_token, _id, section) =>
    section === "percentiles"
      ? { data: [{ percentile: 80, value: 1020 }] }
      : section === "sensitivity"
        ? { data: [{ input_ref: "COST:A", method: "PEARSON_ONLINE_V1", coefficient: 0.92, rank: 1 }] }
        : section === "convergence"
          ? { data: { status: "CONVERGED", method: "RELATIVE_MEAN_SE_V1" } }
          : section === "evidence"
            ? { run_hash: "immutable-result-hash", model_hash: "model-hash", engine_version: "wave4-qra-v1" }
            : section === "histogram"
              ? { data: [{ count: 5, lower: 900, upper: 950 }] }
              : section === "cdf"
                ? { data: [{ value: 950, probability: 0.2 }] }
                : { data: { mean: 1000 } }
  );
  mocks.preflight.mockResolvedValue({ eligible: true, persisted: false, blockers: [], model_hash: "model-hash" });
  mocks.create.mockResolvedValue(queued);
  mocks.action.mockResolvedValue({ ...completed, review_status: "IN_REVIEW", allowed_actions: [] });
  mocks.compare.mockResolvedValue({
    compatible: true,
    mean_delta: 5,
    percentile_deltas: [{ percentile: 80, delta: 8 }],
  });
});
afterEach(() => {
  vi.useRealTimers();
});
describe("QRA governed execution USER workspace", () => {
  it("loads approved model identities in bounded pages without revalidating every listed model", async () => {
    const configured = await mocks.options();
    mocks.options.mockResolvedValue({ ...configured, approved_model_total: 60 });
    mocks.models.mockResolvedValue({
      items: [{ ...model, id: 18, model_number: "QRM-000018" }],
      total: 60,
      page: 2,
      page_size: 25,
    });
    const user = userEvent.setup();
    render(<QraEngineWorkspace token="user" />);
    await screen.findByText("QRR-000002");
    await user.click(screen.getByRole("button", { name: "Next model page" }));
    await waitFor(() => expect(mocks.models).toHaveBeenCalledWith("user", 41, 2));
    expect(screen.getByLabelText("Approved model")).toHaveValue("18");
    expect(mocks.preflight).not.toHaveBeenCalled();
  });
  it("requests incremental sensitivity result pages instead of the entire driver population", async () => {
    mocks.read.mockImplementation(async (_token, _id, section, _signal, page) =>
      section === "sensitivity"
        ? { data: [{ input_ref: `COST:PAGE-${page}`, coefficient: 0.5 }], total: 1000, page, page_size: 100 }
        : {}
    );
    const user = userEvent.setup();
    render(<QraEngineWorkspace token="user" initialView="qra-sensitivity" />);
    await screen.findByText("COST:PAGE-1");
    await user.click(screen.getByRole("button", { name: "Next result page" }));
    await screen.findByText("COST:PAGE-2");
    expect(mocks.read).toHaveBeenLastCalledWith("user", 2, "sensitivity", expect.any(AbortSignal), 2);
    expect(screen.queryByText("COST:PAGE-1")).not.toBeInTheDocument();
  });
  it("honors fixed/system seeds and forbidden iteration override from published methodology", async () => {
    const configured = await mocks.options();
    mocks.options.mockResolvedValue({
      ...configured,
      engine_policy: {
        seed_policy: "FIXED_FOR_REPRODUCIBILITY",
        fixed_seed: "18446744073709551614",
        iteration_policy: { minimum: 100, default: 1000, maximum: 1000, allow_override: false },
      },
    });
    const user = userEvent.setup();
    render(<QraEngineWorkspace token="user" />);
    await screen.findByText("QRR-000002");
    expect(screen.getByLabelText("PRNG seed")).toBeDisabled();
    expect(screen.getByLabelText("Iterations")).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Create governed run" }));
    await screen.findByText("QRR-000003");
    expect(mocks.create).toHaveBeenCalledWith("user", 8, { iterations: 1000, comments: "" }, expect.any(String));
  });
  it("loads approved models and immutable runs under React StrictMode without ADMIN operations", async () => {
    render(
      <StrictMode>
        <QraEngineWorkspace token="user" />
      </StrictMode>
    );
    await screen.findByText("QRR-000002");
    expect(screen.getByLabelText("Approved model")).toHaveValue("8");
    expect(screen.getByRole("button", { name: "Create governed run" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: /Publish|Clone to DRAFT|Edit methodology/ })).not.toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("not approved Budget");
    expect(mocks.options).toHaveBeenCalledWith("user", 41, expect.any(AbortSignal));
  });
  it("performs backend pre-run validation and creates a distinct run with governed settings", async () => {
    const user = userEvent.setup();
    render(<QraEngineWorkspace token="user" />);
    await screen.findByText("QRR-000002");
    await user.click(screen.getByRole("button", { name: "Validate pre-run" }));
    expect(mocks.preflight).toHaveBeenCalledWith("user", 8);
    await screen.findByRole("article", { name: "QRA pre-run validation" });
    await user.type(screen.getByLabelText("PRNG seed"), "19");
    await user.click(screen.getByRole("button", { name: "Create governed run" }));
    await screen.findByText("QRR-000003");
    expect(mocks.create).toHaveBeenCalledWith(
      "user",
      8,
      { seed: 19, iterations: 1000, comments: "" },
      expect.any(String)
    );
    expect(screen.getByRole("button", { name: "Execute approved run" })).toBeEnabled();
    expect(mocks.action).not.toHaveBeenCalled();
  });
  it("retains the idempotency key for retrying the identical failed creation payload", async () => {
    mocks.create.mockRejectedValueOnce(new Error("temporary connection interruption"));
    const user = userEvent.setup();
    render(<QraEngineWorkspace token="user" />);
    await screen.findByText("QRR-000002");
    await user.type(screen.getByLabelText("PRNG seed"), "19");
    await user.click(screen.getByRole("button", { name: "Create governed run" }));
    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: "Create governed run" }));
    await screen.findByText("QRR-000003");
    expect(mocks.create.mock.calls[0][3]).toBe(mocks.create.mock.calls[1][3]);
  });
  it("shows read models, percentiles, sensitivity and convergence without browser-side simulation", async () => {
    const user = userEvent.setup();
    render(<QraEngineWorkspace token="user" initialView="qra-run-overview" />);
    await screen.findByRole("img", { name: "Simulated outcome histogram" });
    await user.click(screen.getByRole("button", { name: "Percentiles" }));
    await screen.findByRole("table", { name: "Backend-governed percentiles" });
    expect(screen.getByText("1020")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Sensitivity / Drivers" }));
    await screen.findByRole("table", { name: "Backend-governed sensitivity" });
    expect(screen.getByText("COST:A")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Convergence" }));
    await screen.findByText(/RELATIVE_MEAN_SE_V1/);
    expect(mocks.read).toHaveBeenCalledWith("user", 2, "convergence", expect.any(AbortSignal), 1);
  });
  it("hides missing create/execute/review/accept permissions and preserves result reads", async () => {
    mocks.options.mockResolvedValue({ approved_models: [model], allowed_actions: [], engine_policy: {} });
    mocks.run.mockResolvedValue({ ...completed, allowed_actions: [] });
    render(<QraEngineWorkspace token="reader" initialView="qra-run-evidence" />);
    await screen.findByText(/immutable-result-hash/);
    for (const name of [
      "Create governed run",
      "Execute approved run",
      "Cancel run",
      "Submit result for review",
      "Accept analysis evidence",
    ])
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
  });
  it("uses backend allowed_actions and carries the ETag run to result review", async () => {
    const user = userEvent.setup();
    render(<QraEngineWorkspace token="reviewer" />);
    await screen.findByText("QRR-000002");
    await user.type(screen.getByLabelText("Run / review comments"), "Independent analytical evidence review");
    await user.click(screen.getByRole("button", { name: "Submit result for review" }));
    await waitFor(() =>
      expect(mocks.action).toHaveBeenCalledWith(
        "reviewer",
        completed,
        "review",
        "Independent analytical evidence review"
      )
    );
    expect(screen.queryByRole("button", { name: "Accept analysis evidence" })).not.toBeInTheDocument();
  });
  it("does not request final result endpoints for a queued or failed run", async () => {
    mocks.run.mockResolvedValue({
      ...queued,
      status: "FAILED",
      allowed_actions: [],
      failure_reason: "CORRELATION_MATRIX_NOT_PSD",
    });
    render(<QraEngineWorkspace token="user" initialView="qra-percentiles" />);
    await screen.findByText(/Run failed: CORRELATION_MATRIX_NOT_PSD/);
    expect(mocks.read).not.toHaveBeenCalled();
    expect(screen.getByText(/Cancelled or failed runs have no final analytical evidence/)).toBeInTheDocument();
  });
  it("clears old Project data when an authorized search has no results", async () => {
    const user = userEvent.setup();
    render(<QraEngineWorkspace token="user" />);
    await screen.findByText("QRR-000002");
    mocks.projects.mockResolvedValueOnce({ projects: [], allowed_actions: [] });
    await user.click(screen.getByRole("button", { name: "Search Projects" }));
    await screen.findByText("No authorized Project selected.");
    expect(screen.queryByText("QRR-000002")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create governed run" })).not.toBeInTheDocument();
  });
  it("ignores a stale initial context response after the token changes", async () => {
    let resolveOld!: (value: unknown) => void;
    mocks.projects.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveOld = resolve;
        })
    );
    const { rerender } = render(<QraEngineWorkspace token="old" />);
    await waitFor(() => expect(mocks.projects).toHaveBeenCalledWith("old"));
    rerender(<QraEngineWorkspace token="new" />);
    await screen.findByText("QRR-000002");
    await act(async () =>
      resolveOld({ projects: [{ id: 99, code: "OLD", name: "Forbidden stale Project" }], allowed_actions: [] })
    );
    expect(screen.queryByText(/Forbidden stale Project/)).not.toBeInTheDocument();
    expect(mocks.options.mock.calls.every((call) => call[1] !== 99)).toBe(true);
  });
  it("does not display a late creation response from the previous token context", async () => {
    let resolveCreate!: (value: QraRun) => void;
    mocks.create.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveCreate = resolve;
        })
    );
    const user = userEvent.setup();
    const { rerender } = render(<QraEngineWorkspace token="old" />);
    await screen.findByText("QRR-000002");
    await user.type(screen.getByLabelText("PRNG seed"), "19");
    await user.click(screen.getByRole("button", { name: "Create governed run" }));
    await waitFor(() => expect(mocks.create).toHaveBeenCalled());
    rerender(<QraEngineWorkspace token="new" />);
    await screen.findByText("QRR-000002");
    await act(async () => resolveCreate(queued));
    expect(screen.queryByText("QRR-000003")).not.toBeInTheDocument();
  });
  it("aborts progress polling on unmount and never starts overlapping requests", async () => {
    mocks.run.mockResolvedValue(queued);
    let resolveStatus!: (value: QraRun) => void;
    mocks.status.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveStatus = resolve;
        })
    );
    const { unmount } = render(<QraEngineWorkspace token="user" />);
    await screen.findByText("QRR-000003");
    await waitFor(() => expect(mocks.status).toHaveBeenCalledTimes(1));
    vi.useFakeTimers();
    await act(async () => {
      vi.advanceTimersByTime(6000);
    });
    expect(mocks.status).toHaveBeenCalledTimes(1);
    const signal = mocks.status.mock.calls[0][2] as AbortSignal;
    unmount();
    expect(signal.aborted).toBe(true);
    await act(async () => resolveStatus(queued));
    expect(mocks.status).toHaveBeenCalledTimes(1);
  });
  it("finishes the terminal detail read before stopping polling and retains completed comparison choices", async () => {
    const final = { ...completed, id: queued.id, run_number: queued.run_number };
    let resolveFinal!: (value: QraRun) => void;
    mocks.run.mockResolvedValueOnce(queued).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveFinal = resolve;
        })
    );
    mocks.runs.mockResolvedValue({ items: [queued, completed], total: 2, page: 1, page_size: 25 });
    mocks.status.mockResolvedValue(final);
    const user = userEvent.setup();
    render(<QraEngineWorkspace token="user" />);
    await screen.findByText("QRR-000003");
    await waitFor(() => expect(mocks.run).toHaveBeenCalledTimes(2));
    const signal = mocks.run.mock.calls[1][2] as AbortSignal;
    expect(signal.aborted).toBe(false);
    expect(screen.getByLabelText("Selected QRA run")).toHaveDisplayValue(/QUEUED/);
    await act(async () => resolveFinal(final));
    await waitFor(() => expect(screen.getByLabelText("Selected QRA run")).toHaveDisplayValue(/COMPLETED/));
    await user.selectOptions(screen.getByLabelText("Selected QRA run"), String(completed.id));
    await user.click(screen.getByRole("button", { name: "Run Comparison" }));
    await waitFor(() => expect(screen.getByLabelText("Compare against run")).toContainHTML('value="3"'));
    expect(signal.aborted).toBe(true);
  });
  it("keeps integrated execution disabled without falsely presenting supported results", async () => {
    mocks.options.mockResolvedValue({
      approved_models: [{ ...model, analysis_type: "INTEGRATED_COST_SCHEDULE_QRA" }],
      allowed_actions: ["create"],
      engine_policy: {},
    });
    render(<QraEngineWorkspace token="user" />);
    await screen.findByText("QRR-000002");
    expect(screen.getByRole("button", { name: "Create governed run" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Integrated Results" })).not.toBeInTheDocument();
  });
  it("validates numeric settings without sending malformed seed or iterations", async () => {
    const user = userEvent.setup();
    render(<QraEngineWorkspace token="user" />);
    await screen.findByText("QRR-000002");
    fireEvent.change(screen.getByLabelText("PRNG seed"), { target: { value: "1.5" } });
    await user.click(screen.getByRole("button", { name: "Create governed run" }));
    await screen.findByText("Seed must be a non-negative safe integer.");
    expect(mocks.create).not.toHaveBeenCalled();
  });
});
