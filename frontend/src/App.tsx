import { useEffect, useMemo, useState, type ChangeEvent, type FormEvent, type ReactNode } from "react";
import { Building2, Download, FileUp, GitBranch, PackagePlus, Save, ShieldCheck } from "lucide-react";
import { Navigate, Route, Routes } from "react-router-dom";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { admin as adminApi } from "./api/admin";
import { ApiError } from "./api/client";
import { dashboard as dashboardApi } from "./api/dashboard";
import { integratedControl as integratedControlApi } from "./api/integratedControl";
import { projects as projectsApi } from "./api/projects";
import ProductLogo from "./components/ProductLogo";
import { useAuthStore } from "./store/auth";
import { useProjectStore } from "./store/project";
import type {
  ActivitySheet,
  ActivitySheetRecostRun,
  ActivitySheetRow,
  ActivitySheetWbsRow,
  BusinessProcessLineItem,
  BusinessProcessLineItemRevision,
  BusinessProcessPolicy,
  CloseoutReport,
  ControlAccount,
  ControlAgentRun,
  CostBreakdownStructure,
  CostCode,
  Dashboard,
  ForecastFundingReport,
  IntegratedControlMatrixRow,
  Project,
  ProjectOperationalSetup,
  RateSheet,
  ReconciliationReport,
  RoleProfile,
  User,
  WbsNode,
} from "./types";
import LoginView from "./views/LoginView";

