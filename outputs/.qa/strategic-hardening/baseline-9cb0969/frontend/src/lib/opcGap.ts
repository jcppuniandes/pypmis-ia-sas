export type OpcGapStatus = "ready" | "partial" | "gap";
export type OpcGapPriority = "P1" | "P2" | "P3";

export type OpcGapInput = {
  activitySheetRowCount: number;
  activitySheetWbsCount: number;
  apuCatalogCount: number;
  bimModelCount: number;
  blockingConstraintCount: number;
  controlAccountCount: number;
  controlSnapshotCount: number;
  costLoadedActivityPercent: number;
  costSheetLineCount: number;
  evidenceScore: number;
  fundingSourceCount: number;
  hasCostBaseline: boolean;
  hasRenderableIfcGeometry: boolean;
  integratedMatrixRowCount: number;
  latestCostRecordCount: number;
  latestProgressRecordCount: number;
  processFlowCompletion: number;
  projectCode: string;
  quantityLineCount: number;
  quantityMappedLineCount: number;
  quantityRuleBlockedCount: number;
  quantityRuleReviewCount: number;
  quantityRuleValidCount: number;
  scheduleActivityCount: number;
  scheduleQualityScore: number;
  scheduleRelationshipCount: number;
  teamRoleCount: number;
  workPackageCount: number;
  workPackageReadyCount: number;
};

export type OpcGapItem = {
  appEvidence: string;
  controlReference: string;
  id: string;
  nextAction: string;
  priority: OpcGapPriority;
  status: OpcGapStatus;
  title: string;
};

export type OpcDataSpineStep = {
  detail: string;
  evidence: string;
  id: string;
  label: string;
  status: OpcGapStatus;
};

export type OpcGapAnalysis = {
  criticalGapCount: number;
  gaps: OpcGapItem[];
  nextActions: string[];
  overallStatus: OpcGapStatus;
  readinessScore: number;
  spine: OpcDataSpineStep[];
};

function statusFrom(required: boolean, partial: boolean): OpcGapStatus {
  if (required) return "ready";
  return partial ? "partial" : "gap";
}

function scoreForStatus(status: OpcGapStatus) {
  if (status === "ready") return 100;
  if (status === "partial") return 50;
  return 0;
}

function priorityRank(priority: OpcGapPriority) {
  return priority === "P1" ? 1 : priority === "P2" ? 2 : 3;
}

