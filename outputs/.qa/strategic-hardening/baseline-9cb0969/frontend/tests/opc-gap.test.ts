import { describe, expect, it } from "vitest";
import { buildOpcGapAnalysis, type OpcGapInput } from "../src/lib/opcGap";

const baseInput: OpcGapInput = {
  activitySheetRowCount: 0,
  activitySheetWbsCount: 0,
  apuCatalogCount: 0,
  bimModelCount: 0,
  blockingConstraintCount: 0,
  controlAccountCount: 0,
  controlSnapshotCount: 0,
  costLoadedActivityPercent: 0,
  costSheetLineCount: 0,
  evidenceScore: 0,
  fundingSourceCount: 0,
  hasCostBaseline: false,
  hasRenderableIfcGeometry: false,
  integratedMatrixRowCount: 0,
  latestCostRecordCount: 0,
  latestProgressRecordCount: 0,
  processFlowCompletion: 0,
  projectCode: "01",
  quantityLineCount: 0,
  quantityMappedLineCount: 0,
  quantityRuleBlockedCount: 0,
  quantityRuleReviewCount: 0,
  quantityRuleValidCount: 0,
  scheduleActivityCount: 0,
  scheduleQualityScore: 0,
  scheduleRelationshipCount: 0,
  teamRoleCount: 1,
  workPackageCount: 0,
  workPackageReadyCount: 0,
};

describe("control diagnostic analysis", () => {
  it("prioritizes the P6 CPM and cost-loaded spine before downstream controls", () => {
    const analysis = buildOpcGapAnalysis({
      ...baseInput,
      apuCatalogCount: 50,
      bimModelCount: 1,
      hasRenderableIfcGeometry: true,
      quantityLineCount: 90,
    });

    expect(analysis.overallStatus).toBe("gap");
    expect(analysis.criticalGapCount).toBeGreaterThan(0);
    expect(analysis.nextActions[0]).toMatch(/P6 XML\/XER/i);
    expect(analysis.gaps.find((gap) => gap.id === "cpm-master-schedule")?.status).toBe("gap");
    expect(analysis.spine[1]).toMatchObject({ id: "p6-cpm", status: "gap" });
  });

  it("recognizes a connected BIM to APU to EVM control spine when the project data is present", () => {
    const analysis = buildOpcGapAnalysis({
      ...baseInput,
      activitySheetRowCount: 24,
      activitySheetWbsCount: 6,
      apuCatalogCount: 50,
      bimModelCount: 1,
      blockingConstraintCount: 1,
      controlAccountCount: 8,
      controlSnapshotCount: 2,
      costLoadedActivityPercent: 100,
      costSheetLineCount: 8,
      evidenceScore: 87,
      fundingSourceCount: 4,
      hasCostBaseline: true,
      hasRenderableIfcGeometry: true,
      integratedMatrixRowCount: 8,
      latestCostRecordCount: 3,
      latestProgressRecordCount: 3,
      processFlowCompletion: 82,
      quantityLineCount: 90,
      quantityMappedLineCount: 82,
      quantityRuleValidCount: 82,
      scheduleActivityCount: 24,
      scheduleQualityScore: 95,
      scheduleRelationshipCount: 28,
      teamRoleCount: 4,
      workPackageCount: 7,
      workPackageReadyCount: 4,
    });

    expect(analysis.overallStatus).toBe("ready");
    expect(analysis.readinessScore).toBeGreaterThanOrEqual(75);
    expect(analysis.gaps.find((gap) => gap.id === "bim-apu-budget")?.status).toBe("ready");
    expect(analysis.gaps.find((gap) => gap.id === "evm-control")?.status).toBe("ready");
  });

  it("keeps the BIM budget bridge partial when quantities exist but IFC geometry is not renderable", () => {
    const analysis = buildOpcGapAnalysis({
      ...baseInput,
      activitySheetRowCount: 24,
      activitySheetWbsCount: 6,
      apuCatalogCount: 50,
      bimModelCount: 1,
      controlAccountCount: 8,
      costSheetLineCount: 8,
      fundingSourceCount: 4,
      hasRenderableIfcGeometry: false,
      integratedMatrixRowCount: 8,
      quantityLineCount: 90,
      quantityMappedLineCount: 82,
      quantityRuleValidCount: 82,
    });

    const bimGap = analysis.gaps.find((gap) => gap.id === "bim-apu-budget");

    expect(bimGap?.status).toBe("partial");
    expect(bimGap?.appEvidence).toMatch(/geometry pending/i);
  });

  it("keeps generated user-facing references free of external product comparison names", () => {
    const analysis = buildOpcGapAnalysis({
      ...baseInput,
      apuCatalogCount: 50,
      bimModelCount: 1,
      quantityLineCount: 90,
    });

    expect(analysis.gaps.map((gap) => gap.controlReference).join(" ")).not.toMatch(/\bOPC\b|Oracle|Primavera Cloud/i);
  });
});
