import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import WorkspaceOperationalPage from "./WorkspaceOperationalPage";

describe("WorkspaceOperationalPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders the backend-derived Header, Breadcrumb, Navigator and planned state", async () => {
    const identity = {
      tenant_id: 1,
      workspace_id: 7,
      workspace_type: "FACILITY",
      workspace_name: "Main Facility",
      workspace_status: "ACTIVE",
      business_number: "FAC-0001",
      record_code: "01.04.01",
      external_key: "facility-main",
    };
    const context = {
      active_context: {
        ...identity,
        parent_workspace_id: 1,
        parent_path: [1],
        template_code: "FACILITY-GENERAL",
        template_revision: 1,
        responsible_user_id: 2,
        enabled_modules: [],
        planned_modules: ["asset-manager"],
        workspace_permissions: ["workspace.open"],
        opened_at: null,
        last_route: "/workspaces/7/home",
      },
      identity,
      parent: null,
      breadcrumb: [
        {
          workspace_id: 1,
          workspace_type: "ENTERPRISE",
          workspace_name: "Enterprise",
          business_number: "ENT",
          record_code: "01",
          status: "ACTIVE",
          navigable: false,
        },
        { ...identity, status: "ACTIVE", navigable: true },
      ],
      template: { code: "FACILITY-GENERAL", revision: 1, content_hash: "hash" },
      responsible: { user_id: 2, name: "Facility Manager", email: "facility@example.test" },
      enabled_modules: [],
      planned_modules: ["asset-manager"],
      navigator: [
        {
          code: "home",
          label: "Home",
          route: "/workspaces/7/home",
          state: "READY",
          permission_key: "",
          read_only: false,
          reason: "",
        },
        {
          code: "asset-manager",
          label: "Asset Manager",
          route: "/workspaces/7/asset-manager",
          state: "PLANNED",
          permission_key: "",
          read_only: false,
          reason: "Planned",
        },
      ],
      permissions: { "workspace.open": true },
      allowed_actions: ["open"],
      home_configuration: {},
      version: 1,
      etag: "1234567890abcdef",
    };
    const home = {
      workspace: identity,
      breadcrumb: context.breadcrumb,
      responsible: context.responsible,
      status: "ACTIVE",
      enabled_modules: [],
      planned_modules: ["asset-manager"],
      recent_activity: [],
      recent_documents: [],
      my_tasks: [],
      related_workspaces: [],
      allowed_actions: ["open"],
      capability_flags: {},
    };
    vi.spyOn(globalThis, "fetch").mockImplementation((input: RequestInfo | URL) => {
      const path = String(input);
      const body =
        path === "/api/v1/workspaces"
          ? [
              {
                workspace_id: 7,
                workspace_name: "Main Facility",
                workspace_type: "FACILITY",
                business_number: "FAC-0001",
                record_code: "01.04.01",
                status: "ACTIVE",
                responsible: "Facility Manager",
                parent: "Enterprise",
                last_route: "/workspaces/7/home",
              },
            ]
          : path.endsWith("/home")
            ? home
            : context;
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
    });

    render(
      <MemoryRouter initialEntries={["/workspaces/7/home"]}>
        <Routes>
          <Route path="/workspaces/:workspaceId/*" element={<WorkspaceOperationalPage token="token" />} />
        </Routes>
      </MemoryRouter>
    );

    expect(await screen.findByRole("heading", { name: "Main Facility" })).toBeInTheDocument();
    expect(screen.getByLabelText("Workspace Breadcrumb")).toHaveTextContent("Enterprise");
    expect(screen.getByText("Workspace Navigator")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Asset Manager/ })).toBeDisabled();
    expect(screen.getByText("Asset Manager · PLANNED")).toBeInTheDocument();
    expect(screen.getAllByText("Facility Manager").length).toBeGreaterThan(0);
  });
});
