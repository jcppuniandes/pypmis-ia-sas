import type React from "react";
import type {
  WorkspaceView,
  Project,
  User,
  RoleProfile,
  Dashboard,
  PilotReadiness,
  RFQBid,
  WorkPackageConstraint,
  ClaimEntitlementItem,
  ContractNotice,
  ClaimImpactAnalysis,
} from "../types";

export type AppShellCtx = {
  // core data
  dashboard: Dashboard;
  pilotReadiness: PilotReadiness | null;
  projects: Project[];
  users: User[];
  roles: RoleProfile[];

  // selection state
  activeView: WorkspaceView;
  setActiveView: (view: WorkspaceView) => void;
  selectedProjectId: string;
  setSelectedProjectId: (id: string) => void;
  selectedUserId: string;
  setSelectedUserId: (id: string) => void;
  selectedBpRecordNo: string;
  setSelectedBpRecordNo: (no: string) => void;

  // upload/action state
  uploading: boolean;
  routingAction: string | null;
  captureAction: string | null;
  uploadMessage: string | null;
  uploadError: string | null;

  // computed values
  project: Dashboard["project"];
  kpi: Dashboard["project_kpi"];
  redAlerts: number;
  amberAlerts: number;
  healthLabel: string;
  healthClass: string;
  workflowInstance: Dashboard["workflow_instance"];
  workflowStatus: string;
  workflowActionButtons: Array<{ action: string; label: string; tone: string }>;
  workflowStages: Array<{ name: string; detail: string; owner: string; status: string; tone: string }>;
  bpRecords: Array<{
    record: string;
    process: string;
    title: string;
    step: string;
    ballInCourt: string;
    status: string;
    tone: string;
  }>;
  selectedBpRecord: {
    record: string;
    process: string;
    title: string;
    step: string;
    ballInCourt: string;
    status: string;
    tone: string;
  } | null;
  primaryNavigatorItems: Array<{ key: WorkspaceView; label: string; count: string | number }>;
  secondaryNavigatorItems: Array<{ key: WorkspaceView; label: string; count: string | number }>;
  chartData: Array<Record<string, number | string>>;
  accountLabel: (accountId: number) => string;
  packageLabel: (packageId: number) => string;
  rfqPackageLabel: (packageId: number) => string;
  bidsByRfq: Record<number, RFQBid[]>;
  constraintsByPackage: Record<number, WorkPackageConstraint[]>;
  entitlementByClaim: Record<number, ClaimEntitlementItem[]>;
  noticesByClaim: Record<number, ContractNotice[]>;
  impactByClaim: Record<number, ClaimImpactAnalysis[]>;
  mappingSummary: Dashboard["control_account_mapping_summary"];
  costManager: Dashboard["cost_manager_summary"];
  controlGateBlocked: boolean;
  progressDisabled: boolean;
  costDisabled: boolean;
  canUploadSchedule: boolean;
  canConfigure: boolean;
  canManageContracts: boolean;
  contractCostDisabled: boolean;
  warehouseDisabled: boolean;
  canManageClaims: boolean;
  canManageDocuments: boolean;
  canCreateChange: boolean;
  canManageAwp: boolean;
  linkedEntityOptions: Array<{ type: string; id: number; label: string }>;
  canRouteCurrentWorkflow: boolean;
  canApproveControlBaseline: boolean;
  roadmapStatus: Array<{ phase: string; title: string; score: number; state: string; detail: string }>;
  overallRoadmapScore: number;

  // draft state
  progressDraft: {
    control_account_id: string;
    physical_percent: string;
    quantity_installed: string;
    labor_hours: string;
    reported_on: string;
    evidence_ref: string;
  };
  setProgressDraft: React.Dispatch<React.SetStateAction<AppShellCtx["progressDraft"]>>;
  costDraft: {
    control_account_id: string;
    source: string;
    amount: string;
    incurred_on: string;
    description: string;
  };
  setCostDraft: React.Dispatch<React.SetStateAction<AppShellCtx["costDraft"]>>;
  fundingDraft: { code: string; name: string; amount: string; status: string };
  setFundingDraft: React.Dispatch<React.SetStateAction<AppShellCtx["fundingDraft"]>>;
  cashFlowDraft: {
    period_label: string;
    planned_inflow: string;
    planned_outflow: string;
    actual_inflow: string;
    actual_outflow: string;
    forecast_outflow: string;
  };
  setCashFlowDraft: React.Dispatch<React.SetStateAction<AppShellCtx["cashFlowDraft"]>>;
  projectDraft: {
    code: string;
    name: string;
    phase: string;
    currency: string;
    start_date: string;
    finish_date: string;
  };
  setProjectDraft: React.Dispatch<React.SetStateAction<AppShellCtx["projectDraft"]>>;
  userDraft: { email: string; full_name: string; title: string };
  setUserDraft: React.Dispatch<React.SetStateAction<AppShellCtx["userDraft"]>>;
  teamDraft: { user_id: string; role: string };
  setTeamDraft: React.Dispatch<React.SetStateAction<AppShellCtx["teamDraft"]>>;
  processDraft: {
    code: string;
    name: string;
    category: string;
    description: string;
    form_schema: string;
    steps: string;
    transitions: string;
  };
  setProcessDraft: React.Dispatch<React.SetStateAction<AppShellCtx["processDraft"]>>;
  changeDraft: {
    control_account_id: string;
    title: string;
    deviation: string;
    cost_impact: string;
    schedule_impact_days: string;
  };
  setChangeDraft: React.Dispatch<React.SetStateAction<AppShellCtx["changeDraft"]>>;
  contractDraft: {
    control_account_id: string;
    code: string;
    title: string;
    counterparty: string;
    contract_type: string;
    value: string;
    status: string;
  };
  setContractDraft: React.Dispatch<React.SetStateAction<AppShellCtx["contractDraft"]>>;
  purchaseOrderDraft: {
    control_account_id: string;
    contract_id: string;
    po_number: string;
    description: string;
    vendor: string;
    committed_amount: string;
    status: string;
    issued_on: string;
  };
  setPurchaseOrderDraft: React.Dispatch<React.SetStateAction<AppShellCtx["purchaseOrderDraft"]>>;
  paymentCertificateDraft: {
    control_account_id: string;
    contract_id: string;
    purchase_order_id: string;
    certificate_no: string;
    period_label: string;
    certified_amount: string;
    retained_amount: string;
    status: string;
    certified_on: string;
  };
  setPaymentCertificateDraft: React.Dispatch<React.SetStateAction<AppShellCtx["paymentCertificateDraft"]>>;
  warehouseReceiptDraft: {
    control_account_id: string;
    contract_id: string;
    purchase_order_id: string;
    receipt_no: string;
    description: string;
    received_quantity: string;
    unit_cost: string;
    received_value: string;
    status: string;
    received_on: string;
  };
  setWarehouseReceiptDraft: React.Dispatch<React.SetStateAction<AppShellCtx["warehouseReceiptDraft"]>>;
  rfqDraft: {
    control_account_id: string;
    package_no: string;
    title: string;
    scope_summary: string;
    procurement_method: string;
    status: string;
    budget_amount: string;
    issue_date: string;
    due_date: string;
  };
  setRfqDraft: React.Dispatch<React.SetStateAction<AppShellCtx["rfqDraft"]>>;
  rfqBidDraft: {
    rfq_package_id: string;
    bidder_name: string;
    bid_amount: string;
    technical_score: string;
    commercial_score: string;
    schedule_score: string;
    risk_score: string;
    status: string;
    submitted_on: string;
    notes: string;
  };
  setRfqBidDraft: React.Dispatch<React.SetStateAction<AppShellCtx["rfqBidDraft"]>>;
  communicationDraft: {
    contract_id: string;
    communication_type: string;
    subject: string;
    reference: string;
    sent_on: string;
    status: string;
  };
  setCommunicationDraft: React.Dispatch<React.SetStateAction<AppShellCtx["communicationDraft"]>>;
  noticeDraft: {
    contract_id: string;
    claim_id: string;
    change_request_id: string;
    notice_type: string;
    subject: string;
    reference: string;
    event_date: string;
    due_date: string;
    notice_date: string;
    status: string;
  };
  setNoticeDraft: React.Dispatch<React.SetStateAction<AppShellCtx["noticeDraft"]>>;
  claimImpactDraft: {
    claim_id: string;
    method: string;
    impacted_activity: string;
    cause: string;
    effect: string;
    schedule_impact_days: string;
    cost_impact: string;
    productivity_loss_percent: string;
    evidence_ref: string;
    confidence_score: string;
    status: string;
  };
  setClaimImpactDraft: React.Dispatch<React.SetStateAction<AppShellCtx["claimImpactDraft"]>>;
  documentDraft: {
    document_number: string;
    revision: string;
    revision_date: string;
    linked_entity_type: string;
    linked_entity_id: string;
    title: string;
    doc_type: string;
    discipline: string;
    organization: string;
    status: string;
    review_status: string;
    confidentiality: string;
    file_name: string;
    uri: string;
  };
  setDocumentDraft: React.Dispatch<React.SetStateAction<AppShellCtx["documentDraft"]>>;
  attachmentDraft: { document_id: string; file: File | null };
  setAttachmentDraft: React.Dispatch<React.SetStateAction<AppShellCtx["attachmentDraft"]>>;
  transmittalDraft: {
    transmittal_no: string;
    subject: string;
    purpose: string;
    recipient_org: string;
    recipient_contact: string;
    due_date: string;
    document_id: string;
  };
  setTransmittalDraft: React.Dispatch<React.SetStateAction<AppShellCtx["transmittalDraft"]>>;
  mailDraft: {
    mail_no: string;
    mail_type: string;
    subject: string;
    to_role: string;
    due_date: string;
    document_id: string;
    body: string;
  };
  setMailDraft: React.Dispatch<React.SetStateAction<AppShellCtx["mailDraft"]>>;
  reviewDraft: {
    document_id: string;
    reviewer_role: string;
    review_status: string;
    due_date: string;
    comments: string;
  };
  setReviewDraft: React.Dispatch<React.SetStateAction<AppShellCtx["reviewDraft"]>>;
  awpDraft: {
    control_account_id: string;
    parent_id: string;
    package_type: string;
    code: string;
    title: string;
    discipline: string;
    sequence_no: string;
    path_of_construction: string;
    owner_role: string;
    readiness_status: string;
    planned_start: string;
    planned_finish: string;
    progress_percent: string;
  };
  setAwpDraft: React.Dispatch<React.SetStateAction<AppShellCtx["awpDraft"]>>;
  constraintDraft: {
    work_package_id: string;
    constraint_type: string;
    description: string;
    owner_role: string;
    required_by: string;
    status: string;
    blocking: boolean;
  };
  setConstraintDraft: React.Dispatch<React.SetStateAction<AppShellCtx["constraintDraft"]>>;
  controlPlanDraft: {
    execution_strategy: string;
    control_strategy: string;
    progress_measurement_rule: string;
    cost_measurement_rule: string;
    change_management_rule: string;
    risk_management_rule: string;
    procurement_strategy: string;
    document_control_rule: string;
    reporting_cadence: string;
    status: string;
  };
  setControlPlanDraft: React.Dispatch<React.SetStateAction<AppShellCtx["controlPlanDraft"]>>;

  // event handlers
  load: () => Promise<void>;
  handleScheduleUpload: (event: React.ChangeEvent<HTMLInputElement>) => Promise<void>;
  handleWorkflowAction: (action: string) => Promise<void>;
  handleProgressSubmit: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  handleCostSubmit: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  handleFundingSubmit: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  handleCashFlowSubmit: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  handleProjectCreate: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  handleUserCreate: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  handleTeamAssign: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  handleProcessTemplateCreate: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  handleControlPlanSubmit: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  handleChangeSubmit: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  handleContractSubmit: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  handlePurchaseOrderSubmit: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  handlePaymentCertificateSubmit: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  handleWarehouseReceiptSubmit: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  handleRfqSubmit: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  handleRfqBidSubmit: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  handleCommunicationSubmit: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  handleNoticeSubmit: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  handleClaimImpactSubmit: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  handleDocumentSubmit: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  handleAttachmentSubmit: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  handleTransmittalSubmit: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  handleProjectMailSubmit: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  handleDocumentReviewSubmit: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  handleAwpSubmit: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  handleConstraintSubmit: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  handleConstraintClose: (constraint: import("../types").WorkPackageConstraint) => Promise<void>;
  handleControlBaselineApprove: () => Promise<void>;
  handleAttachmentDownload: (attachment: import("../types").DocumentAttachment) => Promise<void>;
};
