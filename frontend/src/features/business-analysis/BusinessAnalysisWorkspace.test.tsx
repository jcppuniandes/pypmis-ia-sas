import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import BusinessAnalysisAdminView from "./BusinessAnalysisAdminView";
import BusinessAnalysisWorkspace from "./BusinessAnalysisWorkspace";

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  listPage: vi.fn(),
  options: vi.fn(),
  readiness: vi.fn(),
  history: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  action: vi.fn(),
  newRevision: vi.fn(),
}));

vi.mock("./api", () => ({ businessAnalysisApi: mocks }));

const content = {
  analysis_type: "NEED",
  statement: "Improve governed asset performance",
  background: "",
  business_context: "",
  urgency_timing: "",
  consequences_no_action: "",
  business_drivers: [{ code: "RELIABILITY", label: "Reliability" }],
  strategic_alignment: [{ objective_code: "growth", contribution: "Reliability" }],
  stakeholders: [{ name: "Operations" }],
  current_state: { summary: "Fragmented controls" },
  desired_outcomes: { business_outcomes: "Trusted asset performance" },
  expected_value: [{ dimension: "OPERATIONAL" }],
  assumptions: [{ statement: "Data available" }],
  constraints: [{ statement: "Service continuity" }],
  business_requirements: [{ statement: "Traceability" }],
  options: [
    {
      id: "target",
      name: "Target capability",
      option_type: "NEW_CAPABILITY",
      description: "Implement the target capability",
      scope_concept: "Governed rollout",
      expected_benefits: "Improved reliability",
      rough_cost_range: null,
      rough_timeline: null,
      major_risks: [],
      major_dependencies: [],
      feasibility_notes: "Feasible",
      strategic_fit: "Strong",
      evaluation: [{ criterion_code: "VALUE", rating: 4 }],
    },
  ],
  recommended_option_id: "target",
  recommendation_rationale: "Best governed value",
  key_trade_offs: [],
  conditions: [],
  unresolved_concerns: [],
};

const record = {
  id: 71,
  analysis_number: "BA-00071",
  source_idea_id: 17,
  source_idea_number: "IDEA-00017",
  source_idea_title: "Modernize asset operations",
  source_idea_evaluation_id: 5,
  owning_workspace_id: 1,
  owning_workspace_name: "Enterprise",
  supersedes_analysis_id: null,
  status: "COMPLETED",
  title: "Business Analysis for Modernize asset operations",
  content,
  recommended_option_id: "target",
  readiness: {},
  source_idea_hash: "source-hash",
  configuration_id: 9,
  configuration_revision: 2,
  configuration_hash: "configuration-hash",
  review: { reviewer_user_id: 2 },
  completion_hash: "completion-hash",
  revision_version: 5,
  created_by_user_id: 1,
  reviewer_user_id: 2,
  allowed_actions: ["create_project_proposal", "new_revision"],
  created_at: "2026-09-10T10:00:00Z",
  updated_at: "2026-09-10T10:10:00Z",
  submitted_at: "2026-09-10T10:05:00Z",
  review_started_at: "2026-09-10T10:06:00Z",
  completed_at: "2026-09-10T10:10:00Z",
};

