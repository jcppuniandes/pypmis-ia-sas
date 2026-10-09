import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import IdeaLifecycleWorkspace from "./IdeaLifecycleWorkspace";

const options = {
  number_preview: "IDEA-00001",
  owning_workspaces: [{ id: 10, name: "Enterprise", workspace_type_code: "enterprise", code: "ENT" }],
  target_portfolios: [],
  strategic_objectives: [{ code: "growth", label: "Growth" }],
  users: [{ id: 1, name: "Admin", email: "admin@demo.local" }],
  idea_types: [{ code: "innovation", label: "Innovation" }],
  categories: [{ code: "growth", label: "Growth" }],
  screening_checklist: [{ code: "complete", label: "Complete", blocking: true }],
  objective_selection: "multiple",
  configuration_source: {},
};

const idea = {
  id: 1,
  idea_number: "IDEA-00001",
  title: "Digital field controls",
  description: "Improve controlled field capture.",
  idea_type: "innovation",
  category: "growth",
  expected_benefit: "Faster trusted reporting",
  estimated_value: "1000.00",
  currency_code: "COP",
  owning_workspace_id: 10,
  owning_workspace_name: "Enterprise",
  target_portfolio_workspace_id: null,
  strategic_objective_codes: ["growth"],
  requestor_user_id: 1,
  requestor_name: "Admin",
  owner_user_id: null,
  owner_name: null,
  state: "DRAFT",
  screening: {},
  routing: {},
  attachment_refs: [],
  accepted_evaluation_id: null,
  decision_reason: null,
  readiness: {},
  evaluations: [],
  allowed_actions: ["edit", "submit", "cancel"],
  revision_version: 1,
  created_at: "2026-08-13T10:00:00Z",
  updated_at: "2026-08-13T10:00:00Z",
};

describe("IdeaLifecycleWorkspace", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input);
        return {
          ok: true,
          status: 200,
          json: async () => (path.includes("/options") ? options : [idea]),
        } as Response;
      })
    );
  });

  it("renders the unified lifecycle queues and idea detail", async () => {
    render(<IdeaLifecycleWorkspace token="token" />);
    expect(await screen.findByRole("heading", { name: "Idea Lifecycle" })).toBeInTheDocument();
    expect(await screen.findByText("IDEA-00001 · Digital field controls")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "To Screen" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Submit/ })).toBeInTheDocument();
  });

  it("opens the controlled new Idea drawer", async () => {
    render(<IdeaLifecycleWorkspace token="token" />);
    await screen.findByText("IDEA-00001 · Digital field controls");
    fireEvent.click(screen.getByRole("button", { name: /New Idea/ }));
    await waitFor(() => expect(screen.getByRole("form", { name: "New Idea form" })).toBeInTheDocument());
    expect(screen.getByDisplayValue("IDEA-00001")).toBeDisabled();
    expect(screen.getByText("Strategic objectives (multiple)")).toBeInTheDocument();
  });
});
