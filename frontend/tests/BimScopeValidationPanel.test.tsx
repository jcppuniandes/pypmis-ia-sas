import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import BimScopeValidationPanel from "../src/components/BimScopeValidationPanel";
import type { QuantityTakeoffLine } from "../src/types";

const typedMemberLine: QuantityTakeoffLine = {
  id: 101,
  project_id: 1,
  run_id: 25,
  source_row_id: "#50:ElementCount",
  element_id: "#50",
  element_guid: "MEMBERGUID",
  ifc_class: "IfcMember",
  category: "Montante de fachada",
  family: "Rectangular Mullion",
  type_name: "50 x 150mm",
  instance_name: "Rectangular Mullion:50 x 150mm:123",
  project_name: "Wellness Center",
  site_name: "Default",
  building_name: "Building A",
  storey: "Ground floor",
  system_name: "",
  zone_name: "",
  assembly_name: "",
  classification_system: "",
  classification_code: "",
  quantity: 1,
  unit: "ea",
  measurement_rule: "ElementCount",
  wbs_code: "",
  cbs_code: "",
  fbs_code: "",
  package_code: "",
  wbs_id: null,
  cbs_id: null,
  fbs_id: null,
  work_package_id: null,
  mapping_status: "needs_mapping",
  validation_notes: "Missing WBS; Missing CBS; Missing FBS",
  raw_data: {
    ifc_type_entity: "IFCMEMBERTYPE",
    ifc_predefined_type: "MULLION",
    quantity_calculation: {
      confidence: "Baja",
      fallback_rule: "GeometryLengthBBox",
      fallback_unit: "m",
      recommended_quantity: null,
      source: "Conteo fallback",
      source_quantity: 1,
      source_unit: "ea",
      status: "requires_controlled_measurement",
    },
  },
  created_at: "2026-05-21T23:35:57Z",
  updated_at: "2026-05-21T23:35:57Z",
};

