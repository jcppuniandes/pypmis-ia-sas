import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useActiveWorkspaceContext, WorkspaceContextProvider } from "./WorkspaceContextProvider";

const contextPayload = (workspaceId: number) => ({
  active_context: {
    tenant_id: 1,
    workspace_id: workspaceId,
    workspace_type: "PROJECT",
    workspace_name: `Workspace ${workspaceId}`,
    workspace_status: "ACTIVE",
    business_number: `P-${workspaceId}`,
    record_code: `01.${workspaceId}`,
    external_key: `workspace-${workspaceId}`,
    parent_workspace_id: null,
    parent_path: [],
    template_code: "PROJECT-TEMPLATE",
    template_revision: 1,
    responsible_user_id: 1,
    enabled_modules: ["scope-manager"],
    planned_modules: [],
    workspace_permissions: ["workspace.open"],
    opened_at: null,
    last_route: `/workspaces/${workspaceId}/home`,
  },
  identity: {
    tenant_id: 1,
    workspace_id: workspaceId,
    workspace_type: "PROJECT",
    workspace_name: `Workspace ${workspaceId}`,
    workspace_status: "ACTIVE",
    business_number: `P-${workspaceId}`,
    record_code: `01.${workspaceId}`,
    external_key: `workspace-${workspaceId}`,
  },
  parent: null,
  breadcrumb: [],
  template: { code: "PROJECT-TEMPLATE", revision: 1, content_hash: "hash" },
  responsible: { user_id: 1, name: "Responsible", email: "responsible@example.test" },
  enabled_modules: ["scope-manager"],
  planned_modules: [],
  navigator: [],
  permissions: { "workspace.open": true },
  allowed_actions: ["open"],
  home_configuration: {},
  version: 1,
  etag: `etag-${workspaceId}`,
});

const homePayload = (workspaceId: number) => ({
  workspace: contextPayload(workspaceId).identity,
  breadcrumb: [],
  responsible: contextPayload(workspaceId).responsible,
  status: "ACTIVE",
  enabled_modules: ["scope-manager"],
  planned_modules: [],
  recent_activity: [],
  recent_documents: [],
  my_tasks: [],
  related_workspaces: [],
  allowed_actions: ["open"],
  capability_flags: {},
});

function Probe() {
  const { context, loading } = useActiveWorkspaceContext();
  return <span>{loading ? "loading" : context?.identity.workspace_name}</span>;
}

describe("WorkspaceContextProvider", () => {
  afterEach(() => vi.restoreAllMocks());

  it("invalidates the previous Workspace before resolving a switch", async () => {
    let resolveSecond: ((response: Response) => void) | undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation((input: RequestInfo | URL) => {
      const path = String(input);
      const workspaceId = path.includes("/2/") ? 2 : 1;
      if (workspaceId === 2 && path.endsWith("/open")) {
        return new Promise((resolve) => {
          resolveSecond = resolve;
        });
      }
      const body = path.endsWith("/home") ? homePayload(workspaceId) : contextPayload(workspaceId);
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
    });

    const view = render(
      <WorkspaceContextProvider route="/workspaces/1/home" token="token" workspaceId={1}>
        <Probe />
      </WorkspaceContextProvider>
    );
    expect(await screen.findByText("Workspace 1")).toBeInTheDocument();

    await act(async () => {
      view.rerender(
        <WorkspaceContextProvider route="/workspaces/2/home" token="token" workspaceId={2}>
          <Probe />
        </WorkspaceContextProvider>
      );
      await Promise.resolve();
    });
    expect(screen.getByText("loading")).toBeInTheDocument();
    expect(screen.queryByText("Workspace 1")).not.toBeInTheDocument();

    await act(async () => {
      resolveSecond?.(new Response(JSON.stringify(contextPayload(2)), { status: 200 }));
    });
    await waitFor(() => expect(screen.getByText("Workspace 2")).toBeInTheDocument());
  });
});