describe("Business Analysis mode boundaries", () => {
  beforeEach(() => {
    mocks.list.mockResolvedValue([record]);
    mocks.listPage.mockResolvedValue({ items: [record], nextCursor: null });
    mocks.options.mockResolvedValue({
      number_preview: "BA-00072",
      eligible_ideas: [],
      analysis_types: [{ code: "NEED", label: "Need" }],
      business_drivers: [{ code: "RELIABILITY", label: "Reliability" }],
      strategic_objectives: [{ code: "growth", label: "Growth" }],
      option_types: [{ code: "NEW_CAPABILITY", label: "New capability" }],
      evaluation_criteria: [{ code: "VALUE", label: "Value", weight: 100 }],
      stakeholder_categories: [{ code: "OWNER", label: "Owner" }],
      value_dimensions: [{ code: "OPERATIONAL", label: "Operational" }],
    });
    mocks.readiness.mockResolvedValue({
      business_analysis_id: 71,
      status: "READY",
      ready: true,
      output: "READY_FOR_PROJECT_PROPOSAL",
      blockers: [],
      warnings: [],
      source_idea_hash: "source-hash",
      current_source_idea_hash: "source-hash",
      configuration_hash: "configuration-hash",
      readiness_hash: "readiness-hash",
    });
    mocks.history.mockResolvedValue([
      { event_type: "business_analysis.completed", occurred_at: "2026-09-10T10:10:00Z" },
    ]);
  });

  it("renders the USER workspace, governed sections and Proposal readiness link", async () => {
    render(<BusinessAnalysisWorkspace token="token" />);

    expect(await screen.findByRole("heading", { name: "Business Analysis & Options" })).toBeInTheDocument();
    expect(await screen.findByText("BA-00071")).toBeInTheDocument();
    expect(screen.getAllByText("Target capability")).toHaveLength(2);
    expect(await screen.findByText("READY_FOR_PROJECT_PROPOSAL")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open Project Proposal/ })).toHaveAttribute(
      "href",
      "/app/strategy/project-proposal"
    );
    expect(screen.queryByText("Edit policy")).not.toBeInTheDocument();
  });

  it("loads the next bounded cursor page without duplicating the register", async () => {
    const secondRecord = {
      ...record,
      id: 72,
      analysis_number: "BA-00072",
      source_idea_title: "Expand governed operations",
    };
    mocks.listPage
      .mockResolvedValueOnce({ items: [record], nextCursor: "next-page" })
      .mockResolvedValueOnce({ items: [secondRecord], nextCursor: null });

    render(<BusinessAnalysisWorkspace token="token" />);

    fireEvent.click(await screen.findByRole("button", { name: "Load more analyses" }));
    expect(await screen.findByText(/BA-00072/)).toBeInTheDocument();
    expect(mocks.listPage).toHaveBeenLastCalledWith("token", expect.stringContaining("cursor=next-page"));
    expect(screen.queryByRole("button", { name: "Load more analyses" })).not.toBeInTheDocument();
  });

  it("renders ADMIN configuration without live Business Analysis controls", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input);
        const body = path.includes("/preview")
          ? { persisted: false, validation: { valid: true }, source: { revision: 1 } }
          : [
              {
                id: 9,
                kind: "business_analysis_configuration",
                name: "Default Business Analysis and Options",
                description: "Governed policy",
                status: "published",
                revision: 1,
                version: 1,
                content_json: {},
              },
            ];
        return { ok: true, status: 200, json: async () => body } as Response;
      })
    );

    render(<BusinessAnalysisAdminView token="token" />);

    expect(await screen.findByRole("heading", { name: "Business Analysis Configuration" })).toBeInTheDocument();
    expect(screen.getByText(/This ADMIN surface never creates, submits, reviews or completes/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preview persisted=false" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Submit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Complete" })).not.toBeInTheDocument();
  });

  it("edits governed BA policy with structured controls and keeps raw JSON read only", async () => {
    let savedContent: Record<string, unknown> | null = null;
    const draft = {
      id: 10,
      kind: "business_analysis_configuration",
      name: "Business Analysis Policy r2",
      description: "Controlled draft",
      status: "draft",
      revision: 2,
      version: 1,
      content_json: {
        evaluation_matrix: {
          scale: { min: 1, max: 5, allowed_values: [1, 2, 3, 4, 5] },
          criteria: [{ code: "VALUE", label: "Expected value", weight: 100 }],
        },
        required_fields: ["statement"],
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
        if (init?.method === "PUT") {
          savedContent = (JSON.parse(String(init.body)) as { content_json: Record<string, unknown> }).content_json;
          return { ok: true, status: 200, json: async () => ({ ...draft, content_json: savedContent }) } as Response;
        }
        return { ok: true, status: 200, json: async () => [draft] } as Response;
      })
    );

    render(<BusinessAnalysisAdminView token="token" />);

    fireEvent.click(await screen.findByRole("button", { name: "Edit policy" }));
    fireEvent.click(screen.getByRole("button", { name: /^Evaluation Matrix$/ }));
    fireEvent.change(screen.getByLabelText("Weight VALUE"), { target: { value: "80" } });
    fireEvent.click(screen.getByRole("button", { name: /^Required Fields$/ }));
    fireEvent.change(screen.getByLabelText("Required Fields"), { target: { value: "statement\noptions" } });

    expect(screen.queryByLabelText("Governed configuration JSON")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Advanced configuration JSON read only").tagName).toBe("PRE");
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));

    await waitFor(() => expect(savedContent).not.toBeNull());
    const persistedContent = savedContent as unknown as Record<string, unknown>;
    const evaluationMatrix = persistedContent.evaluation_matrix as { criteria: Array<{ weight: number }> };
    expect(evaluationMatrix.criteria[0].weight).toBe(80);
    expect(persistedContent.required_fields).toEqual(["statement", "options"]);
  });
});
