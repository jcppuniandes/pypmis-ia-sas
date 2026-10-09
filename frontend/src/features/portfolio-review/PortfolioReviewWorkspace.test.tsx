import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PortfolioReviewAdminView from "./PortfolioReviewAdminView";
import PortfolioReviewWorkspace from "./PortfolioReviewWorkspace";
import type {
  PortfolioReviewAction,
  PortfolioReviewAllocationContext,
  PortfolioReviewSession,
  PortfolioReviewSnapshot,
} from "./types";

const mocks = vi.hoisted(() => ({
  options: vi.fn(),
  listSessions: vi.fn(),
  createSession: vi.fn(),
  readSession: vi.fn(),
  updateSession: vi.fn(),
  prepare: vi.fn(),
  transition: vi.fn(),
  snapshotPreview: vi.fn(),
  freezeSnapshot: vi.fn(),
  startReview: vi.fn(),
  complete: vi.fn(),
  projectMatrix: vi.fn(),
  allocation: vi.fn(),
  budgetResources: vi.fn(),
  gateStatus: vi.fn(),
  history: vi.fn(),
  compare: vi.fn(),
  trends: vi.fn(),
  listActions: vi.fn(),
  createConclusion: vi.fn(),
  createAction: vi.fn(),
  updateAction: vi.fn(),
  approveAction: vi.fn(),
  dispatchAction: vi.fn(),
  configurations: vi.fn(),
  previewConfiguration: vi.fn(),
  cloneConfiguration: vi.fn(),
  updateConfiguration: vi.fn(),
  publishConfiguration: vi.fn(),
  archiveConfiguration: vi.fn(),
}));

vi.mock("./api", () => ({ portfolioReviewApi: mocks }));

const session: PortfolioReviewSession = {
  id: 41,
  review_session_id: 41,
  review_number: "PRV-000041",
  portfolio_id: 71,
  portfolio_workspace_id: 71,
  portfolio_name: "Capital Portfolio",
  planning_cycle_id: 7,
  allocation_plan_id: 51,
  allocation_plan_number: "SCA-000051",
  review_type: "QUARTERLY",
  review_date: "2026-10-05",
  planned_review_date: "2026-10-05",
  actual_review_date: null,
  review_period_start: "2026-07-01",
  review_period_end: "2026-09-30",
  next_planned_review_date: "2027-01-05",
  status: "PREPARING",
  chair: "Portfolio Director",
  agenda: [
    { code: "STRATEGIC_ALIGNMENT", label: "Strategic Alignment", status: "READY", required: true },
    { code: "CAPITAL_ALLOCATION", label: "Capital Allocation Balance", status: "ATTENTION", required: true },
  ],
  conclusions: [],
  configuration_revision: 3,
  configuration_hash: "c".repeat(64),
  snapshot_id: 91,
  snapshot_hash: "s".repeat(64),
  snapshot: {
    id: 91,
    snapshot_hash: "s".repeat(64),
    source_current: true,
    persisted: true,
    sources: [
      {
        source_type: "STRATEGIC_CAPITAL_ALLOCATION",
        source_id: 51,
        source_version: 4,
        source_hash: "a".repeat(64),
        source_current: true,
        as_of: "2026-10-05T09:00:00Z",
      },
    ],
    warnings: [],
    blockers: [],
  },
  readiness: {
    overall: "ATTENTION",
    ready: false,
    dimensions: {
      SNAPSHOT_READINESS: "READY",
      ALLOCATION_CONTEXT_READINESS: "READY",
      GATE_CONTEXT_READINESS: "ATTENTION",
    },
    blockers: [],
    warnings: ["ONE_GATE_PACKAGE_STALE"],
  },
  summary: {
    portfolio_size: 3,
    blocked_project_count: 1,
    open_action_count: 0,
    overdue_action_count: 0,
    fid_count: 1,
  },
  actions: [],
  source_current: true,
  revision_version: 4,
  allowed_actions: [
    "prepare",
    "snapshot_preview",
    "freeze_snapshot",
    "start_review",
    "complete",
    "create_action",
    "record_conclusion",
  ],
};

