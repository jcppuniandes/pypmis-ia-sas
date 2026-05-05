import React from "react";
import ReactDOM from "react-dom/client";
import { Activity, ArrowRight, Bot, BriefcaseBusiness, Building2, CalendarClock, ClipboardCheck, FilePlus2, FileText, Gauge, GitBranch, RefreshCw, Send, Settings, ShieldCheck, Upload, UserPlus, Users } from "lucide-react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import "./styles.css";

type WorkspaceView =
  | "business-processes"
  | "control-dashboard"
  | "schedule"
  | "progress"
  | "cost"
  | "awp"
  | "changes"
  | "claims"
  | "contracts"
  | "documents"
  | "roadmap"
  | "bp-entry-forms"
  | "admin";

type Project = {
  id: number;
  code: string;
  name: string;
  phase: string;
  currency: string;
  start_date: string | null;
  finish_date: string | null;
};

type User = {
  id: number;
  email: string;
  full_name: string;
  title: string;
  status: string;
};

type AuthSession = {
  access_token: string;
  token_type: string;
  expires_in: number;
  tenant_id: number;
  user: User;
};

type ProjectMembership = {
  id: number;
  project_id: number;
  user_id: number;
  role: string;
  can_capture_progress: boolean;
  can_capture_cost: boolean;
  can_approve_workflow: boolean;
  can_manage_contract: boolean;
  can_configure: boolean;
};

type ProjectTeamMember = {
  user: User;
  membership: ProjectMembership;
};

type RoleProfile = {
  role: string;
  description: string;
  can_capture_progress: boolean;
  can_capture_cost: boolean;
  can_approve_workflow: boolean;
  can_manage_contract: boolean;
  can_configure: boolean;
};

type KPI = {
  control_account_id: number | null;
  pv: number;
  ev: number;
  ac: number;
  spi: number;
  cpi: number;
  sv: number;
  cv: number;
  bac: number;
  eac: number;
  etc: number;
  vac: number;
};

type ControlSnapshot = {
  id: number;
  control_account_id: number | null;
  period_label: string;
  data_date: string | null;
  pv: number;
  ev: number;
  ac: number;
  spi: number;
  cpi: number;
  sv: number;
  cv: number;
  bac: number;
  eac: number;
  etc: number;
  vac: number;
  productivity_index: number | null;
  created_at: string;
};

type ForecastScenario = {
  id: number;
  period_label: string;
  name: string;
  method: string;
  cpi_factor: number;
  spi_factor: number;
  eac: number;
  etc: number;
  vac: number;
  completion_risk: string;
  summary: string;
  created_at: string;
};

type ProductivitySummary = {
  total_quantity: number;
  total_labor_hours: number;
  productivity_rate: number;
  productivity_index: number;
  low_productivity_accounts: number;
};

type Alert = {
  id: number;
  control_account_id: number | null;
  severity: "green" | "amber" | "red";
  rule: string;
  message: string;
  recommendation: string;
  status: string;
};

type ScheduleImport = {
  id: number;
  source: string;
  file_name: string;
  status: string;
  data_date: string | null;
  baseline_name: string;
  quality_score: number;
  validation_summary: string;
  imported_at: string;
};

type ScheduleFinding = {
  id: number;
  schedule_import_id: number;
  check_code: string;
  severity: string;
  message: string;
  item_count: number;
  weight: number;
};

type BaselineVersion = {
  id: number;
  schedule_import_id: number;
  version_no: number;
  name: string;
  status: string;
  data_date: string | null;
  quality_score: number;
  created_at: string;
};

type ControlPeriod = {
  id: number;
  period_label: string;
  data_date: string | null;
  status: string;
  created_at: string;
};

type WorkflowInstance = {
  id: number;
  process_code: string;
  process_name: string;
  record_no: string;
  title: string;
  status: string;
  current_step: string;
  ball_in_court: string;
  trigger_entity_type: string;
  trigger_entity_id: number;
  created_at: string;
  updated_at: string;
};

type WorkflowStep = {
  id: number;
  process_instance_id: number;
  step_order: number;
  name: string;
  detail: string;
  owner_role: string;
  status: string;
  tone: string;
};

type ProcessStepTemplate = {
  id: number | null;
  step_order: number;
  name: string;
  detail: string;
  owner_role: string;
  status: string;
  tone: string;
};

type ProcessTransitionTemplate = {
  id: number | null;
  action: string;
  label: string;
  from_step: string;
  to_step: string;
  process_status: string;
  ball_in_court: string;
  from_status: string;
  from_tone: string;
  to_status: string;
  to_tone: string;
  requires_approval: boolean;
  permission_key: string;
};

type ProcessTemplate = {
  id: number | null;
  code: string;
  name: string;
  category: string;
  description: string;
  version_no: number;
  form_schema: string[];
  workflow_steps: string[];
  roles: string[];
  status: string;
  step_templates: ProcessStepTemplate[];
  transitions: ProcessTransitionTemplate[];
};

type AuditLog = {
  id: number;
  actor: string;
  action: string;
  entity_type: string;
  entity_id: number | null;
  payload: string;
  created_at: string;
};

type ControlAccount = {
  id: number;
  code: string;
  name: string;
  responsible: string;
  discipline: string;
};

type ControlAccountMapping = {
  id: number;
  schedule_import_id: number;
  schedule_activity_map_id: number;
  activity_id: number | null;
  control_account_id: number | null;
  wbs_code: string;
  wbs_name: string;
  cbs_code: string;
  mapping_rule: string;
  planned_cost: number;
  planned_value: number;
  planned_percent: number;
  status: string;
  review_note: string;
};

type ControlAccountMappingSummary = {
  total_schedule_activities: number;
  mapped_activities: number;
  unmapped_activities: number;
  control_account_count: number;
  cost_loaded_activities: number;
  total_bac: number;
  total_planned_value: number;
  mapping_score: number;
  cost_loading_score: number;
  baseline_status: string;
};

type DataQualityGate = {
  name: string;
  status: string;
  score: number;
  finding: string;
  owner_role: string;
};

type ProgressRecord = {
  id: number;
  control_account_id: number;
  physical_percent: number;
  quantity_installed: number;
  labor_hours: number;
  reported_on: string;
  evidence_ref: string;
};

type CostRecord = {
  id: number;
  control_account_id: number;
  source: string;
  amount: number;
  incurred_on: string;
  description: string;
};

type FlowStep = {
  name: string;
  purpose: string;
  state: string;
};

type WorkItem = {
  id: number;
  control_account_id: number | null;
  title: string;
  status: string;
};

type ChangeItem = WorkItem & {
  deviation: string;
  cost_impact: number;
  schedule_impact_days: number;
};

type ClaimItem = WorkItem & {
  causality: string;
  impact: string;
  evidence_summary: string;
};

type ClaimEntitlementItem = {
  id: number;
  claim_id: number;
  practice_source: string;
  category: string;
  element: string;
  requirement: string;
  assessment: string;
  evidence_ref: string;
  status: string;
  weight: number;
  score: number;
  sequence_no: number;
};

type ClaimEntitlementSummary = {
  total_items: number;
  satisfied_items: number;
  partial_items: number;
  gap_items: number;
  cumulative_items: number;
  cumulative_gap_items: number;
  entitlement_score: number;
};

type ContractNotice = {
  id: number;
  contract_id: number | null;
  claim_id: number | null;
  change_request_id: number | null;
  notice_type: string;
  subject: string;
  reference: string;
  event_date: string | null;
  notice_date: string | null;
  due_date: string | null;
  status: string;
  days_late: number;
  compliance_status: string;
  created_at: string;
};

type ClaimImpactAnalysis = {
  id: number;
  claim_id: number;
  method: string;
  impacted_activity: string;
  cause: string;
  effect: string;
  schedule_impact_days: number;
  cost_impact: number;
  productivity_loss_percent: number;
  evidence_ref: string;
  confidence_score: number;
  status: string;
  created_at: string;
};

type ClaimsForensicSummary = {
  total_claims: number;
  notice_count: number;
  compliant_notices: number;
  late_notices: number;
  impact_analyses: number;
  quantified_claims: number;
  total_claimed_cost: number;
  total_schedule_impact_days: number;
  forensic_readiness_score: number;
};

type Contract = {
  id: number;
  code: string;
  title: string;
  counterparty: string;
  contract_type: string;
  value: number;
  status: string;
};

type ContractCommunication = {
  id: number;
  contract_id: number | null;
  communication_type: string;
  subject: string;
  reference: string;
  sent_on: string;
  status: string;
};

type DocumentItem = {
  id: number;
  linked_entity_type: string;
  linked_entity_id: number;
  title: string;
  doc_type: string;
  uri: string;
};

type WorkPackage = {
  id: number;
  control_account_id: number | null;
  parent_id: number | null;
  package_type: string;
  code: string;
  title: string;
  discipline: string;
  sequence_no: number;
  path_of_construction: string;
  owner_role: string;
  readiness_status: string;
  planned_start: string | null;
  planned_finish: string | null;
  progress_percent: number;
};

type WorkPackageConstraint = {
  id: number;
  work_package_id: number;
  constraint_type: string;
  description: string;
  owner_role: string;
  required_by: string | null;
  status: string;
  blocking: boolean;
};

type AWPReadinessSummary = {
  total_packages: number;
  cwp_count: number;
  iwp_count: number;
  ready_for_release: number;
  blocked_packages: number;
  open_constraints: number;
  blocking_constraints: number;
  readiness_score: number;
};

type Dashboard = {
  project: Project;
  current_user: User;
  current_membership: ProjectMembership;
  project_team: ProjectTeamMember[];
  schedule_import: ScheduleImport | null;
  schedule_activity_count: number;
  schedule_relationship_count: number;
  schedule_findings: ScheduleFinding[];
  baseline_versions: BaselineVersion[];
  control_periods: ControlPeriod[];
  workflow_instance: WorkflowInstance | null;
  workflow_steps: WorkflowStep[];
  business_processes: WorkflowInstance[];
  process_templates: ProcessTemplate[];
  audit_logs: AuditLog[];
  data_quality_gates: DataQualityGate[];
  flow: FlowStep[];
  loop: { step: string; description: string }[];
  control_accounts: ControlAccount[];
  control_account_mappings: ControlAccountMapping[];
  control_account_mapping_summary: ControlAccountMappingSummary;
  latest_progress_records: ProgressRecord[];
  latest_cost_records: CostRecord[];
  project_kpi: KPI;
  account_kpis: KPI[];
  control_snapshots: ControlSnapshot[];
  forecast_scenarios: ForecastScenario[];
  productivity_summary: ProductivitySummary;
  alerts: Alert[];
  changes: ChangeItem[];
  claims: ClaimItem[];
  claim_entitlement_items: ClaimEntitlementItem[];
  claim_entitlement_summary: ClaimEntitlementSummary;
  contract_notices: ContractNotice[];
  claim_impact_analyses: ClaimImpactAnalysis[];
  claims_forensic_summary: ClaimsForensicSummary;
  contracts: Contract[];
  communications: ContractCommunication[];
  documents: DocumentItem[];
  work_packages: WorkPackage[];
  work_package_constraints: WorkPackageConstraint[];
  awp_summary: AWPReadinessSummary;
  ai_brief: string;
};

const apiUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const demoPassword = import.meta.env.VITE_DEMO_PASSWORD ?? "demo123";
const defaultLoginEmail = import.meta.env.VITE_DEMO_EMAIL ?? "ana.control@demo.local";

function authHeaders(token: string, includeJson = false) {
  const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (includeJson) {
    headers["Content-Type"] = "application/json";
  }
  return headers;
}

function currency(value: number, code: string) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: code, maximumFractionDigits: 0 }).format(value);
}

function StatusLight({ value }: { value: number }) {
  const className = value < 0.9 ? "light red" : value < 1 ? "light amber" : "light green";
  return <span className={className} />;
}

function sourceLabel(source?: string) {
  const labels: Record<string, string> = {
    p6_xer: "Schedule XER",
    p6_xml: "Schedule XML",
    ms_project_xml: "Schedule XML",
    ms_project_mpp: "Schedule file"
  };
  return source ? labels[source] ?? source : "Not imported";
}

