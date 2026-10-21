import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { operationalApi } from "./api";
import OperationalProfilesAdminView from "./OperationalProfilesAdminView";
import OperationalSetupWorkspace from "./OperationalSetupWorkspace";
import type { OperationalProjectContext } from "./types";

const context: OperationalProjectContext = {
  tenant_id: 9,
  project_workspace_id: 701,
  name: "Canonical delivery project",
  project_workspace_external_key: "project-delivery-unique",
  project_workspace_record_code: "ENT.701",
  project_workspace_status: "ACTIVE",
  governance_model: "CONTRACTOR_DELIVERY",
  project_type: "DELIVERY",
  authorization_route: "CONTRACT_NTP",
  activation_state: "ACTIVE",
  legacy_project_id: 29,
  binding_state: "ACTIVE",
  binding_version: 2,
  operational_profile: null,
  effective_policy_revision: null,
  current_reporting_period: null,
  authorization: {
    authorized_for_operational_context: true,
    route: "CONTRACT_NTP",
    authority_source: "NTP",
    authority_reference: "NTP-701",
    as_of: "2026-10-19",
    blocking_conditions: [],
    commitment_conditions: ["Award ceiling must be verified before commitment"],
    warnings: [],
    source_hash: "source-revision",
  },
  blocking_conditions: [],
  warnings: [],
  allowed_actions: [],
};

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

describe("O1A frontend component contracts (not browser release proof)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("resolves the canonical Workspace route and sends explicit ETag/idempotency on binding", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(response({}));
    await operationalApi.reconcile(
      "token",
      701,
      {
        legacy_project_id: 29,
        reason: "Explicit verified relationship",
        source: "CONTROLLED_RECONCILIATION",
        expected_binding_version: 2,
      },
      "same-retry-key"
    );
    expect(fetch.mock.calls[0][0]).toBe("/api/v1/operational/projects/701/binding/reconcile");
    const request = fetch.mock.calls[0][1];
    expect(request?.headers).toMatchObject({ "If-Match": '"2"', "Idempotency-Key": "same-retry-key" });
    expect(JSON.parse(String(request?.body)).legacy_project_id).toBe(29);
  });

  it("shows separate canonical and legacy identities and commitment restrictions to a read-only actor", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const path = String(input);
      return Promise.resolve(
        response(
          path.endsWith("/context")
            ? context
            : path.endsWith("/binding")
              ? { state: "ACTIVE", binding: null, history: [] }
              : { items: [], total: 0 }
        )
      );
    });
    render(<OperationalSetupWorkspace token="reader" workspaceId={701} />);
    expect(await screen.findByText("Canonical delivery project")).toBeInTheDocument();
    expect(screen.getByText("CONTRACTOR_DELIVERY")).toBeInTheDocument();
    expect(screen.getByText("701", { selector: "dd" })).toBeInTheDocument();
    expect(screen.getByText("29", { selector: "dd" })).toBeInTheDocument();
    expect(screen.getByText("Award ceiling must be verified before commitment")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reconciliar vinculación" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Abrir periodo" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Configuración del perfil (JSON)")).not.toBeInTheDocument();
  });

  it("does not render a guessed context after a server-side project denial", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      response({ detail: "OPERATIONAL_PROJECT_CONTEXT_UNAUTHORIZED" }, 403)
    );
    render(<OperationalSetupWorkspace token="unauthorized" workspaceId={701} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("OPERATIONAL_PROJECT_CONTEXT_UNAUTHORIZED");
    expect(screen.queryByLabelText("Canonical operational Project identity")).not.toBeInTheDocument();
  });

  it("renders immutable period history and only server-authorized transition commands", async () => {
    const period = {
      id: 80,
      period_code: "2026-W42",
      period_start: "2026-10-12",
      period_end: "2026-10-18",
      cutoff_at: "2026-10-18T20:00:00-05:00",
      timezone: "America/Bogota",
      status: "PUBLISHED",
      revision: 1,
      version: 4,
      schedule_data_date: "2026-10-16",
      source_configuration_revision: 3,
      reopen_parent_id: null,
      notes: "Published header only",
      opened_by: 2,
      closed_by: 3,
      published_by: 4,
      allowed_actions: ["period.reopen"],
    };
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const path = String(input);
      return Promise.resolve(
        response(
          path.endsWith("/context")
            ? context
            : path.endsWith("/binding")
              ? { state: "ACTIVE", binding: null, history: [] }
              : { items: [period], total: 1 }
        )
      );
    });
    render(<OperationalSetupWorkspace token="manager" workspaceId={701} />);
    expect(await screen.findByText("2026-W42 · r1")).toBeInTheDocument();
    expect(screen.getByText("America/Bogota")).toBeInTheDocument();
    expect(screen.getByText("2026-10-16")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "reopen 2026-W42 revision 1" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "publish 2026-W42 revision 1" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "close 2026-W42 revision 1" })).not.toBeInTheDocument();
  });

  it("keeps PUBLISHED policy read-only and offers only a successor draft", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      response({
        items: [
          {
            id: 8,
            code: "OPS",
            name: "Delivery profile",
            status: "published",
            revision: 4,
            version: 3,
            content_json: { effective_from: "2026-01-01" },
          },
        ],
        default_content: {},
        allowed_actions: ["admin.configure", "admin.publish"],
      })
    );
    render(<OperationalProfilesAdminView token="admin" />);
    fireEvent.click(await screen.findByRole("button", { name: "Ver perfil OPS revisión 4" }));
    expect(screen.getByLabelText("Configuración del perfil (JSON)")).toBeDisabled();
    expect(screen.getByLabelText("Nombre del perfil")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Guardar borrador" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Publicar perfil" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Crear sucesor DRAFT" })).toBeDisabled();
  });

  it("does not expose reusable policy editing when the API denies a USER actor", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      response({ detail: "Operational policy administration denied" }, 403)
    );
    render(<OperationalProfilesAdminView token="user" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("administration denied");
    expect(screen.queryByLabelText("Configuración del perfil (JSON)")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Crear perfil DRAFT" })).not.toBeInTheDocument();
  });
});