const allocation: PortfolioReviewAllocationContext = {
  allocation_plan_id: 51,
  allocation_plan_number: "SCA-000051",
  allocation_plan_version: 4,
  allocation_plan_hash: "a".repeat(64),
  source_current: true,
  multi_currency: true,
  normalization_warning: "COP and USD remain grouped; no silent FX normalization.",
  buckets: [
    {
      bucket_code: "growth",
      bucket_name: "Growth Capital",
      target: { percentage: 40, amounts_by_currency: {}, count: 1 },
      current_demand: { percentage: null, amounts_by_currency: { COP: 800000000 }, count: 2 },
      current_portfolio: { percentage: null, amounts_by_currency: { COP: 700000000 }, count: 2 },
      recommended: { percentage: null, amounts_by_currency: { COP: 650000000 }, count: 1 },
      approved: { percentage: null, amounts_by_currency: { COP: 600000000 }, count: 1 },
      variance_percentage: -5,
      variance_amount: null,
      status: "UNDER_TARGET",
    },
  ],
  unclassified: { percentage: null, amounts_by_currency: { USD: 250000 }, count: 1, evaluable: false },
  warnings: ["MULTI_CURRENCY_NOT_EVALUABLE"],
};

const snapshotPreview: PortfolioReviewSnapshot = {
  snapshot_hash: "p".repeat(64),
  source_current: true,
  persisted: false,
  sources: session.snapshot?.sources ?? [],
  warnings: ["GATE_STATUS_CHANGED"],
  blockers: [],
  changes: [
    {
      source_type: "GATE07K",
      change_type: "STATUS_CHANGED",
      label: "Investment Decision status",
      before: "NO_DECISION",
      after: "GO",
      material: true,
    },
  ],
};

const action: PortfolioReviewAction = {
  id: 501,
  action_id: 501,
  review_session_id: 41,
  subject_type: "PROJECT",
  subject_id: 1001,
  subject_name: "Terminal Expansion",
  action_type: "HOLD_FOR_CAPACITY",
  rationale: "Wait for constrained engineering capacity.",
  priority: "HIGH",
  owner: "Portfolio PMO",
  due_date: "2026-10-31",
  status: "OPEN",
  requested_source_authority: "RESOURCE_PLANNING",
  revision_version: 1,
  allowed_actions: ["approve", "dispatch"],
};

