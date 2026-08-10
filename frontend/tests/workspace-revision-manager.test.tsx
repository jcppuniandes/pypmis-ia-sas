import "@testing-library/jest-dom/vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import WorkspaceRevisionManager from "../src/features/enterprise-structure/components/WorkspaceRevisionManager";
import type { EnterpriseStructureConfiguration } from "../src/features/enterprise-structure/types";

const published = {
  id: 1,
  release_code: "ES-PYP-CORE-RECONCILED-20260809",
  release_name: "Published CORE",
  revision_number: 1,
  revision_version: 1,
  state: "published" as const,
  previous_release_id: null,
  source_hash: "a".repeat(64),
  canonical_hash: "b".repeat(64),
  content_fingerprint: "c".repeat(64),
  workspace_count: 2,
  objective_count: 0,
  classification_count: 1,
  link_count: 0,
  published_at: "2026-08-10T10:00:00Z",
  published_by: "admin@demo.local",
};

const data: EnterpriseStructureConfiguration = {
  workspace_types: [
    {
      id: 1,
      kind: "workspace_type",
      code: "enterprise",
      name: "Enterprise",
      description: "",
      status: "published",
      revision: 1,
      version: 1,
      content_json: {},
      content_hash: "",
      published_at: "2026-08-10T10:00:00Z",
    },
    {
      id: 2,
      kind: "workspace_type",
      code: "business-unit",
      name: "Business Unit",
      description: "",
      status: "published",
      revision: 1,
      version: 1,
      content_json: {},
      content_hash: "",
      published_at: "2026-08-10T10:00:00Z",
    },
  ],
  categories: [],
  composition_rules: [
    {
      parent_type_code: "enterprise",
      parent_type_name: "Enterprise",
      configuration_id: 1,
      revision: 1,
      status: "published",
      allowed_children: ["business-unit"],
      max_depth: null,
      can_be_root: true,
      required_categories: [],
      required_fields: ["code", "name"],
    },
  ],
  drafts: [],
  tree: [],
  classifications: [],
  links: [],
  summary: { nodes: 2, types: 2, drafts: 0 },
  published_release: published,
  draft_release: {
    ...published,
    id: 2,
    release_code: "ES-PYP-CORE-REV-002",
    release_name: "Workspace Structure Revision 002",
    revision_number: 2,
    state: "draft",
    previous_release_id: 1,
    base_content_fingerprint: published.content_fingerprint,
    content_fingerprint: "d".repeat(64),
    created_at: "2026-08-10T11:00:00Z",
    created_by: "admin@demo.local",
    updated_at: "2026-08-10T11:00:00Z",
    last_modified_by: "editor@demo.local",
    validated_at: "2026-08-10T11:05:00Z",
    approved_at: null,
    approved_by: null,
    draft_hash: "d".repeat(64),
    diff_hash: "e".repeat(64),
    validation: {
      valid: true,
      errors: [],
      conflicts: [],
      checks: { single_root: true, acyclic: true },
      draft_hash: "d".repeat(64),
      diff_hash: "e".repeat(64),
      validated_at: "2026-08-10T11:05:00Z",
    },
    workspaces: [
      {
        workspace_key: "ENT-PYP",
        technical_id: 1,
        parent_key: null,
        record_code: "01",
        code: "ENT",
        name: "P&P Enterprise",
        workspace_type_code: "enterprise",
        description: "Published baseline",
        responsible_user_id: null,
        status: "active",
        sort_order: 0,
        change_state: "unchanged",
        classifications: [],
      },
      {
        workspace_key: "REV-2-ABC",
        technical_id: null,
        parent_key: "ENT-PYP",
        record_code: "01.01",
        code: "BUS-001",
        name: "Artificial Intelligence",
        workspace_type_code: "business-unit",
        description: "New controlled workspace",
        responsible_user_id: null,
        status: "draft",
        sort_order: 10,
        change_state: "add",
        classifications: [],
      },
    ],
  },
};

describe("Workspace Structure Revision Manager", () => {
  it("shows the published base, DRAFT gate actions, accessible change states and hierarchical tree", () => {
    render(
      <WorkspaceRevisionManager
        busy={false}
        canConfigure
        data={data}
        onBusy={vi.fn()}
        onError={vi.fn()}
        onNotice={vi.fn()}
        onReload={vi.fn().mockResolvedValue(data)}
        token="token"
      />
    );

    expect(screen.getByText("ES-PYP-CORE-RECONCILED-20260809")).toBeInTheDocument();
    expect(screen.getByText("ES-PYP-CORE-REV-002")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Validate/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Compare/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Approve/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /^Publish$/i })).toBeDisabled();
    expect(screen.getAllByText("Published baseline").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Added").length).toBeGreaterThan(0);
    expect(screen.getByText("Artificial Intelligence")).toBeInTheDocument();
    expect(screen.getByText("VALID · 0 errors · 0 conflicts")).toBeInTheDocument();
  });

  it("offers Create New Revision when no DRAFT exists", () => {
    const withoutDraft = { ...data, draft_release: null };
    render(
      <WorkspaceRevisionManager
        busy={false}
        canConfigure
        data={withoutDraft}
        onBusy={vi.fn()}
        onError={vi.fn()}
        onNotice={vi.fn()}
        onReload={vi.fn().mockResolvedValue(withoutDraft)}
        token="token"
      />
    );

    expect(screen.getByRole("button", { name: /Create New Revision/i })).toBeEnabled();
    expect(screen.getByText("Published CORE is immutable")).toBeInTheDocument();
  });

  it("sends If-Match and explains an optimistic concurrency conflict", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: { reason: "REVISION_VERSION_CONFLICT" } }), {
        status: 409,
        headers: { "Content-Type": "application/json" },
      })
    );
    vi.stubGlobal("fetch", fetchMock);
    const onError = vi.fn();
    const user = userEvent.setup();
    render(
      <WorkspaceRevisionManager
        busy={false}
        canConfigure
        data={data}
        onBusy={vi.fn()}
        onError={onError}
        onNotice={vi.fn()}
        onReload={vi.fn().mockResolvedValue(data)}
        token="token"
      />
    );

    await user.click(screen.getByText("Artificial Intelligence"));
    await user.click(screen.getByRole("button", { name: /Archive/i }));

    await waitFor(() =>
      expect(onError).toHaveBeenCalledWith(
        "This revision changed since you opened it. Reload the latest version before continuing."
      )
    );
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/archive"),
      expect.objectContaining({
        headers: expect.objectContaining({ "If-Match": '"1"' }),
      })
    );
    vi.unstubAllGlobals();
  });
});
