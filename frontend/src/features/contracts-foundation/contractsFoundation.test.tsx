import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import ContractsManagerWorkspace from "./ContractsManagerWorkspace";
import ContractProfilesAdminView from "./ContractProfilesAdminView";
import { encodeFields } from "./formValues";
import { permits, query, type Row } from "./api";

const base = "/api/v1/contracts/projects/27";
const send = (data: Row, status = 200) => new Response(JSON.stringify(data), { status });
const contract = {
  id: 77,
  version: 3,
  contract_number: "CT-77",
  title: "Contrato aislado",
  status: "DRAFT",
  current_version_id: 97,
};
const profile = {
  id: 22,
  version: 2,
  code: "PROFILE",
  name: "Perfil publicado",
  status: "published",
  content_json: {},
};
const renderContracts = (readOnly = false) =>
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ContractsManagerWorkspace token="actor" workspaceId={27} readOnly={readOnly} />
    </MemoryRouter>
  );

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Contracts Manager boundaries", () => {
  it("preserves large legal decimals, canonical IDs, URL filters and isolated duties", () => {
    expect(
      encodeFields(
        [
          { key: "amount", label: "Importe", kind: "decimal" },
          { key: "id", label: "Identidad", kind: "id" },
        ],
        { amount: "1000000000000000.12345678", id: "48" }
      )
    ).toEqual({ amount: "1000000000000000.12345678", id: 48 });
    expect(() => encodeFields([{ key: "id", label: "ID", kind: "id" }], { id: "1.5" })).toThrow();
    expect(query("/history?entity_type=ContractChange", { entity_id: 22 })).toBe(
      "/history?entity_type=ContractChange&entity_id=22"
    );
    expect(permits(["cost.mapping.edit"], "mapping.edit")).toBe(false);
    expect(permits(["contracts.mapping.edit"], "mapping.edit")).toBe(true);
  });

  it("uses a pinned record version and retains the draft after a stale write", async () => {
    const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
      const path = url.split("?")[0];
      if (path === base + "/configuration") return send({ profile, allowed_actions: ["read", "contract.approve"] });
      if (path === base + "/contracts") return send({ items: [contract] });
      if (path === base + "/contracts/77") return send(contract);
      if (path === base + "/contracts/77/actions" && init?.method === "POST") {
        return send({ detail: { code: "STALE_VERSION" } }, 412);
      }
      return send({ items: [] });
    });
    vi.stubGlobal("fetch", fetcher);
    renderContracts();
    const nav = await screen.findByRole("navigation", { name: "Contracts Manager submodules" });
    fireEvent.click(within(nav).getByRole("button", { name: "Contracts" }));
    fireEvent.click(await screen.findByRole("button", { name: "Ver Contracts 77" }));
    fireEvent.click(await screen.findByRole("button", { name: "Aprobar contrato…" }));
    const editor = screen.getByRole("form", { name: "Aprobar contrato" });
    fireEvent.change(within(editor).getByLabelText("Motivo contractual"), {
      target: { value: "Revisión independiente" },
    });
    fireEvent.click(within(editor).getByRole("button", { name: "Aprobar contrato" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("La versión cambió");
    await waitFor(() => expect(fetcher.mock.calls.filter(([url]) => url === base + "/contracts/77")).toHaveLength(2));
    const mutation = fetcher.mock.calls.find(([, request]) => request?.method === "POST");
    expect(mutation?.[1]?.headers).toMatchObject({ "If-Match": '"3"', "Idempotency-Key": expect.any(String) });
    expect(JSON.parse(String(mutation?.[1]?.body))).toEqual({ action: "approve", reason: "Revisión independiente" });
    expect(within(editor).getByLabelText("Motivo contractual")).toHaveValue("Revisión independiente");
  });

  it("does not show any allowed writer on an archived Workspace", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url.includes("/configuration")
          ? send({ profile, allowed_actions: ["read", "package.prepare", "contract.approve"] })
          : send({ items: [] })
      )
    );
    renderContracts(true);
    await screen.findByRole("table", { name: "Contract Packages" });
    expect(screen.getByText(/Workspace archivado/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Nuevo registro" })).not.toBeInTheDocument();
  });

  it("shows an immutable published profile and only exposes a controlled successor", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        send({ items: [profile], default_content: {}, allowed_actions: ["admin.configure", "admin.publish"] })
      )
    );
    render(<ContractProfilesAdminView token="publisher" />);
    fireEvent.click(await screen.findByRole("button", { name: "Ver Perfiles contractuales PROFILE" }));
    expect(screen.getByRole("button", { name: "Crear sucesor…" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Publicar perfil…" })).not.toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Guardar borrador contractual" })).not.toBeInTheDocument();
  });
});