describe("PortfolioReviewWorkspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.options.mockResolvedValue({
      review_types: [{ code: "QUARTERLY" }],
      conclusion_types: [{ code: "PORTFOLIO_BALANCED" }],
      action_types: ["HOLD_FOR_CAPACITY", "REQUEST_REASSESSMENT", "REBALANCE_CAPITAL"].map((code) => ({ code })),
      portfolios: [],
      users: [],
      allocation_plans: [],
      effective_configuration: {},
    });
    mocks.listSessions.mockResolvedValue({ items: [session], page: 1, pageSize: 100, total: 1, nextCursor: null });
    mocks.readSession.mockResolvedValue(session);
    mocks.allocation.mockResolvedValue(allocation);
    mocks.projectMatrix.mockResolvedValue({
      items: [
        {
          project_id: 1001,
          project_number: "PRJ-1001",
          project_name: "Terminal Expansion",
          portfolio_rank: 2,
          strategic_bucket: "growth",
          budget_status: "SELECTED",
          resource_status: "CONSTRAINED",
          gate_stage: "GATE07J",
          gate_readiness: "STALE",
          investment_decision: "NO_DECISION",
          fid_status: "NOT_FID",
          risk_readiness: "READY",
          recommended_status: "RECOMMENDED",
          approved_amounts_by_currency: { COP: 600000000 },
          review_action: null,
          action_owner: null,
          action_due_date: null,
        },
      ],
      page: 1,
      pageSize: 100,
      total: 1,
      nextCursor: null,
      source_current: true,
    });
    mocks.budgetResources.mockResolvedValue({
      budget: { scenario: "FROZEN", feasibility: "FEASIBLE" },
      resources: { scenario: "SELECTED", feasibility: "CONSTRAINED" },
      compatibility: { compatible: true },
      source_current: true,
      warnings: [],
      blockers: [],
    });
    mocks.gateStatus.mockResolvedValue({
      summary: { READY: 1, STALE: 1, FID: 1 },
      projects: [
        {
          project_id: 1001,
          project_name: "Terminal Expansion",
          gate07j_status: "STALE",
          gate07k_decision: "NO_DECISION",
          fid_status: "NOT_FID",
        },
      ],
      source_current: true,
      warnings: [],
      blockers: [],
    });
    mocks.history.mockResolvedValue([]);
    mocks.trends.mockResolvedValue({ items: [], warnings: [] });
    mocks.listActions.mockResolvedValue([]);
    mocks.snapshotPreview.mockResolvedValue(snapshotPreview);
    mocks.freezeSnapshot.mockResolvedValue({
      ...session,
      status: "READY_FOR_REVIEW",
      snapshot_hash: snapshotPreview.snapshot_hash,
      revision_version: 5,
      allowed_actions: ["start_review"],
    });
    mocks.createAction.mockResolvedValue(action);
    mocks.updateAction.mockResolvedValue(action);
    mocks.approveAction.mockResolvedValue({ ...action, revision_version: 2, allowed_actions: ["dispatch"] });
    mocks.dispatchAction.mockResolvedValue({ ...action, revision_version: 2, execution_reference: "REQ-9001" });
  });

  it("renders backend-owned Portfolio evidence and preserves the Project Gate authority boundary", async () => {
    const user = userEvent.setup();
    render(<PortfolioReviewWorkspace initialView="portfolio-review-overview" token="token" />);

    expect(await screen.findByRole("heading", { name: "PRV-000041" })).toBeVisible();
    expect(screen.getByText(`Capital Portfolio · review ${new Date(2026, 9, 5).toLocaleDateString()}`)).toBeVisible();
    expect(screen.getByRole("note")).toHaveTextContent("Gate07K HOLD ≠ HOLD_FOR_CAPACITY");
    expect(screen.getByText(/does not rank Projects or approve Budget/i)).toBeVisible();
    expect(screen.queryByText(/Clone to DRAFT/i)).not.toBeInTheDocument();
    expect(screen.getByRole("option", { name: /^STALE$/ })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Strategic Allocation" }));
    expect(await screen.findByRole("table", { name: "Strategic Allocation positions" })).toHaveTextContent(
      "Growth Capital"
    );
    expect(screen.getByText("COP and USD remain grouped; no silent FX normalization.")).toBeVisible();
    expect(screen.getByRole("row", { name: /UNCLASSIFIED/ })).toHaveTextContent(/USD 250[.,]000/);

    await user.click(screen.getByRole("button", { name: "Project Matrix" }));
    expect(await screen.findByRole("table", { name: "Portfolio Review Project Matrix rows" })).toHaveTextContent(
      "Terminal Expansion"
    );
    expect(screen.getByText(/never creates a review rank/i)).toBeVisible();
  });

  it("previews changes with persisted=false and freezes only through the governed lifecycle API", async () => {
    const user = userEvent.setup();
    render(<PortfolioReviewWorkspace token="token" />);
    expect(await screen.findByRole("heading", { name: "PRV-000041" })).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Refresh Snapshot Preview" }));
    await waitFor(() => expect(mocks.snapshotPreview).toHaveBeenCalledWith("token", session));
    expect(await screen.findByText("Snapshot Preview · persisted=false")).toBeVisible();
    expect(screen.getByText("Investment Decision status")).toBeVisible();
    expect(screen.getByText(/NO_DECISION.*GO/)).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Freeze Snapshot" }));
    await waitFor(() => expect(mocks.freezeSnapshot).toHaveBeenCalledWith("token", session));
    expect(await screen.findByText(/lifecycle action freeze completed/i)).toBeVisible();
  });

  it.each(["HOLD_FOR_CAPACITY", "REQUEST_REASSESSMENT", "REBALANCE_CAPITAL"])(
    "records %s as a request without exposing a source-domain mutation control",
    async (actionType) => {
      const user = userEvent.setup();
      mocks.createAction.mockResolvedValue({ ...action, action_type: actionType });
      render(<PortfolioReviewWorkspace initialView="portfolio-review-actions" token="token" />);
      expect(await screen.findByRole("heading", { name: "PRV-000041" })).toBeVisible();

      const surface = screen.getByRole("region", { name: "Portfolio Review Actions" });
      await user.selectOptions(within(surface).getByLabelText("Action type"), actionType);
      await user.type(within(surface).getByLabelText("Owner user ID"), "17");
      await user.type(within(surface).getByLabelText("Rationale"), "Governance follow-up required.");
      await user.click(within(surface).getByRole("button", { name: "Create governance request" }));

      await waitFor(() =>
        expect(mocks.createAction).toHaveBeenCalledWith(
          "token",
          session,
          expect.objectContaining({
            action_type: actionType,
            owner_user_id: 17,
            rationale: "Governance follow-up required.",
          })
        )
      );
      expect(await screen.findByText(/no source-authority record was silently mutated/i)).toBeVisible();
      expect(
        within(surface).queryByRole("button", { name: /issue hold|recalculate rank|edit budget scenario/i })
      ).not.toBeInTheDocument();
    }
  );

  it("retains frozen actions at close while an authorized owner continues the live follow-up queue", async () => {
    const user = userEvent.setup();
    mocks.listSessions.mockResolvedValue({ items: [{ ...session, status: "COMPLETED" }], total: 1 });
    mocks.readSession.mockResolvedValue({
      ...session,
      status: "COMPLETED",
      summary: { ...session.summary, open_action_count: 1 },
      actions: [{ ...action, due_date: "2020-01-01" }],
      allowed_actions: [],
    });
    mocks.listActions.mockResolvedValue([{ ...action, status: "IN_PROGRESS", allowed_actions: ["update"] }]);
    mocks.updateAction.mockResolvedValue({ ...action, status: "COMPLETED", allowed_actions: [] });
    render(<PortfolioReviewWorkspace initialView="portfolio-review-actions" token="token" />);
    expect(await screen.findByRole("heading", { name: "PRV-000041" })).toBeVisible();
    const metrics = screen.getByLabelText("Métricas de Periodic Portfolio Review");
    expect(within(metrics).getByText("Overdue", { exact: true }).parentElement).toHaveTextContent("0");
    const surface = screen.getByRole("region", { name: "Portfolio Review Actions" });
    expect(within(surface).getByRole("button", { name: "Create governance request" })).toBeDisabled();
    const status = await within(surface).findByLabelText("HOLD_FOR_CAPACITY action status");
    expect(status).toBeEnabled();
    await user.selectOptions(status, "COMPLETED");
    await waitFor(() =>
      expect(mocks.updateAction).toHaveBeenCalledWith("token", expect.objectContaining({ status: "IN_PROGRESS" }), {
        status: "COMPLETED",
      })
    );
    await user.click(screen.getByRole("button", { name: "Overview" }));
    const overview = screen.getByRole("region", { name: "Portfolio Review overview" });
    expect(within(overview).getByText("Open actions").parentElement).toHaveTextContent("1");
  });

  it("uses the server matrix filters and stable pagination without querying individual Projects", async () => {
    const user = userEvent.setup();
    mocks.projectMatrix.mockResolvedValue({ items: [], total: 201, page: 1, pageSize: 100 });
    render(<PortfolioReviewWorkspace initialView="portfolio-review-project-matrix" token="token" />);
    expect(await screen.findByRole("heading", { name: "PRV-000041" })).toBeVisible();
    const surface = screen.getByRole("region", { name: "Portfolio Review Project Matrix" });
    await user.type(within(surface).getByLabelText("Minimum rank"), "2");
    await user.type(within(surface).getByLabelText("FID status"), "FID_GRANTED");
    await user.click(within(surface).getByRole("button", { name: "Apply server filters" }));
    await waitFor(() =>
      expect(mocks.projectMatrix).toHaveBeenLastCalledWith(
        "token",
        41,
        expect.objectContaining({ rank_min: 2, fid_status: "FID_GRANTED", page: 1 })
      )
    );
    await user.click(within(surface).getByRole("button", { name: "Next page" }));
    await waitFor(() =>
      expect(mocks.projectMatrix).toHaveBeenLastCalledWith(
        "token",
        41,
        expect.objectContaining({ rank_min: 2, fid_status: "FID_GRANTED", page: 2 })
      )
    );
  });

  it("requires governed rationale for a controlled Review transition", async () => {
    const user = userEvent.setup();
    const governed = { ...session, allowed_actions: ["return", "cancel", "supersede"] };
    mocks.readSession.mockResolvedValue(governed);
    mocks.transition.mockResolvedValue({ ...governed, status: "RETURNED", revision_version: 5, allowed_actions: [] });
    render(<PortfolioReviewWorkspace token="token" />);
    const button = await screen.findByRole("button", { name: "Return for preparation" });
    expect(button).toBeDisabled();
    await user.type(screen.getByLabelText("Lifecycle reason"), "Return to prepare updated evidence.");
    await user.click(button);
    await waitFor(() =>
      expect(mocks.transition).toHaveBeenCalledWith("token", governed, "return", {
        reason: "Return to prepare updated evidence.",
        replacement_review_session_id: null,
      })
    );
    expect(await screen.findByText("Review return recorded with governed rationale.")).toBeVisible();
  });
});