function RequireAuth({ children }: { children: ReactNode }) {
  const { token } = useAuthStore();
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

type ControlFlowView =
  | "dashboard"
  | "setup"
  | "baseline"
  | "progress"
  | "costs"
  | "integrated-control"
  | "decisions"
  | "evidence"
  | "work-packages"
  | "admin";

function isUnauthorizedApiError(err: unknown) {
  return err instanceof ApiError && err.status === 401;
}

function AppShell() {
  const { token, user, logout } = useAuthStore();
  const { dashboard, selectedProjectId, setDashboard, setSelectedProject } = useProjectStore();
  const [projectList, setProjectList] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [projectDraft, setProjectDraft] = useState({
    calendar_base: "5x8 Colombia",
    code: "",
    control_level: "control_account",
    funding_required: true,
    authorization_date: "",
    authorization_ref: "",
    name: "",
    owner: "",
    phase: "Planning",
    currency: "USD",
    status: "draft",
    start_date: "",
    finish_date: "",
  });
  const [projectAction, setProjectAction] = useState(false);
  const [projectMessage, setProjectMessage] = useState<string | null>(null);
  const [projectError, setProjectError] = useState<string | null>(null);
  const [showProjectCreate, setShowProjectCreate] = useState(false);
  const [operationalSetup, setOperationalSetup] = useState<ProjectOperationalSetup | null>(null);
  const [activitySheets, setActivitySheets] = useState<ActivitySheet[]>([]);
  const [activitySheetRows, setActivitySheetRows] = useState<ActivitySheetRow[]>([]);
  const [activitySheetWbsRows, setActivitySheetWbsRows] = useState<ActivitySheetWbsRow[]>([]);
  const [setupDraft, setSetupDraft] = useState({
    project_number: "",
    setup_template: "Capital Project Controls Template",
    attribute_form: "Project Attribute Form",
    permissions_configured: true,
    modules_configured: true,
    cost_sheet_ready: true,
    funding_sheet_ready: true,
    p6_mapping_ready: true,
    status: "ready",
  });
  const [setupAction, setSetupAction] = useState(false);
  const [setupMessage, setSetupMessage] = useState<string | null>(null);
  const [setupError, setSetupError] = useState<string | null>(null);
  const [activityAction, setActivityAction] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [roles, setRoles] = useState<RoleProfile[]>([]);
  const [userDraft, setUserDraft] = useState({
    email: "",
    full_name: "",
    password: "1234",
    role: "Control Manager",
    title: "",
  });
  const [userAction, setUserAction] = useState(false);
  const [userMessage, setUserMessage] = useState<string | null>(null);
  const [userError, setUserError] = useState<string | null>(null);
  const [integratedMatrix, setIntegratedMatrix] = useState<IntegratedControlMatrixRow[]>([]);
  const [forecastFunding, setForecastFunding] = useState<ForecastFundingReport | null>(null);
  const [closeoutReport, setCloseoutReport] = useState<CloseoutReport | null>(null);
  const [wbsCatalog, setWbsCatalog] = useState<WbsNode[]>([]);
  const [controlAccounts, setControlAccounts] = useState<ControlAccount[]>([]);
  const [cbsCatalog, setCbsCatalog] = useState<CostBreakdownStructure[]>([]);
  const [costCodes, setCostCodes] = useState<CostCode[]>([]);
  const [rateSheets, setRateSheets] = useState<RateSheet[]>([]);
  const [reconciliationReport, setReconciliationReport] = useState<ReconciliationReport | null>(null);
  const [bpPolicies, setBpPolicies] = useState<BusinessProcessPolicy[]>([]);
  const [bpLineItems, setBpLineItems] = useState<BusinessProcessLineItem[]>([]);
  const [bpLineItemRevisions, setBpLineItemRevisions] = useState<BusinessProcessLineItemRevision[]>([]);
  const [recostRuns, setRecostRuns] = useState<ActivitySheetRecostRun[]>([]);
  const [controlAgentRuns, setControlAgentRuns] = useState<ControlAgentRun[]>([]);
  const [integratedError, setIntegratedError] = useState<string | null>(null);
  const [fbsDraft, setFbsDraft] = useState({
    code: "",
    source_of_funds: "",
    funding_type: "AFE",
    authorization_ref: "",
    approved_amount: "",
    currency: "USD",
    status: "approved",
  });
  const [fbsAction, setFbsAction] = useState(false);
  const [cbsDraft, setCbsDraft] = useState({
    code: "",
    level: "3",
    cost_category: "",
    description: "",
    status: "active",
  });
  const [priorityDraft, setPriorityDraft] = useState({
    wbs_id: "",
    control_account_id: "",
    cbs_id: "",
    funding_source_id: "",
    amount: "",
    quantity: "",
    description: "",
  });
  const [sovDraft, setSovDraft] = useState({
    contract_id: "",
    line_no: "10",
    description: "",
    amount: "",
  });
  const [rateDraft, setRateDraft] = useState({
    code: "",
    name: "",
    cbs_code: "",
    multiplier: "1.0",
    unit_rate: "0",
  });
  const [policyDraft, setPolicyDraft] = useState({
    process_code: "BP-CBS-WBS",
    action: "approve_baseline",
    required_role: "Control Manager",
    permission_key: "can_approve_workflow",
  });
  const [lineEditDraft, setLineEditDraft] = useState({
    line_item_id: "",
    amount: "",
    quantity: "",
    description: "",
    change_note: "Controlled production edit",
  });
  const [priorityAction, setPriorityAction] = useState<"cbs" | "fund" | "wbs" | "sov" | "rate" | "recost" | null>(
    null,
  );
  const [hardeningAction, setHardeningAction] = useState<"policy" | "line" | "export-xlsx" | "export-pdf" | null>(null);
  const [agentAction, setAgentAction] = useState(false);
  const [constraintAction, setConstraintAction] = useState(false);
  const [baselineAction, setBaselineAction] = useState(false);
  const [integratedMessage, setIntegratedMessage] = useState<string | null>(null);
  const [activeControlView, setActiveControlView] = useState<ControlFlowView>("dashboard");
  const [constraintDraft, setConstraintDraft] = useState({
    work_package_id: "",
    constraint_type: "Engineering Documents",
    description: "",
    owner_role: "Workface Planner",
    required_by: "",
    priority: "medium",
    evidence_ref: "",
    blocking: true,
  });

  useEffect(() => {
    let cancelled = false;
    async function loadProjects() {
      setLoading(true);
      setError(null);
      try {
        const records = await projectsApi.list(token);
        if (cancelled) return;
        setProjectList(records);
        const nextProjectId = selectedProjectId ?? records[0]?.id ?? null;
        if (nextProjectId) {
          setSelectedProject(nextProjectId);
        } else {
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          if (isUnauthorizedApiError(err)) {
            logout();
            return;
          }
          setError(err instanceof Error ? err.message : "Could not load projects");
          setLoading(false);
        }
      }
    }
    loadProjects();
    return () => {
      cancelled = true;
    };
  }, [token, selectedProjectId, setSelectedProject, logout]);

  useEffect(() => {
    if (!selectedProjectId) return;
    const projectId = selectedProjectId;
    let cancelled = false;
    async function loadDashboard() {
      setLoading(true);
      setError(null);
      try {
        const nextDashboard = await dashboardApi.get(token, projectId);
        if (!cancelled) {
          setDashboard(nextDashboard);
          setLoading(false);
          const firstFunding = nextDashboard.funding_sources?.[0];
          const firstContract = nextDashboard.contracts?.[0];
          setPriorityDraft((current) => ({
            ...current,
            funding_source_id: current.funding_source_id || (firstFunding ? String(firstFunding.id) : ""),
          }));
          setSovDraft((current) => ({ ...current, contract_id: current.contract_id || (firstContract ? String(firstContract.id) : "") }));
        }
        const businessProcesses = nextDashboard.business_processes ?? [];
        const priorityProcess =
          businessProcesses.find((process) => process.process_code === "BP-CBS-WBS") ??
          businessProcesses.find((process) => process.process_code === "BP-CBS-FUND");
        if (priorityProcess) {
          const lineItems = await integratedControlApi.businessProcessLineItems(token, projectId, priorityProcess.id).catch(() => []);
          const revisions = lineItems[0]
            ? await integratedControlApi.businessProcessLineItemRevisions(token, projectId, lineItems[0].id).catch(() => [])
            : [];
          if (!cancelled) {
            setBpLineItems(lineItems);
            setBpLineItemRevisions(revisions);
            const selectedLine = lineItems[0];
            if (selectedLine) {
              setLineEditDraft((current) => ({
                ...current,
                line_item_id: String(selectedLine.id),
                amount: String(selectedLine.amount),
                quantity: String(selectedLine.quantity),
                description: selectedLine.description,
              }));
            }
          }
        } else if (!cancelled) {
          setBpLineItems([]);
          setBpLineItemRevisions([]);
        }
      } catch (err) {
        if (!cancelled) {
          if (isUnauthorizedApiError(err)) {
            logout();
            return;
          }
          setError(err instanceof Error ? err.message : "Could not load dashboard");
          setLoading(false);
        }
      }
    }
    loadDashboard();
    return () => {
      cancelled = true;
    };
  }, [token, selectedProjectId, setDashboard, logout]);

  useEffect(() => {
    if (!selectedProjectId) return;
    const projectId = selectedProjectId;
    let cancelled = false;
    async function loadIntegratedControl() {
      setIntegratedError(null);
      try {
        const [matrix, forecast, closeout, wbsRows, accounts, cbsRows, codeRows, sheets, reconciliation, policies, agentRuns] =
          await Promise.all([
            integratedControlApi.matrix(token, projectId),
            integratedControlApi.forecastVsFunding(token, projectId),
            integratedControlApi.closeoutReport(token, projectId),
            integratedControlApi.wbs(token, projectId),
            integratedControlApi.controlAccounts(token, projectId),
            integratedControlApi.cbs(token, projectId),
            integratedControlApi.costCodes(token, projectId),
            integratedControlApi.rateSheets(token, projectId),
            integratedControlApi.reconciliationReport(token, projectId),
            integratedControlApi.businessProcessPolicies(token, projectId),
            integratedControlApi.controlAuditAgentRuns(token, projectId).catch(() => []),
          ]);
        if (!cancelled) {
          setIntegratedMatrix(matrix);
          setForecastFunding(forecast);
          setCloseoutReport(closeout);
          setWbsCatalog(wbsRows);
          setControlAccounts(accounts);
          setCbsCatalog(cbsRows);
          setCostCodes(codeRows);
          setRateSheets(sheets);
          setReconciliationReport(reconciliation);
          setBpPolicies(policies);
          setControlAgentRuns(agentRuns);
          const firstAccount = accounts[0];
          const accountWbs = firstAccount?.wbs_id
            ? wbsRows.find((item) => item.id === firstAccount.wbs_id)
            : undefined;
          const firstWbs = accountWbs ?? wbsRows.find((item) => item.code !== "1.0") ?? wbsRows[0];
          const firstCbs = cbsRows[0];
          setPriorityDraft((current) => ({
            ...current,
            wbs_id: current.wbs_id || (firstWbs ? String(firstWbs.id) : ""),
            control_account_id: current.control_account_id || (firstAccount ? String(firstAccount.id) : ""),
            cbs_id: current.cbs_id || (firstCbs ? String(firstCbs.id) : ""),
          }));
          setRateDraft((current) => ({
            ...current,
            cbs_code: current.cbs_code || firstCbs?.code || "",
          }));
        }
      } catch (err) {
        if (!cancelled) {
          if (isUnauthorizedApiError(err)) {
            logout();
            return;
          }
          setIntegratedError(err instanceof Error ? err.message : "Could not load integrated control data");
        }
      }
    }
    loadIntegratedControl();
    return () => {
      cancelled = true;
    };
  }, [token, selectedProjectId, logout]);

  useEffect(() => {
    if (!selectedProjectId) return;
    const projectId = selectedProjectId;
    let cancelled = false;
    async function loadOperationalSetup() {
      setSetupError(null);
      try {
        const setupPromise = projectsApi.operationalSetup(token, projectId).catch((err: unknown) => {
          if (err instanceof ApiError && err.status === 404) return null;
          throw err;
        });
        const [setup, sheets] = await Promise.all([setupPromise, projectsApi.activitySheets(token, projectId)]);
        const latestSheet = sheets[0];
        const [wbsRows, detailRows] = latestSheet
          ? await Promise.all([
              projectsApi.activitySheetWbsRows(token, projectId, latestSheet.id).catch(() => []),
              projectsApi.activitySheetRows(token, projectId, latestSheet.id).catch(() => []),
            ])
          : [[], []];
        if (cancelled) return;
        setOperationalSetup(setup);
        setActivitySheets(sheets);
        setActivitySheetWbsRows(wbsRows);
        setActivitySheetRows(detailRows);
        setRecostRuns([]);
        if (latestSheet) {
          const firstActivityCbs = detailRows[0]?.cbs_code;
          if (firstActivityCbs) {
            setRateDraft((current) => ({ ...current, cbs_code: current.cbs_code || firstActivityCbs }));
          }
          integratedControlApi.recostRuns(token, projectId, latestSheet.id).then((history) => {
            if (!cancelled) setRecostRuns(history);
          }).catch(() => undefined);
        }
        const selectedProject = projectList.find((item) => item.id === projectId);
        setSetupDraft({
          project_number: setup?.project_number || selectedProject?.code || "",
          setup_template: setup?.setup_template || "Capital Project Controls Template",
          attribute_form: setup?.attribute_form || "Project Attribute Form",
          permissions_configured: setup?.permissions_configured ?? true,
          modules_configured: setup?.modules_configured ?? true,
          cost_sheet_ready: setup?.cost_sheet_ready ?? true,
          funding_sheet_ready: setup?.funding_sheet_ready ?? true,
          p6_mapping_ready: setup?.p6_mapping_ready ?? true,
          status: setup?.status || "ready",
        });
      } catch (err) {
        if (!cancelled) {
          if (isUnauthorizedApiError(err)) {
            logout();
            return;
          }
          setSetupError(err instanceof Error ? err.message : "Could not load project setup");
          setActivitySheetWbsRows([]);
          setActivitySheetRows([]);
        }
      }
    }
    loadOperationalSetup();
    return () => {
      cancelled = true;
    };
  }, [token, selectedProjectId, projectList, logout]);

  useEffect(() => {
    let cancelled = false;
    async function loadAdminData() {
      try {
        const [nextUsers, nextRoles] = await Promise.all([adminApi.listUsers(token), adminApi.listRoles(token)]);
        if (!cancelled) {
          setUsers(nextUsers);
          setRoles(nextRoles);
          setUserDraft((current) => ({
            ...current,
            role: nextRoles.some((role) => role.role === current.role) ? current.role : nextRoles[0]?.role || current.role,
          }));
        }
      } catch (err) {
        if (!cancelled) {
          if (isUnauthorizedApiError(err)) {
            logout();
            return;
          }
          setUserError(err instanceof Error ? err.message : "Could not load users and roles");
        }
      }
    }
    loadAdminData();
    return () => {
      cancelled = true;
    };
  }, [token, logout]);

  async function refreshDashboard(projectId: number) {
    const nextDashboard = await dashboardApi.get(token, projectId);
    setDashboard(nextDashboard);
    const firstFunding = nextDashboard.funding_sources?.[0];
    const firstContract = nextDashboard.contracts?.[0];
    setPriorityDraft((current) => ({
      ...current,
      funding_source_id: current.funding_source_id || (firstFunding ? String(firstFunding.id) : ""),
    }));
    setSovDraft((current) => ({ ...current, contract_id: current.contract_id || (firstContract ? String(firstContract.id) : "") }));
  }

  async function refreshIntegratedControl(projectId: number) {
    const [matrix, forecast, closeout, wbsRows, accounts, cbsRows, codeRows, sheets, reconciliation, policies, agentRuns] =
      await Promise.all([
        integratedControlApi.matrix(token, projectId),
        integratedControlApi.forecastVsFunding(token, projectId),
        integratedControlApi.closeoutReport(token, projectId),
        integratedControlApi.wbs(token, projectId),
        integratedControlApi.controlAccounts(token, projectId),
        integratedControlApi.cbs(token, projectId),
        integratedControlApi.costCodes(token, projectId),
        integratedControlApi.rateSheets(token, projectId),
        integratedControlApi.reconciliationReport(token, projectId),
        integratedControlApi.businessProcessPolicies(token, projectId),
        integratedControlApi.controlAuditAgentRuns(token, projectId).catch(() => []),
      ]);
    setIntegratedMatrix(matrix);
    setForecastFunding(forecast);
    setCloseoutReport(closeout);
    setWbsCatalog(wbsRows);
    setControlAccounts(accounts);
    setCbsCatalog(cbsRows);
    setCostCodes(codeRows);
    setRateSheets(sheets);
    setReconciliationReport(reconciliation);
    setBpPolicies(policies);
    setControlAgentRuns(agentRuns);
    const firstAccount = accounts[0];
    const accountWbs = firstAccount?.wbs_id
      ? wbsRows.find((item) => item.id === firstAccount.wbs_id)
      : undefined;
    const firstWbs = accountWbs ?? wbsRows.find((item) => item.code !== "1.0") ?? wbsRows[0];
    const firstCbs = cbsRows[0];
    setPriorityDraft((current) => ({
      ...current,
      wbs_id: current.wbs_id || (firstWbs ? String(firstWbs.id) : ""),
      control_account_id: current.control_account_id || (firstAccount ? String(firstAccount.id) : ""),
      cbs_id: current.cbs_id || (firstCbs ? String(firstCbs.id) : ""),
    }));
    setRateDraft((current) => ({
      ...current,
      cbs_code: current.cbs_code || firstCbs?.code || "",
    }));
  }

  async function refreshProcessLineItems(projectId: number, processId: number, preferredLineId?: number) {
    const lines = await integratedControlApi.businessProcessLineItems(token, projectId, processId);
    const selectedLine = lines.find((line) => line.id === preferredLineId) ?? lines[0];
    const revisions = selectedLine
      ? await integratedControlApi.businessProcessLineItemRevisions(token, projectId, selectedLine.id)
      : [];
    setBpLineItems(lines);
    setBpLineItemRevisions(revisions);
    if (selectedLine) {
      setLineEditDraft((current) => ({
        ...current,
        line_item_id: String(selectedLine.id),
        amount: String(selectedLine.amount),
        quantity: String(selectedLine.quantity),
        description: selectedLine.description,
      }));
    }
  }

  async function handleProjectCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setProjectAction(true);
    setProjectError(null);
    setProjectMessage(null);
    try {
      const created = await projectsApi.create(token, {
        code: projectDraft.code.trim(),
        name: projectDraft.name.trim(),
        phase: projectDraft.phase,
        currency: projectDraft.currency.trim().toUpperCase() || "USD",
        calendar_base: projectDraft.calendar_base.trim(),
        owner: projectDraft.owner.trim(),
        status: projectDraft.status,
        authorization_date: projectDraft.authorization_date || null,
        authorization_ref: projectDraft.authorization_ref.trim(),
        configuration: {
          control_level: projectDraft.control_level,
          funding_required: projectDraft.funding_required,
        },
        start_date: projectDraft.start_date || null,
        finish_date: projectDraft.finish_date || null,
      });
      setProjectList((current) =>
        current.some((projectItem) => projectItem.id === created.id)
          ? current.map((projectItem) => (projectItem.id === created.id ? created : projectItem))
          : [...current, created],
      );
      setSelectedProject(created.id);
      setProjectDraft({
        calendar_base: created.calendar_base || "5x8 Colombia",
        code: "",
        control_level: "control_account",
        funding_required: true,
        authorization_date: "",
        authorization_ref: "",
        name: "",
        owner: "",
        phase: "Planning",
        currency: created.currency || "USD",
        status: "draft",
        start_date: "",
        finish_date: "",
      });
      setShowProjectCreate(false);
      setProjectMessage(`Project ${created.code} created and selected.`);
    } catch (err) {
      setProjectError(err instanceof Error ? err.message : "Could not create project");
    } finally {
      setProjectAction(false);
    }
  }

  async function handleScheduleUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || !selectedProjectId) return;
    setUploading(true);
    setUploadError(null);
    setUploadMessage(null);
    try {
      await projectsApi.uploadSchedule(token, selectedProjectId, file);
      await refreshDashboard(selectedProjectId);
      setUploadMessage(`${file.name} uploaded. Data Quality Gate refreshed.`);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Could not upload schedule");
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  }

  async function handleOperationalSetupSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId) return;
    setSetupAction(true);
    setSetupError(null);
    setSetupMessage(null);
    try {
      const updated = await projectsApi.updateOperationalSetup(token, selectedProjectId, {
        ...setupDraft,
        expected_version: operationalSetup?.version,
      });
      setOperationalSetup(updated);
      setSetupMessage(`Project setup ${statusLabel(updated.readiness_status)}.`);
    } catch (err) {
      setSetupError(err instanceof Error ? err.message : "Could not update project setup");
    } finally {
      setSetupAction(false);
    }
  }

  async function handleActivitySheetUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || !selectedProjectId) return;
    setActivityAction(true);
    setSetupError(null);
    setSetupMessage(null);
    try {
      const created = await projectsApi.loadActivitySheetData(token, selectedProjectId, file);
      const [sheets, wbsRows, detailRows] = await Promise.all([
        projectsApi.activitySheets(token, selectedProjectId),
        projectsApi.activitySheetWbsRows(token, selectedProjectId, created.id),
        projectsApi.activitySheetRows(token, selectedProjectId, created.id),
      ]);
      await refreshDashboard(selectedProjectId);
      await refreshIntegratedControl(selectedProjectId);
      setActivitySheets(sheets);
      setActivitySheetWbsRows(wbsRows);
      setActivitySheetRows(detailRows);
      setRecostRuns([]);
      setSetupMessage(`Activity data loaded from ${created.source_file_name}.`);
    } catch (err) {
      setSetupError(err instanceof Error ? err.message : "Could not load activity data");
    } finally {
      setActivityAction(false);
      event.target.value = "";
    }
  }

  async function handleUserCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId) return;
    setUserAction(true);
    setUserError(null);
    setUserMessage(null);
    try {
      const created = await adminApi.createUser(token, {
        email: userDraft.email.trim().toLowerCase(),
        full_name: userDraft.full_name.trim(),
        password: userDraft.password,
        title: userDraft.title.trim(),
      });
      await projectsApi.assignTeamMember(token, selectedProjectId, {
        role: userDraft.role,
        user_id: created.id,
      });
      setUsers((current) =>
        current.some((item) => item.id === created.id)
          ? current.map((item) => (item.id === created.id ? created : item))
          : [...current, created],
      );
      await refreshDashboard(selectedProjectId);
      setUserDraft((current) => ({
        ...current,
        email: "",
        full_name: "",
        password: "1234",
        title: "",
      }));
      setUserMessage(`${created.full_name} created and assigned as ${userDraft.role}.`);
    } catch (err) {
      setUserError(err instanceof Error ? err.message : "Could not create user or assign role");
    } finally {
      setUserAction(false);
    }
  }

  async function handleFbsCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId) return;
    setFbsAction(true);
    setIntegratedError(null);
    setIntegratedMessage(null);
    try {
      const created = await integratedControlApi.createFbs(token, selectedProjectId, {
        code: fbsDraft.code.trim(),
        source_of_funds: fbsDraft.source_of_funds.trim(),
        funding_type: fbsDraft.funding_type.trim(),
        authorization_ref: fbsDraft.authorization_ref.trim(),
        approved_amount: Number(fbsDraft.approved_amount),
        currency: fbsDraft.currency.trim().toUpperCase() || project.currency,
        status: fbsDraft.status,
      });
      await refreshDashboard(selectedProjectId);
      await refreshIntegratedControl(selectedProjectId);
      setFbsDraft({
        code: "",
        source_of_funds: "",
        funding_type: created.funding_type || "AFE",
        authorization_ref: "",
        approved_amount: "",
        currency: created.currency || project.currency,
        status: "approved",
      });
      setIntegratedMessage(`FBS ${created.code} created.`);
    } catch (err) {
      setIntegratedError(err instanceof Error ? err.message : "Could not create FBS");
    } finally {
      setFbsAction(false);
    }
  }

  async function handleCbsCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId) return;
    setPriorityAction("cbs");
    setIntegratedError(null);
    setIntegratedMessage(null);
    try {
      const created = await integratedControlApi.createCbs(token, selectedProjectId, {
        code: cbsDraft.code.trim(),
        level: Number(cbsDraft.level || 1),
        cost_category: cbsDraft.cost_category.trim(),
        description: cbsDraft.description.trim(),
        status: cbsDraft.status,
      });
      await refreshIntegratedControl(selectedProjectId);
      setPriorityDraft((current) => ({ ...current, cbs_id: String(created.id) }));
      setRateDraft((current) => ({ ...current, cbs_code: created.code }));
      setCbsDraft({ code: "", level: "3", cost_category: created.cost_category || "", description: "", status: "active" });
      setIntegratedMessage(`CBS ${created.code} created.`);
    } catch (err) {
      setIntegratedError(err instanceof Error ? err.message : "Could not create CBS");
    } finally {
      setPriorityAction(null);
    }
  }

  async function handlePriorityBusinessProcess(kind: "fund" | "wbs") {
    if (!selectedProjectId) return;
    setPriorityAction(kind);
    setIntegratedError(null);
    setIntegratedMessage(null);
    try {
      const selectedAccount = controlAccounts.find((account) => account.id === Number(priorityDraft.control_account_id));
      const wbsId = Number(priorityDraft.wbs_id || selectedAccount?.wbs_id || 0);
      const payload = {
        title: kind === "fund" ? "CBS + Fund Code allocation" : "CBS + WBS Code transaction",
        line_items: [
          {
            wbs_id: kind === "wbs" ? wbsId : null,
            cbs_id: Number(priorityDraft.cbs_id),
            funding_source_id: Number(priorityDraft.funding_source_id),
            control_account_id: Number(priorityDraft.control_account_id),
            amount: Number(priorityDraft.amount),
            quantity: Number(priorityDraft.quantity || 0),
            description: priorityDraft.description.trim(),
          },
        ],
      };
      const process =
        kind === "fund"
          ? await integratedControlApi.createCbsFundBusinessProcess(token, selectedProjectId, payload)
          : await integratedControlApi.createCbsWbsBusinessProcess(token, selectedProjectId, payload);
      await refreshDashboard(selectedProjectId);
      await refreshIntegratedControl(selectedProjectId);
      await refreshProcessLineItems(selectedProjectId, process.id);
      setPriorityDraft((current) => ({ ...current, amount: "", quantity: "", description: "" }));
      setIntegratedMessage(`${process.record_no} created at ${statusLabel(process.current_step)}.`);
    } catch (err) {
      setIntegratedError(err instanceof Error ? err.message : "Could not create the business process");
    } finally {
      setPriorityAction(null);
    }
  }

  async function handleSovAndFundingCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId) return;
    setPriorityAction("sov");
    setIntegratedError(null);
    setIntegratedMessage(null);
    try {
      const contractId = Number(sovDraft.contract_id);
      const sovLine = await integratedControlApi.createSovLine(token, selectedProjectId, contractId, {
        line_no: sovDraft.line_no.trim(),
        description: sovDraft.description.trim(),
        amount: Number(sovDraft.amount),
        cbs_id: Number(priorityDraft.cbs_id),
        wbs_id: Number(priorityDraft.wbs_id),
        control_account_id: Number(priorityDraft.control_account_id),
        status: "active",
      });
      await integratedControlApi.createCommitmentFundingLine(token, selectedProjectId, {
        contract_id: contractId,
        sov_line_id: sovLine.id,
        funding_source_id: Number(priorityDraft.funding_source_id),
        amount: Number(sovDraft.amount),
        status: "active",
      });
      await refreshDashboard(selectedProjectId);
      await refreshIntegratedControl(selectedProjectId);
      setSovDraft((current) => ({ ...current, line_no: String(Number(current.line_no || 0) + 10), description: "", amount: "" }));
      setIntegratedMessage(`SOV ${sovLine.line_no} funded.`);
    } catch (err) {
      setIntegratedError(err instanceof Error ? err.message : "Could not create SOV funding");
    } finally {
      setPriorityAction(null);
    }
  }

  async function handleRateSheetCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId) return;
    setPriorityAction("rate");
    setIntegratedError(null);
    setIntegratedMessage(null);
    try {
      const created = await integratedControlApi.createRateSheet(token, selectedProjectId, {
        code: rateDraft.code.trim(),
        name: rateDraft.name.trim(),
        status: "active",
        line_items: [
          {
            cbs_code: rateDraft.cbs_code.trim(),
            multiplier: Number(rateDraft.multiplier || 1),
            unit_rate: Number(rateDraft.unit_rate || 0),
            status: "active",
          },
        ],
      });
      await refreshIntegratedControl(selectedProjectId);
      setRateDraft((current) => ({ ...current, code: "", name: "", multiplier: "1.0", unit_rate: "0" }));
      setIntegratedMessage(`Rate Sheet ${created.code} created.`);
    } catch (err) {
      setIntegratedError(err instanceof Error ? err.message : "Could not create Rate Sheet");
    } finally {
      setPriorityAction(null);
    }
  }

  async function handlePolicySubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId) return;
    setHardeningAction("policy");
    setIntegratedError(null);
    setIntegratedMessage(null);
    try {
      const policy = await integratedControlApi.upsertBusinessProcessPolicy(token, selectedProjectId, {
        process_code: policyDraft.process_code,
        action: policyDraft.action,
        required_role: policyDraft.required_role,
        permission_key: policyDraft.permission_key,
        status: "active",
      });
      await refreshIntegratedControl(selectedProjectId);
      setIntegratedMessage(`${policy.process_code} ${policy.action} policy saved for ${policy.required_role || "permission key"}.`);
    } catch (err) {
      setIntegratedError(err instanceof Error ? err.message : "Could not save business process policy");
    } finally {
      setHardeningAction(null);
    }
  }

  async function handleLineItemSelect(line: BusinessProcessLineItem) {
    if (!selectedProjectId) return;
    setLineEditDraft((current) => ({
      ...current,
      line_item_id: String(line.id),
      amount: String(line.amount),
      quantity: String(line.quantity),
      description: line.description,
    }));
    try {
      const revisions = await integratedControlApi.businessProcessLineItemRevisions(token, selectedProjectId, line.id);
      setBpLineItemRevisions(revisions);
    } catch (err) {
      setIntegratedError(err instanceof Error ? err.message : "Could not load line item revisions");
    }
  }

  async function handleLineItemUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId) return;
    const selectedLine = bpLineItems.find((line) => String(line.id) === lineEditDraft.line_item_id);
    if (!selectedLine) return;
    setHardeningAction("line");
    setIntegratedError(null);
    setIntegratedMessage(null);
    try {
      const updated = await integratedControlApi.updateBusinessProcessLineItem(token, selectedProjectId, selectedLine.id, {
        amount: Number(lineEditDraft.amount),
        quantity: Number(lineEditDraft.quantity || 0),
        description: lineEditDraft.description,
        change_note: lineEditDraft.change_note,
        expected_version: selectedLine.version,
      });
      await refreshDashboard(selectedProjectId);
      await refreshIntegratedControl(selectedProjectId);
      await refreshProcessLineItems(selectedProjectId, updated.process_instance_id, updated.id);
      setIntegratedMessage(`Line item version ${updated.version} saved.`);
    } catch (err) {
      setIntegratedError(err instanceof Error ? err.message : "Could not update line item");
    } finally {
      setHardeningAction(null);
    }
  }

  async function handleReconciliationExport(format: "xlsx" | "pdf") {
    if (!selectedProjectId) return;
    setHardeningAction(format === "xlsx" ? "export-xlsx" : "export-pdf");
    setIntegratedError(null);
    setIntegratedMessage(null);
    try {
      const blob = await integratedControlApi.exportReconciliationReport(token, selectedProjectId, format);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `reconciliation-${project.code}.${format}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setIntegratedMessage(`Reconciliation ${format.toUpperCase()} export generated.`);
    } catch (err) {
      setIntegratedError(err instanceof Error ? err.message : "Could not export reconciliation report");
    } finally {
      setHardeningAction(null);
    }
  }

  async function handleControlAuditAgentRun() {
    if (!selectedProjectId) return;
    setAgentAction(true);
    setIntegratedError(null);
    setIntegratedMessage(null);
    try {
      const run = await integratedControlApi.runControlAuditAgent(token, selectedProjectId);
      const history = await integratedControlApi.controlAuditAgentRuns(token, selectedProjectId);
      setControlAgentRuns(history.length ? history : [run]);
      setIntegratedMessage(`${run.agent_name} completed with score ${run.score}.`);
    } catch (err) {
      setIntegratedError(err instanceof Error ? err.message : "Could not run Control Audit Agent");
    } finally {
      setAgentAction(false);
    }
  }

  async function handleCreateAwpDraftPackages() {
    if (!selectedProjectId) return;
    setAgentAction(true);
    setIntegratedError(null);
    setIntegratedMessage(null);
    try {
      const run = await integratedControlApi.createAwpDraftPackages(token, selectedProjectId);
      await refreshDashboard(selectedProjectId);
      await refreshIntegratedControl(selectedProjectId);
      const history = await integratedControlApi.controlAuditAgentRuns(token, selectedProjectId);
      setControlAgentRuns(history.length ? history : [run]);
      setIntegratedMessage(`${run.summary} Review the draft packages in Work Packages.`);
    } catch (err) {
      setIntegratedError(err instanceof Error ? err.message : "Could not create AWP draft packages");
    } finally {
      setAgentAction(false);
    }
  }

  async function handleRecostLatestActivitySheet() {
    if (!selectedProjectId || !activitySheets[0] || !rateSheets[0]) return;
    setPriorityAction("recost");
    setIntegratedError(null);
    setIntegratedMessage(null);
    try {
      const result = await integratedControlApi.recostActivitySheet(token, selectedProjectId, activitySheets[0].id, rateSheets[0].id);
      const [wbsRows, detailRows] = await Promise.all([
        projectsApi.activitySheetWbsRows(token, selectedProjectId, activitySheets[0].id),
        projectsApi.activitySheetRows(token, selectedProjectId, activitySheets[0].id),
      ]);
      const history = await integratedControlApi.recostRuns(token, selectedProjectId, activitySheets[0].id);
      await refreshDashboard(selectedProjectId);
      await refreshIntegratedControl(selectedProjectId);
      setActivitySheetWbsRows(wbsRows);
      setActivitySheetRows(detailRows);
      setRecostRuns(history);
      setIntegratedMessage(`${result.updated_rows} activity rows recosted in run ${result.recost_run_id ?? "latest"}.`);
    } catch (err) {
      setIntegratedError(err instanceof Error ? err.message : "Could not recost Activity Sheet");
    } finally {
      setPriorityAction(null);
    }
  }

  async function handleBaselineApproval() {
    if (!selectedProjectId) return;
    setBaselineAction(true);
    setIntegratedError(null);
    setIntegratedMessage(null);
    try {
      const result = await integratedControlApi.approveBaseline(token, selectedProjectId);
      await refreshDashboard(selectedProjectId);
      await refreshIntegratedControl(selectedProjectId);
      setIntegratedMessage(`Baseline status: ${statusLabel(result.project_status)}.`);
    } catch (err) {
      setIntegratedError(err instanceof Error ? err.message : "Could not approve integrated baseline");
    } finally {
      setBaselineAction(false);
    }
  }

  async function handleCreateWorkPackageConstraint(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId || !dashboard) return;
    const packageId = Number(constraintDraft.work_package_id || dashboard.work_packages[0]?.id || 0);
    if (!packageId || !constraintDraft.description.trim()) {
      setIntegratedError("Select a work package and describe the constraint.");
      return;
    }
    setConstraintAction(true);
    setIntegratedError(null);
    setIntegratedMessage(null);
    try {
      await integratedControlApi.createWorkPackageConstraint(token, selectedProjectId, packageId, {
        constraint_type: constraintDraft.constraint_type,
        description: constraintDraft.description.trim(),
        owner_role: constraintDraft.owner_role,
        required_by: constraintDraft.required_by || null,
        status: "open",
        priority: constraintDraft.priority,
        evidence_ref: constraintDraft.evidence_ref,
        blocking: constraintDraft.blocking,
      });
      await refreshDashboard(selectedProjectId);
      setIntegratedMessage("Constraint added to the selected draft package.");
      setConstraintDraft((draft) => ({
        ...draft,
        description: "",
        required_by: "",
        evidence_ref: "",
      }));
    } catch (err) {
      setIntegratedError(err instanceof Error ? err.message : "Could not create work package constraint");
    } finally {
      setConstraintAction(false);
    }
  }

  function handleControlFlowNavigate(view: ControlFlowView) {
    setActiveControlView(view);
    document.getElementById("control-flow-content")?.scrollIntoView?.({ block: "start", behavior: "smooth" });
  }

  const constraintsByPackage = useMemo(() => {
    return (dashboard?.work_package_constraints ?? []).reduce<Record<number, number>>((acc, constraint) => {
      if (constraint.status === "open" && constraint.blocking) {
        acc[constraint.work_package_id] = (acc[constraint.work_package_id] ?? 0) + 1;
      }
      return acc;
    }, {});
  }, [dashboard?.work_package_constraints]);

  const evmCurveData = useMemo(() => {
    if (!dashboard) return [];
    const kpiSnapshot = dashboard.project_kpi;
    const snapshots = dashboard.control_snapshots ?? [];
    const projectSnapshots = snapshots.filter((snapshot) => snapshot.control_account_id === null);
    const source = projectSnapshots.length ? projectSnapshots : snapshots;
    if (!source.length) {
      return [{ period: "Current", PV: kpiSnapshot.pv, EV: kpiSnapshot.ev, AC: kpiSnapshot.ac }];
    }

    return [...source]
      .sort((first, second) => {
        const firstDate = new Date(first.data_date ?? first.created_at).getTime();
        const secondDate = new Date(second.data_date ?? second.created_at).getTime();
        return firstDate - secondDate;
      })
      .map((snapshot) => ({
        period: snapshot.period_label,
        PV: snapshot.pv,
        EV: snapshot.ev,
        AC: snapshot.ac,
      }));
  }, [dashboard]);

  if (loading && !dashboard) {
    return <div className="loading">Loading workspace...</div>;
  }

  if (error || !dashboard) {
    return (
      <main>
        <section className="panel workspaceEmpty">
          <h1>Workspace unavailable</h1>
          <p>{error ?? "No project dashboard is available."}</p>
        </section>
      </main>
    );
  }

  const project = dashboard.project;
  const kpi = dashboard.project_kpi;
  const currentMembership = dashboard.project_team.find((member) => member.user.id === user?.id)?.membership;
  const canConfigure = Boolean(currentMembership?.can_configure);
  const canCaptureCost = Boolean(currentMembership?.can_capture_cost);
  const canManageContract = Boolean(currentMembership?.can_manage_contract);
  const canUploadSchedule = currentMembership?.role === "Planner" || currentMembership?.role === "Control Manager";
  const activeImport = dashboard.schedule_import;
  const cbsCostLines = dashboard.cost_sheet ?? [];
  const fbsFundingSources = dashboard.funding_sources ?? [];
  const contractRows = dashboard.contracts ?? [];
  const selectedControlAccount = controlAccounts.find((account) => account.id === Number(priorityDraft.control_account_id));
  const selectedWbsForAccount = selectedControlAccount
    ? wbsCatalog.find((wbs) => wbs.id === selectedControlAccount.wbs_id)
    : undefined;
  const selectedCbs = cbsCatalog.find((cbs) => cbs.id === Number(priorityDraft.cbs_id));
  const rateCbsOptions = Array.from(
    new Set([...cbsCatalog.map((cbs) => cbs.code), ...activitySheetRows.map((row) => row.cbs_code).filter(Boolean)]),
  );
  const latestActivitySheet = activitySheets[0];
  const reconciliationRows = reconciliationReport?.rows ?? [];
  const latestAgentRun = controlAgentRuns[0];
  const agentFindings = latestAgentRun?.findings ?? [];
  const selectedLineItem = bpLineItems.find((line) => String(line.id) === lineEditDraft.line_item_id);
  const policyRoleOptions = roles.length ? roles.map((role) => role.role) : ["Control Manager"];
  const canRunPriority =
    Boolean(priorityDraft.cbs_id && priorityDraft.funding_source_id && priorityDraft.control_account_id && priorityDraft.amount) &&
    Number(priorityDraft.amount) > 0;
  const totalFunding = fbsFundingSources.reduce((total, source) => total + source.amount, 0);
  const activitySheetPlannedCost = activitySheetWbsRows.reduce((total, row) => total + row.planned_cost, 0);
  const activitySheetNeedsReview = activitySheetWbsRows.reduce((total, row) => total + row.needs_review_count, 0);
  const controlMixData = [
    {
      actual: dashboard.baseline_versions.length || (activeImport ? 1 : 0),
      color: "#0f8b8d",
      name: "Baseline",
      value: Math.max(dashboard.baseline_versions.length || (activeImport ? 1 : 0), 1),
    },
    {
      actual: dashboard.latest_progress_records.length,
      color: "#d89b2b",
      name: "Progress",
      value: Math.max(dashboard.latest_progress_records.length, 1),
    },
    {
      actual: cbsCostLines.length,
      color: "#52616f",
      name: "Costs",
      value: Math.max(cbsCostLines.length, 1),
    },
    {
      actual: dashboard.awp_summary.total_packages,
      color: "#c85a3a",
      name: "AWP",
      value: Math.max(dashboard.awp_summary.total_packages, 1),
    },
  ];
  const workloadChartData = [
    { color: "#0f8b8d", name: "Activities", value: dashboard.schedule_activity_count },
    { color: "#d89b2b", name: "Progress", value: dashboard.latest_progress_records.length },
    { color: "#52616f", name: "Cost Lines", value: cbsCostLines.length },
    { color: "#c85a3a", name: "AWP Packages", value: dashboard.awp_summary.total_packages },
  ];
  const forecastFundingRows = forecastFunding?.rows ?? [];
  const fundingAlerts = forecastFundingRows.filter((row) => row.forecast_vs_available < 0);
  const controlFlowItems: Array<{ key: ControlFlowView; label: string; count: string | number }> = [
    { key: "dashboard", label: "Dashboard", count: `${kpi.spi.toFixed(2)} SPI` },
    { key: "setup", label: "Project Setup", count: operationalSetup?.readiness_status === "ready" ? "ready" : "open" },
    { key: "baseline", label: "Baseline", count: dashboard.schedule_activity_count },
    { key: "progress", label: "Progress", count: dashboard.latest_progress_records.length },
    { key: "costs", label: "Costs", count: dashboard.cost_sheet.length },
    { key: "integrated-control", label: "Integrated Control", count: integratedMatrix.length },
    { key: "decisions", label: "Decisions", count: dashboard.changes.length },
    {
      key: "evidence",
      label: "Evidence",
      count: `${dashboard.document_control_summary.controlled_document_score.toFixed(0)}%`,
    },
  ];

  return (
    <main>
      <header className="topbar">
        <div className="brandBlock">
          <ProductLogo compact />
          <p className="eyebrow">Project Controls</p>
          <h1>{project.name}</h1>
          <p className="productStatement">
            {project.code} / {project.phase} / {project.currency}
          </p>
        </div>
        <div className="headerActions">
          <div className="contextSwitch">
            <label>
              <span>Project</span>
              <select
                onChange={(event) => setSelectedProject(Number(event.target.value))}
                value={selectedProjectId ?? project.id}
              >
                {projectList.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.code}
                  </option>
                ))}
              </select>
            </label>
            <strong>{user?.email ?? "Signed in"}</strong>
            <button className="quickNavButton" onClick={logout} type="button">
              Logout
            </button>
          </div>
        </div>
      </header>

      <section className="projectWorkspace" aria-label="Project workspace and control flow">
        <aside className="projectWorkspaceRail">
          <aside className="navigatorRail" aria-label="Control Flow">
            <div className="navigatorHeader">
              <strong>Control Flow</strong>
              <span>Essential views</span>
            </div>
            {controlFlowItems.map((item) => (
              <button
                aria-current={activeControlView === item.key ? "page" : undefined}
                className={activeControlView === item.key ? "navigatorItem active" : "navigatorItem"}
                key={item.key}
                onClick={() => handleControlFlowNavigate(item.key)}
                type="button"
              >
                <span>{item.label}</span>
                <strong>{item.count}</strong>
              </button>
            ))}
            <div className="navigatorDivider">
              <span>Advanced</span>
            </div>
            <button
              aria-current={activeControlView === "work-packages" ? "page" : undefined}
              className={activeControlView === "work-packages" ? "navigatorItem active" : "navigatorItem"}
              onClick={() => handleControlFlowNavigate("work-packages")}
              type="button"
            >
              <span>Work Packages</span>
              <strong>{dashboard.awp_summary.total_packages}</strong>
            </button>
            <button
              aria-current={activeControlView === "admin" ? "page" : undefined}
              className={activeControlView === "admin" ? "navigatorItem active" : "navigatorItem"}
              onClick={() => handleControlFlowNavigate("admin")}
              type="button"
            >
              <span>Users & Roles</span>
              <strong>{dashboard.project_team.length}</strong>
            </button>
          </aside>

          <section className="adminPanel projectCreatePanel" aria-label="Project">
            <div className="panelHeader">
              <h2>
                <Building2 size={18} /> Project
              </h2>
              <button
                className="quickNavButton"
                disabled={!canConfigure}
                onClick={() => setShowProjectCreate((current) => !current)}
                type="button"
              >
                {showProjectCreate ? "Close" : "New Project"}
              </button>
            </div>
            <div className="projectCurrentProject">
              <span>Selected project</span>
              <strong>{project.code}</strong>
              <small>{projectList.length} projects available</small>
            </div>

            {showProjectCreate ? (
              <form className="projectCreateForm" onSubmit={handleProjectCreate}>
                <div className="formColumns">
                  <label>
                    <span>Code</span>
                    <input
                      disabled={!canConfigure || projectAction}
                      onChange={(event) => setProjectDraft((current) => ({ ...current, code: event.target.value }))}
                      placeholder="PRJ-001"
                      required
                      value={projectDraft.code}
                    />
                  </label>
                  <label>
                    <span>Phase</span>
                    <select
                      disabled={!canConfigure || projectAction}
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
                    disabled={!canConfigure || projectAction}
                    onChange={(event) => setProjectDraft((current) => ({ ...current, name: event.target.value }))}
                    placeholder="Project control name"
                    required
                    value={projectDraft.name}
                  />
                </label>
                <div className="formColumns">
                  <label>
                    <span>Owner</span>
                    <input
                      disabled={!canConfigure || projectAction}
                      onChange={(event) => setProjectDraft((current) => ({ ...current, owner: event.target.value }))}
                      value={projectDraft.owner}
                    />
                  </label>
                  <label>
                    <span>Base Calendar</span>
                    <input
                      disabled={!canConfigure || projectAction}
                      onChange={(event) =>
                        setProjectDraft((current) => ({ ...current, calendar_base: event.target.value }))
                      }
                      value={projectDraft.calendar_base}
                    />
                  </label>
                </div>
                <div className="formColumns">
                  <label>
                    <span>Status</span>
                    <select
                      disabled={!canConfigure || projectAction}
                      onChange={(event) => setProjectDraft((current) => ({ ...current, status: event.target.value }))}
                      value={projectDraft.status}
                    >
                      <option value="draft">Draft</option>
                      <option value="authorized">Authorized</option>
                      <option value="baseline_approved">Baseline Approved</option>
                      <option value="in_execution">In Execution</option>
                      <option value="closed">Closed</option>
                    </select>
                  </label>
                  <label>
                    <span>Authorization Reference</span>
                    <input
                      disabled={!canConfigure || projectAction}
                      onChange={(event) =>
                        setProjectDraft((current) => ({ ...current, authorization_ref: event.target.value }))
                      }
                      value={projectDraft.authorization_ref}
                    />
                  </label>
                  <label>
                    <span>Authorization Date</span>
                    <input
                      disabled={!canConfigure || projectAction}
                      onChange={(event) =>
                        setProjectDraft((current) => ({ ...current, authorization_date: event.target.value }))
                      }
                      type="date"
                      value={projectDraft.authorization_date}
                    />
                  </label>
                </div>
                <div className="formColumns">
                  <label>
                    <span>Currency</span>
                    <input
                      disabled={!canConfigure || projectAction}
                      maxLength={3}
                      onChange={(event) =>
                        setProjectDraft((current) => ({ ...current, currency: event.target.value.toUpperCase() }))
                      }
                      value={projectDraft.currency}
                    />
                  </label>
                  <label>
                    <span>Start</span>
                    <input
                      disabled={!canConfigure || projectAction}
                      onChange={(event) =>
                        setProjectDraft((current) => ({ ...current, start_date: event.target.value }))
                      }
                      type="date"
                      value={projectDraft.start_date}
                    />
                  </label>
                  <label>
                    <span>Finish</span>
                    <input
                      disabled={!canConfigure || projectAction}
                      onChange={(event) =>
                        setProjectDraft((current) => ({ ...current, finish_date: event.target.value }))
                      }
                      type="date"
                      value={projectDraft.finish_date}
                    />
                  </label>
                </div>
                <div className="formColumns">
                  <label>
                    <span>Control Level</span>
                    <select
                      disabled={!canConfigure || projectAction}
                      onChange={(event) =>
                        setProjectDraft((current) => ({ ...current, control_level: event.target.value }))
                      }
                      value={projectDraft.control_level}
                    >
                      <option value="control_account">Control Account</option>
                      <option value="cost_code">Cost Code</option>
                      <option value="awp_package">AWP Package</option>
                    </select>
                  </label>
                  <label className="checkboxLine">
                    <input
                      checked={projectDraft.funding_required}
                      disabled={!canConfigure || projectAction}
                      onChange={(event) =>
                        setProjectDraft((current) => ({ ...current, funding_required: event.target.checked }))
                      }
                      type="checkbox"
                    />
                    <span>Funding Required</span>
                  </label>
                </div>
                <button className="workflowAction primary" disabled={!canConfigure || projectAction} type="submit">
                  {projectAction ? "Creating..." : "Create Project"}
                </button>
              </form>
            ) : (
              <p className="projectHint">
                The selected project dashboard is open. Create a project only when onboarding a new project.
              </p>
            )}
            {projectMessage && <div className="uploadMessage success">{projectMessage}</div>}
            {projectError && <div className="uploadMessage error">{projectError}</div>}
          </section>
        </aside>

        <section className="projectDashboardArea" aria-label="Control dashboard">
          <section className="controlSummary">
            <div>
              <span>PV</span>
              <strong>{currency(kpi.pv, project.currency)}</strong>
            </div>
            <div>
              <span>EV</span>
              <strong>{currency(kpi.ev, project.currency)}</strong>
            </div>
            <div>
              <span>AC</span>
              <strong>{currency(kpi.ac, project.currency)}</strong>
            </div>
            <div>
              <span>SPI</span>
              <strong>{kpi.spi.toFixed(3)}</strong>
            </div>
            <div>
              <span>CPI</span>
              <strong>{kpi.cpi.toFixed(3)}</strong>
            </div>
            <div>
              <span>AWP Ready</span>
              <strong>{dashboard.awp_summary.readiness_score.toFixed(1)}%</strong>
            </div>
          </section>

          <section className="flowBand" aria-label="Project control process flow">
            <div className="flowTrack">
              {[
                ["Project", "Create"],
                ["Team Roles", currentMembership?.role ?? "Membership"],
                ["XML/XER Intake", activeImport ? "Loaded" : "Open"],
                ["Data Quality Gate", `${activeImport?.quality_score.toFixed(0) ?? "0"}%`],
                ["Control Accounts", dashboard.control_accounts.length],
                ["AWP Packages", dashboard.awp_summary.total_packages],
                ["Control Core", `${kpi.spi.toFixed(2)} SPI`],
              ].map(([label, value], index, items) => (
                <div className="flowStepWrap" key={label}>
                  <div className="flowStep">
                    <strong>{label}</strong>
                    <span>{value}</span>
                  </div>
                  {index < items.length - 1 && <div className="flowArrow">/</div>}
                </div>
              ))}
            </div>
          </section>

          <section aria-live="polite" className="viewPanel workspaceSection" id="control-flow-content">
          {activeControlView === "setup" && (
            <>
              <div className="panelHeader">
                <h2>Project Setup</h2>
                <span>{operationalSetup?.readiness_status === "ready" ? "Ready" : "Open"}</span>
              </div>
              <div className="viewSplit">
                <form className="adminPanel" onSubmit={handleOperationalSetupSubmit}>
                  <div className="panelHeader compactHeader">
                    <h2>Operational Readiness</h2>
                    <span>{operationalSetup?.readiness_notes ?? "Pending setup"}</span>
                  </div>
                  <div className="formColumns">
                    <label>
                      <span>Project Number</span>
                      <input
                        disabled={!canConfigure || setupAction}
                        onChange={(event) =>
                          setSetupDraft((current) => ({ ...current, project_number: event.target.value }))
                        }
                        required
                        value={setupDraft.project_number}
                      />
                    </label>
                    <label>
                      <span>Status</span>
                      <select
                        disabled={!canConfigure || setupAction}
                        onChange={(event) => setSetupDraft((current) => ({ ...current, status: event.target.value }))}
                        value={setupDraft.status}
                      >
                        <option value="draft">Draft</option>
                        <option value="in_review">In Review</option>
                        <option value="ready">Ready</option>
                        <option value="active">Active</option>
                      </select>
                    </label>
                  </div>
                  <label>
                    <span>Setup Template</span>
                    <input
                      disabled={!canConfigure || setupAction}
                      onChange={(event) =>
                        setSetupDraft((current) => ({ ...current, setup_template: event.target.value }))
                      }
                      required
                      value={setupDraft.setup_template}
                    />
                  </label>
                  <label>
                    <span>Attribute Form</span>
                    <input
                      disabled={!canConfigure || setupAction}
                      onChange={(event) =>
                        setSetupDraft((current) => ({ ...current, attribute_form: event.target.value }))
                      }
                      required
                      value={setupDraft.attribute_form}
                    />
                  </label>
                  <div className="formColumns">
                    {[
                      ["permissions_configured", "Permissions"],
                      ["modules_configured", "Modules"],
                      ["cost_sheet_ready", "Cost Sheet"],
                      ["funding_sheet_ready", "Funding Sheet"],
                      ["p6_mapping_ready", "P6 Mapping"],
                    ].map(([field, label]) => (
                      <label className="checkboxLine" key={field}>
                        <input
                          checked={Boolean(setupDraft[field as keyof typeof setupDraft])}
                          disabled={!canConfigure || setupAction}
                          onChange={(event) =>
                            setSetupDraft((current) => ({ ...current, [field]: event.target.checked }))
                          }
                          type="checkbox"
                        />
                        <span>{label}</span>
                      </label>
                    ))}
                  </div>
                  <button className="workflowAction primary" disabled={!canConfigure || setupAction} type="submit">
                    {setupAction ? "Saving..." : "Save Setup"}
                  </button>
                </form>

                <div className="panel">
                  <div className="panelHeader compactHeader">
                    <h2>
                      <FileUp size={18} /> Activity Sheet
                    </h2>
                    <span>{activitySheets.length} loads</span>
                  </div>
                  <label
                    className={
                      activityAction || operationalSetup?.readiness_status !== "ready"
                        ? "uploadButton disabled"
                        : "uploadButton"
                    }
                  >
                    <input
                      accept=".xml,.xer"
                      disabled={!canUploadSchedule || activityAction || operationalSetup?.readiness_status !== "ready"}
                      onChange={handleActivitySheetUpload}
                      type="file"
                    />
                    <span>{activityAction ? "Loading..." : "Load XML/XER"}</span>
                  </label>
                  <div className="workList compactList">
                    {activitySheets.slice(0, 6).map((sheet) => (
                      <article key={sheet.id}>
                        <strong>{sheet.source_file_name}</strong>
                        <span>
                          {sheet.row_count} rows / {statusLabel(sheet.status)}
                        </span>
                        <small>{sheet.data_date ?? "No data date"}</small>
                      </article>
                    ))}
                    {!activitySheets.length && (
                      <article>
                        <strong>No activity loads</strong>
                        <span>Activity data will appear after controlled load.</span>
                      </article>
                    )}
                  </div>
                </div>
              </div>
              <div className="panel wide">
                <div className="panelHeader compactHeader">
                  <h2>WBS Sheet</h2>
                  <span>
                    {activitySheetWbsRows.length} WBS / {currency(activitySheetPlannedCost, project.currency)}
                  </span>
                </div>
                {activitySheetWbsRows.length ? (
                  <table>
                    <thead>
                      <tr>
                        <th>WBS</th>
                        <th>Activities</th>
                        <th>Control Accounts</th>
                        <th>PV</th>
                        <th>Review</th>
                      </tr>
                    </thead>
                    <tbody>
                      {activitySheetWbsRows.slice(0, 8).map((row) => (
                        <tr key={row.wbs_code}>
                          <td>
                            <strong>{row.wbs_code}</strong>
                            <span>{row.wbs_name}</span>
                          </td>
                          <td>{row.activity_count}</td>
                          <td>{row.control_account_count}</td>
                          <td>
                            <strong>{currency(row.planned_value, project.currency)}</strong>
                            <span>{currency(row.planned_cost, project.currency)} planned</span>
                          </td>
                          <td>
                            <strong>{row.needs_review_count}</strong>
                            <span>{row.unmapped_activity_count} unmapped</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <div className="workspaceEmpty compactEmpty">
                    <strong>WBS Sheet pending</strong>
                    <p>WBS roll-up will appear after the first controlled Activity Sheet load.</p>
                  </div>
                )}
                {activitySheetNeedsReview > 0 && (
                  <div className="uploadMessage error">
                    {activitySheetNeedsReview} activity rows need CBS, cost or control-account review.
                  </div>
                )}
              </div>
              <div className="panel wide">
                <div className="panelHeader compactHeader">
                  <h2>Activity Rows</h2>
                  <span>{activitySheetRows.length} lines</span>
                </div>
                {activitySheetRows.length ? (
                  <table>
                    <thead>
                      <tr>
                        <th>Activity</th>
                        <th>WBS / CA</th>
                        <th>CBS</th>
                        <th>Planned</th>
                        <th>PV</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {activitySheetRows.slice(0, 10).map((row) => (
                        <tr key={row.id}>
                          <td>
                            <strong>{row.external_activity_id}</strong>
                            <span>{row.activity_name}</span>
                          </td>
                          <td>
                            <strong>{row.wbs_code}</strong>
                            <span>{row.control_account_code || "CA pending"}</span>
                          </td>
                          <td>{row.cbs_code || "CBS pending"}</td>
                          <td>{currency(row.planned_cost, project.currency)}</td>
                          <td>
                            <strong>{currency(row.planned_value, project.currency)}</strong>
                            <span>{row.planned_percent.toFixed(1)}%</span>
                          </td>
                          <td>{statusLabel(row.mapping_status)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <div className="workspaceEmpty compactEmpty">
                    <strong>No activity rows</strong>
                  </div>
                )}
              </div>
              {setupMessage && <div className="uploadMessage success">{setupMessage}</div>}
              {setupError && <div className="uploadMessage error">{setupError}</div>}
            </>
          )}
          {activeControlView === "dashboard" && (
            <>
              <div className="panelHeader">
                <h2>Control Dashboard</h2>
                <span>
                  {project.code} / {project.phase}
                </span>
              </div>
              <div className="dashboardOverviewPanel">
                <div className="panelHeader compactHeader">
                  <h2>Dashboard Overview</h2>
                  <span>Project control visual summary</span>
                </div>
                <div className="dashboardChartDeck">
                  <section className="chartTile" aria-label="Control Mix">
                    <div className="chartTileHeader">
                      <h3>Control Mix</h3>
                      <span>Baseline / progress / cost / AWP</span>
                    </div>
                    <div className="pieChartLayout">
                      <div className="pieChartCanvas">
                        <ResponsiveContainer width="100%" height={220}>
                          <PieChart>
                            <Pie
                              data={controlMixData}
                              dataKey="value"
                              innerRadius={48}
                              nameKey="name"
                              outerRadius={82}
                              paddingAngle={2}
                            >
                              {controlMixData.map((entry) => (
                                <Cell fill={entry.color} key={entry.name} />
                              ))}
                            </Pie>
                            <Tooltip formatter={(value) => Number(value).toLocaleString()} />
                          </PieChart>
                        </ResponsiveContainer>
                      </div>
                      <div className="dashboardLegend">
                        {controlMixData.map((entry) => (
                          <div key={entry.name}>
                            <span style={{ backgroundColor: entry.color }} />
                            <strong>{entry.name}</strong>
                            <small>{entry.actual.toLocaleString()}</small>
                          </div>
                        ))}
                      </div>
                    </div>
                  </section>

                  <section className="chartTile" aria-label="Workload by Area">
                    <div className="chartTileHeader">
                      <h3>Workload by Area</h3>
                      <span>Live control records</span>
                    </div>
                    <div className="barChartCanvas">
                      <ResponsiveContainer width="100%" height={220}>
                        <BarChart data={workloadChartData} layout="vertical" margin={{ left: 4, right: 20 }}>
                          <CartesianGrid horizontal={false} stroke="#e4e8ec" />
                          <XAxis allowDecimals={false} axisLine={false} tickLine={false} type="number" />
                          <YAxis
                            axisLine={false}
                            dataKey="name"
                            tickLine={false}
                            type="category"
                            width={96}
                          />
                          <Tooltip formatter={(value) => Number(value).toLocaleString()} />
                          <Bar dataKey="value" radius={[0, 8, 8, 0]}>
                            {workloadChartData.map((entry) => (
                              <Cell fill={entry.color} key={entry.name} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </section>
                </div>
              </div>
              <div className="awpSummary">
                <article>
                  <span>PV</span>
                  <strong>{currency(kpi.pv, project.currency)}</strong>
                  <small>Planned value</small>
                </article>
                <article>
                  <span>EV</span>
                  <strong>{currency(kpi.ev, project.currency)}</strong>
                  <small>Earned value</small>
                </article>
                <article className={kpi.cpi < 0.95 ? "risk" : ""}>
                  <span>CPI</span>
                  <strong>{kpi.cpi.toFixed(3)}</strong>
                  <small>Cost performance</small>
                </article>
                <article className={kpi.spi < 0.95 ? "risk" : ""}>
                  <span>SPI</span>
                  <strong>{kpi.spi.toFixed(3)}</strong>
                  <small>Schedule performance</small>
                </article>
              </div>
              <div className="panel wide evmCurvePanel">
                <div className="panelHeader compactHeader">
                  <h2>EVM S-Curve</h2>
                  <span>PV / EV / AC</span>
                </div>
                <ResponsiveContainer width="100%" height={270}>
                  <AreaChart data={evmCurveData}>
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
              <div className="viewSplit">
                <div className="panel">
                  <div className="panelHeader compactHeader">
                    <h2>Control Core Status</h2>
                    <span>{dashboard.control_accounts.length} accounts</span>
                  </div>
                  <div className="workList">
                    <article>
                      <strong>{activeImport ? "Baseline loaded" : "Baseline pending"}</strong>
                      <span>
                        {activeImport
                          ? `${activeImport.baseline_name} / quality ${activeImport.quality_score.toFixed(0)}%`
                          : "Upload XML/XER to start the baseline and control workflow."}
                      </span>
                      <small>
                        {dashboard.schedule_activity_count} activities / {dashboard.schedule_findings.length} findings
                      </small>
                    </article>
                    <article>
                      <strong>AWP readiness {dashboard.awp_summary.readiness_score.toFixed(1)}%</strong>
                      <span>
                        {dashboard.awp_summary.ready_for_release} ready / {dashboard.awp_summary.blocked_packages} blocked
                      </span>
                      <small>{dashboard.awp_summary.total_packages} work packages</small>
                    </article>
                  </div>
                </div>
                <div className="panel">
                  <div className="panelHeader compactHeader">
                    <h2>Control Flow Snapshot</h2>
                    <span>Live project controls</span>
                  </div>
                  <div className="loopList">
                    {(dashboard.flow ?? []).length ? (
                      dashboard.flow.map((item) => (
                        <div key={item.name}>
                          <strong>{item.name}</strong>
                          <span>
                            {item.state} / {item.purpose}
                          </span>
                        </div>
                      ))
                    ) : (
                      <>
                        <div>
                          <strong>Baseline</strong>
                          <span>{dashboard.schedule_activity_count} activities loaded</span>
                        </div>
                        <div>
                          <strong>Progress</strong>
                          <span>{dashboard.latest_progress_records.length} records captured</span>
                        </div>
                        <div>
                          <strong>Costs</strong>
                          <span>{dashboard.cost_sheet.length} cost lines available</span>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              </div>
              <div className="viewSplit">
                <div className="panel">
                  <div className="panelHeader compactHeader">
                    <h2>CBS Cost Codes</h2>
                    <span>{cbsCostLines.length} cost lines</span>
                  </div>
                  {cbsCostLines.length ? (
                    <table>
                      <thead>
                        <tr>
                          <th>CBS</th>
                          <th>Control Account</th>
                          <th>BAC</th>
                          <th>EV</th>
                          <th>AC</th>
                        </tr>
                      </thead>
                      <tbody>
                        {cbsCostLines.slice(0, 6).map((line) => (
                          <tr key={line.control_account_id}>
                            <td>{line.cbs_code || "CBS pending"}</td>
                            <td>
                              <strong>{line.control_account_code}</strong>
                              <span>{line.control_account_name}</span>
                            </td>
                            <td>{currency(line.bac, project.currency)}</td>
                            <td>{currency(line.earned_value, project.currency)}</td>
                            <td>{currency(line.actual_cost, project.currency)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <div className="workspaceEmpty compactEmpty">
                      <strong>CBS pending</strong>
                      <p>Cost codes will appear after budget and control account mapping are loaded.</p>
                    </div>
                  )}
                </div>
                <div className="panel">
                  <div className="panelHeader compactHeader">
                    <h2>FBS Funding Codes</h2>
                    <span>{currency(totalFunding, project.currency)}</span>
                  </div>
                  <div className="workList compactList">
                    {fbsFundingSources.length ? (
                      fbsFundingSources.slice(0, 6).map((source) => (
                        <article key={source.id}>
                          <strong>
                            {source.code} / {currency(source.amount, source.currency)}
                          </strong>
                          <span>{source.name}</span>
                          <small>{statusLabel(source.status)} funding source</small>
                        </article>
                      ))
                    ) : (
                      <article>
                        <strong>FBS pending</strong>
                        <span>Funding codes will appear after sources, restrictions or authorizations are loaded.</span>
                      </article>
                    )}
                  </div>
                </div>
              </div>
            </>
          )}
          {activeControlView === "integrated-control" && (
            <>
              <div className="panelHeader">
                <h2>Integrated Control Matrix</h2>
                <span>{integratedMatrix.length} trace rows</span>
              </div>
              <div className="viewSplit">
                <form className="adminPanel" onSubmit={handleFbsCreate}>
                  <div className="panelHeader compactHeader">
                    <h2>Initial FBS</h2>
                    <span>{fbsFundingSources.length} sources</span>
                  </div>
                  <label>
                    <span>FBS Code</span>
                    <input
                      disabled={!canConfigure || fbsAction}
                      onChange={(event) => setFbsDraft((current) => ({ ...current, code: event.target.value }))}
                      placeholder="FBS-OWN-AFE002-PLT"
                      required
                      value={fbsDraft.code}
                    />
                  </label>
                  <label>
                    <span>Source</span>
                    <input
                      disabled={!canConfigure || fbsAction}
                      onChange={(event) =>
                        setFbsDraft((current) => ({ ...current, source_of_funds: event.target.value }))
                      }
                      required
                      value={fbsDraft.source_of_funds}
                    />
                  </label>
                  <div className="formColumns">
                    <label>
                      <span>Type</span>
                      <select
                        disabled={!canConfigure || fbsAction}
                        onChange={(event) =>
                          setFbsDraft((current) => ({ ...current, funding_type: event.target.value }))
                        }
                        value={fbsDraft.funding_type}
                      >
                        <option value="AFE">AFE</option>
                        <option value="Debt">Debt</option>
                        <option value="Public funding">Public funding</option>
                        <option value="Reserve">Reserve</option>
                      </select>
                    </label>
                    <label>
                      <span>Authorization</span>
                      <input
                        disabled={!canConfigure || fbsAction}
                        onChange={(event) =>
                          setFbsDraft((current) => ({ ...current, authorization_ref: event.target.value }))
                        }
                        value={fbsDraft.authorization_ref}
                      />
                    </label>
                  </div>
                  <div className="formColumns">
                    <label>
                      <span>Approved</span>
                      <input
                        disabled={!canConfigure || fbsAction}
                        min="0"
                        onChange={(event) =>
                          setFbsDraft((current) => ({ ...current, approved_amount: event.target.value }))
                        }
                        required
                        type="number"
                        value={fbsDraft.approved_amount}
                      />
                    </label>
                    <label>
                      <span>Currency</span>
                      <input
                        disabled={!canConfigure || fbsAction}
                        maxLength={3}
                        onChange={(event) =>
                          setFbsDraft((current) => ({ ...current, currency: event.target.value.toUpperCase() }))
                        }
                        value={fbsDraft.currency}
                      />
                    </label>
                  </div>
                  <button className="workflowAction primary" disabled={!canConfigure || fbsAction} type="submit">
                    {fbsAction ? "Creating..." : "Create FBS"}
                  </button>
                </form>

                <div className="panel">
                  <div className="panelHeader compactHeader">
                    <h2>Funding Alerts</h2>
                    <span>{fundingAlerts.length} alerts</span>
                  </div>
                  <div className="awpSummary">
                    <article className={fundingAlerts.length ? "risk" : ""}>
                      <span>Forecast Gaps</span>
                      <strong>{fundingAlerts.length}</strong>
                      <small>FBS below forecast</small>
                    </article>
                    <article>
                      <span>Unused Balance</span>
                      <strong>{currency(closeoutReport?.unused_balance ?? 0, project.currency)}</strong>
                      <small>{closeoutReport?.open_commitments ?? 0} open commitments</small>
                    </article>
                  </div>
                  <div className="workList compactList">
                    {forecastFundingRows.slice(0, 6).map((row) => (
                      <article className={row.forecast_vs_available < 0 ? "blockedPackage" : undefined} key={row.fbs_code}>
                        <strong>
                          {row.fbs_code} / {currency(row.funds_available, project.currency)}
                        </strong>
                        <span>{currency(row.forecast, project.currency)} forecast</span>
                        <small>{currency(row.forecast_vs_available, project.currency)} vs available</small>
                      </article>
                    ))}
                    {!forecastFundingRows.length && (
                      <article>
                        <strong>No funding rows</strong>
                        <span>FBS records will appear after funding is configured.</span>
                      </article>
                    )}
                  </div>
                  <button
                    className="workflowAction"
                    disabled={!canConfigure || baselineAction}
                    onClick={handleBaselineApproval}
                    type="button"
                  >
                    {baselineAction ? "Approving..." : "Approve Baseline"}
                  </button>
                </div>
              </div>

              <div className="viewSplit">
                <form className="adminPanel" onSubmit={handleCbsCreate}>
                  <div className="panelHeader compactHeader">
                    <h2>CBS Setup</h2>
                    <span>{cbsCatalog.length} codes / {costCodes.length} cost codes</span>
                  </div>
                  <label>
                    <span>CBS Code</span>
                    <input
                      disabled={!canCaptureCost || priorityAction === "cbs"}
                      onChange={(event) => setCbsDraft((current) => ({ ...current, code: event.target.value }))}
                      placeholder={activitySheetRows[0]?.cbs_code || "CBS-PLT-CIV-A100"}
                      required
                      value={cbsDraft.code}
                    />
                  </label>
                  <div className="formColumns">
                    <label>
                      <span>Category</span>
                      <input
                        disabled={!canCaptureCost || priorityAction === "cbs"}
                        onChange={(event) => setCbsDraft((current) => ({ ...current, cost_category: event.target.value }))}
                        required
                        value={cbsDraft.cost_category}
                      />
                    </label>
                    <label>
                      <span>Level</span>
                      <input
                        disabled={!canCaptureCost || priorityAction === "cbs"}
                        min="1"
                        onChange={(event) => setCbsDraft((current) => ({ ...current, level: event.target.value }))}
                        type="number"
                        value={cbsDraft.level}
                      />
                    </label>
                  </div>
                  <label>
                    <span>Description</span>
                    <input
                      disabled={!canCaptureCost || priorityAction === "cbs"}
                      onChange={(event) => setCbsDraft((current) => ({ ...current, description: event.target.value }))}
                      value={cbsDraft.description}
                    />
                  </label>
                  <button className="workflowAction primary" disabled={!canCaptureCost || priorityAction === "cbs"} type="submit">
                    {priorityAction === "cbs" ? "Creating..." : "Create CBS"}
                  </button>
                </form>

                <div className="panel">
                  <div className="panelHeader compactHeader">
                    <h2>BP Lines</h2>
                    <span>{selectedCbs?.code || "CBS pending"}</span>
                  </div>
                  <div className="formColumns">
                    <label>
                      <span>CBS</span>
                      <select
                        disabled={!canCaptureCost || Boolean(priorityAction)}
                        onChange={(event) => {
                          const nextCbs = cbsCatalog.find((item) => item.id === Number(event.target.value));
                          setPriorityDraft((current) => ({ ...current, cbs_id: event.target.value }));
                          if (nextCbs) setRateDraft((current) => ({ ...current, cbs_code: nextCbs.code }));
                        }}
                        value={priorityDraft.cbs_id}
                      >
                        <option value="">Select CBS</option>
                        {cbsCatalog.map((cbs) => (
                          <option key={cbs.id} value={cbs.id}>
                            {cbs.code}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      <span>FBS</span>
                      <select
                        disabled={!canCaptureCost || Boolean(priorityAction)}
                        onChange={(event) => setPriorityDraft((current) => ({ ...current, funding_source_id: event.target.value }))}
                        value={priorityDraft.funding_source_id}
                      >
                        <option value="">Select FBS</option>
                        {fbsFundingSources.map((source) => (
                          <option key={source.id} value={source.id}>
                            {source.code}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  <div className="formColumns">
                    <label>
                      <span>Control Account</span>
                      <select
                        disabled={!canCaptureCost || Boolean(priorityAction)}
                        onChange={(event) => {
                          const account = controlAccounts.find((item) => item.id === Number(event.target.value));
                          setPriorityDraft((current) => ({
                            ...current,
                            control_account_id: event.target.value,
                            wbs_id: account?.wbs_id ? String(account.wbs_id) : current.wbs_id,
                          }));
                        }}
                        value={priorityDraft.control_account_id}
                      >
                        <option value="">Select CA</option>
                        {controlAccounts.map((account) => (
                          <option key={account.id} value={account.id}>
                            {account.code}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      <span>WBS</span>
                      <select
                        disabled={!canCaptureCost || Boolean(priorityAction)}
                        onChange={(event) => setPriorityDraft((current) => ({ ...current, wbs_id: event.target.value }))}
                        value={priorityDraft.wbs_id || (selectedWbsForAccount ? String(selectedWbsForAccount.id) : "")}
                      >
                        <option value="">Select WBS</option>
                        {wbsCatalog.map((wbs) => (
                          <option key={wbs.id} value={wbs.id}>
                            {wbs.code}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  <div className="formColumns">
                    <label>
                      <span>Amount</span>
                      <input
                        disabled={!canCaptureCost || Boolean(priorityAction)}
                        min="0"
                        onChange={(event) => setPriorityDraft((current) => ({ ...current, amount: event.target.value }))}
                        type="number"
                        value={priorityDraft.amount}
                      />
                    </label>
                    <label>
                      <span>Quantity</span>
                      <input
                        disabled={!canCaptureCost || Boolean(priorityAction)}
                        min="0"
                        onChange={(event) => setPriorityDraft((current) => ({ ...current, quantity: event.target.value }))}
                        type="number"
                        value={priorityDraft.quantity}
                      />
                    </label>
                  </div>
                  <label>
                    <span>Description</span>
                    <input
                      disabled={!canCaptureCost || Boolean(priorityAction)}
                      onChange={(event) => setPriorityDraft((current) => ({ ...current, description: event.target.value }))}
                      value={priorityDraft.description}
                    />
                  </label>
                  <div className="actionRow">
                    <button
                      className="workflowAction"
                      disabled={!canCaptureCost || !canRunPriority || Boolean(priorityAction)}
                      onClick={() => handlePriorityBusinessProcess("fund")}
                      type="button"
                    >
                      {priorityAction === "fund" ? "Creating..." : "BP CBS-Fund"}
                    </button>
                    <button
                      className="workflowAction primary"
                      disabled={!canCaptureCost || !canRunPriority || !priorityDraft.wbs_id || Boolean(priorityAction)}
                      onClick={() => handlePriorityBusinessProcess("wbs")}
                      type="button"
                    >
                      {priorityAction === "wbs" ? "Creating..." : "BP CBS-WBS"}
                    </button>
                  </div>
                </div>
              </div>

              <div className="viewSplit">
                <form className="adminPanel" onSubmit={handleSovAndFundingCreate}>
                  <div className="panelHeader compactHeader">
                    <h2>SOV Funding</h2>
                    <span>{contractRows.length} contracts</span>
                  </div>
                  <label>
                    <span>Contract</span>
                    <select
                      disabled={!canManageContract || priorityAction === "sov"}
                      onChange={(event) => setSovDraft((current) => ({ ...current, contract_id: event.target.value }))}
                      required
                      value={sovDraft.contract_id}
                    >
                      <option value="">Select contract</option>
                      {contractRows.map((contract) => (
                        <option key={contract.id} value={contract.id}>
                          {contract.code}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="formColumns">
                    <label>
                      <span>Line</span>
                      <input
                        disabled={!canManageContract || priorityAction === "sov"}
                        onChange={(event) => setSovDraft((current) => ({ ...current, line_no: event.target.value }))}
                        required
                        value={sovDraft.line_no}
                      />
                    </label>
                    <label>
                      <span>Amount</span>
                      <input
                        disabled={!canManageContract || priorityAction === "sov"}
                        min="0"
                        onChange={(event) => setSovDraft((current) => ({ ...current, amount: event.target.value }))}
                        required
                        type="number"
                        value={sovDraft.amount}
                      />
                    </label>
                  </div>
                  <label>
                    <span>Description</span>
                    <input
                      disabled={!canManageContract || priorityAction === "sov"}
                      onChange={(event) => setSovDraft((current) => ({ ...current, description: event.target.value }))}
                      value={sovDraft.description}
                    />
                  </label>
                  <button
                    className="workflowAction primary"
                    disabled={!canManageContract || !sovDraft.contract_id || !sovDraft.amount || !canRunPriority || priorityAction === "sov"}
                    type="submit"
                  >
                    {priorityAction === "sov" ? "Funding..." : "Create SOV Funding"}
                  </button>
                </form>

                <form className="panel" onSubmit={handleRateSheetCreate}>
                  <div className="panelHeader compactHeader">
                    <h2>Rate / Recost</h2>
                    <span>{rateSheets.length} sheets</span>
                  </div>
                  <div className="formColumns">
                    <label>
                      <span>Rate Code</span>
                      <input
                        disabled={!canCaptureCost || priorityAction === "rate"}
                        onChange={(event) => setRateDraft((current) => ({ ...current, code: event.target.value }))}
                        required
                        value={rateDraft.code}
                      />
                    </label>
                    <label>
                      <span>CBS Code</span>
                      <select
                        disabled={!canCaptureCost || priorityAction === "rate"}
                        onChange={(event) => setRateDraft((current) => ({ ...current, cbs_code: event.target.value }))}
                        value={rateDraft.cbs_code}
                      >
                        <option value="">Select CBS code</option>
                        {rateCbsOptions.map((code) => (
                          <option key={code} value={code}>
                            {code}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  <label>
                    <span>Name</span>
                    <input
                      disabled={!canCaptureCost || priorityAction === "rate"}
                      onChange={(event) => setRateDraft((current) => ({ ...current, name: event.target.value }))}
                      value={rateDraft.name}
                    />
                  </label>
                  <div className="formColumns">
                    <label>
                      <span>Multiplier</span>
                      <input
                        disabled={!canCaptureCost || priorityAction === "rate"}
                        min="0.01"
                        onChange={(event) => setRateDraft((current) => ({ ...current, multiplier: event.target.value }))}
                        step="0.01"
                        type="number"
                        value={rateDraft.multiplier}
                      />
                    </label>
                    <label>
                      <span>Unit Rate</span>
                      <input
                        disabled={!canCaptureCost || priorityAction === "rate"}
                        min="0"
                        onChange={(event) => setRateDraft((current) => ({ ...current, unit_rate: event.target.value }))}
                        type="number"
                        value={rateDraft.unit_rate}
                      />
                    </label>
                  </div>
                  <div className="actionRow">
                    <button className="workflowAction" disabled={!canCaptureCost || priorityAction === "rate"} type="submit">
                      {priorityAction === "rate" ? "Creating..." : "Create Rate"}
                    </button>
                    <button
                      className="workflowAction primary"
                      disabled={!canCaptureCost || !latestActivitySheet || !rateSheets.length || priorityAction === "recost"}
                      onClick={handleRecostLatestActivitySheet}
                      type="button"
                    >
                      {priorityAction === "recost" ? "Recosting..." : "Recost Latest"}
                    </button>
                  </div>
                  <div className="workList compactWorkList">
                    {recostRuns.slice(0, 3).map((run) => (
                      <article key={run.id}>
                        <strong>
                          Run {run.run_no} / {currency(run.total_planned_cost, project.currency)}
                        </strong>
                        <span>
                          {run.updated_rows} rows by {run.created_by || "Project Controls"}
                        </span>
                      </article>
                    ))}
                    {!recostRuns.length && (
                      <article>
                        <strong>Recost History</strong>
                        <span>No runs</span>
                      </article>
                    )}
                  </div>
                </form>
              </div>

              <div className="viewSplit">
                <form className="adminPanel" onSubmit={handlePolicySubmit}>
                  <div className="panelHeader compactHeader">
                    <h2>BP Permissions</h2>
                    <span>{bpPolicies.length} policies</span>
                  </div>
                  <div className="formColumns">
                    <label>
                      <span>Process</span>
                      <select
                        disabled={!canConfigure || hardeningAction === "policy"}
                        onChange={(event) => setPolicyDraft((current) => ({ ...current, process_code: event.target.value }))}
                        value={policyDraft.process_code}
                      >
                        <option value="BP-CBS-WBS">BP CBS-WBS</option>
                        <option value="BP-CBS-FUND">BP CBS-Fund</option>
                      </select>
                    </label>
                    <label>
                      <span>Action</span>
                      <select
                        disabled={!canConfigure || hardeningAction === "policy"}
                        onChange={(event) => setPolicyDraft((current) => ({ ...current, action: event.target.value }))}
                        value={policyDraft.action}
                      >
                        <option value="approve_baseline">Approve</option>
                        <option value="reject_baseline">Reject</option>
                        <option value="close_action">Close</option>
                      </select>
                    </label>
                  </div>
                  <div className="formColumns">
                    <label>
                      <span>Role</span>
                      <select
                        disabled={!canConfigure || hardeningAction === "policy"}
                        onChange={(event) => setPolicyDraft((current) => ({ ...current, required_role: event.target.value }))}
                        value={policyDraft.required_role}
                      >
                        {policyRoleOptions.map((role) => (
                          <option key={role} value={role}>
                            {role}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      <span>Permission</span>
                      <select
                        disabled={!canConfigure || hardeningAction === "policy"}
                        onChange={(event) => setPolicyDraft((current) => ({ ...current, permission_key: event.target.value }))}
                        value={policyDraft.permission_key}
                      >
                        <option value="can_approve_workflow">Approve Workflow</option>
                        <option value="can_capture_cost">Capture Cost</option>
                        <option value="can_configure">Configure</option>
                      </select>
                    </label>
                  </div>
                  <button className="workflowAction primary" disabled={!canConfigure || hardeningAction === "policy"} type="submit">
                    <ShieldCheck size={15} />
                    {hardeningAction === "policy" ? "Saving..." : "Save Policy"}
                  </button>
                  <div className="workList compactWorkList">
                    {bpPolicies.slice(0, 3).map((policy) => (
                      <article key={policy.id}>
                        <strong>
                          {policy.process_code} / {statusLabel(policy.action)}
                        </strong>
                        <span>
                          {policy.required_role || "Any role"} / v{policy.version}
                        </span>
                      </article>
                    ))}
                  </div>
                </form>

                <form className="panel" onSubmit={handleLineItemUpdate}>
                  <div className="panelHeader compactHeader">
                    <h2>Line Versions</h2>
                    <span>{bpLineItems.length} items</span>
                  </div>
                  <label>
                    <span>Line Item</span>
                    <select
                      disabled={!canCaptureCost || hardeningAction === "line" || !bpLineItems.length}
                      onChange={(event) => {
                        const nextLine = bpLineItems.find((line) => String(line.id) === event.target.value);
                        if (nextLine) void handleLineItemSelect(nextLine);
                      }}
                      value={lineEditDraft.line_item_id}
                    >
                      {bpLineItems.map((line) => (
                        <option key={line.id} value={line.id}>
                          #{line.id} / {currency(line.amount, project.currency)} / v{line.version}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="formColumns">
                    <label>
                      <span>Amount</span>
                      <input
                        disabled={!canCaptureCost || hardeningAction === "line" || !selectedLineItem}
                        min="0"
                        onChange={(event) => setLineEditDraft((current) => ({ ...current, amount: event.target.value }))}
                        type="number"
                        value={lineEditDraft.amount}
                      />
                    </label>
                    <label>
                      <span>Quantity</span>
                      <input
                        disabled={!canCaptureCost || hardeningAction === "line" || !selectedLineItem}
                        min="0"
                        onChange={(event) => setLineEditDraft((current) => ({ ...current, quantity: event.target.value }))}
                        type="number"
                        value={lineEditDraft.quantity}
                      />
                    </label>
                  </div>
                  <label>
                    <span>Description</span>
                    <input
                      disabled={!canCaptureCost || hardeningAction === "line" || !selectedLineItem}
                      onChange={(event) => setLineEditDraft((current) => ({ ...current, description: event.target.value }))}
                      value={lineEditDraft.description}
                    />
                  </label>
                  <label>
                    <span>Change Note</span>
                    <input
                      disabled={!canCaptureCost || hardeningAction === "line" || !selectedLineItem}
                      onChange={(event) => setLineEditDraft((current) => ({ ...current, change_note: event.target.value }))}
                      value={lineEditDraft.change_note}
                    />
                  </label>
                  <button
                    className="workflowAction primary"
                    disabled={!canCaptureCost || !selectedLineItem || hardeningAction === "line"}
                    type="submit"
                  >
                    <Save size={15} />
                    {hardeningAction === "line" ? "Saving..." : "Save Version"}
                  </button>
                  <div className="workList compactWorkList">
                    {bpLineItemRevisions.slice(0, 3).map((revision) => (
                      <article key={revision.id}>
                        <strong>
                          v{revision.previous_version} to v{revision.new_version}
                        </strong>
                        <span>
                          {currency(revision.previous_amount, project.currency)} to{" "}
                          {currency(revision.new_amount, project.currency)}
                        </span>
                      </article>
                    ))}
                  </div>
                </form>
              </div>

              <div className="panel wide">
                <div className="panelHeader compactHeader">
                  <div className="agentProfileBlock">
                    <h2>AI Control Auditor</h2>
                    <small>Senior AWP Packaging Advisor</small>
                  </div>
                  <span>{latestAgentRun ? `${latestAgentRun.score}/100` : "No run"}</span>
                </div>
                <div className="gateFacts">
                  <div>
                    <span>Mode</span>
                    <strong>{latestAgentRun?.run_mode || "deterministic"}</strong>
                  </div>
                  <div>
                    <span>Model</span>
                    <strong>{latestAgentRun?.model_name || "low-cost audit rules"}</strong>
                  </div>
                  <div>
                    <span>Findings</span>
                    <strong>{agentFindings.length}</strong>
                  </div>
                </div>
                <div className="actionRow">
                  <button className="workflowAction primary" disabled={agentAction} onClick={handleControlAuditAgentRun} type="button">
                    <ShieldCheck size={15} />
                    {agentAction ? "Auditing..." : "Run Audit"}
                  </button>
                  <button className="workflowAction" disabled={agentAction} onClick={handleCreateAwpDraftPackages} type="button">
                    <PackagePlus size={15} />
                    {agentAction ? "Creating..." : "Create Draft Packages"}
                  </button>
                </div>
                <div className="workList compactWorkList">
                  {latestAgentRun && (
                    <article>
                      <strong>{latestAgentRun.summary}</strong>
                      <span>
                        {latestAgentRun.agent_name} by {latestAgentRun.created_by || "Project Controls"}
                      </span>
                    </article>
                  )}
                  {agentFindings.slice(0, 5).map((finding) => (
                    <article key={finding.id} className={finding.severity === "high" ? "risk" : ""}>
                      <strong>
                        {statusLabel(finding.severity)} / {finding.title}
                      </strong>
                      <span>{finding.evidence}</span>
                      <span>{finding.recommendation}</span>
                    </article>
                  ))}
                  {!latestAgentRun && (
                    <article>
                      <strong>No agent audit yet</strong>
                      <span>Run the read-only audit to prioritize BP policy, recost and funding checks.</span>
                    </article>
                  )}
                </div>
              </div>

              <div className="panel wide">
                <div className="panelHeader compactHeader">
                  <h2>Traceability</h2>
                  <span>FBS-WBS-AWP-CA-CBS-Cost Code</span>
                </div>
                <table>
                  <thead>
                    <tr>
                      <th>Project / FBS</th>
                      <th>WBS / AWP</th>
                      <th>Control Account / CBS</th>
                      <th>Cost Code / Contract</th>
                      <th>Budget</th>
                      <th>Funding</th>
                      <th>Forecast</th>
                    </tr>
                  </thead>
                  <tbody>
                    {integratedMatrix.map((row) => (
                      <tr key={row.cost_code}>
                        <td>
                          <strong>{row.project_code}</strong>
                          <span>{row.fbs_code}</span>
                        </td>
                        <td>
                          <strong>{row.wbs_code}</strong>
                          <span>
                            {row.awp_package_type || "AWP"} {row.awp_package_code || "pending"}
                          </span>
                        </td>
                        <td>
                          <strong>{row.control_account_code}</strong>
                          <span>{row.cbs_code}</span>
                        </td>
                        <td>
                          <strong>{row.cost_code}</strong>
                          <span>{row.contract_ref || "Commitment pending"}</span>
                        </td>
                        <td>{currency(row.budget, project.currency)}</td>
                        <td>
                          <strong>{currency(row.funds_available, project.currency)}</strong>
                          <span>{currency(row.committed, project.currency)} committed</span>
                        </td>
                        <td>
                          <strong>{currency(row.forecast, project.currency)}</strong>
                          <span>{currency(row.balance, project.currency)} balance</span>
                        </td>
                      </tr>
                    ))}
                    {!integratedMatrix.length && (
                      <tr>
                        <td colSpan={7}>
                          <strong>No integrated matrix rows</strong>
                          <span>Create cost codes linked to FBS, WBS, control accounts and CBS.</span>
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              <div className="panel wide">
                <div className="panelHeader compactHeader">
                  <h2>Reconciliation</h2>
                  <span>{reconciliationRows.length} rows</span>
                </div>
                <div className="actionRow">
                  <button
                    className="workflowAction"
                    disabled={hardeningAction === "export-xlsx"}
                    onClick={() => void handleReconciliationExport("xlsx")}
                    type="button"
                  >
                    <Download size={15} />
                    {hardeningAction === "export-xlsx" ? "Exporting..." : "Export XLSX"}
                  </button>
                  <button
                    className="workflowAction"
                    disabled={hardeningAction === "export-pdf"}
                    onClick={() => void handleReconciliationExport("pdf")}
                    type="button"
                  >
                    <Download size={15} />
                    {hardeningAction === "export-pdf" ? "Exporting..." : "Export PDF"}
                  </button>
                </div>
                <table>
                  <thead>
                    <tr>
                      <th>WBS / CBS</th>
                      <th>FBS / CA</th>
                      <th>Contract</th>
                      <th>Budget</th>
                      <th>SOV</th>
                      <th>Funding</th>
                      <th>Forecast</th>
                    </tr>
                  </thead>
                  <tbody>
                    {reconciliationRows.slice(0, 8).map((row) => (
                      <tr key={`${row.wbs_code}-${row.cbs_code}-${row.contract_ref}`}>
                        <td>
                          <strong>{row.wbs_code || "WBS pending"}</strong>
                          <span>{row.cbs_code || "CBS pending"}</span>
                        </td>
                        <td>
                          <strong>{row.fbs_code || "FBS pending"}</strong>
                          <span>{row.control_account_code || "CA pending"}</span>
                        </td>
                        <td>{row.contract_ref || "Pending"}</td>
                        <td>{currency(row.budget, project.currency)}</td>
                        <td>{currency(row.sov_amount, project.currency)}</td>
                        <td>{currency(row.funded_amount, project.currency)}</td>
                        <td>
                          <strong>{currency(row.forecast, project.currency)}</strong>
                          <span>{currency(row.variance, project.currency)} variance</span>
                        </td>
                      </tr>
                    ))}
                    {!reconciliationRows.length && (
                      <tr>
                        <td colSpan={7}>
                          <strong>No reconciliation rows</strong>
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              {integratedMessage && <div className="uploadMessage success">{integratedMessage}</div>}
              {integratedError && <div className="uploadMessage error">{integratedError}</div>}
            </>
          )}
          {activeControlView === "baseline" && (
            <>
              <div className="panelHeader">
                <h2>Baseline Control</h2>
                <span>
                  {dashboard.schedule_activity_count} activities / {dashboard.schedule_relationship_count} links
                </span>
              </div>
              <div className="gateFacts">
                <div>
                  <span>Current Baseline</span>
                  <strong>{activeImport?.baseline_name ?? "Pending upload"}</strong>
                </div>
                <div>
                  <span>Data Quality Gate</span>
                  <strong>
                    {activeImport ? `${activeImport.quality_score.toFixed(0)}% / ${activeImport.status}` : "Open"}
                  </strong>
                </div>
                <div>
                  <span>Data Date</span>
                  <strong>{activeImport?.data_date ?? "Pending"}</strong>
                </div>
                <div>
                  <span>Baseline Versions</span>
                  <strong>{dashboard.baseline_versions.length}</strong>
                </div>
              </div>
              <div className="viewSplit">
                <div className="panel">
                  <div className="panelHeader compactHeader">
                    <h2>Baseline Versions</h2>
                    <span>{dashboard.baseline_versions.length} records</span>
                  </div>
                  <div className="workList">
                    {dashboard.baseline_versions.length ? (
                      dashboard.baseline_versions.map((baseline) => (
                        <article key={baseline.id}>
                          <strong>
                            BL-{baseline.version_no.toString().padStart(2, "0")} / {statusLabel(baseline.status)}
                          </strong>
                          <span>{baseline.name}</span>
                          <small>
                            {baseline.data_date ?? "No data date"} / Quality {baseline.quality_score.toFixed(0)}%
                          </small>
                        </article>
                      ))
                    ) : (
                      <article>
                        <strong>No baseline versions yet</strong>
                        <span>Upload XML/XER to create the first controlled schedule baseline.</span>
                      </article>
                    )}
                  </div>
                </div>
                <div className="panel">
                  <div className="panelHeader compactHeader">
                    <h2>Quality Findings</h2>
                    <span>{dashboard.schedule_findings.length} records</span>
                  </div>
                  <div className="qualityList">
                    {dashboard.schedule_findings.length ? (
                      dashboard.schedule_findings.map((finding) => (
                        <article key={finding.id}>
                          <div>
                            <strong>{finding.check_code}</strong>
                            <span className={`qualityStatus ${finding.severity.toLowerCase()}`}>
                              {statusLabel(finding.severity)}
                            </span>
                          </div>
                          <p>{finding.message}</p>
                          <small>{finding.item_count} items</small>
                        </article>
                      ))
                    ) : (
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
              </div>
            </>
          )}
          {activeControlView === "progress" && (
            <>
              <div className="panelHeader">
                <h2>Progress Control</h2>
                <span>{dashboard.latest_progress_records.length} records</span>
              </div>
              <div className="workList">
                {dashboard.latest_progress_records.length ? (
                  dashboard.latest_progress_records.map((record) => (
                    <article key={record.id}>
                      <strong>{controlAccountLabel(dashboard, record.control_account_id)}</strong>
                      <span>{record.physical_percent.toFixed(1)}% physical progress</span>
                      <small>
                        {record.quantity_installed} installed / {record.labor_hours} hours /{" "}
                        {record.reported_on ?? "No report date"}
                      </small>
                    </article>
                  ))
                ) : (
                  <article>
                    <strong>No progress captured</strong>
                    <span>Progress records will appear here after field updates are captured.</span>
                  </article>
                )}
              </div>
            </>
          )}
          {activeControlView === "costs" && (
            <>
              <div className="panelHeader">
                <h2>Cost Control</h2>
                <span>{dashboard.cost_sheet.length} cost lines</span>
              </div>
              <table>
                <thead>
                  <tr>
                    <th>Control Account</th>
                    <th>CBS</th>
                    <th>BAC</th>
                    <th>EV</th>
                    <th>AC</th>
                    <th>CPI</th>
                  </tr>
                </thead>
                <tbody>
                  {dashboard.cost_sheet.map((line) => (
                    <tr key={line.control_account_id}>
                      <td>
                        <strong>{line.control_account_code}</strong>
                        <span>{line.control_account_name}</span>
                      </td>
                      <td>{line.cbs_code || "CBS pending"}</td>
                      <td>{currency(line.bac, project.currency)}</td>
                      <td>{currency(line.earned_value, project.currency)}</td>
                      <td>{currency(line.actual_cost, project.currency)}</td>
                      <td>{line.cpi.toFixed(3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!dashboard.cost_sheet.length && (
                <div className="workspaceEmpty">
                  <strong>No cost lines yet</strong>
                  <p>Cost data will appear after CBS and control account mapping are loaded.</p>
                </div>
              )}
            </>
          )}
          {activeControlView === "decisions" && (
            <>
              <div className="panelHeader">
                <h2>Decision Register</h2>
                <span>{dashboard.changes.length} changes</span>
              </div>
              <div className="workList">
                {dashboard.changes.length ? (
                  dashboard.changes.map((change) => (
                    <article key={change.id}>
                      <strong>{change.title}</strong>
                      <span>{change.deviation}</span>
                      <small>
                        {currency(change.cost_impact, project.currency)} / {change.schedule_impact_days} days /{" "}
                        {statusLabel(change.status)}
                      </small>
                    </article>
                  ))
                ) : (
                  <article>
                    <strong>No decisions pending</strong>
                    <span>Change and deviation decisions will be listed here.</span>
                  </article>
                )}
              </div>
            </>
          )}
          {activeControlView === "evidence" && (
            <>
              <div className="panelHeader">
                <h2>Evidence Register</h2>
                <span>{dashboard.document_control_summary.controlled_document_score.toFixed(0)}% controlled</span>
              </div>
              <div className="awpSummary">
                <article>
                  <span>Documents</span>
                  <strong>{dashboard.document_control_summary.total_documents ?? 0}</strong>
                  <small>{dashboard.document_control_summary.current_documents ?? 0} current</small>
                </article>
                <article className={dashboard.document_control_summary.overdue_reviews ? "risk" : ""}>
                  <span>Reviews</span>
                  <strong>{dashboard.document_control_summary.outstanding_reviews ?? 0}</strong>
                  <small>{dashboard.document_control_summary.overdue_reviews ?? 0} overdue</small>
                </article>
                <article>
                  <span>Transmittals</span>
                  <strong>{dashboard.document_control_summary.transmittals_sent ?? 0}</strong>
                  <small>{dashboard.document_control_summary.open_mail ?? 0} open mail</small>
                </article>
                <article>
                  <span>Attachments</span>
                  <strong>{dashboard.document_attachments.length}</strong>
                  <small>Evidence files</small>
                </article>
              </div>
              <div className="workList">
                {dashboard.documents.length ? (
                  dashboard.documents.slice(0, 12).map((document) => (
                    <article key={document.id}>
                      <strong>
                        {document.document_number} / Rev {document.revision}
                      </strong>
                      <span>{document.title}</span>
                      <small>
                        {document.doc_type} / {statusLabel(document.review_status)} / {document.file_name}
                      </small>
                    </article>
                  ))
                ) : (
                  <article>
                    <strong>No evidence documents yet</strong>
                    <span>Controlled documents and attachments will appear here.</span>
                  </article>
                )}
              </div>
            </>
          )}
          {activeControlView === "work-packages" && (
            <>
          <div className="panelHeader">
            <h2>AWP Minimum Register</h2>
            <span>
              {dashboard.awp_summary.cwp_count} CWP / {dashboard.awp_summary.iwp_count} IWP /{" "}
              {dashboard.awp_summary.twp_count} TWP / {dashboard.awp_summary.top_count} TOP
            </span>
          </div>

          <div className="awpSummary">
            <article className={dashboard.awp_summary.blocking_constraints ? "risk" : ""}>
              <span>Open Constraints</span>
              <strong>{dashboard.awp_summary.open_constraints}</strong>
              <small>{dashboard.awp_summary.blocking_constraints} blocking</small>
            </article>
            <article className={dashboard.awp_summary.high_priority_constraints ? "risk" : ""}>
              <span>High Priority</span>
              <strong>{dashboard.awp_summary.high_priority_constraints}</strong>
              <small>Before release</small>
            </article>
            <article>
              <span>Closure Evidence</span>
              <strong>{dashboard.awp_summary.closure_evidence_count}</strong>
              <small>Closed constraints</small>
            </article>
            <article>
              <span>Ready Packages</span>
              <strong>{dashboard.awp_summary.ready_for_release}</strong>
              <small>{dashboard.awp_summary.blocked_packages} blocked</small>
            </article>
          </div>

          <div className="viewSplit">
            <div className="panel">
              <div className="panelHeader compactHeader">
                <h2>Master Packages</h2>
                <span>{dashboard.work_packages.length} records</span>
              </div>
              <div className="workList">
                {dashboard.work_packages.map((workPackage) => (
                  <article
                    className={constraintsByPackage[workPackage.id] ? "blockedPackage" : ""}
                    key={workPackage.id}
                  >
                    <strong>
                      {workPackage.package_type} / {workPackage.code}
                    </strong>
                    <span>{workPackage.title}</span>
                    <small>
                      POC: {workPackage.path_of_construction || "No path defined"}
                    </small>
                    <div className="packageFacts">
                      <span>{statusLabel(workPackage.readiness_status)}</span>
                      <span>{controlAccountLabel(dashboard, workPackage.control_account_id)}</span>
                      <span>Release {workPackage.release_required_on ?? workPackage.planned_start ?? "Pending"}</span>
                      <span>{constraintsByPackage[workPackage.id] ?? 0} blockers</span>
                    </div>
                  </article>
                ))}
              </div>
            </div>

            <div className="panel">
              <div className="panelHeader compactHeader">
                <h2>Constraint Register</h2>
                <span>{dashboard.work_package_constraints.length} records</span>
              </div>
              <form className="captureForm compactForm" onSubmit={handleCreateWorkPackageConstraint}>
                <label>
                  Package
                  <select
                    value={constraintDraft.work_package_id}
                    onChange={(event) => setConstraintDraft((draft) => ({ ...draft, work_package_id: event.target.value }))}
                  >
                    <option value="">Select package</option>
                    {dashboard.work_packages.map((workPackage) => (
                      <option key={workPackage.id} value={workPackage.id}>
                        {workPackage.package_type} / {workPackage.code}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Type
                  <select
                    value={constraintDraft.constraint_type}
                    onChange={(event) => setConstraintDraft((draft) => ({ ...draft, constraint_type: event.target.value }))}
                  >
                    <option>Engineering Documents</option>
                    <option>Materials</option>
                    <option>Safety / Quality</option>
                    <option>Permits / Access</option>
                    <option>Recost / Funding</option>
                    <option>Field Execution</option>
                  </select>
                </label>
                <label>
                  Owner
                  <input
                    value={constraintDraft.owner_role}
                    onChange={(event) => setConstraintDraft((draft) => ({ ...draft, owner_role: event.target.value }))}
                  />
                </label>
                <label>
                  Required
                  <input
                    type="date"
                    value={constraintDraft.required_by}
                    onChange={(event) => setConstraintDraft((draft) => ({ ...draft, required_by: event.target.value }))}
                  />
                </label>
                <label>
                  Priority
                  <select
                    value={constraintDraft.priority}
                    onChange={(event) => setConstraintDraft((draft) => ({ ...draft, priority: event.target.value }))}
                  >
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="low">Low</option>
                  </select>
                </label>
                <label>
                  Evidence
                  <input
                    placeholder="Document, RFI or checklist reference"
                    value={constraintDraft.evidence_ref}
                    onChange={(event) => setConstraintDraft((draft) => ({ ...draft, evidence_ref: event.target.value }))}
                  />
                </label>
                <label className="checkboxLine">
                  <input
                    checked={constraintDraft.blocking}
                    type="checkbox"
                    onChange={(event) => setConstraintDraft((draft) => ({ ...draft, blocking: event.target.checked }))}
                  />
                  Blocking
                </label>
                <label className="fullWidth">
                  Description
                  <textarea
                    placeholder="Describe what must be resolved before package release"
                    value={constraintDraft.description}
                    onChange={(event) => setConstraintDraft((draft) => ({ ...draft, description: event.target.value }))}
                  />
                </label>
                <button className="workflowAction primary" disabled={constraintAction || !dashboard.work_packages.length} type="submit">
                  {constraintAction ? "Adding..." : "Add Constraint"}
                </button>
              </form>
              <div className="workList">
                {dashboard.work_package_constraints.map((constraint) => (
                  <article
                    className={constraint.status === "open" && constraint.blocking ? "blockedPackage" : undefined}
                    key={constraint.id}
                  >
                    <strong>
                      {statusLabel(constraint.priority)} / {packageLabel(dashboard, constraint.work_package_id)}
                    </strong>
                    <span>{constraint.description}</span>
                    <small>
                      {constraint.constraint_type} / Required {constraint.required_by ?? "Pending"} /{" "}
                      {statusLabel(constraint.status)}
                    </small>
                    <div className="packageFacts">
                      <span>{constraint.owner_role}</span>
                      <span>{constraint.evidence_ref || "Evidence pending"}</span>
                      <span>{constraint.closed_on ? `Closed ${constraint.closed_on}` : "Open"}</span>
                    </div>
                  </article>
                ))}
              </div>
            </div>
          </div>

          <div className="panel wide">
            <div className="panelHeader compactHeader">
              <h2>Control Accounts</h2>
              <span>{dashboard.control_accounts.length} mapped accounts</span>
            </div>
            <table>
              <thead>
                <tr>
                  <th>Account</th>
                  <th>Owner</th>
                  <th>CBS / Contract</th>
                  <th>Measurement</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {dashboard.control_accounts.map((account) => (
                  <tr key={account.id}>
                    <td>
                      <strong>{account.code}</strong>
                      <span>{account.name}</span>
                    </td>
                    <td>{account.responsible}</td>
                    <td>
                      <strong>{account.cbs_code || "CBS pending"}</strong>
                      <span>{account.contract_ref || "Contract pending"}</span>
                    </td>
                    <td>{account.measurement_rule || "Physical progress rule pending"}</td>
                    <td>
                      <strong>{statusLabel(account.lifecycle_status)}</strong>
                      <span>{account.risk_ref || "No risk ref"}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
            </>
          )}
          {activeControlView === "admin" && (
            <>
              <div className="panelHeader">
                <h2>Users & Roles</h2>
                <span>{dashboard.project_team.length} project assignments</span>
              </div>
              <div className="viewSplit">
                <form className="adminPanel" onSubmit={handleUserCreate}>
                  <div className="panelHeader compactHeader">
                    <h2>Create User</h2>
                    <span>{users.length} tenant users / default password 1234</span>
                  </div>
                  <label>
                    <span>Full Name</span>
                    <input
                      disabled={!canConfigure || userAction}
                      onChange={(event) => setUserDraft((current) => ({ ...current, full_name: event.target.value }))}
                      required
                      value={userDraft.full_name}
                    />
                  </label>
                  <label>
                    <span>Login Email</span>
                    <input
                      disabled={!canConfigure || userAction}
                      onChange={(event) => setUserDraft((current) => ({ ...current, email: event.target.value }))}
                      required
                      type="email"
                      value={userDraft.email}
                    />
                  </label>
                  <div className="formColumns">
                    <label>
                      <span>Temporary Password</span>
                      <input
                        disabled={!canConfigure || userAction}
                        onChange={(event) => setUserDraft((current) => ({ ...current, password: event.target.value }))}
                        required
                        type="text"
                        value={userDraft.password}
                      />
                    </label>
                    <label>
                      <span>Role Profile</span>
                      <select
                        disabled={!canConfigure || userAction}
                        onChange={(event) => setUserDraft((current) => ({ ...current, role: event.target.value }))}
                        value={userDraft.role}
                      >
                        {roles.map((role) => (
                          <option key={role.role} value={role.role}>
                            {role.role}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  <label>
                    <span>Title</span>
                    <input
                      disabled={!canConfigure || userAction}
                      onChange={(event) => setUserDraft((current) => ({ ...current, title: event.target.value }))}
                      value={userDraft.title}
                    />
                  </label>
                  <div className="permissionStrip">
                    {roles.find((role) => role.role === userDraft.role)?.can_capture_progress && <span>Progress</span>}
                    {roles.find((role) => role.role === userDraft.role)?.can_capture_cost && <span>Cost</span>}
                    {roles.find((role) => role.role === userDraft.role)?.can_approve_workflow && <span>Approve</span>}
                    {roles.find((role) => role.role === userDraft.role)?.can_manage_contract && <span>Contract</span>}
                    {roles.find((role) => role.role === userDraft.role)?.can_configure && <span>Admin</span>}
                  </div>
                  <button className="workflowAction primary" disabled={!canConfigure || userAction} type="submit">
                    {userAction ? "Creating..." : "Create User & Assign Role"}
                  </button>
                  {userMessage && <div className="uploadMessage success">{userMessage}</div>}
                  {userError && <div className="uploadMessage error">{userError}</div>}
                </form>

                <div className="panel">
                  <div className="panelHeader compactHeader">
                    <h2>Project Team</h2>
                    <span>{dashboard.project_team.length} assigned</span>
                  </div>
                  <div className="workList compactList">
                    {dashboard.project_team.map((member) => (
                      <article key={member.membership.id}>
                        <strong>
                          {member.user.full_name} / {member.membership.role}
                        </strong>
                        <span>{member.user.email}</span>
                        <small>{member.user.title || "No title"}</small>
                      </article>
                    ))}
                  </div>
                </div>
              </div>

              <div className="panel wide">
                <div className="panelHeader compactHeader">
                  <h2>Role Profiles</h2>
                  <span>{roles.length} profiles</span>
                </div>
                <table>
                  <thead>
                    <tr>
                      <th>Role</th>
                      <th>Description</th>
                      <th>Permissions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {roles.map((role) => (
                      <tr key={role.role}>
                        <td>
                          <strong>{role.role}</strong>
                        </td>
                        <td>{role.description}</td>
                        <td>
                          <div className="permissionStrip">
                            {role.can_capture_progress && <span>Progress</span>}
                            {role.can_capture_cost && <span>Cost</span>}
                            {role.can_approve_workflow && <span>Approve</span>}
                            {role.can_manage_contract && <span>Contract</span>}
                            {role.can_configure && <span>Admin</span>}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
          </section>

          <section className="scheduleGate" aria-label="Schedule Intake">
            <div className="gateHeader">
              <div className="gateIntro">
                <GitBranch size={20} />
                <div>
                  <strong>Schedule Intake</strong>
                  <span>Upload the source XML/XER to open the Data Quality Gate and baseline workflow.</span>
                </div>
              </div>
              <label className={uploading ? "uploadButton disabled" : "uploadButton"}>
                <FileUp size={18} />
                <span>{uploading ? "Uploading..." : "Schedule XML or XER"}</span>
                <input
                  aria-label="Schedule XML or XER"
                  accept=".xml,.xer"
                  disabled={!canUploadSchedule || uploading}
                  onChange={handleScheduleUpload}
                  type="file"
                />
              </label>
            </div>
            <div className="gateFacts">
              <div>
                <span>Current Baseline</span>
                <strong>{activeImport?.baseline_name ?? "Pending upload"}</strong>
              </div>
              <div>
                <span>Data Quality Gate</span>
                <strong>
                  {activeImport ? `${activeImport.quality_score.toFixed(0)}% / ${activeImport.status}` : "Open"}
                </strong>
              </div>
              <div>
                <span>Data Date</span>
                <strong>{activeImport?.data_date ?? "Pending"}</strong>
              </div>
              <div>
                <span>Activities</span>
                <strong>{dashboard.schedule_activity_count}</strong>
              </div>
              <div>
                <span>Findings</span>
                <strong>{dashboard.schedule_findings.length}</strong>
              </div>
            </div>
            <p>
              The approved baseline feeds control accounts, AWP packages, progress capture, cost loading and Control
              Core decisions.
            </p>
            {uploadMessage && <div className="uploadMessage success">{uploadMessage}</div>}
            {uploadError && <div className="uploadMessage error">{uploadError}</div>}
            {!canUploadSchedule && (
              <div className="uploadMessage error">Only Planner or Control Manager roles can upload baselines.</div>
            )}
          </section>
        </section>
      </section>
    </main>
  );
}

function currency(value: number, code: string) {
  return new Intl.NumberFormat("en-US", {
    currency: code || "USD",
    maximumFractionDigits: 0,
    style: "currency",
  }).format(value || 0);
}

function statusLabel(value: string) {
  const neutralValue = value === "create_project_shell" ? "create_project" : value;
  return neutralValue
    ? neutralValue
        .split("_")
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(" ")
    : "Pending";
}

function packageLabel(dashboard: Dashboard, packageId: number) {
  const workPackage = dashboard.work_packages.find((item) => item.id === packageId);
  return workPackage ? workPackage.code : `WP-${packageId}`;
}

function controlAccountLabel(dashboard: Dashboard, accountId: number | null) {
  if (!accountId) return "Area level";
  const account = dashboard.control_accounts.find((item) => item.id === accountId);
  return account ? account.code : `CA-${accountId}`;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/app" replace />} />
      <Route path="/login" element={<LoginView />} />
      <Route
        path="/app/*"
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      />
    </Routes>
  );
}