export function buildOpcGapAnalysis(input: OpcGapInput): OpcGapAnalysis {
  const hasSchedule = input.scheduleActivityCount > 0;
  const hasLogic = input.scheduleRelationshipCount > 0;
  const scheduleHealthy = hasSchedule && hasLogic && input.scheduleQualityScore >= 90;
  const hasCostLoadedSchedule = input.costLoadedActivityPercent >= 95 && input.hasCostBaseline;
  const hasActivitySheetSpine =
    input.activitySheetRowCount > 0 && input.activitySheetWbsCount > 0 && input.controlAccountCount > 0;
  const hasBimBudgetBridge =
    input.bimModelCount > 0 &&
    input.hasRenderableIfcGeometry &&
    input.quantityLineCount > 0 &&
    input.apuCatalogCount > 0 &&
    input.quantityMappedLineCount > 0;
  const hasBimQuantityEvidence = input.bimModelCount > 0 || input.quantityLineCount > 0 || input.apuCatalogCount > 0;
  const hasControlledCostFunding =
    input.costSheetLineCount > 0 && input.fundingSourceCount > 0 && input.integratedMatrixRowCount > 0;
  const hasEvmOperations =
    hasCostLoadedSchedule &&
    input.latestProgressRecordCount > 0 &&
    input.latestCostRecordCount > 0 &&
    input.controlSnapshotCount > 0;
  const hasMakeReady = input.workPackageCount > 0 && input.blockingConstraintCount > 0;
  const hasDashboardGovernance = input.processFlowCompletion >= 75 && input.teamRoleCount >= 2;
  const hasEvidence = input.evidenceScore >= 80;

  const gaps: OpcGapItem[] = [
    {
      appEvidence: hasSchedule
        ? `${input.scheduleActivityCount} activities, ${input.scheduleRelationshipCount} relationship(s), ${input.scheduleQualityScore.toFixed(0)}% quality`
        : "No P6 XML/XER schedule loaded",
      controlReference: "Cronograma contractual CPM conectado con actividades de campo, riesgos y responsables.",
      id: "cpm-master-schedule",
      nextAction: "Cargar P6 XML/XER, validar DCMA/calidad y mantener la logica CPM como fuente contractual.",
      priority: "P1",
      status: statusFrom(scheduleHealthy, hasSchedule),
      title: "CPM master schedule and quality gate",
    },
    {
      appEvidence: `${input.costLoadedActivityPercent.toFixed(0)}% cost-loaded, ${input.costSheetLineCount} cost line(s), ${input.fundingSourceCount} fund(s)`,
      controlReference:
        "Costos, recursos y financiacion deben estar trazados a WBS/CBS/FBS para flujo de caja controlable.",
      id: "cost-resource-cashflow",
      nextAction: "Completar cost loading por actividad/WBS y conectar CBS/FBS para cash flow controlable.",
      priority: "P1",
      status: statusFrom(
        hasCostLoadedSchedule && hasControlledCostFunding,
        input.hasCostBaseline || input.costSheetLineCount > 0
      ),
      title: "Cost/resource loading and cash flow",
    },
    {
      appEvidence: `${input.activitySheetRowCount} activity row(s), ${input.activitySheetWbsCount} WBS row(s), ${input.controlAccountCount} control account(s)`,
      controlReference: "Activity Sheet, WBS y cuentas de control forman el registro maestro de ejecucion.",
      id: "activity-sheet-spine",
      nextAction: "Alinear Activity Sheet, WBS, control accounts, CBS y FBS antes de usar EVM o paquetes.",
      priority: "P1",
      status: statusFrom(hasActivitySheetSpine && hasControlledCostFunding, hasActivitySheetSpine),
      title: "WBS / Activity Sheet / control account spine",
    },
    {
      appEvidence: `${input.bimModelCount} model(s), ${input.hasRenderableIfcGeometry ? "geometry ready" : "geometry pending"}, ${input.quantityLineCount} quantity line(s), ${input.quantityMappedLineCount} mapped, ${input.apuCatalogCount} APU item(s)`,
      controlReference: "Cantidades IFC conectadas a APU Colombia, presupuesto y codigos de control del proyecto.",
      id: "bim-apu-budget",
      nextAction: "Mapear cantidades BIM a WBS/CBS/FBS/APU y aprobar unidades antes del presupuesto controlable.",
      priority: "P2",
      status: statusFrom(
        hasBimBudgetBridge && input.quantityMappedLineCount >= Math.max(1, Math.floor(input.quantityLineCount * 0.8)),
        hasBimQuantityEvidence
      ),
      title: "BIM -> APU -> controlled budget bridge",
    },
    {
      appEvidence: `${input.workPackageCount} package(s), ${input.workPackageReadyCount} ready, ${input.blockingConstraintCount} blocking constraint(s)`,
      controlReference:
        "El make-ready debe validar restricciones, compromisos semanales, ruta constructiva y liberacion por paquete.",
      id: "make-ready-awp",
      nextAction: "Convertir paquetes AWP en flujo make-ready: restricciones, weekly work plan, compromisos y PPC.",
      priority: "P2",
      status: statusFrom(hasMakeReady && input.workPackageReadyCount > 0, input.workPackageCount > 0),
      title: "AWP make-ready and weekly work control",
    },
    {
      appEvidence: `${input.latestProgressRecordCount} progress record(s), ${input.latestCostRecordCount} cost record(s), ${input.controlSnapshotCount} control snapshot(s)`,
      controlReference:
        "PV, EV y AC deben salir de linea base, avance fisico aprobado y costos certificados por periodo.",
      id: "evm-control",
      nextAction: "Capturar avance fisico aprobado y AC certificado por periodo para que PV/EV/AC sean auditables.",
      priority: "P1",
      status: statusFrom(
        hasEvmOperations,
        input.hasCostBaseline || input.latestProgressRecordCount > 0 || input.latestCostRecordCount > 0
      ),
      title: "EVM period control and S-curve evidence",
    },
    {
      appEvidence: `${input.processFlowCompletion.toFixed(0)}% process flow, ${input.teamRoleCount} role(s), ${input.evidenceScore.toFixed(0)}% evidence score`,
      controlReference:
        "Tableros por rol y evidencia de aprobacion deben mantener la trazabilidad ejecutiva y operativa.",
      id: "role-dashboard-governance",
      nextAction:
        "Configurar vistas por rol y evidencia de aprobacion para direccion, control, BIM/costos y planeacion.",
      priority: "P3",
      status: statusFrom(
        hasDashboardGovernance && hasEvidence,
        input.processFlowCompletion > 0 || input.teamRoleCount > 1
      ),
      title: "Role dashboards, governance and evidence",
    },
  ];

  const spine: OpcDataSpineStep[] = [
    {
      detail: "Identity, team, permissions and WBS are the first control anchor.",
      evidence: `${input.projectCode} / ${input.teamRoleCount} role(s)`,
      id: "project-wbs",
      label: "Project + WBS",
      status: statusFrom(input.teamRoleCount > 0, true),
    },
    {
      detail: "The contractual schedule must provide activities, dates and logic.",
      evidence: `${input.scheduleActivityCount} act / ${input.scheduleRelationshipCount} link(s)`,
      id: "p6-cpm",
      label: "P6 CPM",
      status: statusFrom(scheduleHealthy, hasSchedule),
    },
    {
      detail: "Activity Sheet turns P6 data into a control register.",
      evidence: `${input.activitySheetRowCount} row(s) / ${input.activitySheetWbsCount} WBS`,
      id: "activity-sheet",
      label: "Activity Sheet",
      status: statusFrom(hasActivitySheetSpine, input.activitySheetRowCount > 0),
    },
    {
      detail: "BIM quantities and APU pricing become physical budget items.",
      evidence: `${input.quantityLineCount} qty / ${input.apuCatalogCount} APU`,
      id: "bim-apu",
      label: "BIM + APU",
      status: statusFrom(hasBimBudgetBridge, input.quantityLineCount > 0 || input.apuCatalogCount > 0),
    },
    {
      detail: "CBS/FBS/cost lines are the budget and funding control ledger.",
      evidence: `${input.costSheetLineCount} cost / ${input.fundingSourceCount} fund`,
      id: "cbs-fbs",
      label: "CBS/FBS",
      status: statusFrom(hasControlledCostFunding, input.costSheetLineCount > 0 || input.fundingSourceCount > 0),
    },
    {
      detail: "PV, EV and AC must come from baseline, approved progress and certified costs.",
      evidence: `${input.controlSnapshotCount} snapshot(s)`,
      id: "evm",
      label: "EVM",
      status: statusFrom(hasEvmOperations, input.hasCostBaseline),
    },
    {
      detail: "AWP release should follow constraints, POC and workface readiness.",
      evidence: `${input.workPackageReadyCount}/${input.workPackageCount} ready`,
      id: "awp-release",
      label: "AWP release",
      status: statusFrom(hasMakeReady && input.workPackageReadyCount > 0, input.workPackageCount > 0),
    },
  ];

  const readinessScore = Math.round(gaps.reduce((total, gap) => total + scoreForStatus(gap.status), 0) / gaps.length);
  const criticalGapCount = gaps.filter((gap) => gap.priority === "P1" && gap.status !== "ready").length;
  const overallStatus: OpcGapStatus =
    readinessScore >= 75 && criticalGapCount === 0 ? "ready" : readinessScore >= 45 ? "partial" : "gap";
  const nextActions = gaps
    .filter((gap) => gap.status !== "ready")
    .sort((left, right) => priorityRank(left.priority) - priorityRank(right.priority))
    .slice(0, 3)
    .map((gap) => gap.nextAction);

  return {
    criticalGapCount,
    gaps,
    nextActions,
    overallStatus,
    readinessScore,
    spine,
  };
}