describe("PortfolioReviewAdminView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.configurations.mockResolvedValue([
      {
        id: 801,
        code: "PORTFOLIO_REVIEW_DEFAULT",
        name: "Capital Owner Quarterly Review",
        description: "Governed recurring review policy.",
        status: "published",
        revision: 3,
        version: 5,
        content_json: {
          review_types: ["QUARTERLY", "AD_HOC"],
          cadence: { QUARTERLY: 90 },
          review_sod: { preparer_must_differ_from_authority: true },
        },
      },
    ]);
    mocks.previewConfiguration.mockResolvedValue({ persisted: false, readiness: { overall: "READY" } });
  });

  it("contains configuration only, supports persisted=false preview and exposes no live Session controls", async () => {
    const user = userEvent.setup();
    render(<PortfolioReviewAdminView token="token" />);
    const surface = screen.getByRole("region", { name: "Periodic Portfolio Review configuration" });
    expect(await within(surface).findByText("Capital Owner Quarterly Review")).toBeVisible();
    expect(within(surface).getByText("Review Types", { exact: true })).toBeVisible();
    expect(within(surface).getByText("Cadence", { exact: true })).toBeVisible();
    expect(within(surface).getByText("Review / SoD", { exact: true })).toBeVisible();
    await user.click(within(surface).getByRole("button", { name: "Preview effective configuration" }));
    await waitFor(() => expect(mocks.previewConfiguration).toHaveBeenCalled());
    expect(await within(surface).findByText("persisted=false")).toBeVisible();
    expect(
      within(surface).queryByRole("button", { name: /New Review Session|Freeze Snapshot|Complete Review/i })
    ).not.toBeInTheDocument();
  });

  it("stages SoD edits under the actual backend policy key without adding inert UI sections", async () => {
    const user = userEvent.setup();
    const configuration = {
      id: 802,
      name: "Scoped draft",
      description: "Governed policy",
      status: "draft",
      revision: 4,
      version: 1,
      content_json: {
        scope: { type: "tenant", workspace_id: null },
        separation_of_duties: { preparer_cannot_complete: true, action_creator_cannot_approve: true },
      },
    };
    mocks.configurations.mockResolvedValue([configuration]);
    mocks.updateConfiguration.mockResolvedValue({ ...configuration, version: 2 });
    render(<PortfolioReviewAdminView token="token" />);
    await user.click(await screen.findByRole("button", { name: "Edit governed sections" }));
    const editor = screen.getByRole("region", { name: "Edit Portfolio Review configuration" });
    await user.click(within(editor).getByRole("button", { name: "Review / SoD" }));
    expect(
      (within(editor).getByLabelText("Portfolio Review configuration JSON") as HTMLTextAreaElement).value
    ).toContain("preparer_cannot_complete");
    await user.clear(within(editor).getByLabelText("Portfolio Review configuration JSON"));
    await user.paste('{"preparer_cannot_complete":false,"action_creator_cannot_approve":true}');
    await user.click(within(editor).getByRole("button", { name: "Save DRAFT revision" }));
    await waitFor(() =>
      expect(mocks.updateConfiguration).toHaveBeenCalledWith("token", configuration, {
        scope: { type: "tenant", workspace_id: null },
        separation_of_duties: { preparer_cannot_complete: false, action_creator_cannot_approve: true },
      })
    );
  });
});
