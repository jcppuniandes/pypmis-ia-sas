import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import FieldOperationsWorkspace from "./FieldOperationsWorkspace";
import FieldProfilesAdminView from "./FieldProfilesAdminView";
import FieldConsumerPanel from "./FieldConsumerPanel";
import { encodeFields } from "./formValues";
import { FieldCommandForm } from "./FieldForms";
import { permits, type Row } from "./api";

const base = "/api/v1/field-operations/projects/27";
const send = (value: Row, status = 200) => new Response(JSON.stringify(value), { status });
const profile = {
  id: 3,
  version: 2,
  status: "published",
  code: "FIELD",
  content_json: { production_types: ["INSTALLED"] },
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Field Operations authority", () => {
  it("keeps canonical target identities in native reference choices", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => send({ items: [{ target_kind: "CWA", target_id: 41, code: "CWA-41" }] }))
    );
    const submit = vi.fn(async () => ({ id: 8 }));
    render(
      <FieldCommandForm
        label="Crear vínculo"
        spec={{
          fields: [
            {
              key: "cwa_id",
              label: "CWA",
              kind: "id",
              collection: "/reference-targets?target_kind=CWA",
              required: true,
            },
          ],
        }}
        environment={{ token: "field", base, profile: null, revision: 0 }}
        busy={false}
        submit={submit}
      />
    );
    await screen.findByRole("option", { name: "CWA-41" });
    fireEvent.change(screen.getByLabelText("CWA"), { target: { value: "41" } });
    fireEvent.change(screen.getByLabelText("Motivo operacional"), { target: { value: "Canonical target chosen" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear vínculo" }));
    await waitFor(() => expect(submit).toHaveBeenCalledWith({ cwa_id: 41, reason: "Canonical target chosen" }));
  });
  it("preserves observed decimals, normalizes instants and isolates native permissions", () => {
    expect(
      encodeFields(
        [
          { key: "quantity", label: "Cantidad", kind: "decimal" },
          { key: "observed_at", label: "Observado", kind: "datetime" },
          { key: "blocking", label: "Bloqueante", kind: "boolean" },
        ],
        { quantity: "900000000000000.12345678", observed_at: "2026-11-18T08:00:00-05:00", blocking: "false" }
      )
    ).toEqual({
      quantity: "900000000000000.12345678",
      observed_at: "2026-11-18T13:00:00.000Z",
      blocking: false,
    });
    expect(() => encodeFields([{ key: "id", label: "ID", kind: "id" }], { id: "1.5" })).toThrow();
    expect(permits(["cost.mapping.edit"], "mapping.edit")).toBe(false);
    expect(permits(["field_operations.mapping.edit"], "mapping.edit")).toBe(true);
  });

  it("shows the field views but no writes in an archived workspace", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url.includes("/configuration")
          ? send({ profile, allowed_actions: ["read", "workfront.edit", "production.record"] })
          : send({ items: [] })
      )
    );
    render(<FieldOperationsWorkspace token="reader" workspaceId={27} readOnly />);
    const nav = await screen.findByRole("navigation", { name: "Field Operations Manager submodules" });
    expect(within(nav).getByRole("button", { name: "Installed Quantity Evidence" })).toBeVisible();
    expect(within(nav).getByRole("button", { name: "Constraints Observed" })).toBeVisible();
    fireEvent.click(within(nav).getByRole("button", { name: "Workfronts" }));
    await screen.findByRole("table", { name: "Workfronts" });
    expect(screen.getByText(/Workspace archivado/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Nuevo registro" })).not.toBeInTheDocument();
  });

  it("pins a production version and keeps the reason after a stale verification", async () => {
    const record = { id: 51, version: 3, status: "RECORDED", production_code: "P-51", quantity: "2.25", uom: "m3" };
    const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
      const path = url.split("?")[0];
      if (path === base + "/configuration") return send({ profile, allowed_actions: ["read", "production.verify"] });
      if (path === base + "/production") return send({ items: [record] });
      if (path === base + "/production/51") return send(record);
      if (path === base + "/production/51/actions" && init?.method === "POST")
        return send({ detail: { code: "ETAG_MISMATCH" } }, 412);
      return send({ items: [] });
    });
    vi.stubGlobal("fetch", fetcher);
    render(<FieldOperationsWorkspace token="verifier" workspaceId={27} />);
    const nav = await screen.findByRole("navigation", { name: "Field Operations Manager submodules" });
    fireEvent.click(within(nav).getByRole("button", { name: "Production Records" }));
    fireEvent.click(await screen.findByRole("button", { name: "Ver Production Records 51" }));
    fireEvent.click(await screen.findByRole("button", { name: "Verificar producción…" }));
    const form = screen.getByRole("form", { name: "Verificar producción" });
    fireEvent.change(within(form).getByLabelText("Motivo operacional"), {
      target: { value: "Verificación independiente de campo" },
    });
    fireEvent.click(within(form).getByRole("button", { name: "Verificar producción" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("La versión cambió");
    const mutation = fetcher.mock.calls.find(([, init]) => init?.method === "POST");
    expect(mutation?.[1]?.headers).toMatchObject({ "If-Match": '"3"', "Idempotency-Key": expect.any(String) });
    expect(JSON.parse(String(mutation?.[1]?.body))).toEqual({
      action: "verify",
      reason: "Verificación independiente de campo",
    });
    expect(within(form).getByLabelText("Motivo operacional")).toHaveValue("Verificación independiente de campo");
  });

  it("protects a published field profile and exposes only a controlled successor", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        send({
          items: [profile],
          default_content: profile.content_json,
          allowed_actions: ["admin.configure", "admin.publish"],
        })
      )
    );
    render(<FieldProfilesAdminView token="configurator" />);
    fireEvent.click(await screen.findByRole("button", { name: "Ver Perfiles de campo FIELD" }));
    expect(screen.getByRole("button", { name: "Crear sucesor…" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Publicar perfil…" })).not.toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Guardar borrador de campo" })).not.toBeInTheDocument();
  });

  it("adopts via native Progress only after a real source pin is returned", async () => {
    const native = "/api/v1/progress/projects/27/field-adoptions";
    const source = {
      source_domain: "FIELD_OPERATIONS",
      source_entity_type: "PRODUCTION",
      source_entity_id: 51,
      source_version: 2,
      source_hash: "a".repeat(64),
      observed_at: "2026-11-18T13:00:00+00:00",
      quantity: "3",
      version: 0,
      consumer_allowed_actions: ["progress.capture"],
    };
    const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.startsWith(native + "/lookup")) return send(source);
      if (url === native && init?.method === "POST")
        return send({ id: 19, version: 1, decision: "PARTIAL_ADOPT", linked_entity_id: 40 }, 201);
      return send({ items: [] });
    });
    vi.stubGlobal("fetch", fetcher);
    render(<FieldConsumerPanel token="progress-actor" workspaceId={27} />);
    expect(screen.queryByRole("button", { name: "Registrar decisión PROGRESS" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Evidencia de campo ID"), { target: { value: "51" } });
    fireEvent.click(screen.getByRole("button", { name: "Consultar origen de campo" }));
    const form = await screen.findByRole("form", { name: "Registrar decisión PROGRESS" });
    fireEvent.change(within(form).getByLabelText("Decisión Progress"), { target: { value: "PARTIAL_ADOPT" } });
    fireEvent.change(within(form).getByLabelText("Cantidad a adoptar"), { target: { value: "1.25" } });
    fireEvent.change(within(form).getByLabelText("Período de Progress"), { target: { value: "4" } });
    fireEvent.change(within(form).getByLabelText("Código de medición borrador"), { target: { value: "FIELD-51" } });
    fireEvent.change(within(form).getByLabelText("Motivo operacional"), {
      target: { value: "Adopción parcial revisada" },
    });
    fireEvent.click(within(form).getByRole("button", { name: "Registrar decisión PROGRESS" }));
    await waitFor(() => expect(fetcher.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true));
    const mutation = fetcher.mock.calls.find(([, init]) => init?.method === "POST");
    expect(mutation?.[0]).toBe(native);
    expect(mutation?.[1]?.headers).toMatchObject({ "If-Match": '"0"' });
    expect(JSON.parse(String(mutation?.[1]?.body))).toMatchObject({
      source_entity_type: "PRODUCTION",
      source_entity_id: 51,
      source_version: 2,
      source_hash: "a".repeat(64),
      quantity: "1.25",
      decision: "PARTIAL_ADOPT",
      period_id: 4,
    });
    expect(fetcher.mock.calls.some(([url]) => url.includes("/measurements"))).toBe(false);
  });

  it("does not infer Progress rights from Field rights", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url.includes("/lookup")
          ? send({
              source_entity_id: 51,
              source_entity_type: "PRODUCTION",
              source_version: 2,
              source_hash: "a".repeat(64),
              observed_at: "2026-11-18T13:00:00Z",
              version: 0,
              consumer_allowed_actions: ["field_operations.production.record"],
            })
          : send({ items: [] })
      )
    );
    render(<FieldConsumerPanel token="field-actor" workspaceId={27} />);
    fireEvent.change(screen.getByLabelText("Evidencia de campo ID"), { target: { value: "51" } });
    fireEvent.click(screen.getByRole("button", { name: "Consultar origen de campo" }));
    await screen.findByText("PRODUCTION");
    await waitFor(() => expect(screen.getByText("Versión")).toBeVisible());
    expect(screen.queryByRole("form", { name: "Registrar decisión PROGRESS" })).not.toBeInTheDocument();
  });
});