function statusLabel(status?: string) {
  if (!status) {
    return "";
  }
  return status.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function neutralScheduleText(value: string) {
  return value
    .replace(/Schedule file received from Primavera P6 or MS Project\./gi, "Source schedule file received.")
    .replace(/Primavera P6 or MS Project/gi, "source schedule")
    .replace(/MSPROJECT_WORKFLOW_TRIGGER/gi, "Schedule Baseline Intake")
    .replace(/SCHEDULE_WORKFLOW_TRIGGER/gi, "Schedule Baseline Intake")
    .replace(/MSPROJECT/gi, "SCHEDULE")
    .replace(/MS Project/gi, "schedule")
    .replace(/Imported_Schedule_/gi, "Imported Schedule ")
    .replace(/Imported Schedule_/gi, "Imported Schedule ")
    .replace(/SCHEDULE_XML_IMPORT/gi, "Imported Schedule")
    .replace(/P6\/MSP/gi, "source schedule")
    .replace(/\bMSP\b/gi, "schedule")
    .replace(/Imported\W+Schedule[_\s-]*/gi, "Imported Schedule ")
    .replace(/CONTROL\W+BASELINE[_\s-]*/gi, "Control Baseline ");
}

function listFromInput(value: string) {
  return value
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function processStepsFromInput(value: string) {
  return value
    .split("\n")
    .map((row) => row.trim())
    .filter(Boolean)
    .map((row, index) => {
      const [name = `Step ${index + 1}`, owner_role = "Project Controls", detail = "Workflow step."] = row.split("|").map((item) => item.trim());
      return {
        name,
        owner_role,
        detail,
        status: index === 0 ? "Active" : "Queued",
        tone: index === 0 ? "active" : "queued"
      };
    });
}

function processTransitionsFromInput(value: string) {
  return value
    .split("\n")
    .map((row) => row.trim())
    .filter(Boolean)
    .map((row) => {
      const [action = "", from_step = "", to_step = "", ball_in_court = "", process_status = "in_review"] = row.split("|").map((item) => item.trim());
      return {
        action: action.toLowerCase().replace(/\s+/g, "_"),
        label: statusLabel(action),
        from_step,
        to_step,
        process_status,
        ball_in_court,
        from_status: "Complete",
        from_tone: "complete",
        to_status: to_step.toLowerCase() === "closed" ? "Complete" : "Active",
        to_tone: to_step.toLowerCase() === "closed" ? "complete" : "active",
        requires_approval: process_status === "approved",
        permission_key: process_status === "approved" ? "can_approve_workflow" : ""
      };
    })
    .filter((transition) => transition.action && transition.from_step && transition.to_step);
}

const defaultControlDate = new Date().toISOString().slice(0, 10);

function App() {
  const [dashboard, setDashboard] = React.useState<Dashboard | null>(null);
  const [projects, setProjects] = React.useState<Project[]>([]);
  const [users, setUsers] = React.useState<User[]>([]);
  const [roles, setRoles] = React.useState<RoleProfile[]>([]);
  const [selectedProjectId, setSelectedProjectId] = React.useState<string>("");
  const [selectedUserId, setSelectedUserId] = React.useState<string>("1");
  const [authToken, setAuthToken] = React.useState<string>(() => window.localStorage.getItem("pypmis_access_token") ?? "");
  const [authUser, setAuthUser] = React.useState<User | null>(null);
  const [activeView, setActiveView] = React.useState<WorkspaceView>("business-processes");
  const [selectedBpRecordNo, setSelectedBpRecordNo] = React.useState<string>("");
  const [loading, setLoading] = React.useState(true);
  const [uploading, setUploading] = React.useState(false);
  const [routingAction, setRoutingAction] = React.useState<string | null>(null);
  const [captureAction, setCaptureAction] = React.useState<string | null>(null);
  const [uploadMessage, setUploadMessage] = React.useState<string | null>(null);
  const [uploadError, setUploadError] = React.useState<string | null>(null);
  const [authError, setAuthError] = React.useState<string | null>(null);
  const [progressDraft, setProgressDraft] = React.useState({
    control_account_id: "",
    physical_percent: "",
    quantity_installed: "",
    labor_hours: "",
    reported_on: defaultControlDate,
    evidence_ref: ""
  });
  const [costDraft, setCostDraft] = React.useState({
    control_account_id: "",
    source: "invoice",
    amount: "",
    incurred_on: defaultControlDate,
    description: ""
  });
  const [projectDraft, setProjectDraft] = React.useState({
    code: "",
    name: "",
    phase: "Planning",
    currency: "USD",
    start_date: "",
    finish_date: ""
  });
  const [userDraft, setUserDraft] = React.useState({
    email: "",
    full_name: "",
    title: ""
  });
  const [teamDraft, setTeamDraft] = React.useState({
    user_id: "",
    role: "Planner"
  });
  const [processDraft, setProcessDraft] = React.useState({
    code: "",
    name: "",
    category: "Project Controls",
    description: "",
    form_schema: "Business need, Control account, Impact, Evidence, Recommendation",
    steps: "Creation | Originator | Record is created and validated.\nImpact Review | Project Controls | Schedule, cost and contractual impact are analyzed.\nApproval | Control Manager | Governance decision is recorded.\nAction | Execution Lead | Approved decision is converted into execution action.",
    transitions: "route_to_approval | Impact Review | Approval | Control Manager | in_review\napprove_record | Approval | Action | Execution Lead | approved"
  });
  const [changeDraft, setChangeDraft] = React.useState({
    control_account_id: "",
    title: "",
    deviation: "",
    cost_impact: "",
    schedule_impact_days: ""
  });
  const [contractDraft, setContractDraft] = React.useState({
    code: "",
    title: "",
    counterparty: "",
    contract_type: "Services",
    value: "",
    status: "active"
  });
  const [communicationDraft, setCommunicationDraft] = React.useState({
    contract_id: "",
    communication_type: "notice",
    subject: "",
    reference: "",
    sent_on: defaultControlDate,
    status: "issued"
  });
  const [noticeDraft, setNoticeDraft] = React.useState({
    contract_id: "",
    claim_id: "",
    change_request_id: "",
    notice_type: "contractual_notice",
    subject: "",
    reference: "",
    event_date: defaultControlDate,
    due_date: defaultControlDate,
    notice_date: defaultControlDate,
    status: "issued"
  });
  const [claimImpactDraft, setClaimImpactDraft] = React.useState({
    claim_id: "",
    method: "Time Impact Analysis",
    impacted_activity: "",
    cause: "",
    effect: "",
    schedule_impact_days: "",
    cost_impact: "",
    productivity_loss_percent: "",
    evidence_ref: "",
    confidence_score: "0.65",
    status: "draft"
  });
  const [documentDraft, setDocumentDraft] = React.useState({
    linked_entity_type: "ControlAccount",
    linked_entity_id: "",
    title: "",
    doc_type: "Field Evidence",
    uri: ""
  });
  const [awpDraft, setAwpDraft] = React.useState({
    control_account_id: "",
    parent_id: "",
    package_type: "IWP",
    code: "",
    title: "",
    discipline: "",
    sequence_no: "",
    path_of_construction: "",
    owner_role: "Workface Planner",
    readiness_status: "constraint_review",
    planned_start: "",
    planned_finish: "",
    progress_percent: ""
  });
  const [constraintDraft, setConstraintDraft] = React.useState({
    work_package_id: "",
    constraint_type: "Material",
    description: "",
    owner_role: "Workface Planner",
    required_by: defaultControlDate,
    status: "open",
    blocking: true
  });

  const login = React.useCallback(async (email = defaultLoginEmail) => {
    const response = await fetch(`${apiUrl}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password: demoPassword, tenant_slug: "demo-energy" })
    });
    if (!response.ok) {
      throw new Error("Authentication failed");
    }
    const session = (await response.json()) as AuthSession;
    window.localStorage.setItem("pypmis_access_token", session.access_token);
    setAuthToken(session.access_token);
    setAuthUser(session.user);
    setSelectedUserId(String(session.user.id));
    setAuthError(null);
    return session;
  }, []);

  const apiHeaders = React.useCallback((includeJson = false, tokenOverride?: string) => {
    return authHeaders(tokenOverride ?? authToken, includeJson);
  }, [authToken]);

  const load = React.useCallback(async () => {
    setLoading(true);
    let sessionToken = authToken;
    if (!sessionToken) {
      sessionToken = (await login()).access_token;
    }

    let usersResponse = await fetch(`${apiUrl}/api/v1/users`, { headers: authHeaders(sessionToken) });
    if (usersResponse.status === 401) {
      sessionToken = (await login()).access_token;
      usersResponse = await fetch(`${apiUrl}/api/v1/users`, { headers: authHeaders(sessionToken) });
    }
    const availableUsers = (await usersResponse.json()) as User[];
    const selectedUserIsAvailable = availableUsers.some((user) => String(user.id) === selectedUserId);
    const fallbackUserId = selectedUserId || "1";
    const userId = selectedUserIsAvailable ? selectedUserId : String(availableUsers[0]?.id ?? fallbackUserId);
    const selectedUser = availableUsers.find((user) => String(user.id) === userId);
    if (selectedUser && authUser && authUser.id !== selectedUser.id) {
      sessionToken = (await login(selectedUser.email)).access_token;
    }
    const headers = authHeaders(sessionToken);
    const [projectsResponse, rolesResponse] = await Promise.all([
      fetch(`${apiUrl}/api/v1/projects`, { headers }),
      fetch(`${apiUrl}/api/v1/roles`, { headers })
    ]);
    const availableProjects = (await projectsResponse.json()) as Project[];
    const availableRoles = (await rolesResponse.json()) as RoleProfile[];
    setUsers(availableUsers);
    setRoles(availableRoles);
    if (userId !== selectedUserId) {
      setSelectedUserId(userId);
    }
    setProjects(availableProjects);
    if (!availableProjects.length) {
      setDashboard(null);
      setLoading(false);
      return;
    }
    const selectedProjectIsAllowed = availableProjects.some((project) => String(project.id) === selectedProjectId);
    const projectId = selectedProjectIsAllowed ? selectedProjectId : String(availableProjects[0]?.id ?? 1);
    if (projectId !== selectedProjectId) {
      setSelectedProjectId(projectId);
    }
    const dashboardResponse = await fetch(`${apiUrl}/api/v1/projects/${projectId}/dashboard`, { headers });
    setDashboard((await dashboardResponse.json()) as Dashboard);
    setLoading(false);
  }, [authToken, authUser, login, selectedProjectId, selectedUserId]);

  React.useEffect(() => {
    load().catch((error) => {
      setAuthError(error instanceof Error ? error.message : "Authentication failed");
      setLoading(false);
    });
  }, [load]);

  React.useEffect(() => {
    if (!dashboard?.control_accounts.length) {
      return;
    }
    const firstAccountId = String(dashboard.control_accounts[0].id);
    const controlDate = dashboard.schedule_import?.data_date ?? defaultControlDate;
    const accountIds = new Set(dashboard.control_accounts.map((account) => String(account.id)));
    setProgressDraft((current) => accountIds.has(current.control_account_id) ? current : { ...current, control_account_id: firstAccountId, reported_on: controlDate });
    setCostDraft((current) => accountIds.has(current.control_account_id) ? current : { ...current, control_account_id: firstAccountId, incurred_on: controlDate });
    setChangeDraft((current) => accountIds.has(current.control_account_id) ? current : { ...current, control_account_id: firstAccountId });
    setAwpDraft((current) => {
      const packageIds = new Set(dashboard.work_packages.map((item) => String(item.id)));
      return {
        ...current,
        control_account_id: accountIds.has(current.control_account_id) ? current.control_account_id : firstAccountId,
        parent_id: !current.parent_id || packageIds.has(current.parent_id) ? current.parent_id : ""
      };
    });
    setConstraintDraft((current) => {
      const packageIds = new Set(dashboard.work_packages.map((item) => String(item.id)));
      return {
        ...current,
        work_package_id: packageIds.has(current.work_package_id) ? current.work_package_id : String(dashboard.work_packages[0]?.id ?? "")
      };
    });
    setDocumentDraft((current) => {
      const linkedValueIsAvailable = current.linked_entity_type !== "ControlAccount" || accountIds.has(current.linked_entity_id);
      return linkedValueIsAvailable ? current : { ...current, linked_entity_type: "ControlAccount", linked_entity_id: firstAccountId };
    });
  }, [dashboard]);

  React.useEffect(() => {
    setTeamDraft((current) => ({
      user_id: current.user_id || String(users[0]?.id ?? ""),
      role: roles.some((role) => role.role === current.role) ? current.role : roles[0]?.role ?? "Planner"
    }));
  }, [roles, users]);

  React.useEffect(() => {
    setCommunicationDraft((current) => ({
      ...current,
      contract_id: current.contract_id || String(dashboard?.contracts[0]?.id ?? "")
    }));
    setNoticeDraft((current) => ({
      ...current,
      contract_id: current.contract_id || String(dashboard?.contracts[0]?.id ?? ""),
      claim_id: current.claim_id || String(dashboard?.claims[0]?.id ?? "")
    }));
    setClaimImpactDraft((current) => ({
      ...current,
      claim_id: current.claim_id || String(dashboard?.claims[0]?.id ?? "")
    }));
  }, [dashboard?.contracts]);

  async function handleScheduleUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0];
    if (!file || !dashboard) {
      return;
    }

    setUploading(true);
    setUploadMessage(null);
    setUploadError(null);

    try {
      const formData = new FormData();
      formData.append("file", file);
      const response = await fetch(`${apiUrl}/api/v1/projects/${dashboard.project.id}/schedule-imports`, {
        method: "POST",
        headers: apiHeaders(),
        body: formData
      });

      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || "Schedule import failed");
      }

      const result = (await response.json()) as ScheduleImport;
      setUploadMessage(`Schedule loaded. Workflow triggered from ${neutralScheduleText(result.file_name)} with quality ${result.quality_score.toFixed(0)}%.`);
      await load();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Schedule import failed");
    } finally {
      setUploading(false);
      event.currentTarget.value = "";
    }
  }

  async function handleWorkflowAction(action: string) {
    if (!dashboard?.workflow_instance) {
      return;
    }

    setRoutingAction(action);
    setUploadMessage(null);
    setUploadError(null);

    try {
      const response = await fetch(
        `${apiUrl}/api/v1/projects/${dashboard.project.id}/workflow-instances/${dashboard.workflow_instance.id}/actions`,
        {
          method: "POST",
          headers: apiHeaders(true),
          body: JSON.stringify({ action, actor: dashboard.current_user.full_name })
        }
      );
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || "Workflow action failed");
      }
      await load();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Workflow action failed");
    } finally {
      setRoutingAction(null);
    }
  }

  async function handleProgressSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!dashboard) {
      return;
    }
    setCaptureAction("progress");
    setUploadMessage(null);
    setUploadError(null);
    try {
      const response = await fetch(`${apiUrl}/api/v1/projects/${dashboard.project.id}/progress-records`, {
        method: "POST",
        headers: apiHeaders(true),
        body: JSON.stringify({
          control_account_id: Number(progressDraft.control_account_id),
          physical_percent: Number(progressDraft.physical_percent),
          quantity_installed: Number(progressDraft.quantity_installed),
          labor_hours: Number(progressDraft.labor_hours),
          reported_on: progressDraft.reported_on,
          evidence_ref: progressDraft.evidence_ref
        })
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || "Progress capture failed");
      }
      setUploadMessage("Progress captured. Control Core recalculated EVM and early warnings.");
      setProgressDraft((current) => ({ ...current, physical_percent: "", quantity_installed: "", labor_hours: "", evidence_ref: "" }));
      await load();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Progress capture failed");
    } finally {
      setCaptureAction(null);
    }
  }

  async function handleCostSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!dashboard) {
      return;
    }
    setCaptureAction("cost");
    setUploadMessage(null);
    setUploadError(null);
    try {
      const response = await fetch(`${apiUrl}/api/v1/projects/${dashboard.project.id}/cost-records`, {
        method: "POST",
        headers: apiHeaders(true),
        body: JSON.stringify({
          control_account_id: Number(costDraft.control_account_id),
          source: costDraft.source,
          amount: Number(costDraft.amount),
          incurred_on: costDraft.incurred_on,
          description: costDraft.description
        })
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || "Actual cost capture failed");
      }
      setUploadMessage("Actual cost captured. Control Core recalculated EVM and early warnings.");
      setCostDraft((current) => ({ ...current, amount: "", description: "" }));
      await load();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Actual cost capture failed");
    } finally {
      setCaptureAction(null);
    }
  }

  async function handleProjectCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCaptureAction("project");
    setUploadMessage(null);
    setUploadError(null);
    try {
      const response = await fetch(`${apiUrl}/api/v1/projects`, {
        method: "POST",
        headers: apiHeaders(true),
        body: JSON.stringify({
          ...projectDraft,
          start_date: projectDraft.start_date || null,
          finish_date: projectDraft.finish_date || null
        })
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || "Project creation failed");
      }
      const created = (await response.json()) as Project;
      setSelectedProjectId(String(created.id));
      setProjects((current) => [...current.filter((project) => project.id !== created.id), created]);
      setProjectDraft({ code: "", name: "", phase: "Planning", currency: "USD", start_date: "", finish_date: "" });
      setUploadMessage("Project shell created. Load the source schedule to trigger the control workflow.");
      const dashboardResponse = await fetch(`${apiUrl}/api/v1/projects/${created.id}/dashboard`, {
        headers: apiHeaders()
      });
      setDashboard((await dashboardResponse.json()) as Dashboard);
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Project creation failed");
    } finally {
      setCaptureAction(null);
    }
  }

  async function handleUserCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCaptureAction("user");
    setUploadMessage(null);
    setUploadError(null);
    try {
      const response = await fetch(`${apiUrl}/api/v1/users`, {
        method: "POST",
        headers: apiHeaders(true),
        body: JSON.stringify(userDraft)
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || "User creation failed");
      }
      const created = (await response.json()) as User;
      setTeamDraft((current) => ({ ...current, user_id: String(created.id) }));
      setUserDraft({ email: "", full_name: "", title: "" });
      setUploadMessage("User created. Assign a project role to give access.");
      await load();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "User creation failed");
    } finally {
      setCaptureAction(null);
    }
  }

  async function handleTeamAssign(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!dashboard) {
      return;
    }
    setCaptureAction("team");
    setUploadMessage(null);
    setUploadError(null);
    try {
      const response = await fetch(`${apiUrl}/api/v1/projects/${dashboard.project.id}/team`, {
        method: "POST",
        headers: apiHeaders(true),
        body: JSON.stringify({ user_id: Number(teamDraft.user_id), role: teamDraft.role })
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || "Role assignment failed");
      }
      setUploadMessage("Project role assigned and permissions updated.");
      await load();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Role assignment failed");
    } finally {
      setCaptureAction(null);
    }
  }

  async function handleProcessTemplateCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCaptureAction("process-template");
    setUploadMessage(null);
    setUploadError(null);
    try {
      const response = await fetch(`${apiUrl}/api/v1/process-templates`, {
        method: "POST",
        headers: apiHeaders(true),
        body: JSON.stringify({
          code: processDraft.code,
          name: processDraft.name,
          category: processDraft.category,
          description: processDraft.description,
          form_schema: listFromInput(processDraft.form_schema),
          status: "Draft",
          version_no: 1,
          steps: processStepsFromInput(processDraft.steps),
          transitions: processTransitionsFromInput(processDraft.transitions)
        })
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || "Business process template creation failed");
      }
      setProcessDraft((current) => ({
        ...current,
        code: "",
        name: "",
        description: ""
      }));
      setUploadMessage("Business process template created. It is now available in BP Setup and API routing.");
      await load();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Business process template creation failed");
    } finally {
      setCaptureAction(null);
    }
  }

  async function handleControlBaselineApprove() {
    if (!dashboard) {
      return;
    }
    setCaptureAction("control-baseline-approve");
    setUploadMessage(null);
    setUploadError(null);
    try {
      const response = await fetch(`${apiUrl}/api/v1/projects/${dashboard.project.id}/control-account-mapping/approve`, {
        method: "POST",
        headers: apiHeaders(true)
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || "Control baseline approval failed");
      }
      setUploadMessage("Control baseline approved. WBS/CBS/Activity mapping is now ready for EVM control.");
      await load();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Control baseline approval failed");
    } finally {
      setCaptureAction(null);
    }
  }

  async function handleChangeSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!dashboard) {
      return;
    }
    setCaptureAction("change");
    setUploadMessage(null);
    setUploadError(null);
    try {
      const response = await fetch(`${apiUrl}/api/v1/projects/${dashboard.project.id}/changes`, {
        method: "POST",
        headers: apiHeaders(true),
        body: JSON.stringify({
          control_account_id: changeDraft.control_account_id ? Number(changeDraft.control_account_id) : null,
          title: changeDraft.title,
          deviation: changeDraft.deviation,
          cost_impact: Number(changeDraft.cost_impact || 0),
          schedule_impact_days: Number(changeDraft.schedule_impact_days || 0)
        })
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || "Change request failed");
      }
      setChangeDraft((current) => ({ ...current, title: "", deviation: "", cost_impact: "", schedule_impact_days: "" }));
      setUploadMessage("Change request created and routed as a business process.");
      await load();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Change request failed");
    } finally {
      setCaptureAction(null);
    }
  }

  async function handleContractSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!dashboard) {
      return;
    }
    setCaptureAction("contract");
    setUploadMessage(null);
    setUploadError(null);
    try {
      const response = await fetch(`${apiUrl}/api/v1/projects/${dashboard.project.id}/contracts`, {
        method: "POST",
        headers: apiHeaders(true),
        body: JSON.stringify({ ...contractDraft, value: Number(contractDraft.value || 0) })
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || "Contract creation failed");
      }
      setContractDraft({ code: "", title: "", counterparty: "", contract_type: "Services", value: "", status: "active" });
      setUploadMessage("Contract registered for contractual administration.");
      await load();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Contract creation failed");
    } finally {
      setCaptureAction(null);
    }
  }

  async function handleCommunicationSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!dashboard) {
      return;
    }
    setCaptureAction("communication");
    setUploadMessage(null);
    setUploadError(null);
    try {
      const response = await fetch(`${apiUrl}/api/v1/projects/${dashboard.project.id}/communications`, {
        method: "POST",
        headers: apiHeaders(true),
        body: JSON.stringify({
          ...communicationDraft,
          contract_id: communicationDraft.contract_id ? Number(communicationDraft.contract_id) : null
        })
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || "Communication creation failed");
      }
      setCommunicationDraft((current) => ({ ...current, subject: "", reference: "" }));
      setUploadMessage("Contractual communication issued and added to the audit trail.");
      await load();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Communication creation failed");
    } finally {
      setCaptureAction(null);
    }
  }

  async function handleNoticeSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!dashboard) {
      return;
    }
    setCaptureAction("contract-notice");
    setUploadMessage(null);
    setUploadError(null);
    try {
      const response = await fetch(`${apiUrl}/api/v1/projects/${dashboard.project.id}/contract-notices`, {
        method: "POST",
        headers: apiHeaders(true),
        body: JSON.stringify({
          ...noticeDraft,
          contract_id: noticeDraft.contract_id ? Number(noticeDraft.contract_id) : null,
          claim_id: noticeDraft.claim_id ? Number(noticeDraft.claim_id) : null,
          change_request_id: noticeDraft.change_request_id ? Number(noticeDraft.change_request_id) : null,
          event_date: noticeDraft.event_date || null,
          due_date: noticeDraft.due_date || null,
          notice_date: noticeDraft.notice_date || null
        })
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || "Contract notice creation failed");
      }
      setNoticeDraft((current) => ({ ...current, subject: "", reference: "" }));
      setUploadMessage("Contract notice issued. Compliance and claim readiness were updated.");
      await load();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Contract notice creation failed");
    } finally {
      setCaptureAction(null);
    }
  }

  async function handleClaimImpactSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!dashboard || !claimImpactDraft.claim_id) {
      return;
    }
    setCaptureAction("claim-impact");
    setUploadMessage(null);
    setUploadError(null);
    try {
      const response = await fetch(`${apiUrl}/api/v1/projects/${dashboard.project.id}/claims/${claimImpactDraft.claim_id}/impact-analyses`, {
        method: "POST",
        headers: apiHeaders(true),
        body: JSON.stringify({
          method: claimImpactDraft.method,
          impacted_activity: claimImpactDraft.impacted_activity,
          cause: claimImpactDraft.cause,
          effect: claimImpactDraft.effect,
          schedule_impact_days: Number(claimImpactDraft.schedule_impact_days || 0),
          cost_impact: Number(claimImpactDraft.cost_impact || 0),
          productivity_loss_percent: Number(claimImpactDraft.productivity_loss_percent || 0),
          evidence_ref: claimImpactDraft.evidence_ref,
          confidence_score: Number(claimImpactDraft.confidence_score || 0),
          status: claimImpactDraft.status
        })
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || "Claim impact analysis failed");
      }
      setClaimImpactDraft((current) => ({
        ...current,
        impacted_activity: "",
        cause: "",
        effect: "",
        schedule_impact_days: "",
        cost_impact: "",
        productivity_loss_percent: "",
        evidence_ref: ""
      }));
      setUploadMessage("Claim impact analysis added to the forensic package.");
      await load();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Claim impact analysis failed");
    } finally {
      setCaptureAction(null);
    }
  }

  async function handleDocumentSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!dashboard) {
      return;
    }
    setCaptureAction("document");
    setUploadMessage(null);
    setUploadError(null);
    try {
      const response = await fetch(`${apiUrl}/api/v1/projects/${dashboard.project.id}/documents`, {
        method: "POST",
        headers: apiHeaders(true),
        body: JSON.stringify({
          ...documentDraft,
          linked_entity_id: Number(documentDraft.linked_entity_id || 0)
        })
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || "Document link failed");
      }
      setDocumentDraft((current) => ({ ...current, title: "", uri: "" }));
      setUploadMessage("Document linked to the project control record.");
      await load();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Document link failed");
    } finally {
      setCaptureAction(null);
    }
  }

  async function handleAwpSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!dashboard) {
      return;
    }
    setCaptureAction("awp");
    setUploadMessage(null);
    setUploadError(null);
    try {
      const response = await fetch(`${apiUrl}/api/v1/projects/${dashboard.project.id}/work-packages`, {
        method: "POST",
        headers: apiHeaders(true),
        body: JSON.stringify({
          ...awpDraft,
          control_account_id: awpDraft.control_account_id ? Number(awpDraft.control_account_id) : null,
          parent_id: awpDraft.parent_id ? Number(awpDraft.parent_id) : null,
          sequence_no: Number(awpDraft.sequence_no || dashboard.work_packages.length * 10 + 10),
          planned_start: awpDraft.planned_start || null,
          planned_finish: awpDraft.planned_finish || null,
          progress_percent: Number(awpDraft.progress_percent || 0)
        })
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || "AWP package creation failed");
      }
      const created = (await response.json()) as WorkPackage;
      setConstraintDraft((current) => ({ ...current, work_package_id: String(created.id) }));
      setAwpDraft((current) => ({ ...current, code: "", title: "", path_of_construction: "", sequence_no: "", progress_percent: "" }));
      setUploadMessage("AWP work package created and routed to readiness workflow.");
      await load();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "AWP package creation failed");
    } finally {
      setCaptureAction(null);
    }
  }

  async function handleConstraintSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!dashboard || !constraintDraft.work_package_id) {
      return;
    }
    setCaptureAction("awp-constraint");
    setUploadMessage(null);
    setUploadError(null);
    try {
      const response = await fetch(`${apiUrl}/api/v1/projects/${dashboard.project.id}/work-packages/${constraintDraft.work_package_id}/constraints`, {
        method: "POST",
        headers: apiHeaders(true),
        body: JSON.stringify({
          constraint_type: constraintDraft.constraint_type,
          description: constraintDraft.description,
          owner_role: constraintDraft.owner_role,
          required_by: constraintDraft.required_by || null,
          status: constraintDraft.status,
          blocking: constraintDraft.blocking
        })
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || "AWP constraint creation failed");
      }
      setConstraintDraft((current) => ({ ...current, description: "", constraint_type: "Material", status: "open", blocking: true }));
      setUploadMessage("AWP constraint registered. Package readiness updated.");
      await load();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "AWP constraint creation failed");
    } finally {
      setCaptureAction(null);
    }
  }

  async function handleConstraintClose(constraint: WorkPackageConstraint) {
    if (!dashboard) {
      return;
    }
    setCaptureAction(`awp-constraint-${constraint.id}`);
    setUploadMessage(null);
    setUploadError(null);
    try {
      const response = await fetch(`${apiUrl}/api/v1/projects/${dashboard.project.id}/work-packages/${constraint.work_package_id}/constraints/${constraint.id}`, {
        method: "PATCH",
        headers: apiHeaders(true),
        body: JSON.stringify({ status: "closed" })
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || "AWP constraint update failed");
      }
      setUploadMessage("AWP constraint closed. Readiness recalculated.");
      await load();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "AWP constraint update failed");
    } finally {
      setCaptureAction(null);
    }
  }

  if (loading) {
    return <main className="loading">Loading control core...</main>;
  }

  if (!dashboard) {
    return <main className="loading">{authError ?? "API unavailable. Start Docker Compose to run the demo."}</main>;
  }

  const { project, project_kpi: kpi } = dashboard;
  const redAlerts = dashboard.alerts.filter((alert) => alert.severity === "red").length;
  const amberAlerts = dashboard.alerts.filter((alert) => alert.severity === "amber").length;
  const healthLabel = kpi.spi < 0.9 || kpi.cpi < 0.9 ? "Intervention required" : "Under control";
  const healthClass = kpi.spi < 0.9 || kpi.cpi < 0.9 ? "critical" : "stable";
  const workflowInstance = dashboard.workflow_instance;
  const workflowStatus = statusLabel(workflowInstance?.status);
  const workflowActionButtons = workflowInstance?.current_step === "Impact Review"
    ? [{ action: "route_to_approval", label: "Route to Approval", tone: "primary" }]
    : workflowInstance?.current_step === "Approval"
      ? [
          { action: "approve_baseline", label: "Approve Baseline", tone: "primary" },
          { action: "reject_baseline", label: "Reject", tone: "danger" }
        ]
      : workflowInstance?.current_step === "Action"
        ? [{ action: "close_action", label: "Close Action Loop", tone: "primary" }]
        : [];
  const workflowStages = dashboard.workflow_steps.length
    ? dashboard.workflow_steps.map((stage) => ({
        name: stage.name,
        detail: neutralScheduleText(stage.detail),
        owner: stage.owner_role,
        status: stage.status,
        tone: stage.tone
      }))
    : [
        { name: "Creation", detail: "Waiting for source schedule upload.", owner: "Planner", status: "Waiting", tone: "queued" },
        { name: "Data Quality", detail: "Calendar, logic and baseline gate starts after import.", owner: "Controls Engineer", status: "Queued", tone: "queued" },
        { name: "Impact Review", detail: "Cost, schedule and productivity impact requires a valid schedule.", owner: "Project Controls", status: "Queued", tone: "queued" },
        { name: "Approval", detail: "Control Manager route opens after impact analysis.", owner: "Control Manager", status: "Queued", tone: "queued" },
        { name: "Action", detail: "Forecast and field actions wait for an approved decision.", owner: "Execution Lead", status: "Queued", tone: "queued" }
      ];
  const scheduleBpRecords = dashboard.business_processes.length
    ? dashboard.business_processes.map((process) => ({
        record: process.record_no,
        process: process.process_name,
        title: neutralScheduleText(process.title),
        step: process.current_step,
        ballInCourt: process.ball_in_court,
        status: statusLabel(process.status),
        tone: process.status === "rejected" ? "critical" : process.status === "closed" ? "complete" : "active"
      }))
    : [{
        record: "SCH-PENDING",
        process: "Schedule Intake",
        title: "Waiting for source schedule upload",
        step: "Schedule Upload Gate",
        ballInCourt: "Planner",
        status: "Not Started",
        tone: "queued"
      }];
  const bpRecords = [
    ...scheduleBpRecords,
    ...dashboard.alerts.slice(0, 3).map((alert) => ({
      record: `EWS-${alert.id}`,
      process: "Early Warning",
      title: alert.rule,
      step: "Impact Review",
      ballInCourt: "Project Controls",
      status: alert.severity,
      tone: alert.severity === "red" ? "critical" : alert.severity
    })),
    ...dashboard.changes.map((change) => ({
      record: `CR-${change.id}`,
      process: "Change Management",
      title: change.title,
      step: "Cost and Schedule Review",
      ballInCourt: "Control Manager",
      status: change.status,
      tone: "pending"
    })),
    ...dashboard.claims.map((claim) => ({
      record: `CL-${claim.id}`,
      process: "Claims / Forensic",
      title: claim.title,
      step: "Causality Review",
      ballInCourt: "Contract Manager",
      status: claim.status,
      tone: "active"
    })),
    ...dashboard.contract_notices.map((notice) => ({
      record: `NT-${notice.id}`,
      process: "Contract Notice",
      title: notice.subject,
      step: "Notice Compliance",
      ballInCourt: "Contract Manager",
      status: notice.compliance_status,
      tone: notice.compliance_status === "late" ? "critical" : "complete"
    })),
    ...dashboard.claim_impact_analyses.map((analysis) => ({
      record: `IA-${analysis.id}`,
      process: "Claim Impact Analysis",
      title: analysis.impacted_activity || analysis.method,
      step: "Impact / Quantum Analysis",
      ballInCourt: "Claims Analyst",
      status: analysis.status,
      tone: analysis.status === "reviewed" ? "complete" : "pending"
    }))
  ];
  const selectedBpRecord = bpRecords.find((record) => record.record === selectedBpRecordNo) ?? bpRecords[0] ?? null;
  const navigatorItems: Array<{ key: WorkspaceView; label: string; count: string | number }> = [
    { key: "business-processes", label: "Business Processes", count: bpRecords.length },
    { key: "control-dashboard", label: "Control Dashboard", count: redAlerts },
    { key: "schedule", label: "Schedule", count: dashboard.schedule_activity_count },
    { key: "progress", label: "Progress", count: dashboard.latest_progress_records.length },
    { key: "cost", label: "Cost", count: dashboard.latest_cost_records.length },
    { key: "awp", label: "AWP Workface", count: dashboard.awp_summary.total_packages },
    { key: "changes", label: "Changes", count: dashboard.changes.length },
    { key: "claims", label: "Claims", count: dashboard.claims.length },
    { key: "contracts", label: "Contracts", count: dashboard.contracts.length },
    { key: "documents", label: "Documents", count: dashboard.documents.length },
    { key: "roadmap", label: "Roadmap", count: "59%" },
    { key: "bp-entry-forms", label: "BP Entry Forms", count: "Open" },
    { key: "admin", label: "Projects / Users / Roles", count: dashboard.project_team.length }
  ];
  const chartData = dashboard.control_snapshots.length
    ? dashboard.control_snapshots.map((snapshot) => ({
        period: snapshot.period_label,
        PV: snapshot.pv,
        EV: snapshot.ev,
        AC: snapshot.ac,
        SPI: snapshot.spi,
        CPI: snapshot.cpi
      }))
    : [{ period: "Current", PV: kpi.pv, EV: kpi.ev, AC: kpi.ac, SPI: kpi.spi, CPI: kpi.cpi }];
  const accountLabel = (accountId: number) => {
    const account = dashboard.control_accounts.find((item) => item.id === accountId);
    return account ? `${account.code} / ${account.name}` : `Control Account ${accountId}`;
  };
  const packageLabel = (packageId: number) => {
    const item = dashboard.work_packages.find((workPackage) => workPackage.id === packageId);
    return item ? `${item.code} / ${item.title}` : `Work Package ${packageId}`;
  };
  const constraintsByPackage = dashboard.work_package_constraints.reduce<Record<number, WorkPackageConstraint[]>>((acc, constraint) => {
    acc[constraint.work_package_id] = [...(acc[constraint.work_package_id] ?? []), constraint];
    return acc;
  }, {});
  const entitlementByClaim = dashboard.claim_entitlement_items.reduce<Record<number, ClaimEntitlementItem[]>>((acc, item) => {
    acc[item.claim_id] = [...(acc[item.claim_id] ?? []), item];
    return acc;
  }, {});
  const noticesByClaim = dashboard.contract_notices.reduce<Record<number, ContractNotice[]>>((acc, notice) => {
    if (notice.claim_id) {
      acc[notice.claim_id] = [...(acc[notice.claim_id] ?? []), notice];
    }
    return acc;
  }, {});
  const impactByClaim = dashboard.claim_impact_analyses.reduce<Record<number, ClaimImpactAnalysis[]>>((acc, analysis) => {
    acc[analysis.claim_id] = [...(acc[analysis.claim_id] ?? []), analysis];
    return acc;
  }, {});
  const mappingSummary = dashboard.control_account_mapping_summary;
  const controlGateBlocked = !dashboard.schedule_import || dashboard.schedule_import.quality_score < 70 || !dashboard.control_accounts.length;
  const progressDisabled = controlGateBlocked || !dashboard.current_membership.can_capture_progress;
  const costDisabled = controlGateBlocked || !dashboard.current_membership.can_capture_cost;
  const canUploadSchedule = ["Planner", "Control Manager"].includes(dashboard.current_membership.role);
  const canConfigure = dashboard.current_membership.can_configure;
  const canManageContracts = dashboard.current_membership.can_manage_contract;
  const canManageClaims = canManageContracts || ["Control Manager", "Claims Analyst", "Project Controls"].includes(dashboard.current_membership.role);
  const canCreateChange = dashboard.project_team.some((member) => member.user.id === dashboard.current_user.id);
  const canManageAwp = ["Control Manager", "Planner", "Project Controls", "Field Engineer", "Workface Planner"].includes(dashboard.current_membership.role);
  const linkedEntityOptions = [
    ...dashboard.control_accounts.map((account) => ({ type: "ControlAccount", id: account.id, label: account.code })),
    ...dashboard.work_packages.map((workPackage) => ({ type: "WorkPackage", id: workPackage.id, label: workPackage.code })),
    ...dashboard.changes.map((change) => ({ type: "ChangeRequest", id: change.id, label: `CR-${change.id}` })),
    ...dashboard.claims.map((claim) => ({ type: "Claim", id: claim.id, label: `CL-${claim.id}` })),
    ...dashboard.contract_notices.map((notice) => ({ type: "ContractNotice", id: notice.id, label: `N-${notice.id}` })),
    ...dashboard.contracts.map((contract) => ({ type: "Contract", id: contract.id, label: contract.code }))
  ];
  const canRouteCurrentWorkflow =
    !workflowInstance ||
    workflowInstance.current_step === "Impact Review" ||
    dashboard.current_membership.can_approve_workflow;
  const canApproveControlBaseline =
    dashboard.current_membership.can_approve_workflow &&
    mappingSummary.mapping_score >= 100 &&
    mappingSummary.cost_loading_score >= 80 &&
    mappingSummary.baseline_status !== "approved";
  const roadmapStatus = [
    {
      phase: "Fase 1",
      title: "Schedule ingestion",
      score: 65,
      state: "Parcial funcional",
      detail: "XML/XER intake, QA gate, baseline y BP trigger existen; falta parser XER completo, validaciones DCMA/AACE profundas y log de errores operativo."
    },
    {
      phase: "Fase 2",
      title: "BP Engine configurable",
      score: 68,
      state: "MVP configurable",
      detail: "Plantillas BP persistentes, formularios, pasos, transiciones, ball-in-court y permisos basicos ya gobiernan el workflow; falta versionado avanzado y editor visual completo."
    },
    {
      phase: "Fase 3",
      title: "Control accounts automaticos",
      score: 58,
      state: "MVP automatico",
      detail: "Mapeo WBS/CBS/Activity, trazabilidad por actividad, cost loading ponderado y aprobacion formal del baseline ya existen; falta reglas avanzadas de desglose y revision masiva."
    },
    {
      phase: "Fase 4",
      title: "EVM historico y forecast",
      score: 62,
      state: "MVP historico",
      detail: "Snapshots EVM por periodo, curva PV/EV/AC historica, productividad e escenarios EAC ya existen; falta curva de caja real, escenarios configurables y tendencia por disciplina."
    },
    {
      phase: "Fase 5",
      title: "Contracts & claims",
      score: 72,
      state: "MVP operativo",
      detail: "Contratos, comunicaciones, notices formales, cumplimiento, matriz RP120R/RP130R, TIA, measured mile inicial e impactos cuantificados ya alimentan el paquete forense; falta quantum avanzado y generacion documental completa."
    },
    {
      phase: "Fase 6",
      title: "SaaS empresarial",
      score: 30,
      state: "SaaS-ready tecnico",
      detail: "Multi-proyecto, tenant_id, usuarios, roles y permisos existen; falta auth real, API tokens, hardening, observabilidad y auditoria avanzada."
    }
  ];
  const overallRoadmapScore = Math.round(roadmapStatus.reduce((total, item) => total + item.score, 0) / roadmapStatus.length);

  return (
    <main>
      <header className="topbar">
        <div className="brandBlock">
          <p className="eyebrow">P&Pmis Ai SaaS</p>
          <h1>{project.name}</h1>
          <p className="productStatement">
            Sistema integrado de Project Controls basado en AACE TCM para convertir cronograma, costos,
            avance, cambios, reclamos y documentos en alertas, decisiones y acciones tempranas.
          </p>
          <span className="projectMeta">{project.code} - {project.phase} - {project.start_date ?? "Pending"} to {project.finish_date ?? "Pending"}</span>
        </div>
        <div className="headerActions">
          <div className="contextSwitch">
            <label>
              <span>Project</span>
              <select onChange={(event) => setSelectedProjectId(event.target.value)} value={selectedProjectId || String(project.id)}>
                {projects.map((item) => (
                  <option key={item.id} value={item.id}>{item.code}</option>
                ))}
              </select>
            </label>
            <label>
              <span>User / Role</span>
              <select onChange={(event) => setSelectedUserId(event.target.value)} value={selectedUserId}>
                {users.map((user) => (
                  <option key={user.id} value={user.id}>{user.full_name}</option>
                ))}
              </select>
            </label>
            <strong>{dashboard.current_membership.role}</strong>
          </div>
          <button
            className={activeView === "admin" ? "quickNavButton active" : "quickNavButton"}
            onClick={() => setActiveView("admin")}
            title="Create projects, users and project roles"
            type="button"
          >
            <UserPlus size={16} />
            <span>Projects / Users</span>
          </button>
          <div className={`healthBadge ${healthClass}`}>
            <span>{healthLabel}</span>
            <strong>SPI {kpi.spi.toFixed(3)} / CPI {kpi.cpi.toFixed(3)}</strong>
          </div>
        <button className="iconButton" onClick={load} title="Run control refresh">
          <RefreshCw size={18} />
        </button>
        </div>
      </header>

      <section className="scheduleGate" id="schedule-intake">
        <div className="gateHeader">
          <div className="gateIntro">
            <CalendarClock size={20} />
            <div>
              <strong>Schedule Intake Gate</strong>
              <span>Schedule XML or XER is the master input before Planeacion</span>
            </div>
          </div>
          <label className={`uploadButton ${uploading || !canUploadSchedule ? "disabled" : ""}`} title="Upload a schedule XML or XER file">
            <Upload size={16} />
            <span>{uploading ? "Uploading" : "Upload Schedule"}</span>
            <input accept=".xer,.xml,.mpp" disabled={uploading || !canUploadSchedule} onChange={handleScheduleUpload} type="file" />
          </label>
        </div>
        <div className="gateFacts">
          <div>
            <span>Source</span>
            <strong>{sourceLabel(dashboard.schedule_import?.source)}</strong>
          </div>
          <div>
            <span>Baseline</span>
            <strong>{dashboard.schedule_import ? neutralScheduleText(dashboard.schedule_import.baseline_name) : "Pending"}</strong>
          </div>
          <div>
            <span>Data Date</span>
            <strong>{dashboard.schedule_import?.data_date ?? "Pending"}</strong>
          </div>
          <div>
            <span>Quality</span>
            <strong>{dashboard.schedule_import?.quality_score.toFixed(0) ?? "0"}%</strong>
          </div>
          <div>
            <span>Activities / Logic</span>
            <strong>{dashboard.schedule_activity_count} / {dashboard.schedule_relationship_count}</strong>
          </div>
        </div>
        <p>{dashboard.schedule_import?.validation_summary ?? "Import a schedule XML or XER file to activate the control baseline."}</p>
        {uploadMessage && <p className="uploadMessage success">{uploadMessage}</p>}
        {uploadError && <p className="uploadMessage error">{uploadError}</p>}
      </section>

      <section className="unifierFrame">
        <aside className="navigatorRail" aria-label="Project controls navigation">
          <div className="navigatorHeader">
            <strong>Project Controls</strong>
            <span>Navigator</span>
          </div>
          {navigatorItems.map((item) => (
            <button
              className={activeView === item.key ? "navigatorItem active" : "navigatorItem"}
              key={item.key}
              onClick={() => setActiveView(item.key)}
              type="button"
            >
              <span>{item.label}</span>
              <strong>{item.count}</strong>
            </button>
          ))}
        </aside>

        <div className="workArea">
      <details className={activeView === "admin" ? "adminDrawer workspaceSection" : "adminDrawer workspaceSection hidden"} id="admin-setup" open={activeView === "admin"}>
        <summary>
          <span>Projects, Users & Roles</span>
          <strong>Create project shells, tenant users and project role assignments</strong>
        </summary>
      <section className="workspaceAdmin">
        <form className="adminPanel" onSubmit={handleProjectCreate}>
          <div className="panelHeader">
            <h2><Building2 size={18} /> Project Shell</h2>
            <span>{projects.length} projects</span>
          </div>
          <div className="formColumns">
            <label>
              <span>Code</span>
              <input
                disabled={!canConfigure}
                onChange={(event) => setProjectDraft((current) => ({ ...current, code: event.target.value }))}
                placeholder="PRJ-001"
                required
                value={projectDraft.code}
              />
            </label>
            <label>
              <span>Phase</span>
              <select
                disabled={!canConfigure}
                onChange={(event) => setProjectDraft((current) => ({ ...current, phase: event.target.value }))}
                value={projectDraft.phase}
              >
                <option value="Planning">Planning</option>
                <option value="Execution">Execution</option>
                <option value="Closeout">Closeout</option>
              </select>
            </label>
          </div>
          <label>
            <span>Name</span>
            <input
              disabled={!canConfigure}
              onChange={(event) => setProjectDraft((current) => ({ ...current, name: event.target.value }))}
              placeholder="Project control shell name"
              required
              value={projectDraft.name}
            />
          </label>
          <div className="formColumns">
            <label>
              <span>Start</span>
              <input
                disabled={!canConfigure}
                onChange={(event) => setProjectDraft((current) => ({ ...current, start_date: event.target.value }))}
                type="date"
                value={projectDraft.start_date}
              />
            </label>
            <label>
              <span>Finish</span>
              <input
                disabled={!canConfigure}
                onChange={(event) => setProjectDraft((current) => ({ ...current, finish_date: event.target.value }))}
                type="date"
                value={projectDraft.finish_date}
              />
            </label>
          </div>
          <button className="workflowAction primary" disabled={!canConfigure || captureAction !== null} type="submit">
            {captureAction === "project" ? "Creating..." : "Create Project Shell"}
          </button>
        </form>

        <form className="adminPanel" onSubmit={handleUserCreate}>
          <div className="panelHeader">
            <h2><UserPlus size={18} /> Users</h2>
            <span>{users.length} active</span>
          </div>
          <label>
            <span>Full Name</span>
            <input
              disabled={!canConfigure}
              onChange={(event) => setUserDraft((current) => ({ ...current, full_name: event.target.value }))}
              required
              value={userDraft.full_name}
            />
          </label>
          <label>
            <span>Email</span>
            <input
              disabled={!canConfigure}
              onChange={(event) => setUserDraft((current) => ({ ...current, email: event.target.value }))}
              required
              type="email"
              value={userDraft.email}
            />
          </label>
          <label>
            <span>Title</span>
            <input
              disabled={!canConfigure}
              onChange={(event) => setUserDraft((current) => ({ ...current, title: event.target.value }))}
              value={userDraft.title}
            />
          </label>
          <button className="workflowAction primary" disabled={!canConfigure || captureAction !== null} type="submit">
            {captureAction === "user" ? "Creating..." : "Create User"}
          </button>
        </form>

        <form className="adminPanel" onSubmit={handleTeamAssign}>
          <div className="panelHeader">
            <h2><Users size={18} /> Roles</h2>
            <span>{dashboard.project_team.length} assigned</span>
          </div>
          <label>
            <span>User</span>
            <select
              disabled={!canConfigure}
              onChange={(event) => setTeamDraft((current) => ({ ...current, user_id: event.target.value }))}
              required
              value={teamDraft.user_id}
            >
              {users.map((user) => (
                <option key={user.id} value={user.id}>{user.full_name}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Role Profile</span>
            <select
              disabled={!canConfigure}
              onChange={(event) => setTeamDraft((current) => ({ ...current, role: event.target.value }))}
              required
              value={teamDraft.role}
            >
              {roles.map((role) => (
                <option key={role.role} value={role.role}>{role.role}</option>
              ))}
            </select>
          </label>
          <div className="permissionStrip">
            {roles.find((role) => role.role === teamDraft.role)?.can_capture_progress && <span>Progress</span>}
            {roles.find((role) => role.role === teamDraft.role)?.can_capture_cost && <span>Cost</span>}
            {roles.find((role) => role.role === teamDraft.role)?.can_approve_workflow && <span>Approve</span>}
            {roles.find((role) => role.role === teamDraft.role)?.can_manage_contract && <span>Contract</span>}
            {roles.find((role) => role.role === teamDraft.role)?.can_configure && <span>Admin</span>}
          </div>
          <button className="workflowAction primary" disabled={!canConfigure || captureAction !== null} type="submit">
            {captureAction === "team" ? "Assigning..." : "Assign Role"}
          </button>
        </form>

        <form className="adminPanel bpDesignerPanel" onSubmit={handleProcessTemplateCreate}>
          <div className="panelHeader">
            <h2><Settings size={18} /> BP Designer</h2>
            <span>{dashboard.process_templates.length} templates</span>
          </div>
          <div className="formColumns">
            <label>
              <span>Code</span>
              <input
                disabled={!canConfigure}
                onChange={(event) => setProcessDraft((current) => ({ ...current, code: event.target.value.toUpperCase() }))}
                placeholder="BP-CUSTOM"
                required
                value={processDraft.code}
              />
            </label>
            <label>
              <span>Category</span>
              <input
                disabled={!canConfigure}
                onChange={(event) => setProcessDraft((current) => ({ ...current, category: event.target.value }))}
                value={processDraft.category}
              />
            </label>
          </div>
          <label>
            <span>Name</span>
            <input
              disabled={!canConfigure}
              onChange={(event) => setProcessDraft((current) => ({ ...current, name: event.target.value }))}
              placeholder="Business process name"
              required
              value={processDraft.name}
            />
          </label>
          <label>
            <span>Description</span>
            <textarea
              disabled={!canConfigure}
              onChange={(event) => setProcessDraft((current) => ({ ...current, description: event.target.value }))}
              placeholder="Control purpose and decision point"
              value={processDraft.description}
            />
          </label>
          <label>
            <span>Form Fields</span>
            <textarea
              disabled={!canConfigure}
              onChange={(event) => setProcessDraft((current) => ({ ...current, form_schema: event.target.value }))}
              value={processDraft.form_schema}
            />
          </label>
          <label>
            <span>Steps: Step | Role | Detail</span>
            <textarea
              disabled={!canConfigure}
              onChange={(event) => setProcessDraft((current) => ({ ...current, steps: event.target.value }))}
              value={processDraft.steps}
            />
          </label>
          <label>
            <span>Transitions: action | from | to | ball in court | status</span>
            <textarea
              disabled={!canConfigure}
              onChange={(event) => setProcessDraft((current) => ({ ...current, transitions: event.target.value }))}
              value={processDraft.transitions}
            />
          </label>
          <button className="workflowAction primary" disabled={!canConfigure || captureAction !== null} type="submit">
            {captureAction === "process-template" ? "Saving..." : "Create BP Template"}
          </button>
        </form>
      </section>
      </details>

      <section className="controlSummary">
        <div>
          <span>Control Date</span>
          <strong>{dashboard.schedule_import?.data_date ?? "Pending"}</strong>
        </div>
        <div>
          <span>Control Period</span>
          <strong>{dashboard.control_periods[0]?.period_label ?? "Pending"}</strong>
        </div>
        <div>
          <span>Baseline</span>
          <strong>{statusLabel(mappingSummary.baseline_status)}</strong>
        </div>
        <div>
          <span>CA Mapping</span>
          <strong>{mappingSummary.mapping_score.toFixed(0)}% / Cost {mappingSummary.cost_loading_score.toFixed(0)}%</strong>
        </div>
        <div>
          <span>Open Warnings</span>
          <strong>{redAlerts} red / {amberAlerts} amber</strong>
        </div>
        <div>
          <span>Forecast Variance</span>
          <strong>{currency(kpi.vac, project.currency)}</strong>
        </div>
      </section>

      <section className="flowBand">
        <div className="flowTrack">
          {dashboard.flow.map((step, index) => (
            <React.Fragment key={step.name}>
              <div className="flowStep">
                <strong>{step.name}</strong>
                <span>{step.state}</span>
              </div>
              {index < dashboard.flow.length - 1 && <ArrowRight className="flowArrow" size={18} />}
            </React.Fragment>
          ))}
        </div>
      </section>

      <section className={activeView === "roadmap" ? "viewPanel workspaceSection" : "viewPanel workspaceSection hidden"}>
        <div className="panelHeader">
          <h2>Roadmap Maturity Assessment</h2>
          <span>Estado global {overallRoadmapScore}%</span>
        </div>
        <div className="appAssessment">
          <article>
            <span>Calificacion actual</span>
            <strong>{overallRoadmapScore}/100</strong>
            <small>Demo funcional avanzada, todavia no produccion empresarial.</small>
          </article>
          <article>
            <span>TCM / Control Core</span>
            <strong>7/10</strong>
            <small>Flujo TCM, EVM, alertas, BP y trazabilidad ya estan conectados.</small>
          </article>
          <article>
            <span>AWP</span>
            <strong>4/10</strong>
            <small>CWA/CWP/EWP/PWP/IWP, readiness y constraints quedan integrados como MVP inicial.</small>
          </article>
          <article>
            <span>Produccion SaaS</span>
            <strong>3/10</strong>
            <small>Faltan auth real, migraciones, hardening, observabilidad y pruebas amplias.</small>
          </article>
        </div>
        <div className="roadmapGrid">
          {roadmapStatus.map((item) => (
            <article className="roadmapPhase" key={item.phase}>
              <div>
                <span>{item.phase}</span>
                <strong>{item.title}</strong>
              </div>
              <div className="scoreBar">
                <span style={{ width: `${item.score}%` }} />
              </div>
              <div className="phaseMeta">
                <strong>{item.score}%</strong>
                <span>{item.state}</span>
              </div>
              <p>{item.detail}</p>
            </article>
          ))}
        </div>
      </section>

      <section className={activeView === "schedule" ? "viewPanel workspaceSection" : "viewPanel workspaceSection hidden"}>
        <div className="panelHeader">
          <h2>Schedule Control</h2>
          <button
            className="linkButton"
            disabled={!canApproveControlBaseline || captureAction !== null}
            onClick={handleControlBaselineApprove}
            type="button"
          >
            {captureAction === "control-baseline-approve" ? "Approving..." : "Approve Control Baseline"}
          </button>
        </div>
        <div className="mappingSummary">
          <article>
            <span>Mapped Activities</span>
            <strong>{mappingSummary.mapped_activities}/{mappingSummary.total_schedule_activities}</strong>
            <small>{mappingSummary.mapping_score.toFixed(1)}% WBS to control account coverage</small>
          </article>
          <article>
            <span>Cost Loading</span>
            <strong>{mappingSummary.cost_loaded_activities}/{mappingSummary.total_schedule_activities}</strong>
            <small>{mappingSummary.cost_loading_score.toFixed(1)}% schedule activities with cost</small>
          </article>
          <article>
            <span>Control Accounts</span>
            <strong>{mappingSummary.control_account_count}</strong>
            <small>{currency(mappingSummary.total_bac, project.currency)} BAC / PV {currency(mappingSummary.total_planned_value, project.currency)}</small>
          </article>
          <article>
            <span>Baseline Status</span>
            <strong>{statusLabel(mappingSummary.baseline_status)}</strong>
            <small>{dashboard.schedule_activity_count} activities / {dashboard.schedule_relationship_count} relationships</small>
          </article>
        </div>
        <div className="viewSplit">
          <div className="workList">
            <article>
              <strong>{dashboard.schedule_import ? neutralScheduleText(dashboard.schedule_import.baseline_name) : "No baseline"}</strong>
              <span>{dashboard.schedule_import?.validation_summary ?? "Upload a schedule XML or XER file to start the baseline workflow."}</span>
              <small>Quality {dashboard.schedule_import?.quality_score.toFixed(0) ?? "0"}% / Data date {dashboard.schedule_import?.data_date ?? "Pending"}</small>
            </article>
            {dashboard.baseline_versions.map((baseline) => (
              <article key={baseline.id}>
                <strong>BL-{baseline.version_no.toString().padStart(2, "0")} / {statusLabel(baseline.status)}</strong>
                <span>{neutralScheduleText(baseline.name)}</span>
                <small>{baseline.data_date ?? "No data date"} / Quality {baseline.quality_score.toFixed(0)}%</small>
              </article>
            ))}
          </div>
          <div className="qualityList">
            {dashboard.schedule_findings.length ? dashboard.schedule_findings.map((finding) => (
              <article key={finding.id}>
                <div>
                  <strong>{finding.check_code}</strong>
                  <span className={`qualityStatus ${finding.severity.toLowerCase()}`}>{statusLabel(finding.severity)}</span>
                </div>
                <p>{finding.message}</p>
                <small>{finding.item_count} items / weight {finding.weight}</small>
              </article>
            )) : (
              <article>
                <div>
                  <strong>No findings</strong>
                  <span className="qualityStatus pass">Pass</span>
                </div>
                <p>The active schedule has no stored QA findings.</p>
              </article>
            )}
          </div>
        </div>
        <div className="mappingTable">
          <div className="panelHeader compactHeader">
            <h2>WBS / CBS / Activity Mapping</h2>
            <span>{dashboard.control_account_mappings.length} linked activities</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>WBS</th>
                <th>CBS</th>
                <th>Control Account</th>
                <th>Planned %</th>
                <th>BAC</th>
                <th>PV</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {dashboard.control_account_mappings.slice(0, 12).map((mapping) => (
                <tr key={mapping.id}>
                  <td><strong>{mapping.wbs_code}</strong><span>{mapping.wbs_name}</span></td>
                  <td>{mapping.cbs_code}</td>
                  <td>{mapping.control_account_id ? accountLabel(mapping.control_account_id) : "Unmapped"}</td>
                  <td>{mapping.planned_percent.toFixed(1)}%</td>
                  <td>{currency(mapping.planned_cost, project.currency)}</td>
                  <td>{currency(mapping.planned_value, project.currency)}</td>
                  <td>{statusLabel(mapping.status)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className={activeView === "progress" ? "viewPanel workspaceSection" : "viewPanel workspaceSection hidden"}>
        <div className="panelHeader">
          <h2>Progress Records</h2>
          <button className="linkButton" onClick={() => setActiveView("bp-entry-forms")} type="button">Open capture form</button>
        </div>
        <table>
          <thead>
            <tr>
              <th>Control Account</th>
              <th>Physical %</th>
              <th>Quantity</th>
              <th>Labor Hours</th>
              <th>Reported On</th>
            </tr>
          </thead>
          <tbody>
            {dashboard.latest_progress_records.map((record) => (
              <tr key={record.id}>
                <td>{accountLabel(record.control_account_id)}</td>
                <td>{record.physical_percent.toFixed(1)}%</td>
                <td>{record.quantity_installed.toLocaleString()}</td>
                <td>{record.labor_hours.toLocaleString()}</td>
                <td>{record.reported_on}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className={activeView === "cost" ? "viewPanel workspaceSection" : "viewPanel workspaceSection hidden"}>
        <div className="panelHeader">
          <h2>Actual Cost Records</h2>
          <button className="linkButton" onClick={() => setActiveView("bp-entry-forms")} type="button">Open capture form</button>
        </div>
        <table>
          <thead>
            <tr>
              <th>Control Account</th>
              <th>Source</th>
              <th>Amount</th>
              <th>Incurred On</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            {dashboard.latest_cost_records.map((record) => (
              <tr key={record.id}>
                <td>{accountLabel(record.control_account_id)}</td>
                <td>{statusLabel(record.source)}</td>
                <td>{currency(record.amount, project.currency)}</td>
                <td>{record.incurred_on}</td>
                <td>{record.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className={activeView === "awp" ? "viewPanel workspaceSection" : "viewPanel workspaceSection hidden"}>
        <div className="panelHeader">
          <h2>AWP Workface Readiness</h2>
          <button className="linkButton" onClick={() => setActiveView("bp-entry-forms")} type="button">Open AWP forms</button>
        </div>
        <div className="awpSummary">
          <article>
            <span>Readiness Score</span>
            <strong>{dashboard.awp_summary.readiness_score.toFixed(1)}%</strong>
            <small>{dashboard.awp_summary.ready_for_release} ready / {dashboard.awp_summary.total_packages} packages</small>
          </article>
          <article>
            <span>CWP / IWP</span>
            <strong>{dashboard.awp_summary.cwp_count} / {dashboard.awp_summary.iwp_count}</strong>
            <small>Construction and installation work packages</small>
          </article>
          <article className={dashboard.awp_summary.blocking_constraints ? "risk" : ""}>
            <span>Open Constraints</span>
            <strong>{dashboard.awp_summary.open_constraints}</strong>
            <small>{dashboard.awp_summary.blocking_constraints} blocking constraints</small>
          </article>
          <article className={dashboard.awp_summary.blocked_packages ? "risk" : ""}>
            <span>Blocked Packages</span>
            <strong>{dashboard.awp_summary.blocked_packages}</strong>
            <small>Constraint review before field release</small>
          </article>
        </div>
        <div className="viewSplit">
          <div>
            <div className="subHeader">
              <strong>Path of Construction Packages</strong>
              <span>{dashboard.work_packages.length} records</span>
            </div>
            <div className="workList">
              {dashboard.work_packages.map((workPackage) => {
                const openBlocking = (constraintsByPackage[workPackage.id] ?? []).filter((constraint) => constraint.status === "open" && constraint.blocking).length;
                return (
                  <article className={openBlocking ? "blockedPackage" : ""} key={workPackage.id}>
                    <strong>{workPackage.package_type} / {workPackage.code}</strong>
                    <span>{workPackage.title}</span>
                    <small>{workPackage.path_of_construction || "No path defined"} / {statusLabel(workPackage.readiness_status)}</small>
                    <div className="packageFacts">
                      <span>{workPackage.control_account_id ? accountLabel(workPackage.control_account_id) : "Area level"}</span>
                      <span>{workPackage.planned_start ?? "Pending"} to {workPackage.planned_finish ?? "Pending"}</span>
                      <span>{workPackage.progress_percent.toFixed(1)}% progress</span>
                      <span>{openBlocking} blockers</span>
                    </div>
                  </article>
                );
              })}
            </div>
          </div>
          <div>
            <div className="subHeader">
              <strong>Constraint Log</strong>
              <span>{dashboard.work_package_constraints.length} constraints</span>
            </div>
            <div className="workList">
              {dashboard.work_package_constraints.map((constraint) => (
                <article className={constraint.status === "open" && constraint.blocking ? "blockedPackage" : ""} key={constraint.id}>
                  <strong>{constraint.constraint_type} / {packageLabel(constraint.work_package_id)}</strong>
                  <span>{constraint.description}</span>
                  <small>{constraint.owner_role} / Required {constraint.required_by ?? "Pending"} / {statusLabel(constraint.status)}</small>
                  {constraint.status === "open" && (
                    <button
                      className="linkButton compact"
                      disabled={!canManageAwp || captureAction === `awp-constraint-${constraint.id}`}
                      onClick={() => handleConstraintClose(constraint)}
                      type="button"
                    >
                      {captureAction === `awp-constraint-${constraint.id}` ? "Closing..." : "Close Constraint"}
                    </button>
                  )}
                </article>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className={activeView === "changes" ? "viewPanel workspaceSection" : "viewPanel workspaceSection hidden"}>
        <div className="panelHeader">
          <h2>Change Management</h2>
          <button className="linkButton" onClick={() => setActiveView("bp-entry-forms")} type="button">Create change BP</button>
        </div>
        <div className="workList">
          {dashboard.changes.map((change) => (
            <article key={change.id}>
              <strong>{change.title}</strong>
              <span>{change.deviation}</span>
              <small>{currency(change.cost_impact, project.currency)} / {change.schedule_impact_days} days / {statusLabel(change.status)}</small>
            </article>
          ))}
        </div>
      </section>

      <section className={activeView === "claims" ? "viewPanel workspaceSection" : "viewPanel workspaceSection hidden"}>
        <div className="panelHeader">
          <h2>Claims / Forensic Entitlement</h2>
          <span>Notice / causation / impact / quantum / evidence</span>
        </div>
        <div className="claimSummary">
          <article>
            <span>Forensic Readiness</span>
            <strong>{dashboard.claims_forensic_summary.forensic_readiness_score.toFixed(1)}%</strong>
            <small>Weighted from notices, impact analysis and entitlement evidence</small>
          </article>
          <article className={dashboard.claims_forensic_summary.late_notices ? "risk" : ""}>
            <span>Notice Compliance</span>
            <strong>{dashboard.claims_forensic_summary.compliant_notices}/{dashboard.claims_forensic_summary.notice_count}</strong>
            <small>{dashboard.claims_forensic_summary.late_notices} late notices / {dashboard.claims_forensic_summary.total_claims} claims</small>
          </article>
          <article>
            <span>Quantified Claims</span>
            <strong>{dashboard.claims_forensic_summary.quantified_claims}</strong>
            <small>{dashboard.claims_forensic_summary.impact_analyses} impact analyses registered</small>
          </article>
          <article className={dashboard.claim_entitlement_summary.cumulative_gap_items ? "risk" : ""}>
            <span>Claimed Impact</span>
            <strong>{currency(dashboard.claims_forensic_summary.total_claimed_cost, project.currency)}</strong>
            <small>{dashboard.claims_forensic_summary.total_schedule_impact_days} schedule days / {dashboard.claim_entitlement_summary.gap_items} entitlement gaps</small>
          </article>
        </div>

        <div className="forensicWorkspace">
          <div>
            <div className="subHeader">
              <strong>Contractual Notices</strong>
              <span>{dashboard.contract_notices.length} records</span>
            </div>
            <div className="noticeGrid">
              {dashboard.contract_notices.map((notice) => (
                <article className={notice.compliance_status === "late" ? "late" : "compliant"} key={notice.id}>
                  <div>
                    <strong>{notice.reference || `Notice ${notice.id}`}</strong>
                    <span>{statusLabel(notice.compliance_status)}</span>
                  </div>
                  <p>{notice.subject}</p>
                  <small>Event {notice.event_date ?? "pending"} / due {notice.due_date ?? "pending"} / issued {notice.notice_date ?? "pending"}</small>
                </article>
              ))}
            </div>
          </div>
          <div>
            <div className="subHeader">
              <strong>Impact Analysis</strong>
              <span>{dashboard.claim_impact_analyses.length} analyses</span>
            </div>
            <div className="impactGrid">
              {dashboard.claim_impact_analyses.map((analysis) => (
                <article key={analysis.id}>
                  <div>
                    <strong>{analysis.method}</strong>
                    <span>{(analysis.confidence_score * 100).toFixed(0)}% confidence</span>
                  </div>
                  <p>{analysis.impacted_activity}</p>
                  <small>{currency(analysis.cost_impact, project.currency)} / {analysis.schedule_impact_days} days / {analysis.productivity_loss_percent.toFixed(1)}% productivity loss</small>
                </article>
              ))}
            </div>
          </div>
        </div>

        <div className="workList">
          {dashboard.claims.map((claim) => {
            const entitlementItems = entitlementByClaim[claim.id] ?? [];
            const claimNotices = noticesByClaim[claim.id] ?? [];
            const claimImpacts = impactByClaim[claim.id] ?? [];
            const claimScore = entitlementItems.length
              ? Math.round((entitlementItems.reduce((total, item) => total + item.score * item.weight, 0) / entitlementItems.reduce((total, item) => total + item.weight, 0)) * 100)
              : 0;
            const claimedCost = claimImpacts.reduce((total, item) => total + item.cost_impact, 0);
            const claimedDays = claimImpacts.reduce((total, item) => total + item.schedule_impact_days, 0);
            return (
              <article className="claimCard" key={claim.id}>
                <div className="claimHeader">
                  <div>
                    <strong>{claim.title}</strong>
                    <span>{claim.causality}</span>
                  </div>
                  <div>
                    <strong>{claimScore}%</strong>
                    <small>{statusLabel(claim.status)}</small>
                  </div>
                </div>
                <p>{claim.impact}</p>
                <small>{claim.evidence_summary}</small>
                <div className="claimTrace">
                  <span>{claimNotices.length} notices</span>
                  <span>{claimImpacts.length} impact analyses</span>
                  <span>{currency(claimedCost, project.currency)} / {claimedDays} days</span>
                </div>
                <div className="entitlementMatrix">
                  {entitlementItems.map((item) => (
                    <article className={`entitlementItem ${item.status}`} key={item.id}>
                      <div>
                        <span>{item.practice_source} / {item.category}</span>
                        <strong>{item.element}</strong>
                      </div>
                      <p>{item.requirement}</p>
                      <small>{item.assessment}</small>
                      <div className="entitlementMeta">
                        <span>{item.evidence_ref || "No evidence linked"}</span>
                        <strong>{statusLabel(item.status)} / {(item.score * 100).toFixed(0)}%</strong>
                      </div>
                    </article>
                  ))}
                </div>
              </article>
            );
          })}
        </div>
      </section>

      <section className={activeView === "contracts" ? "viewPanel workspaceSection" : "viewPanel workspaceSection hidden"}>
        <div className="panelHeader">
          <h2>Contract Administration</h2>
          <button className="linkButton" onClick={() => setActiveView("bp-entry-forms")} type="button">Open contract forms</button>
        </div>
        <div className="contractGrid">
          <div>
            <strong>Contracts</strong>
            <div className="workList">
              {dashboard.contracts.map((contract) => (
                <article key={contract.id}>
                  <strong>{contract.code} / {contract.counterparty}</strong>
                  <span>{contract.title}</span>
                  <small>{currency(contract.value, project.currency)} / {statusLabel(contract.status)}</small>
                </article>
              ))}
            </div>
          </div>
          <div>
            <strong>Communications</strong>
            <div className="workList">
              {dashboard.communications.map((communication) => (
                <article key={communication.id}>
                  <strong>{statusLabel(communication.communication_type)} / {communication.sent_on}</strong>
                  <span>{communication.subject}</span>
                  <small>{communication.reference || "No reference"}</small>
                </article>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className={activeView === "documents" ? "viewPanel workspaceSection" : "viewPanel workspaceSection hidden"}>
        <div className="panelHeader">
          <h2>Document Traceability</h2>
          <button className="linkButton" onClick={() => setActiveView("bp-entry-forms")} type="button">Link document</button>
        </div>
        <div className="documentGrid">
          {dashboard.documents.map((document) => (
            <article key={document.id}>
              <strong>{document.title}</strong>
              <span>{document.doc_type} / {document.linked_entity_type}</span>
              <small>{document.uri}</small>
            </article>
          ))}
        </div>
      </section>

      <section className={activeView === "business-processes" ? "workflowShell workspaceSection" : "workflowShell workspaceSection hidden"} id="workflow-record">
        <aside className="processRail">
          <div className="railHeader">
            <span>Business Processes</span>
            <strong>Project Control Shell</strong>
          </div>
          {["Project Shell", "Schedule Intake", "AWP Readiness", "Progress Update", "Cost Actuals", "Change Request", "Contract Notice", "Claim Impact", "Document Link", "Decision Action"].map((item, index) => (
            <button className={index === 0 ? "railItem active" : "railItem"} key={item}>
              <span>{item}</span>
              <strong>{item === "Schedule Intake" ? (workflowInstance ? "Open" : "Waiting") : item === "AWP Readiness" ? `${dashboard.awp_summary.open_constraints} open` : item === "Contract Notice" ? `${dashboard.contract_notices.length} records` : item === "Claim Impact" ? `${dashboard.claim_impact_analyses.length} analyses` : item === "Project Shell" ? "Active" : "Ready"}</strong>
            </button>
          ))}
        </aside>

        <div className="workflowCanvas">
          <div className="workflowHeader">
            <div>
              <span>Workflow Routing</span>
              <h2>{workflowInstance ? neutralScheduleText(workflowInstance.title) : "Schedule upload triggers the control workflow"}</h2>
            </div>
            <div className="workflowMeta">
              <span>BP Status</span>
              <strong>{workflowInstance ? workflowStatus : "Waiting for schedule"}</strong>
            </div>
          </div>

          <div className="stageTrack">
            {workflowStages.map((stage, index) => (
              <React.Fragment key={stage.name}>
                <article className={`stageCard ${stage.tone}`}>
                  <span>{stage.status}</span>
                  <strong>{stage.name}</strong>
                  <p>{stage.detail}</p>
                  <small>Ball in Court: {stage.owner}</small>
                </article>
                {index < workflowStages.length - 1 && <ArrowRight className="stageArrow" size={18} />}
              </React.Fragment>
            ))}
          </div>

          <div className="recordRegistry">
            <div className="registryHeader">
              <h2>BP Records</h2>
              <span>{bpRecords.length} routed records</span>
            </div>
            <table>
              <thead>
                <tr>
                  <th>Record No.</th>
                  <th>Business Process</th>
                  <th>Title</th>
                  <th>Current Step</th>
                  <th>Ball in Court</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {bpRecords.map((record) => (
                  <tr className={selectedBpRecord?.record === record.record ? "selectedRecord" : ""} key={record.record}>
                    <td>
                      <button className="recordLink" onClick={() => setSelectedBpRecordNo(record.record)} type="button">
                        {record.record}
                      </button>
                    </td>
                    <td>{record.process}</td>
                    <td>{record.title}</td>
                    <td>{record.step}</td>
                    <td>{record.ballInCourt}</td>
                    <td><span className={`statusPill ${record.tone}`}>{record.status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {selectedBpRecord && (
            <div className="bpRecordDetail">
              <div>
                <span>Selected BP Record</span>
                <strong>{selectedBpRecord.record} / {selectedBpRecord.process}</strong>
              </div>
              <p>{selectedBpRecord.title}</p>
              <div className="detailFacts">
                <span>Current Step: <strong>{selectedBpRecord.step}</strong></span>
                <span>Ball in Court: <strong>{selectedBpRecord.ballInCourt}</strong></span>
                <span>Status: <strong>{selectedBpRecord.status}</strong></span>
              </div>
            </div>
          )}
        </div>

        <aside className="routingPanel">
          <div>
            <span>Current Step</span>
            <strong>{workflowInstance?.current_step ?? "Schedule Upload Gate"}</strong>
            <p>{workflowInstance ? "Validate schedule variance, cost exposure and contractual notice before routing to approval." : "Upload a schedule XML or XER file to create the BP record and start routing."}</p>
          </div>
          <div>
            <span>Required Attachments</span>
            <strong>{dashboard.documents.length} linked</strong>
            <p>Field reports, correspondence and supporting evidence remain tied to each BP record.</p>
          </div>
          <div>
            <span>Ball in Court</span>
            <strong>{workflowInstance?.ball_in_court ?? "Planner"}</strong>
            <p>{workflowInstance ? "The responsible role owns the next routed action in the control cycle." : "The planner must load the schedule before downstream controls can run."}</p>
          </div>
          <div>
            <span>Workflow Actions</span>
            <div className="actionStack">
              {workflowActionButtons.length ? workflowActionButtons.map((item) => (
                <button
                  className={`workflowAction ${item.tone}`}
                  disabled={routingAction !== null || !canRouteCurrentWorkflow}
                  key={item.action}
                  onClick={() => handleWorkflowAction(item.action)}
                  type="button"
                >
                  {routingAction === item.action ? "Routing..." : item.label}
                </button>
              )) : <strong>No pending action</strong>}
            </div>
            <p>Each action updates the routed step, ball-in-court and audit trail.</p>
          </div>
        </aside>
      </section>

      <section className={activeView === "control-dashboard" ? "kpiGrid workspaceSection" : "kpiGrid workspaceSection hidden"}>
        <article className="metric">
          <div><Gauge size={18} /><span>SPI</span></div>
          <strong>{kpi.spi.toFixed(3)}</strong>
          <small>Schedule performance</small>
          <StatusLight value={kpi.spi} />
        </article>
        <article className="metric">
          <div><ShieldCheck size={18} /><span>CPI</span></div>
          <strong>{kpi.cpi.toFixed(3)}</strong>
          <small>Cost performance</small>
          <StatusLight value={kpi.cpi} />
        </article>
        <article className="metric">
          <div><Activity size={18} /><span>VAC</span></div>
          <strong>{currency(kpi.vac, project.currency)}</strong>
          <small>Variance at completion</small>
        </article>
        <article className="metric">
          <div><GitBranch size={18} /><span>EAC</span></div>
          <strong>{currency(kpi.eac, project.currency)}</strong>
          <small>Estimate at completion</small>
        </article>
      </section>

      <details className={activeView === "bp-entry-forms" ? "bpFormsDrawer workspaceSection" : "bpFormsDrawer workspaceSection hidden"} id="bp-entry-forms" open={activeView === "bp-entry-forms"}>
        <summary>
          <span>BP Entry Forms</span>
          <strong>Progress, cost, AWP, change, contract notice, claim impact and document capture</strong>
        </summary>
      <section className="captureGrid">
        <div className="panel">
          <div className="panelHeader">
            <h2>Data Quality Gate</h2>
            <span>{dashboard.schedule_import ? `${dashboard.schedule_import.quality_score.toFixed(0)}%` : "waiting"}</span>
          </div>
          <div className="qualityList">
            {(dashboard.data_quality_gates ?? []).map((gate) => (
              <article key={gate.name}>
                <div>
                  <strong>{gate.name}</strong>
                  <span className={`qualityStatus ${gate.status.toLowerCase()}`}>{gate.status}</span>
                </div>
                <p>{gate.finding}</p>
                <small>{gate.owner_role} / Score {gate.score.toFixed(0)}%</small>
              </article>
            ))}
          </div>
        </div>

        <form className="panel captureForm" onSubmit={handleProgressSubmit}>
          <div className="panelHeader">
            <h2>Progress Capture</h2>
            <span>{(dashboard.latest_progress_records ?? []).length} recent</span>
          </div>
          <label>
            <span>Control Account</span>
            <select
              disabled={progressDisabled}
              onChange={(event) => setProgressDraft((current) => ({ ...current, control_account_id: event.target.value }))}
              required
              value={progressDraft.control_account_id}
            >
              {dashboard.control_accounts.map((account) => (
                <option key={account.id} value={account.id}>{account.code}</option>
              ))}
            </select>
          </label>
          <div className="formColumns">
            <label>
              <span>Physical %</span>
              <input
                disabled={progressDisabled}
                max="100"
                min="0"
                onChange={(event) => setProgressDraft((current) => ({ ...current, physical_percent: event.target.value }))}
                required
                step="0.01"
                type="number"
                value={progressDraft.physical_percent}
              />
            </label>
            <label>
              <span>Reported On</span>
              <input
                disabled={progressDisabled}
                onChange={(event) => setProgressDraft((current) => ({ ...current, reported_on: event.target.value }))}
                required
                type="date"
                value={progressDraft.reported_on}
              />
            </label>
          </div>
          <div className="formColumns">
            <label>
              <span>Quantity</span>
              <input
                disabled={progressDisabled}
                min="0"
                onChange={(event) => setProgressDraft((current) => ({ ...current, quantity_installed: event.target.value }))}
                required
                step="0.01"
                type="number"
                value={progressDraft.quantity_installed}
              />
            </label>
            <label>
              <span>Labor Hours</span>
              <input
                disabled={progressDisabled}
                min="0"
                onChange={(event) => setProgressDraft((current) => ({ ...current, labor_hours: event.target.value }))}
                required
                step="0.01"
                type="number"
                value={progressDraft.labor_hours}
              />
            </label>
          </div>
          <label>
            <span>Evidence Ref</span>
            <input
              disabled={progressDisabled}
              onChange={(event) => setProgressDraft((current) => ({ ...current, evidence_ref: event.target.value }))}
              placeholder="FIELD-REPORT-YYYY-MM-DD"
              value={progressDraft.evidence_ref}
            />
          </label>
          <button className="workflowAction primary" disabled={progressDisabled || captureAction !== null} type="submit">
            {captureAction === "progress" ? "Capturing..." : "Capture Progress"}
          </button>
          <div className="recentList">
            {(dashboard.latest_progress_records ?? []).slice(0, 2).map((record) => (
              <article key={record.id}>
                <strong>{record.physical_percent.toFixed(1)}% / {record.reported_on}</strong>
                <span>{accountLabel(record.control_account_id)}</span>
              </article>
            ))}
          </div>
        </form>

        <form className="panel captureForm" onSubmit={handleCostSubmit}>
          <div className="panelHeader">
            <h2>Actual Cost Capture</h2>
            <span>{(dashboard.latest_cost_records ?? []).length} recent</span>
          </div>
          <label>
            <span>Control Account</span>
            <select
              disabled={costDisabled}
              onChange={(event) => setCostDraft((current) => ({ ...current, control_account_id: event.target.value }))}
              required
              value={costDraft.control_account_id}
            >
              {dashboard.control_accounts.map((account) => (
                <option key={account.id} value={account.id}>{account.code}</option>
              ))}
            </select>
          </label>
          <div className="formColumns">
            <label>
              <span>Source</span>
              <select
                disabled={costDisabled}
                onChange={(event) => setCostDraft((current) => ({ ...current, source: event.target.value }))}
                required
                value={costDraft.source}
              >
                <option value="invoice">Invoice</option>
                <option value="payroll">Payroll</option>
                <option value="equipment">Equipment</option>
                <option value="materials">Materials</option>
                <option value="commitment">Commitment</option>
              </select>
            </label>
            <label>
              <span>Incurred On</span>
              <input
                disabled={costDisabled}
                onChange={(event) => setCostDraft((current) => ({ ...current, incurred_on: event.target.value }))}
                required
                type="date"
                value={costDraft.incurred_on}
              />
            </label>
          </div>
          <label>
            <span>Amount</span>
            <input
              disabled={costDisabled}
              min="0"
              onChange={(event) => setCostDraft((current) => ({ ...current, amount: event.target.value }))}
              required
              step="0.01"
              type="number"
              value={costDraft.amount}
            />
          </label>
          <label>
            <span>Description</span>
            <input
              disabled={costDisabled}
              onChange={(event) => setCostDraft((current) => ({ ...current, description: event.target.value }))}
              required
              value={costDraft.description}
            />
          </label>
          <button className="workflowAction primary" disabled={costDisabled || captureAction !== null} type="submit">
            {captureAction === "cost" ? "Capturing..." : "Capture Actual Cost"}
          </button>
          <div className="recentList">
            {(dashboard.latest_cost_records ?? []).slice(0, 2).map((record) => (
              <article key={record.id}>
                <strong>{currency(record.amount, project.currency)} / {statusLabel(record.source)}</strong>
                <span>{accountLabel(record.control_account_id)}</span>
              </article>
            ))}
          </div>
        </form>
      </section>

      <section className="phaseTwoGrid">
        <form className="panel captureForm" onSubmit={handleAwpSubmit}>
          <div className="panelHeader">
            <h2>AWP Package</h2>
            <span>{dashboard.work_packages.length} packages</span>
          </div>
          <div className="formColumns">
            <label>
              <span>Type</span>
              <select
                disabled={!canManageAwp || controlGateBlocked}
                onChange={(event) => setAwpDraft((current) => ({ ...current, package_type: event.target.value }))}
                value={awpDraft.package_type}
              >
                <option value="CWA">CWA</option>
                <option value="EWA">EWA</option>
                <option value="EWP">EWP</option>
                <option value="CWP">CWP</option>
                <option value="PWP">PWP</option>
                <option value="IWP">IWP</option>
              </select>
            </label>
            <label>
              <span>Sequence</span>
              <input
                disabled={!canManageAwp || controlGateBlocked}
                min="0"
                onChange={(event) => setAwpDraft((current) => ({ ...current, sequence_no: event.target.value }))}
                type="number"
                value={awpDraft.sequence_no}
              />
            </label>
          </div>
          <label>
            <span>Code</span>
            <input
              disabled={!canManageAwp || controlGateBlocked}
              onChange={(event) => setAwpDraft((current) => ({ ...current, code: event.target.value }))}
              placeholder="IWP-PIPE-001"
              required
              value={awpDraft.code}
            />
          </label>
          <label>
            <span>Title</span>
            <input
              disabled={!canManageAwp || controlGateBlocked}
              onChange={(event) => setAwpDraft((current) => ({ ...current, title: event.target.value }))}
              required
              value={awpDraft.title}
            />
          </label>
          <label>
            <span>Control Account</span>
            <select
              disabled={!canManageAwp || controlGateBlocked}
              onChange={(event) => setAwpDraft((current) => ({ ...current, control_account_id: event.target.value }))}
              value={awpDraft.control_account_id}
            >
              <option value="">Area level</option>
              {dashboard.control_accounts.map((account) => (
                <option key={account.id} value={account.id}>{account.code}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Parent Package</span>
            <select
              disabled={!canManageAwp || controlGateBlocked}
              onChange={(event) => setAwpDraft((current) => ({ ...current, parent_id: event.target.value }))}
              value={awpDraft.parent_id}
            >
              <option value="">No parent</option>
              {dashboard.work_packages.map((workPackage) => (
                <option key={workPackage.id} value={workPackage.id}>{workPackage.code}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Path of Construction</span>
            <textarea
              disabled={!canManageAwp || controlGateBlocked}
              onChange={(event) => setAwpDraft((current) => ({ ...current, path_of_construction: event.target.value }))}
              required
              value={awpDraft.path_of_construction}
            />
          </label>
          <div className="formColumns">
            <label>
              <span>Start</span>
              <input
                disabled={!canManageAwp || controlGateBlocked}
                onChange={(event) => setAwpDraft((current) => ({ ...current, planned_start: event.target.value }))}
                type="date"
                value={awpDraft.planned_start}
              />
            </label>
            <label>
              <span>Finish</span>
              <input
                disabled={!canManageAwp || controlGateBlocked}
                onChange={(event) => setAwpDraft((current) => ({ ...current, planned_finish: event.target.value }))}
                type="date"
                value={awpDraft.planned_finish}
              />
            </label>
          </div>
          <button className="workflowAction primary" disabled={!canManageAwp || controlGateBlocked || captureAction !== null} type="submit">
            {captureAction === "awp" ? "Creating..." : "Create AWP Package"}
          </button>
        </form>

        <form className="panel captureForm" onSubmit={handleConstraintSubmit}>
          <div className="panelHeader">
            <h2>AWP Constraint</h2>
            <span>{dashboard.awp_summary.open_constraints} open</span>
          </div>
          <label>
            <span>Work Package</span>
            <select
              disabled={!canManageAwp || !dashboard.work_packages.length}
              onChange={(event) => setConstraintDraft((current) => ({ ...current, work_package_id: event.target.value }))}
              required
              value={constraintDraft.work_package_id}
            >
              {dashboard.work_packages.map((workPackage) => (
                <option key={workPackage.id} value={workPackage.id}>{workPackage.code}</option>
              ))}
            </select>
          </label>
          <div className="formColumns">
            <label>
              <span>Type</span>
              <select
                disabled={!canManageAwp || !dashboard.work_packages.length}
                onChange={(event) => setConstraintDraft((current) => ({ ...current, constraint_type: event.target.value }))}
                value={constraintDraft.constraint_type}
              >
                <option value="Engineering">Engineering</option>
                <option value="Material">Material</option>
                <option value="Access">Access</option>
                <option value="Permit">Permit</option>
                <option value="Safety">Safety</option>
                <option value="Document">Document</option>
              </select>
            </label>
            <label>
              <span>Required By</span>
              <input
                disabled={!canManageAwp || !dashboard.work_packages.length}
                onChange={(event) => setConstraintDraft((current) => ({ ...current, required_by: event.target.value }))}
                type="date"
                value={constraintDraft.required_by}
              />
            </label>
          </div>
          <label>
            <span>Description</span>
            <textarea
              disabled={!canManageAwp || !dashboard.work_packages.length}
              onChange={(event) => setConstraintDraft((current) => ({ ...current, description: event.target.value }))}
              required
              value={constraintDraft.description}
            />
          </label>
          <label>
            <span>Owner Role</span>
            <input
              disabled={!canManageAwp || !dashboard.work_packages.length}
              onChange={(event) => setConstraintDraft((current) => ({ ...current, owner_role: event.target.value }))}
              required
              value={constraintDraft.owner_role}
            />
          </label>
          <label className="checkRow">
            <input
              checked={constraintDraft.blocking}
              disabled={!canManageAwp || !dashboard.work_packages.length}
              onChange={(event) => setConstraintDraft((current) => ({ ...current, blocking: event.target.checked }))}
              type="checkbox"
            />
            <span>Blocking readiness constraint</span>
          </label>
          <button className="workflowAction primary" disabled={!canManageAwp || !dashboard.work_packages.length || captureAction !== null} type="submit">
            {captureAction === "awp-constraint" ? "Registering..." : "Register Constraint"}
          </button>
        </form>

        <form className="panel captureForm" onSubmit={handleChangeSubmit}>
          <div className="panelHeader">
            <h2><GitBranch size={18} /> Change Control</h2>
            <span>{dashboard.changes.length} open</span>
          </div>
          <label>
            <span>Control Account</span>
            <select
              disabled={!canCreateChange || !dashboard.control_accounts.length}
              onChange={(event) => setChangeDraft((current) => ({ ...current, control_account_id: event.target.value }))}
              value={changeDraft.control_account_id}
            >
              {dashboard.control_accounts.map((account) => (
                <option key={account.id} value={account.id}>{account.code}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Title</span>
            <input
              disabled={!canCreateChange}
              onChange={(event) => setChangeDraft((current) => ({ ...current, title: event.target.value }))}
              required
              value={changeDraft.title}
            />
          </label>
          <label>
            <span>Deviation</span>
            <textarea
              disabled={!canCreateChange}
              onChange={(event) => setChangeDraft((current) => ({ ...current, deviation: event.target.value }))}
              required
              value={changeDraft.deviation}
            />
          </label>
          <div className="formColumns">
            <label>
              <span>Cost Impact</span>
              <input
                disabled={!canCreateChange}
                min="0"
                onChange={(event) => setChangeDraft((current) => ({ ...current, cost_impact: event.target.value }))}
                step="0.01"
                type="number"
                value={changeDraft.cost_impact}
              />
            </label>
            <label>
              <span>Days</span>
              <input
                disabled={!canCreateChange}
                onChange={(event) => setChangeDraft((current) => ({ ...current, schedule_impact_days: event.target.value }))}
                type="number"
                value={changeDraft.schedule_impact_days}
              />
            </label>
          </div>
          <button className="workflowAction primary" disabled={!canCreateChange || captureAction !== null} type="submit">
            {captureAction === "change" ? "Routing..." : "Create Change BP"}
          </button>
        </form>

        <form className="panel captureForm" onSubmit={handleContractSubmit}>
          <div className="panelHeader">
            <h2><BriefcaseBusiness size={18} /> Contracts</h2>
            <span>{dashboard.contracts.length} active</span>
          </div>
          <div className="formColumns">
            <label>
              <span>Code</span>
              <input
                disabled={!canManageContracts}
                onChange={(event) => setContractDraft((current) => ({ ...current, code: event.target.value }))}
                required
                value={contractDraft.code}
              />
            </label>
            <label>
              <span>Type</span>
              <select
                disabled={!canManageContracts}
                onChange={(event) => setContractDraft((current) => ({ ...current, contract_type: event.target.value }))}
                value={contractDraft.contract_type}
              >
                <option value="EPC">EPC</option>
                <option value="Services">Services</option>
                <option value="Supply">Supply</option>
                <option value="Construction">Construction</option>
              </select>
            </label>
          </div>
          <label>
            <span>Title</span>
            <input
              disabled={!canManageContracts}
              onChange={(event) => setContractDraft((current) => ({ ...current, title: event.target.value }))}
              required
              value={contractDraft.title}
            />
          </label>
          <label>
            <span>Counterparty</span>
            <input
              disabled={!canManageContracts}
              onChange={(event) => setContractDraft((current) => ({ ...current, counterparty: event.target.value }))}
              required
              value={contractDraft.counterparty}
            />
          </label>
          <label>
            <span>Value</span>
            <input
              disabled={!canManageContracts}
              min="0"
              onChange={(event) => setContractDraft((current) => ({ ...current, value: event.target.value }))}
              step="0.01"
              type="number"
              value={contractDraft.value}
            />
          </label>
          <button className="workflowAction primary" disabled={!canManageContracts || captureAction !== null} type="submit">
            {captureAction === "contract" ? "Registering..." : "Register Contract"}
          </button>
        </form>

        <form className="panel captureForm" onSubmit={handleCommunicationSubmit}>
          <div className="panelHeader">
            <h2><Send size={18} /> Communications</h2>
            <span>{dashboard.communications.length} recent</span>
          </div>
          <label>
            <span>Contract</span>
            <select
              disabled={!canManageContracts || !dashboard.contracts.length}
              onChange={(event) => setCommunicationDraft((current) => ({ ...current, contract_id: event.target.value }))}
              required
              value={communicationDraft.contract_id}
            >
              {dashboard.contracts.map((contract) => (
                <option key={contract.id} value={contract.id}>{contract.code}</option>
              ))}
            </select>
          </label>
          <div className="formColumns">
            <label>
              <span>Type</span>
              <select
                disabled={!canManageContracts || !dashboard.contracts.length}
                onChange={(event) => setCommunicationDraft((current) => ({ ...current, communication_type: event.target.value }))}
                value={communicationDraft.communication_type}
              >
                <option value="notice">Notice</option>
                <option value="letter">Letter</option>
                <option value="rfi">RFI</option>
                <option value="meeting_minute">Minute</option>
              </select>
            </label>
            <label>
              <span>Date</span>
              <input
                disabled={!canManageContracts || !dashboard.contracts.length}
                onChange={(event) => setCommunicationDraft((current) => ({ ...current, sent_on: event.target.value }))}
                required
                type="date"
                value={communicationDraft.sent_on}
              />
            </label>
          </div>
          <label>
            <span>Subject</span>
            <input
              disabled={!canManageContracts || !dashboard.contracts.length}
              onChange={(event) => setCommunicationDraft((current) => ({ ...current, subject: event.target.value }))}
              required
              value={communicationDraft.subject}
            />
          </label>
          <label>
            <span>Reference</span>
            <input
              disabled={!canManageContracts || !dashboard.contracts.length}
              onChange={(event) => setCommunicationDraft((current) => ({ ...current, reference: event.target.value }))}
              value={communicationDraft.reference}
            />
          </label>
          <button className="workflowAction primary" disabled={!canManageContracts || !dashboard.contracts.length || captureAction !== null} type="submit">
            {captureAction === "communication" ? "Issuing..." : "Issue Communication"}
          </button>
        </form>

        <form className="panel captureForm" onSubmit={handleNoticeSubmit}>
          <div className="panelHeader">
            <h2><ShieldCheck size={18} /> Contract Notices</h2>
            <span>{dashboard.contract_notices.length} records</span>
          </div>
          <div className="formColumns">
            <label>
              <span>Contract</span>
              <select
                disabled={!canManageContracts || !dashboard.contracts.length}
                onChange={(event) => setNoticeDraft((current) => ({ ...current, contract_id: event.target.value }))}
                value={noticeDraft.contract_id}
              >
                {dashboard.contracts.map((contract) => (
                  <option key={contract.id} value={contract.id}>{contract.code}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Claim</span>
              <select
                disabled={!canManageClaims || !dashboard.claims.length}
                onChange={(event) => setNoticeDraft((current) => ({ ...current, claim_id: event.target.value }))}
                value={noticeDraft.claim_id}
              >
                {dashboard.claims.map((claim) => (
                  <option key={claim.id} value={claim.id}>{claim.title}</option>
                ))}
              </select>
            </label>
          </div>
          <div className="formColumns">
            <label>
              <span>Type</span>
              <select
                disabled={!canManageContracts}
                onChange={(event) => setNoticeDraft((current) => ({ ...current, notice_type: event.target.value }))}
                value={noticeDraft.notice_type}
              >
                <option value="contractual_notice">Contractual Notice</option>
                <option value="potential_claim">Potential Claim</option>
                <option value="time_bar_response">Time Bar Response</option>
              </select>
            </label>
            <label>
              <span>Reference</span>
              <input
                disabled={!canManageContracts}
                onChange={(event) => setNoticeDraft((current) => ({ ...current, reference: event.target.value }))}
                placeholder="CON-001-NOT-001"
                value={noticeDraft.reference}
              />
            </label>
          </div>
          <label>
            <span>Subject</span>
            <input
              disabled={!canManageContracts}
              onChange={(event) => setNoticeDraft((current) => ({ ...current, subject: event.target.value }))}
              required
              value={noticeDraft.subject}
            />
          </label>
          <div className="formColumns">
            <label>
              <span>Event Date</span>
              <input
                disabled={!canManageContracts}
                onChange={(event) => setNoticeDraft((current) => ({ ...current, event_date: event.target.value }))}
                type="date"
                value={noticeDraft.event_date}
              />
            </label>
            <label>
              <span>Due Date</span>
              <input
                disabled={!canManageContracts}
                onChange={(event) => setNoticeDraft((current) => ({ ...current, due_date: event.target.value }))}
                type="date"
                value={noticeDraft.due_date}
              />
            </label>
          </div>
          <label>
            <span>Notice Date</span>
            <input
              disabled={!canManageContracts}
              onChange={(event) => setNoticeDraft((current) => ({ ...current, notice_date: event.target.value }))}
              required
              type="date"
              value={noticeDraft.notice_date}
            />
          </label>
          <button className="workflowAction primary" disabled={!canManageContracts || !dashboard.contracts.length || captureAction !== null} type="submit">
            {captureAction === "contract-notice" ? "Issuing..." : "Issue Notice"}
          </button>
        </form>

        <form className="panel captureForm" onSubmit={handleClaimImpactSubmit}>
          <div className="panelHeader">
            <h2><GitBranch size={18} /> Claim Impact</h2>
            <span>{dashboard.claim_impact_analyses.length} analyses</span>
          </div>
          <label>
            <span>Claim</span>
            <select
              disabled={!canManageClaims || !dashboard.claims.length}
              onChange={(event) => setClaimImpactDraft((current) => ({ ...current, claim_id: event.target.value }))}
              required
              value={claimImpactDraft.claim_id}
            >
              {dashboard.claims.map((claim) => (
                <option key={claim.id} value={claim.id}>{claim.title}</option>
              ))}
            </select>
          </label>
          <div className="formColumns">
            <label>
              <span>Method</span>
              <select
                disabled={!canManageClaims || !dashboard.claims.length}
                onChange={(event) => setClaimImpactDraft((current) => ({ ...current, method: event.target.value }))}
                value={claimImpactDraft.method}
              >
                <option value="Time Impact Analysis">Time Impact Analysis</option>
                <option value="Measured Mile / Productivity">Measured Mile / Productivity</option>
                <option value="Impacted As-Planned">Impacted As-Planned</option>
                <option value="Window Analysis">Window Analysis</option>
              </select>
            </label>
            <label>
              <span>Impacted Activity</span>
              <input
                disabled={!canManageClaims || !dashboard.claims.length}
                onChange={(event) => setClaimImpactDraft((current) => ({ ...current, impacted_activity: event.target.value }))}
                placeholder="Activity / control account"
                value={claimImpactDraft.impacted_activity}
              />
            </label>
          </div>
          <label>
            <span>Cause</span>
            <textarea
              disabled={!canManageClaims || !dashboard.claims.length}
              onChange={(event) => setClaimImpactDraft((current) => ({ ...current, cause: event.target.value }))}
              value={claimImpactDraft.cause}
            />
          </label>
          <label>
            <span>Effect</span>
            <textarea
              disabled={!canManageClaims || !dashboard.claims.length}
              onChange={(event) => setClaimImpactDraft((current) => ({ ...current, effect: event.target.value }))}
              value={claimImpactDraft.effect}
            />
          </label>
          <div className="formColumns">
            <label>
              <span>Days</span>
              <input
                disabled={!canManageClaims || !dashboard.claims.length}
                onChange={(event) => setClaimImpactDraft((current) => ({ ...current, schedule_impact_days: event.target.value }))}
                type="number"
                value={claimImpactDraft.schedule_impact_days}
              />
            </label>
            <label>
              <span>Cost Impact</span>
              <input
                disabled={!canManageClaims || !dashboard.claims.length}
                min="0"
                onChange={(event) => setClaimImpactDraft((current) => ({ ...current, cost_impact: event.target.value }))}
                step="0.01"
                type="number"
                value={claimImpactDraft.cost_impact}
              />
            </label>
          </div>
          <div className="formColumns">
            <label>
              <span>Productivity Loss %</span>
              <input
                disabled={!canManageClaims || !dashboard.claims.length}
                min="0"
                onChange={(event) => setClaimImpactDraft((current) => ({ ...current, productivity_loss_percent: event.target.value }))}
                step="0.01"
                type="number"
                value={claimImpactDraft.productivity_loss_percent}
              />
            </label>
            <label>
              <span>Confidence</span>
              <input
                disabled={!canManageClaims || !dashboard.claims.length}
                max="1"
                min="0"
                onChange={(event) => setClaimImpactDraft((current) => ({ ...current, confidence_score: event.target.value }))}
                step="0.01"
                type="number"
                value={claimImpactDraft.confidence_score}
              />
            </label>
          </div>
          <label>
            <span>Evidence Ref</span>
            <input
              disabled={!canManageClaims || !dashboard.claims.length}
              onChange={(event) => setClaimImpactDraft((current) => ({ ...current, evidence_ref: event.target.value }))}
              placeholder="edms:// or field report package"
              value={claimImpactDraft.evidence_ref}
            />
          </label>
          <button className="workflowAction primary" disabled={!canManageClaims || !dashboard.claims.length || captureAction !== null} type="submit">
            {captureAction === "claim-impact" ? "Analyzing..." : "Add Impact Analysis"}
          </button>
        </form>

        <form className="panel captureForm" onSubmit={handleDocumentSubmit}>
          <div className="panelHeader">
            <h2><FilePlus2 size={18} /> Documents</h2>
            <span>{dashboard.documents.length} linked</span>
          </div>
          <label>
            <span>Linked Record</span>
            <select
              disabled={!linkedEntityOptions.length}
              onChange={(event) => {
                const [linkedType, linkedId] = event.target.value.split(":");
                setDocumentDraft((current) => ({ ...current, linked_entity_type: linkedType, linked_entity_id: linkedId }));
              }}
              value={`${documentDraft.linked_entity_type}:${documentDraft.linked_entity_id}`}
            >
              {linkedEntityOptions.map((option) => (
                <option key={`${option.type}-${option.id}`} value={`${option.type}:${option.id}`}>{option.label}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Title</span>
            <input
              disabled={!linkedEntityOptions.length}
              onChange={(event) => setDocumentDraft((current) => ({ ...current, title: event.target.value }))}
              required
              value={documentDraft.title}
            />
          </label>
          <div className="formColumns">
            <label>
              <span>Type</span>
              <input
                disabled={!linkedEntityOptions.length}
                onChange={(event) => setDocumentDraft((current) => ({ ...current, doc_type: event.target.value }))}
                required
                value={documentDraft.doc_type}
              />
            </label>
            <label>
              <span>URI</span>
              <input
                disabled={!linkedEntityOptions.length}
                onChange={(event) => setDocumentDraft((current) => ({ ...current, uri: event.target.value }))}
                placeholder="edms://..."
                required
                value={documentDraft.uri}
              />
            </label>
          </div>
          <button className="workflowAction primary" disabled={!linkedEntityOptions.length || captureAction !== null} type="submit">
            {captureAction === "document" ? "Linking..." : "Link Document"}
          </button>
        </form>
      </section>
      </details>

      <section className={activeView === "control-dashboard" ? "mainGrid workspaceSection" : "mainGrid workspaceSection hidden"} id="control-dashboard">
        <div className="panel wide">
          <div className="panelHeader">
            <h2>S-Curve Control View</h2>
            <span>PV / EV / AC</span>
          </div>
          <ResponsiveContainer width="100%" height={270}>
            <AreaChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#d8dee5" />
              <XAxis dataKey="period" />
              <YAxis tickFormatter={(value) => `$${Number(value) / 1000000}M`} />
              <Tooltip formatter={(value) => currency(Number(value), project.currency)} />
              <Area type="monotone" dataKey="PV" stroke="#52616f" fill="#dce3ea" strokeWidth={2} />
              <Area type="monotone" dataKey="EV" stroke="#0f8b8d" fill="#bde7e5" strokeWidth={2} />
              <Area type="monotone" dataKey="AC" stroke="#c85a3a" fill="#f2c5b8" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <h2>Control Core Loop</h2>
            <ClipboardCheck size={18} />
          </div>
          <div className="loopList">
            {dashboard.loop.map((item) => (
              <div key={item.step}>
                <strong>{item.step}</strong>
                <span>{item.description}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <h2>Early Warnings</h2>
            <span>{redAlerts} critical</span>
          </div>
          <div className="stack">
            {dashboard.alerts.map((alert) => (
              <article className={`alert ${alert.severity}`} key={alert.id}>
                <strong>{alert.rule}</strong>
                <span>{alert.message}</span>
                <small>{alert.recommendation}</small>
              </article>
            ))}
          </div>
        </div>

        <div className="panel wide">
          <div className="panelHeader">
            <h2>EAC Forecast Scenarios</h2>
            <span>{dashboard.forecast_scenarios.length} scenarios</span>
          </div>
          <div className="scenarioGrid">
            {dashboard.forecast_scenarios.map((scenario) => (
              <article className={`scenarioCard ${scenario.completion_risk}`} key={scenario.id}>
                <div>
                  <strong>{scenario.name}</strong>
                  <span>{scenario.method}</span>
                </div>
                <div className="scenarioNumbers">
                  <span>EAC <strong>{currency(scenario.eac, project.currency)}</strong></span>
                  <span>VAC <strong>{currency(scenario.vac, project.currency)}</strong></span>
                  <span>CPI/SPI <strong>{scenario.cpi_factor.toFixed(3)} / {scenario.spi_factor.toFixed(3)}</strong></span>
                </div>
                <small>{statusLabel(scenario.completion_risk)} risk / {scenario.period_label}</small>
              </article>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <h2>Productivity</h2>
            <span>{dashboard.productivity_summary.low_productivity_accounts} low accounts</span>
          </div>
          <div className="productivityCard">
            <strong>{dashboard.productivity_summary.productivity_index.toFixed(3)}</strong>
            <span>Productivity index</span>
            <small>{dashboard.productivity_summary.total_quantity.toLocaleString()} qty / {dashboard.productivity_summary.total_labor_hours.toLocaleString()} labor hours</small>
          </div>
        </div>

        <div className="panel wide">
          <div className="panelHeader">
            <h2>Control Accounts</h2>
            <span>{dashboard.control_accounts.length} mapped from schedule</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>Account</th>
                <th>Owner</th>
                <th>Discipline</th>
                <th>PV</th>
                <th>EV</th>
                <th>AC</th>
                <th>SPI</th>
                <th>CPI</th>
              </tr>
            </thead>
            <tbody>
              {dashboard.control_accounts.map((account) => {
                const accountKpi = dashboard.account_kpis.find((item) => item.control_account_id === account.id);
                return (
                  <tr key={account.id}>
                    <td><strong>{account.code}</strong><span>{account.name}</span></td>
                    <td>{account.responsible}</td>
                    <td>{account.discipline}</td>
                    <td>{currency(accountKpi?.pv ?? 0, project.currency)}</td>
                    <td>{currency(accountKpi?.ev ?? 0, project.currency)}</td>
                    <td>{currency(accountKpi?.ac ?? 0, project.currency)}</td>
                    <td>{accountKpi?.spi.toFixed(3)}</td>
                    <td>{accountKpi?.cpi.toFixed(3)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="panel wide">
          <div className="panelHeader">
            <h2>Schedule QA & Baseline</h2>
            <span>{dashboard.schedule_findings.length} findings / {dashboard.baseline_versions.length} baselines</span>
          </div>
          <div className="contractGrid">
            <div>
              <strong>Validation Findings</strong>
              <div className="workList">
                {dashboard.schedule_findings.length ? dashboard.schedule_findings.slice(0, 5).map((finding) => (
                  <article key={finding.id}>
                    <strong>{finding.check_code} / {statusLabel(finding.severity)}</strong>
                    <span>{finding.message}</span>
                    <small>{finding.item_count} items / weight {finding.weight}</small>
                  </article>
                )) : (
                  <article>
                    <strong>No findings</strong>
                    <span>The active schedule has no stored QA findings.</span>
                  </article>
                )}
              </div>
            </div>
            <div>
              <strong>Baseline Versions</strong>
              <div className="workList">
                {dashboard.baseline_versions.length ? dashboard.baseline_versions.map((baseline) => (
                  <article key={baseline.id}>
                    <strong>BL-{baseline.version_no.toString().padStart(2, "0")} / {statusLabel(baseline.status)}</strong>
                    <span>{neutralScheduleText(baseline.name)}</span>
                    <small>{baseline.data_date ?? "No data date"} / Quality {baseline.quality_score.toFixed(0)}%</small>
                  </article>
                )) : (
                  <article>
                    <strong>No baseline versions</strong>
                    <span>Load a source schedule to create the first baseline version.</span>
                  </article>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="panel wide">
          <div className="panelHeader">
            <h2>BP Engine / uDesigner</h2>
            <span>{dashboard.process_templates.length} persistent templates</span>
          </div>
          <div className="designerSummary">
            <div>
              <strong>{dashboard.process_templates.reduce((total, template) => total + template.step_templates.length, 0)}</strong>
              <span>configured steps</span>
            </div>
            <div>
              <strong>{dashboard.process_templates.reduce((total, template) => total + template.transitions.length, 0)}</strong>
              <span>workflow transitions</span>
            </div>
            <div>
              <strong>{dashboard.process_templates.filter((template) => template.status.toLowerCase() === "active").length}</strong>
              <span>active BP definitions</span>
            </div>
          </div>
          <div className="templateGrid">
            {dashboard.process_templates.map((template) => (
              <article key={template.code}>
                <div>
                  <strong>{template.name}</strong>
                  <span>{template.code} / {template.category} / v{template.version_no}</span>
                </div>
                <p>{template.description || "Business process controlled by the configurable workflow engine."}</p>
                <small>Form: {template.form_schema.join(", ")}</small>
                <small>Workflow: {template.workflow_steps.join(" -> ")}</small>
                <small>Transitions: {template.transitions.map((transition) => `${transition.label || statusLabel(transition.action)}: ${transition.from_step} -> ${transition.to_step}`).join(" / ") || "Pending"}</small>
                <small>Roles: {template.roles.join(", ")}</small>
                <span className="templateStatus">{template.status}</span>
              </article>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <h2>Project Team & Roles</h2>
            <span>{dashboard.project_team.length} users</span>
          </div>
          <div className="teamList">
            {dashboard.project_team.map((member) => (
              <article key={member.membership.id}>
                <strong>{member.user.full_name}</strong>
                <span>{member.membership.role}</span>
                <small>{member.user.title}</small>
              </article>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <h2>Audit Trail</h2>
            <span>{dashboard.audit_logs.length} recent</span>
          </div>
          <div className="auditList">
            {dashboard.audit_logs.length ? dashboard.audit_logs.map((log) => (
              <article key={log.id}>
                <strong>{statusLabel(log.action.replace("workflow.", ""))}</strong>
                <span>{log.actor} / {log.entity_type} #{log.entity_id ?? "-"}</span>
                <small>{new Date(log.created_at).toLocaleString()}</small>
              </article>
            )) : (
              <article>
                <strong>No workflow actions yet</strong>
                <span>Route a BP to create an audit entry.</span>
              </article>
            )}
          </div>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <h2>Decision Layer</h2>
            <Bot size={18} />
          </div>
          <p className="aiBrief">{dashboard.ai_brief}</p>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <h2>Changes & Claims</h2>
            <FileText size={18} />
          </div>
          <div className="workList">
            {[...dashboard.changes, ...dashboard.claims].map((item) => (
              <article key={`${item.title}-${item.id}`}>
                <strong>{item.title}</strong>
                <span>{item.status}</span>
              </article>
            ))}
          </div>
        </div>

        <div className="panel wide">
          <div className="panelHeader">
            <h2>Contract Administration</h2>
            <span>{dashboard.contracts.length} contracts / {dashboard.communications.length} communications</span>
          </div>
          <div className="contractGrid">
            <div>
              <strong>Contracts</strong>
              <div className="workList">
                {dashboard.contracts.map((contract) => (
                  <article key={contract.id}>
                    <strong>{contract.code} / {contract.counterparty}</strong>
                    <span>{contract.title}</span>
                    <small>{currency(contract.value, project.currency)} / {statusLabel(contract.status)}</small>
                  </article>
                ))}
              </div>
            </div>
            <div>
              <strong>Communications</strong>
              <div className="workList">
                {dashboard.communications.map((communication) => (
                  <article key={communication.id}>
                    <strong>{statusLabel(communication.communication_type)} / {communication.sent_on}</strong>
                    <span>{communication.subject}</span>
                    <small>{communication.reference || "No reference"}</small>
                  </article>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="panel wide">
          <div className="panelHeader">
            <h2>Document Traceability</h2>
            <span>{dashboard.documents.length} linked records</span>
          </div>
          <div className="documentGrid">
            {dashboard.documents.map((document) => (
              <article key={document.id}>
                <strong>{document.title}</strong>
                <span>{document.doc_type} / {document.linked_entity_type}</span>
                <small>{document.uri}</small>
              </article>
            ))}
          </div>
        </div>
      </section>
        </div>
      </section>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<App />);