describe("BimScopeValidationPanel", () => {
  it("shows the single controlled quantity table with constructive element before the technical IFC class", () => {
    render(<BimScopeValidationPanel lines={[typedMemberLine]} />);

    const panel = screen.getByRole("region", { name: /tabla de cantidades controladas/i });

    expect(within(panel).getByRole("heading", { name: /tabla de cantidades controladas/i })).toBeInTheDocument();
    expect(within(panel).getAllByRole("table")).toHaveLength(1);
    expect(within(panel).getByRole("heading", { name: /calculador de cantidades bim/i })).toBeInTheDocument();
    expect(within(panel).getAllByText(/Conteo fallback/i).length).toBeGreaterThan(0);
    expect(within(panel).getByText(/Unidad ea no coincide con la regla esperada/i)).toBeInTheDocument();
    expect(within(panel).getByText(/Fuente: 1 ea/i)).toBeInTheDocument();
    expect(within(panel).getByText(/Confianza Baja/i)).toBeInTheDocument();
    expect(within(panel).getByText(/Fallback sugerido: GeometryLengthBBox \/ m/i)).toBeInTheDocument();
    expect(within(panel).getByRole("columnheader", { name: /elemento constructivo/i })).toBeInTheDocument();
    expect(within(panel).getByRole("columnheader", { name: /regla de cantidad/i })).toBeInTheDocument();
    expect(within(panel).getByText("Montante de fachada / Rectangular Mullion / 50 x 150mm")).toBeInTheDocument();
    expect(within(panel).getByText(/IfcMember \/ ElementCount/)).toBeInTheDocument();
  });

  it("shows an editable project catalog for BIM quantity rules", async () => {
    const onUpdateQuantityRule = vi.fn();
    const user = userEvent.setup();

    render(
      <BimScopeValidationPanel
        lines={[typedMemberLine]}
        quantityRules={[
          {
            id: 7,
            project_id: 1,
            ifc_class: "IFCWALLSTANDARDCASE",
            element_label: "Muro",
            expected_measure: "area o volumen",
            rule_hint: "NetSideArea / NetVolume",
            expected_units: ["m2", "m3"],
            allow_fallback_count: true,
            source: "system_default",
            status: "active",
            version: 1,
            created_at: "2026-06-03T00:00:00Z",
            updated_at: "2026-06-03T00:00:00Z",
          },
        ]}
        onUpdateQuantityRule={onUpdateQuantityRule}
      />
    );

    const panel = screen.getByRole("region", { name: /tabla de cantidades controladas/i });
    expect(within(panel).getByRole("heading", { name: /catalogo de reglas de cantidad/i })).toBeInTheDocument();
    expect(within(panel).getByText("IFCWALLSTANDARDCASE")).toBeInTheDocument();
    expect(within(panel).getByText("m2 / m3")).toBeInTheDocument();

    await user.click(within(panel).getByRole("button", { name: /editar regla ifcwallstandardcase/i }));
    await user.clear(within(panel).getByLabelText(/medida esperada/i));
    await user.type(within(panel).getByLabelText(/medida esperada/i), "conteo controlado");
    await user.clear(within(panel).getByLabelText(/unidades esperadas/i));
    await user.type(within(panel).getByLabelText(/unidades esperadas/i), "ea");
    await user.click(within(panel).getByRole("button", { name: /guardar regla bim/i }));

    expect(onUpdateQuantityRule).toHaveBeenCalledWith(7, {
      element_label: "Muro",
      expected_measure: "conteo controlado",
      rule_hint: "NetSideArea / NetVolume",
      expected_units: ["ea"],
      allow_fallback_count: true,
      status: "active",
      expected_version: 1,
    });
  });

  it("lets the user recalculate stored quantity lines with the current BIM rules", async () => {
    const onRecalculateQuantityRules = vi.fn();
    const user = userEvent.setup();

    render(
      <BimScopeValidationPanel
        lines={[typedMemberLine]}
        onRecalculateQuantityRules={onRecalculateQuantityRules}
        recalculationSummary={{
          project_id: 1,
          run_id: 25,
          total_lines: 1,
          changed_line_count: 1,
          valid_count: 1,
          review_count: 0,
          blocked_count: 0,
          cost_rollup_gate: "ready",
          affected_classes: ["IfcMember"],
          impacts: [
            {
              line_id: 101,
              element_guid: "MEMBERGUID",
              ifc_class: "IfcMember",
              previous_status: "blocked",
              new_status: "valid",
              previous_measure: "longitud",
              new_measure: "conteo controlado",
              previous_units: ["m"],
              new_units: ["ea"],
              mapping_status: "mapped",
            },
          ],
        }}
      />
    );

    const panel = screen.getByRole("region", { name: /tabla de cantidades controladas/i });
    await user.click(within(panel).getByRole("button", { name: /recalcular reglas/i }));

    expect(onRecalculateQuantityRules).toHaveBeenCalledTimes(1);
    expect(within(panel).getByText(/1 linea\(s\) cambiadas/i)).toBeInTheDocument();
    expect(within(panel).getByText(/Gate de costos: ready/i)).toBeInTheDocument();
    expect(within(panel).getByText(/blocked -> valid/i)).toBeInTheDocument();
  });

  it("lets the user approve the current controlled measurement group", async () => {
    const onApproveControlledMeasurement = vi.fn();
    const user = userEvent.setup();

    render(
      <BimScopeValidationPanel
        lines={[typedMemberLine]}
        onApproveControlledMeasurement={onApproveControlledMeasurement}
      />
    );

    const panel = screen.getByRole("region", { name: /tabla de cantidades controladas/i });
    expect(within(panel).getByText(/medicion: pendiente/i)).toBeInTheDocument();

    await user.clear(within(panel).getByLabelText(/cantidad controlada si-ifcmember-01/i));
    await user.type(within(panel).getByLabelText(/cantidad controlada si-ifcmember-01/i), "2.5");
    await user.clear(within(panel).getByLabelText(/unidad controlada si-ifcmember-01/i));
    await user.type(within(panel).getByLabelText(/unidad controlada si-ifcmember-01/i), "m");
    await user.click(within(panel).getByRole("button", { name: /aprobar medicion/i }));

    expect(onApproveControlledMeasurement).toHaveBeenCalledWith({
      line_ids: [101],
      measurement_rule: "ElementCount",
      quantity: 2.5,
      unit: "m",
      source: "Conteo fallback",
      note: "Aprobacion controlada de SI-IFCMEMBER-01 - Montante de fachada / Rectangular Mullion / 50 x 150mm",
    });
  });

  it("lets the user assign WBS, CBS, FBS and package codes from the controlled quantity table", async () => {
    const onAssignControlCodes = vi.fn();
    const user = userEvent.setup();

    render(
      <BimScopeValidationPanel
        lines={[typedMemberLine]}
        wbsCatalog={[
          {
            id: 11,
            parent_id: null,
            code: "QTO-WBS-01",
            name: "Civil area",
            level: 2,
            description: "",
            dictionary: "",
            responsible: "",
            status: "active",
          },
        ]}
        cbsCatalog={[
          {
            id: 21,
            project_id: 1,
            parent_id: null,
            code: "QTO-CBS-01",
            cost_category: "Concrete",
            level: 2,
            description: "",
            status: "active",
            version: 1,
            created_at: "2026-06-04T00:00:00Z",
            updated_at: "2026-06-04T00:00:00Z",
          },
        ]}
        fbsFundingSources={[
          {
            id: 31,
            project_id: 1,
            code: "QTO-FBS-01",
            name: "AFE civil",
            amount: 100000,
            approved_amount: 100000,
            source_of_funds: "Corporate Budget",
            funding_type: "CAPEX",
            authorization_ref: "AFE-01",
            usage_restrictions: "",
            funds_available: 100000,
            funds_committed: 0,
            funds_executed: 0,
            balance: 100000,
            currency: "USD",
            status: "approved",
            usage_rules: "",
            version: 1,
            created_at: "2026-06-04T00:00:00Z",
            updated_at: "2026-06-04T00:00:00Z",
          },
        ]}
        workPackages={[
          {
            id: 41,
            wbs_id: 11,
            control_account_id: null,
            parent_id: null,
            package_type: "IWP",
            code: "IWP-CIV-01",
            title: "Civil install package",
            description: "",
            discipline: "Civil",
            sequence_no: 1,
            path_of_construction: "",
            owner_role: "Workface Planner",
            readiness_status: "constraint_review",
            planned_release_date: null,
            planned_start: null,
            planned_finish: null,
            release_required_on: null,
            main_constraints: "",
            progress_percent: 0,
            version: 1,
            updated_at: "2026-06-04T00:00:00Z",
          },
        ]}
        onAssignControlCodes={onAssignControlCodes}
      />
    );

    const panel = screen.getByRole("region", { name: /tabla de cantidades controladas/i });
    await user.selectOptions(within(panel).getByLabelText(/wbs para si-ifcmember-01/i), "QTO-WBS-01");
    await user.selectOptions(within(panel).getByLabelText(/cbs para si-ifcmember-01/i), "QTO-CBS-01");
    await user.selectOptions(within(panel).getByLabelText(/fbs para si-ifcmember-01/i), "QTO-FBS-01");
    await user.selectOptions(within(panel).getByLabelText(/paquete para si-ifcmember-01/i), "IWP-CIV-01");
    await user.clear(within(panel).getByLabelText(/codigo de partida para si-ifcmember-01/i));
    await user.type(within(panel).getByLabelText(/codigo de partida para si-ifcmember-01/i), "PART-CIV-001");
    await user.clear(within(panel).getByLabelText(/partida apu para si-ifcmember-01/i));
    await user.type(within(panel).getByLabelText(/partida apu para si-ifcmember-01/i), "Montante fachada 50 x 150mm");
    await user.clear(within(panel).getByLabelText(/precio unitario para si-ifcmember-01/i));
    await user.type(within(panel).getByLabelText(/precio unitario para si-ifcmember-01/i), "85.5");
    await user.click(within(panel).getByRole("button", { name: /guardar codigos/i }));

    expect(onAssignControlCodes).toHaveBeenCalledWith({
      line_ids: [101],
      wbs_code: "QTO-WBS-01",
      cbs_code: "QTO-CBS-01",
      fbs_code: "QTO-FBS-01",
      package_code: "IWP-CIV-01",
      cost_item_code: "PART-CIV-001",
      cost_item_name: "Montante fachada 50 x 150mm",
      budget_unit: "ea",
      unit_rate: 85.5,
      note: "Asignacion de codigos de control SI-IFCMEMBER-01",
    });
  });

  it("summarizes BIM budget items already assigned to takeoff lines", () => {
    render(
      <BimScopeValidationPanel
        lines={[
          {
            ...typedMemberLine,
            raw_data: {
              ...typedMemberLine.raw_data,
              budget_item_assignment: {
                cost_item_code: "PART-CIV-001",
                cost_item_name: "Montante fachada 50 x 150mm",
                budget_amount: 171,
                budget_unit: "ea",
                quantity: 2,
                unit_rate: 85.5,
              },
            },
          },
        ]}
      />
    );

    const panel = screen.getByRole("region", { name: /tabla de cantidades controladas/i });
    expect(within(panel).getByText(/Presupuesto BIM/i)).toBeInTheDocument();
    expect(within(panel).getByText("$171")).toBeInTheDocument();
    expect(within(panel).getByText(/PART-CIV-001 \/ Montante fachada 50 x 150mm/i)).toBeInTheDocument();
    expect(within(panel).getByText(/2 ea x \$85.50 = \$171/i)).toBeInTheDocument();
  });

  it("shows Colombia APU catalog actions and suggested budget items in COP", async () => {
    const onSyncColombiaApuCatalog = vi.fn();
    const onSuggestApuForLines = vi.fn();
    const user = userEvent.setup();

    render(
      <BimScopeValidationPanel
        lines={[
          {
            ...typedMemberLine,
            ifc_class: "IfcWall",
            category: "Muros",
            family: "Concreto",
            type_name: "Muro 15 cm",
            quantity: 12.5,
            unit: "m2",
            raw_data: {
              ...typedMemberLine.raw_data,
              apu_suggestion: {
                budget_amount: 565000,
                budget_unit: "m2",
                cost_item_code: "1.05.0101",
                cost_item_name: "Muro en concreto reforzado e=0.15 m",
                currency: "COP",
                match_score: 92,
                quantity: 12.5,
                source_key: "datacauca_public_apu",
                status: "suggested",
                structure_note: "Estructura de recursos estimada desde catalogo publico.",
                structure_status: "review_required",
                apu_structure: [
                  {
                    amount: 11300,
                    component: "Mano de obra",
                    component_type: "LABOR",
                    description: "Cuadrilla y rendimiento para muro",
                    quantity: 1,
                    status: "review",
                    unit: "m2",
                    unit_rate: 11300,
                  },
                  {
                    amount: 24860,
                    component: "Materiales",
                    component_type: "MATERIAL",
                    description: "Concreto, refuerzo e insumos",
                    quantity: 1,
                    status: "review",
                    unit: "m2",
                    unit_rate: 24860,
                  },
                ],
                unit_rate: 45200,
              },
            },
          },
        ]}
        colombiaApuCatalog={[
          {
            id: 7,
            tenant_id: 1,
            project_id: 1,
            source_key: "datacauca_public_apu",
            external_id: "datacauca_public_apu:1.05.0101:centro",
            item_code: "1.05.0101",
            item_name: "Muro en concreto reforzado e=0.15 m",
            unit: "m2",
            unit_rate: 45200,
            currency: "COP",
            group_name: "Edificaciones",
            chapter: "Muros",
            region: "Centro",
            source_url: "https://datacauca.gov.co/apu/apu/apu/query",
            license_note: "Fuente publica gratuita; validar vigencia y oficialidad antes de aprobar presupuesto.",
            update_frequency: "Public source / manual or scheduled sync",
            status: "review",
            raw_data: {
              structure_note: "Validar contra APU oficial antes de aprobar.",
              structure_status: "review_required",
              apu_structure: [
                {
                  amount: 11300,
                  component: "Mano de obra",
                  component_type: "LABOR",
                  description: "Cuadrilla y rendimiento para muro",
                  quantity: 1,
                  status: "review",
                  unit: "m2",
                  unit_rate: 11300,
                },
                {
                  amount: 24860,
                  component: "Materiales",
                  component_type: "MATERIAL",
                  description: "Concreto, refuerzo e insumos",
                  quantity: 1,
                  status: "review",
                  unit: "m2",
                  unit_rate: 24860,
                },
              ],
            },
            created_at: "2026-06-06T00:00:00Z",
            updated_at: "2026-06-06T00:00:00Z",
          },
        ]}
        colombiaApuSync={{
          project_id: 1,
          source_key: "datacauca_public_apu",
          source_url: "https://datacauca.gov.co/apu/apu/apu/query",
          created_count: 1,
          updated_count: 0,
          skipped_count: 0,
          total_count: 1,
          license_note: "Fuente publica gratuita; validar vigencia y oficialidad antes de aprobar presupuesto.",
          update_frequency: "Public source / manual or scheduled sync",
          synced_at: "2026-06-06T00:00:00Z",
        }}
        onSuggestApuForLines={onSuggestApuForLines}
        onSyncColombiaApuCatalog={onSyncColombiaApuCatalog}
      />
    );

    const panel = screen.getByRole("region", { name: /tabla de cantidades controladas/i });
    expect(within(panel).getByRole("region", { name: /base apu colombia/i })).toBeInTheDocument();
    expect(within(panel).getAllByText(/1.05.0101/i).length).toBeGreaterThan(0);
    expect(within(panel).getByText(/Sugerido \/ 92%/i)).toBeInTheDocument();
    expect(within(panel).getAllByText(/datacauca_public_apu/i).length).toBeGreaterThan(0);
    expect(within(panel).getAllByText(/COP/i).length).toBeGreaterThan(0);
    expect(within(panel).getAllByText(/Mano de obra/i).length).toBeGreaterThan(0);
    expect(within(panel).getAllByText(/Materiales/i).length).toBeGreaterThan(0);
    expect(within(panel).getByText(/Validar contra APU oficial antes de aprobar/i)).toBeInTheDocument();
    expect(within(panel).getByText(/Estructura de recursos estimada desde catalogo publico/i)).toBeInTheDocument();

    await user.click(within(panel).getByRole("button", { name: /actualizar base gratis/i }));
    await user.click(within(panel).getByRole("button", { name: /^sugerir apu$/i }));

    expect(onSyncColombiaApuCatalog).toHaveBeenCalledTimes(1);
    expect(onSuggestApuForLines).toHaveBeenCalledWith([101]);
  });
});
