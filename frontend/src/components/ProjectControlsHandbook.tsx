/* eslint-disable react-refresh/only-export-components --
 * Schedule-control helpers are exported for the vitest suite; they move to
 * src/lib in the frontend refactor wave. HMR degradation is acceptable here.
 */
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { AlertTriangle, CalendarDays, Gauge, ListChecks, RotateCcw } from "lucide-react";
import type { ScheduleActivityMap, ScheduleRelationship, WbsNode as ImportedWbsNode } from "../types";

export type ProjectControlModule = {
  id: string;
  name: string;
  projectId: number;
  status: string;
};

export type WBSNode = {
  code: string;
  id: string;
  level: number;
  name: string;
  parentId: string | null;
  projectId: number;
};

export type ScheduleActivity = {
  actualFinish: string;
  actualStart: string;
  code: string;
  duration: number;
  id: string;
  isCritical: boolean;
  lag: number;
  name: string;
  percentComplete: number;
  plannedFinish: string;
  plannedStart: string;
  predecessors: string[];
  relationshipType: string;
  remainingDuration: number;
  responsible: string;
  totalFloat: number;
  wbsId: string;
};

export type LookaheadConstraint = {
  activityId: string;
  description: string;
  dueDate: string;
  id: string;
  responsible: string;
  status: string;
  type: string;
};

export type DelayEvent = {
  activityId: string;
  baselineFinish: string;
  cause: string;
  criticalPathImpact: boolean;
  currentFinish: string;
  delayDays: number;
  id: string;
  responsibility: string;
};

export type RecoveryAction = {
  actionType: string;
  activityId: string;
  description: string;
  dueDate: string;
  expectedDaysRecovered: number;
  id: string;
  responsible: string;
  status: string;
};

export type ScheduleControlData = {
  activities: ScheduleActivity[];
  constraints: LookaheadConstraint[];
  dataDate: string;
  delayEvents: DelayEvent[];
  module: ProjectControlModule;
  recoveryActions: RecoveryAction[];
  wbsNodes: WBSNode[];
};

type ScheduleControlSection =
  | "dashboard"
  | "wbs"
  | "baseline"
  | "cpm"
  | "progress"
  | "lookahead"
  | "delays"
  | "recovery";

type CalculatedScheduleActivity = ScheduleActivity & {
  earlyFinish: number;
  earlyStart: number;
  lateFinish: number;
  lateStart: number;
};

const DAY_MS = 24 * 60 * 60 * 1000;

const sectionTabs: Array<{ key: ScheduleControlSection; label: string }> = [
  { key: "dashboard", label: "Dashboard" },
  { key: "wbs", label: "WBS" },
  { key: "baseline", label: "Baseline Schedule" },
  { key: "cpm", label: "CPM / Critical Path" },
  { key: "progress", label: "Progress Update" },
  { key: "lookahead", label: "Lookahead Planning" },
  { key: "delays", label: "Delay Identification" },
  { key: "recovery", label: "Recovery Planning" },
];

function dateValue(value: string) {
  const parsed = new Date(`${value}T00:00:00`);
  return Number.isFinite(parsed.getTime()) ? parsed.getTime() : 0;
}

function daysBetween(start: string, finish: string) {
  if (!start || !finish) return 0;
  return Math.max(0, Math.round((dateValue(finish) - dateValue(start)) / DAY_MS));
}

function durationDays(start: string, finish: string) {
  return Math.max(1, daysBetween(start, finish) + 1);
}

function addDays(date: string, days: number) {
  const next = new Date(dateValue(date));
  next.setDate(next.getDate() + days);
  return next.toISOString().slice(0, 10);
}

function makeId(prefix: string) {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
}

function storageKey(projectId: number) {
  return `pypmis.schedule-control.${projectId}`;
}

function activityLabel(activity: ScheduleActivity | undefined) {
  return activity ? `${activity.code} / ${activity.name}` : "Activity pending";
}

// Exported for deterministic tests; this is pure schedule-control data, not a React component.
// eslint-disable-next-line react-refresh/only-export-components
export function createDefaultScheduleControlData(projectId: number, projectCode: string): ScheduleControlData {
  const codeSeed = projectCode || "PROJECT";
  const wbsNodes: WBSNode[] = [
    { code: codeSeed, id: "wbs-root", level: 1, name: "Project Planning Baseline", parentId: null, projectId },
    { code: `${codeSeed}.01`, id: "wbs-eng", level: 2, name: "Engineering", parentId: "wbs-root", projectId },
    { code: `${codeSeed}.02`, id: "wbs-proc", level: 2, name: "Procurement", parentId: "wbs-root", projectId },
    { code: `${codeSeed}.03`, id: "wbs-con", level: 2, name: "Construction", parentId: "wbs-root", projectId },
    { code: `${codeSeed}.04`, id: "wbs-com", level: 2, name: "Commissioning", parentId: "wbs-root", projectId },
  ];
  const activities: ScheduleActivity[] = [
    {
      actualFinish: "2026-06-07",
      actualStart: "2026-06-01",
      code: "SCH-100",
      duration: 7,
      id: "act-design",
      isCritical: false,
      lag: 0,
      name: "Issue IFC design package",
      percentComplete: 100,
      plannedFinish: "2026-06-07",
      plannedStart: "2026-06-01",
      predecessors: [],
      relationshipType: "FS",
      remainingDuration: 0,
      responsible: "Planner",
      totalFloat: 0,
      wbsId: "wbs-eng",
    },
    {
      actualFinish: "",
      actualStart: "2026-06-08",
      code: "SCH-110",
      duration: 8,
      id: "act-proc",
      isCritical: false,
      lag: 0,
      name: "Release long lead procurement",
      percentComplete: 55,
      plannedFinish: "2026-06-15",
      plannedStart: "2026-06-08",
      predecessors: ["SCH-100"],
      relationshipType: "FS",
      remainingDuration: 4,
      responsible: "Procurement",
      totalFloat: 0,
      wbsId: "wbs-proc",
    },
    {
      actualFinish: "",
      actualStart: "2026-06-08",
      code: "SCH-120",
      duration: 5,
      id: "act-site",
      isCritical: false,
      lag: 0,
      name: "Prepare workface access",
      percentComplete: 75,
      plannedFinish: "2026-06-12",
      plannedStart: "2026-06-08",
      predecessors: ["SCH-100"],
      relationshipType: "FS",
      remainingDuration: 2,
      responsible: "Construction",
      totalFloat: 0,
      wbsId: "wbs-con",
    },
    {
      actualFinish: "",
      actualStart: "",
      code: "SCH-130",
      duration: 10,
      id: "act-structure",
      isCritical: false,
      lag: 0,
      name: "Structural erection",
      percentComplete: 10,
      plannedFinish: "2026-06-25",
      plannedStart: "2026-06-16",
      predecessors: ["SCH-110", "SCH-120"],
      relationshipType: "FS",
      remainingDuration: 9,
      responsible: "Construction",
      totalFloat: 0,
      wbsId: "wbs-con",
    },
    {
      actualFinish: "",
      actualStart: "",
      code: "SCH-140",
      duration: 5,
      id: "act-testing",
      isCritical: false,
      lag: 0,
      name: "Systems testing",
      percentComplete: 0,
      plannedFinish: "2026-06-30",
      plannedStart: "2026-06-26",
      predecessors: ["SCH-130"],
      relationshipType: "FS",
      remainingDuration: 5,
      responsible: "Commissioning",
      totalFloat: 0,
      wbsId: "wbs-com",
    },
  ];
  return {
    activities,
    constraints: [
      {
        activityId: "act-structure",
        description: "Confirm steel delivery sequence before erection release.",
        dueDate: "2026-06-18",
        id: "con-material",
        responsible: "Procurement",
        status: "open",
        type: "Material",
      },
      {
        activityId: "act-testing",
        description: "Validate test pack readiness and temporary power.",
        dueDate: "2026-06-24",
        id: "con-access",
        responsible: "Commissioning",
        status: "open",
        type: "Access",
      },
    ],
    dataDate: "2026-06-18",
    delayEvents: [],
    module: {
      id: `schedule-control-${projectId}`,
      name: "Schedule",
      projectId,
      status: "active",
    },
    recoveryActions: [
      {
        actionType: "Crashing",
        activityId: "act-structure",
        description: "Add second crew to recover steel erection sequence.",
        dueDate: "2026-06-19",
        expectedDaysRecovered: 2,
        id: "rec-crash",
        responsible: "Construction Manager",
        status: "open",
      },
    ],
    wbsNodes,
  };
}

function importedWbsIdFor(code: string) {
  return `wbs-${code || "pending"}`;
}

function normalizeRelationshipType(value: string) {
  const normalized = value.toString().split(".").pop()?.toUpperCase() ?? "FS";
  return normalized || "FS";
}

function firstImportedScheduleDate(activities: ScheduleActivityMap[], dataDate?: string | null) {
  const firstDate = activities.find((activity) => activity.planned_start)?.planned_start;
  return dataDate || firstDate || "2026-01-01";
}

export function createScheduleControlDataFromSchedule({
  dataDate,
  projectId,
  relationships = [],
  scheduleActivities = [],
  wbsCatalog = [],
}: {
  dataDate?: string | null;
  projectCode: string;
  projectId: number;
  relationships?: ScheduleRelationship[];
  scheduleActivities?: ScheduleActivityMap[];
  wbsCatalog?: ImportedWbsNode[];
}): ScheduleControlData {
  const fallbackDate = firstImportedScheduleDate(scheduleActivities, dataDate);
  const importedWbsNodes: WBSNode[] = wbsCatalog.map((node) => ({
    code: node.code,
    id: String(node.id),
    level: node.level,
    name: node.name,
    parentId: node.parent_id ? String(node.parent_id) : null,
    projectId,
  }));
  const wbsByCode = new Map(importedWbsNodes.map((node) => [node.code, node]));
  const activityIds = new Set(scheduleActivities.map((activity) => activity.external_activity_id));
  const activities: ScheduleActivity[] = scheduleActivities.map((activity) => {
    const predecessors = relationships
      .filter((relationship) => relationship.successor_external_id === activity.external_activity_id)
      .map((relationship) => relationship.predecessor_external_id)
      .filter((id) => activityIds.has(id));
    const firstRelationship = relationships.find(
      (relationship) => relationship.successor_external_id === activity.external_activity_id
    );
    const plannedStart = activity.planned_start || fallbackDate;
    const plannedFinish = activity.planned_finish || plannedStart;
    const duration = durationDays(plannedStart, plannedFinish);
    return {
      actualFinish: "",
      actualStart: "",
      code: activity.external_activity_id,
      duration,
      id: String(activity.activity_id ?? activity.id),
      isCritical: activity.critical_path,
      lag: firstRelationship?.lag_days ?? firstRelationship?.days_lag ?? 0,
      name: activity.activity_name,
      percentComplete: 0,
      plannedFinish,
      plannedStart,
      predecessors,
      relationshipType: normalizeRelationshipType(firstRelationship?.relationship_type ?? "FS"),
      remainingDuration: duration,
      responsible: "",
      totalFloat: activity.total_float_days,
      wbsId: wbsByCode.get(activity.wbs_code)?.id ?? importedWbsIdFor(activity.wbs_code),
    };
  });
  const missingWbsNodes: WBSNode[] = [...new Set(scheduleActivities.map((activity) => activity.wbs_code))]
    .filter((code) => code && !wbsByCode.has(code))
    .map((code) => ({
      code,
      id: importedWbsIdFor(code),
      level: 1,
      name: code,
      parentId: null,
      projectId,
    }));

  return {
    activities,
    constraints: [],
    dataDate: fallbackDate,
    delayEvents: [],
    module: {
      id: `planning-${projectId}`,
      name: "Schedule",
      projectId,
      status: scheduleActivities.length ? "imported" : "waiting_for_schedule",
    },
    recoveryActions: [],
    wbsNodes: [...importedWbsNodes, ...missingWbsNodes],
  };
}

function resolvePredecessor<TActivity extends Pick<ScheduleActivity, "code" | "id">>(
  predecessor: string,
  activities: TActivity[]
): TActivity | undefined {
  return activities.find((activity) => activity.code === predecessor || activity.id === predecessor);
}

// Exported for deterministic tests; this is pure CPM logic, not a React component.
// eslint-disable-next-line react-refresh/only-export-components
export function calculateScheduleControlState(data: ScheduleControlData) {
  const projectStart = Math.min(...data.activities.map((activity) => dateValue(activity.plannedStart)).filter(Boolean));
  const normalizedStart = Number.isFinite(projectStart) ? projectStart : dateValue(data.dataDate);
  const baseActivities: CalculatedScheduleActivity[] = data.activities.map((activity) => {
    const duration = activity.duration || durationDays(activity.plannedStart, activity.plannedFinish);
    const plannedOffset = Math.max(0, Math.round((dateValue(activity.plannedStart) - normalizedStart) / DAY_MS));
    return {
      ...activity,
      duration,
      earlyFinish: plannedOffset + duration,
      earlyStart: plannedOffset,
      lateFinish: 0,
      lateStart: 0,
    };
  });
  const byCode = new Map(baseActivities.map((activity) => [activity.code, activity]));

  for (let index = 0; index < baseActivities.length; index += 1) {
    for (const activity of baseActivities) {
      const predecessorFinish = activity.predecessors.reduce((latest, predecessorRef) => {
        const predecessor = resolvePredecessor(predecessorRef, baseActivities);
        return Math.max(latest, predecessor ? predecessor.earlyFinish + activity.lag : latest);
      }, activity.earlyStart);
      activity.earlyStart = Math.max(activity.earlyStart, predecessorFinish);
      activity.earlyFinish = activity.earlyStart + activity.duration;
      byCode.set(activity.code, activity);
    }
  }

  const projectFinish = Math.max(...baseActivities.map((activity) => activity.earlyFinish), 0);
  const successors = new Map<string, CalculatedScheduleActivity[]>();
  for (const activity of baseActivities) {
    for (const predecessorRef of activity.predecessors) {
      const predecessor = resolvePredecessor(predecessorRef, baseActivities);
      if (!predecessor) continue;
      successors.set(predecessor.code, [...(successors.get(predecessor.code) ?? []), activity]);
    }
  }

  [...baseActivities].reverse().forEach((activity) => {
    const activitySuccessors = successors.get(activity.code) ?? [];
    activity.lateFinish = activitySuccessors.length
      ? Math.min(...activitySuccessors.map((successor) => successor.lateStart - successor.lag))
      : projectFinish;
    activity.lateStart = activity.lateFinish - activity.duration;
    activity.totalFloat = Math.max(0, activity.lateStart - activity.earlyStart);
    activity.isCritical = activity.isCritical || activity.totalFloat <= 0;
  });

  const activities = baseActivities.map((activity) => ({ ...activity }));
  const activitiesByCode = new Map(activities.map((activity) => [activity.code, activity]));
  const activitiesById = new Map(activities.map((activity) => [activity.id, activity]));
  const generatedDelayEvents = activities
    .filter((activity) => activity.percentComplete < 100 && daysBetween(activity.plannedFinish, data.dataDate) > 0)
    .map<DelayEvent>((activity) => {
      const delayDays = daysBetween(activity.plannedFinish, data.dataDate);
      return {
        activityId: activity.id,
        baselineFinish: activity.plannedFinish,
        cause: "Progress update behind baseline",
        criticalPathImpact: activity.isCritical,
        currentFinish: addDays(activity.plannedFinish, delayDays),
        delayDays,
        id: `delay-${activity.id}`,
        responsibility: activity.responsible || "Project team",
      };
    });
  const openConstraints = data.constraints.filter((constraint) => constraint.status !== "closed");
  const openRecovery = data.recoveryActions.filter((action) => action.status !== "closed");
  const completed = activities.filter((activity) => activity.percentComplete >= 100).length;
  const criticalActivities = activities.filter((activity) => activity.isCritical).length;
  const expectedDaysRecovered = openRecovery.reduce((total, action) => total + action.expectedDaysRecovered, 0);
  const plannedFinish = activities.reduce(
    (latest, activity) => (dateValue(activity.plannedFinish) > dateValue(latest) ? activity.plannedFinish : latest),
    activities[0]?.plannedFinish ?? data.dataDate
  );
  const forecastFinish = generatedDelayEvents.reduce(
    (latest, delay) => (dateValue(delay.currentFinish) > dateValue(latest) ? delay.currentFinish : latest),
    plannedFinish
  );

  return {
    activities,
    activitiesByCode,
    activitiesById,
    criticalPath: activities.filter((activity) => activity.isCritical).map((activity) => activity.code),
    dashboard: {
      criticalActivities,
      delayedActivities: generatedDelayEvents.length,
      forecastFinish,
      openConstraints: openConstraints.length,
      percentComplete: activities.length ? Math.round((completed / activities.length) * 100) : 0,
      plannedFinish,
      recoveryDays: expectedDaysRecovered,
      totalActivities: activities.length,
    },
    delayEvents: [...generatedDelayEvents, ...data.delayEvents],
    openConstraints,
    openRecovery,
  };
}

function loadScheduleControlData(projectId: number, projectCode: string) {
  if (typeof window === "undefined") return createDefaultScheduleControlData(projectId, projectCode);
  const stored = window.localStorage.getItem(storageKey(projectId));
  if (!stored) return createDefaultScheduleControlData(projectId, projectCode);
  try {
    return JSON.parse(stored) as ScheduleControlData;
  } catch {
    return createDefaultScheduleControlData(projectId, projectCode);
  }
}

function wbsName(nodes: WBSNode[], id: string) {
  return nodes.find((node) => node.id === id)?.name ?? "WBS pending";
}

function WbsTree({ node, nodes }: { node: WBSNode; nodes: WBSNode[] }) {
  const children = nodes.filter((candidate) => candidate.parentId === node.id);
  return (
    <div className="handbookWbsBranch">
      <article className="handbookWbsNode">
        <strong>{node.name}</strong>
        <span>{node.code}</span>
        <small>Level {node.level}</small>
      </article>
      {children.length > 0 && (
        <div className="handbookWbsChildren">
          {children.map((child) => (
            <WbsTree key={child.id} node={child} nodes={nodes} />
          ))}
        </div>
      )}
    </div>
  );
}

type ProjectControlsHandbookProps = {
  currencyCode: string;
  projectCode: string;
  projectId: number;
  scheduleActivities?: ScheduleActivityMap[];
  scheduleDataDate?: string | null;
  scheduleRelationships?: ScheduleRelationship[];
  wbsCatalog?: ImportedWbsNode[];
};

export default function ProjectControlsHandbook({
  currencyCode,
  projectCode,
  projectId,
  scheduleActivities = [],
  scheduleDataDate,
  scheduleRelationships = [],
  wbsCatalog = [],
}: ProjectControlsHandbookProps) {
  const [section, setSection] = useState<ScheduleControlSection>("dashboard");
  const hasImportedSchedule = scheduleActivities.length > 0;
  const importedData = useMemo(
    () =>
      createScheduleControlDataFromSchedule({
        dataDate: scheduleDataDate,
        projectCode,
        projectId,
        relationships: scheduleRelationships,
        scheduleActivities,
        wbsCatalog,
      }),
    [projectCode, projectId, scheduleActivities, scheduleDataDate, scheduleRelationships, wbsCatalog]
  );
  const [localData, setData] = useState(() => loadScheduleControlData(projectId, projectCode));
  const data = hasImportedSchedule ? importedData : localData;
  const [wbsDraft, setWbsDraft] = useState({ code: "", name: "", parentId: "wbs-root" });
  const [activityDraft, setActivityDraft] = useState({
    code: "",
    name: "",
    plannedFinish: "2026-07-05",
    plannedStart: "2026-07-01",
    predecessor: "",
    responsible: "",
    wbsId: data.wbsNodes[0]?.id ?? "",
  });
  const [progressDraft, setProgressDraft] = useState({
    activityId: data.activities[0]?.id ?? "",
    actualFinish: "",
    actualStart: "",
    percentComplete: "0",
    remainingDuration: "0",
  });
  const [constraintDraft, setConstraintDraft] = useState({
    activityId: data.activities[0]?.id ?? "",
    description: "",
    dueDate: data.dataDate,
    responsible: "",
    status: "open",
    type: "Material",
  });
  const [recoveryDraft, setRecoveryDraft] = useState({
    actionType: "Crashing",
    activityId: data.activities[0]?.id ?? "",
    description: "",
    dueDate: data.dataDate,
    expectedDaysRecovered: "1",
    responsible: "",
    status: "open",
  });
  const state = useMemo(() => calculateScheduleControlState(data), [data]);
  const activityOptions = state.activities;
  const rootNodes = data.wbsNodes.filter((node) => !node.parentId);
  const ganttDateValues = state.activities
    .flatMap((activity) => [dateValue(activity.plannedStart), dateValue(activity.plannedFinish)])
    .filter(Boolean);
  const ganttStart = ganttDateValues.length ? Math.min(...ganttDateValues) : dateValue(data.dataDate);
  const ganttFinish = ganttDateValues.length ? Math.max(...ganttDateValues) : ganttStart;
  const ganttDays = Math.max(1, Math.round((ganttFinish - ganttStart) / DAY_MS) + 1);

  useEffect(() => {
    if (!hasImportedSchedule) {
      window.localStorage.setItem(storageKey(projectId), JSON.stringify(localData));
    }
  }, [hasImportedSchedule, localData, projectId]);

  function handleWbsCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parent = data.wbsNodes.find((node) => node.id === wbsDraft.parentId);
    const nextNode: WBSNode = {
      code: wbsDraft.code.trim(),
      id: makeId("wbs"),
      level: parent ? parent.level + 1 : 1,
      name: wbsDraft.name.trim(),
      parentId: parent?.id ?? null,
      projectId,
    };
    setData((current) => ({ ...current, wbsNodes: [...current.wbsNodes, nextNode] }));
    setWbsDraft({ code: "", name: "", parentId: parent?.id ?? "wbs-root" });
  }

  function handleActivityCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const duration = durationDays(activityDraft.plannedStart, activityDraft.plannedFinish);
    const nextActivity: ScheduleActivity = {
      actualFinish: "",
      actualStart: "",
      code: activityDraft.code.trim(),
      duration,
      id: makeId("act"),
      isCritical: false,
      lag: 0,
      name: activityDraft.name.trim(),
      percentComplete: 0,
      plannedFinish: activityDraft.plannedFinish,
      plannedStart: activityDraft.plannedStart,
      predecessors: activityDraft.predecessor ? [activityDraft.predecessor] : [],
      relationshipType: "FS",
      remainingDuration: duration,
      responsible: activityDraft.responsible.trim(),
      totalFloat: 0,
      wbsId: activityDraft.wbsId,
    };
    setData((current) => ({ ...current, activities: [...current.activities, nextActivity] }));
    setActivityDraft((current) => ({ ...current, code: "", name: "", predecessor: "", responsible: "" }));
  }

  function handleProgressUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setData((current) => ({
      ...current,
      activities: current.activities.map((activity) =>
        activity.id === progressDraft.activityId
          ? {
              ...activity,
              actualFinish: progressDraft.actualFinish,
              actualStart: progressDraft.actualStart,
              percentComplete: Number(progressDraft.percentComplete),
              remainingDuration: Number(progressDraft.remainingDuration),
            }
          : activity
      ),
    }));
  }

  function handleConstraintCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setData((current) => ({
      ...current,
      constraints: [
        ...current.constraints,
        {
          ...constraintDraft,
          description: constraintDraft.description.trim(),
          id: makeId("constraint"),
          responsible: constraintDraft.responsible.trim(),
        },
      ],
    }));
    setConstraintDraft((current) => ({ ...current, description: "", responsible: "" }));
  }

  function handleRecoveryCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setData((current) => ({
      ...current,
      recoveryActions: [
        ...current.recoveryActions,
        {
          ...recoveryDraft,
          description: recoveryDraft.description.trim(),
          expectedDaysRecovered: Number(recoveryDraft.expectedDaysRecovered),
          id: makeId("recovery"),
          responsible: recoveryDraft.responsible.trim(),
        },
      ],
    }));
    setRecoveryDraft((current) => ({ ...current, description: "", expectedDaysRecovered: "1", responsible: "" }));
  }

  function resetModule() {
    const next = createDefaultScheduleControlData(projectId, projectCode);
    setData(next);
    window.localStorage.setItem(storageKey(projectId), JSON.stringify(next));
  }

  return (
    <section aria-label="Schedule" className="scheduleControlModule">
      <div className="panelHeader scheduleControlHeader">
        <div>
          <h2>
            <CalendarDays size={20} /> Schedule
          </h2>
          <span>
            {hasImportedSchedule ? "Imported schedule baseline" : "Schedule planning workspace"} / {projectCode}
          </span>
        </div>
        {hasImportedSchedule ? (
          <span className="sourceBadge">Source: schedule import</span>
        ) : (
          <button className="quickNavButton" onClick={resetModule} type="button">
            <RotateCcw size={15} /> Reset example data
          </button>
        )}
      </div>

      <div className="mappingSummary scheduleControlSummary">
        <article>
          <span>Activities</span>
          <strong>{state.dashboard.totalActivities}</strong>
          <small>{state.dashboard.percentComplete}% complete</small>
        </article>
        <article className={state.dashboard.criticalActivities ? "risk" : ""}>
          <span>Critical Activities</span>
          <strong>{state.dashboard.criticalActivities}</strong>
          <small>{state.criticalPath.join(" -> ") || "No critical path"}</small>
        </article>
        <article className={state.dashboard.delayedActivities ? "risk" : ""}>
          <span>Delayed</span>
          <strong>{state.dashboard.delayedActivities}</strong>
          <small>Data date {data.dataDate}</small>
        </article>
        <article>
          <span>Recovery</span>
          <strong>{state.dashboard.recoveryDays}d</strong>
          <small>{state.openRecovery.length} open action(s)</small>
        </article>
      </div>

      <div className="scheduleControlTabs" role="tablist" aria-label="Schedule sections">
        {sectionTabs.map((tab) => (
          <button
            aria-selected={section === tab.key}
            className={section === tab.key ? "active" : ""}
            key={tab.key}
            onClick={() => setSection(tab.key)}
            role="tab"
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </div>

      {section === "dashboard" && (
        <div className="viewSplit">
          <div className="panel">
            <div className="panelHeader compactHeader">
              <h2>Dashboard del modulo</h2>
              <span>{data.module.status}</span>
            </div>
            <div className="workList compactList">
              <article>
                <strong>Baseline finish {state.dashboard.plannedFinish}</strong>
                <span>Forecast finish {state.dashboard.forecastFinish}</span>
                <small>{state.dashboard.delayedActivities} delayed activity(s)</small>
              </article>
              <article>
                <strong>{state.dashboard.openConstraints} lookahead constraint(s)</strong>
                <span>{state.openRecovery.length} recovery action(s) open</span>
                <small>{currencyCode} control workspace</small>
              </article>
            </div>
          </div>
          <div className="panel">
            <div className="panelHeader compactHeader">
              <h2>Control focus</h2>
              <span>{"WBS -> Baseline -> CPM -> Update -> Recovery"}</span>
            </div>
            <div className="scheduleHealthGauge">
              <Gauge size={34} />
              <strong>{state.dashboard.percentComplete}%</strong>
              <span>progress complete</span>
            </div>
          </div>
          {hasImportedSchedule && (
            <div className="panel wide">
              <div className="panelHeader compactHeader">
                <h2>Schedule import evidence</h2>
                <span>{state.activities.length} activity row(s) from XML/XER</span>
              </div>
              <div className="workList compactList">
                {state.activities.slice(0, 5).map((activity) => (
                  <article key={activity.id}>
                    <strong>{activity.code}</strong>
                    <span>{activity.name}</span>
                    <small>
                      {wbsName(data.wbsNodes, activity.wbsId)} / {activity.plannedStart} - {activity.plannedFinish}
                    </small>
                  </article>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {section === "wbs" && (
        <div className="viewSplit">
          <form className="adminPanel" onSubmit={handleWbsCreate}>
            <div className="panelHeader compactHeader">
              <h2>WBS</h2>
              <span>{data.wbsNodes.length} nodes</span>
            </div>
            <label>
              <span>Parent</span>
              <select
                onChange={(event) => setWbsDraft((current) => ({ ...current, parentId: event.target.value }))}
                value={wbsDraft.parentId}
              >
                {data.wbsNodes.map((node) => (
                  <option key={node.id} value={node.id}>
                    {node.code}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>WBS Code</span>
              <input
                onChange={(event) => setWbsDraft((current) => ({ ...current, code: event.target.value }))}
                placeholder={`${projectCode}.05`}
                required
                value={wbsDraft.code}
              />
            </label>
            <label>
              <span>WBS Name</span>
              <input
                onChange={(event) => setWbsDraft((current) => ({ ...current, name: event.target.value }))}
                required
                value={wbsDraft.name}
              />
            </label>
            <button className="workflowAction primary" type="submit">
              Create WBS
            </button>
          </form>
          <div className="panel">
            <div className="panelHeader compactHeader">
              <h2>WBS Tree</h2>
              <span>Hierarchical view</span>
            </div>
            <div className="handbookWbsTree" role="tree">
              {rootNodes.map((node) => (
                <WbsTree key={node.id} node={node} nodes={data.wbsNodes} />
              ))}
            </div>
          </div>
        </div>
      )}

      {section === "baseline" && (
        <>
          <div className="viewSplit">
            <form className="adminPanel" onSubmit={handleActivityCreate}>
              <div className="panelHeader compactHeader">
                <h2>Baseline Schedule</h2>
                <span>Create activity</span>
              </div>
              <div className="formColumns">
                <label>
                  <span>Code</span>
                  <input
                    onChange={(event) => setActivityDraft((current) => ({ ...current, code: event.target.value }))}
                    required
                    value={activityDraft.code}
                  />
                </label>
                <label>
                  <span>WBS</span>
                  <select
                    onChange={(event) => setActivityDraft((current) => ({ ...current, wbsId: event.target.value }))}
                    value={activityDraft.wbsId}
                  >
                    {data.wbsNodes.map((node) => (
                      <option key={node.id} value={node.id}>
                        {node.code}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <label>
                <span>Name</span>
                <input
                  onChange={(event) => setActivityDraft((current) => ({ ...current, name: event.target.value }))}
                  required
                  value={activityDraft.name}
                />
              </label>
              <div className="formColumns">
                <label>
                  <span>Start</span>
                  <input
                    onChange={(event) =>
                      setActivityDraft((current) => ({ ...current, plannedStart: event.target.value }))
                    }
                    type="date"
                    value={activityDraft.plannedStart}
                  />
                </label>
                <label>
                  <span>Finish</span>
                  <input
                    onChange={(event) =>
                      setActivityDraft((current) => ({ ...current, plannedFinish: event.target.value }))
                    }
                    type="date"
                    value={activityDraft.plannedFinish}
                  />
                </label>
              </div>
              <div className="formColumns">
                <label>
                  <span>Predecessor</span>
                  <select
                    onChange={(event) =>
                      setActivityDraft((current) => ({ ...current, predecessor: event.target.value }))
                    }
                    value={activityDraft.predecessor}
                  >
                    <option value="">None</option>
                    {data.activities.map((activity) => (
                      <option key={activity.id} value={activity.code}>
                        {activity.code}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Responsible</span>
                  <input
                    onChange={(event) =>
                      setActivityDraft((current) => ({ ...current, responsible: event.target.value }))
                    }
                    value={activityDraft.responsible}
                  />
                </label>
              </div>
              <button className="workflowAction primary" type="submit">
                Create Activity
              </button>
            </form>
            <div className="panel handbookGanttPanel">
              <div className="panelHeader compactHeader">
                <h2>Basic Gantt</h2>
                <span>{ganttDays} calendar days</span>
              </div>
              <div className="handbookGantt" aria-label="Basic Gantt">
                {state.activities.map((activity) => {
                  const left = Math.max(
                    0,
                    ((dateValue(activity.plannedStart) - ganttStart) / DAY_MS / ganttDays) * 100
                  );
                  const width = Math.max(4, (activity.duration / ganttDays) * 100);
                  return (
                    <div className="handbookGanttRow" key={activity.id}>
                      <strong>{activity.code}</strong>
                      <span
                        className={activity.isCritical ? "critical" : ""}
                        style={{ left: `${left}%`, width: `${width}%` }}
                      >
                        {activity.name}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
          <ActivityTable activities={state.activities} nodes={data.wbsNodes} />
        </>
      )}

      {section === "cpm" && (
        <>
          <div className="panelHeader compactHeader">
            <h2>CPM / Critical Path</h2>
            <span>Critical path: {state.criticalPath.join(" -> ")}</span>
          </div>
          <ActivityTable activities={state.activities} nodes={data.wbsNodes} showCpm />
        </>
      )}

      {section === "progress" && (
        <div className="viewSplit">
          <form className="adminPanel" onSubmit={handleProgressUpdate}>
            <div className="panelHeader compactHeader">
              <h2>Progress Update</h2>
              <span>Data date {data.dataDate}</span>
            </div>
            <label>
              <span>Activity</span>
              <select
                onChange={(event) => setProgressDraft((current) => ({ ...current, activityId: event.target.value }))}
                value={progressDraft.activityId}
              >
                {activityOptions.map((activity) => (
                  <option key={activity.id} value={activity.id}>
                    {activity.code}
                  </option>
                ))}
              </select>
            </label>
            <div className="formColumns">
              <label>
                <span>% Complete</span>
                <input
                  max="100"
                  min="0"
                  onChange={(event) =>
                    setProgressDraft((current) => ({ ...current, percentComplete: event.target.value }))
                  }
                  type="number"
                  value={progressDraft.percentComplete}
                />
              </label>
              <label>
                <span>Remaining Duration</span>
                <input
                  min="0"
                  onChange={(event) =>
                    setProgressDraft((current) => ({ ...current, remainingDuration: event.target.value }))
                  }
                  type="number"
                  value={progressDraft.remainingDuration}
                />
              </label>
            </div>
            <div className="formColumns">
              <label>
                <span>Actual Start</span>
                <input
                  onChange={(event) => setProgressDraft((current) => ({ ...current, actualStart: event.target.value }))}
                  type="date"
                  value={progressDraft.actualStart}
                />
              </label>
              <label>
                <span>Actual Finish</span>
                <input
                  onChange={(event) =>
                    setProgressDraft((current) => ({ ...current, actualFinish: event.target.value }))
                  }
                  type="date"
                  value={progressDraft.actualFinish}
                />
              </label>
            </div>
            <button className="workflowAction primary" type="submit">
              Save Progress
            </button>
          </form>
          <div className="panel">
            <div className="panelHeader compactHeader">
              <h2>Progress Register</h2>
              <span>{state.activities.length} rows</span>
            </div>
            <div className="workList compactList">
              {state.activities.map((activity) => (
                <article key={activity.id}>
                  <strong>{activityLabel(activity)}</strong>
                  <span>
                    {activity.percentComplete}% complete / {activity.remainingDuration}d remaining
                  </span>
                  <small>
                    {activity.actualStart || "Actual start pending"} /{" "}
                    {activity.actualFinish || "Actual finish pending"}
                  </small>
                </article>
              ))}
            </div>
          </div>
        </div>
      )}

      {section === "lookahead" && (
        <div className="viewSplit">
          <form className="adminPanel" onSubmit={handleConstraintCreate}>
            <div className="panelHeader compactHeader">
              <h2>Lookahead Planning</h2>
              <span>{state.openConstraints.length} open constraints</span>
            </div>
            <label>
              <span>Activity</span>
              <select
                onChange={(event) => setConstraintDraft((current) => ({ ...current, activityId: event.target.value }))}
                value={constraintDraft.activityId}
              >
                {activityOptions.map((activity) => (
                  <option key={activity.id} value={activity.id}>
                    {activity.code}
                  </option>
                ))}
              </select>
            </label>
            <div className="formColumns">
              <label>
                <span>Type</span>
                <select
                  onChange={(event) => setConstraintDraft((current) => ({ ...current, type: event.target.value }))}
                  value={constraintDraft.type}
                >
                  <option>Material</option>
                  <option>Engineering</option>
                  <option>Access</option>
                  <option>Permit</option>
                  <option>Labor</option>
                </select>
              </label>
              <label>
                <span>Due Date</span>
                <input
                  onChange={(event) => setConstraintDraft((current) => ({ ...current, dueDate: event.target.value }))}
                  type="date"
                  value={constraintDraft.dueDate}
                />
              </label>
            </div>
            <label>
              <span>Description</span>
              <textarea
                onChange={(event) => setConstraintDraft((current) => ({ ...current, description: event.target.value }))}
                required
                value={constraintDraft.description}
              />
            </label>
            <label>
              <span>Responsible</span>
              <input
                onChange={(event) => setConstraintDraft((current) => ({ ...current, responsible: event.target.value }))}
                value={constraintDraft.responsible}
              />
            </label>
            <button className="workflowAction primary" type="submit">
              Add Constraint
            </button>
          </form>
          <ConstraintList activitiesById={state.activitiesById} constraints={data.constraints} />
        </div>
      )}

      {section === "delays" && (
        <div className="panel">
          <div className="panelHeader compactHeader">
            <h2>Delay Identification</h2>
            <span>{state.delayEvents.length} event(s)</span>
          </div>
          <table aria-label="Delay events">
            <thead>
              <tr>
                <th>Activity</th>
                <th>Baseline Finish</th>
                <th>Current Finish</th>
                <th>Delay</th>
                <th>Cause</th>
                <th>Impact</th>
              </tr>
            </thead>
            <tbody>
              {state.delayEvents.map((delay) => (
                <tr key={delay.id}>
                  <td>{activityLabel(state.activitiesById.get(delay.activityId))}</td>
                  <td>{delay.baselineFinish}</td>
                  <td>{delay.currentFinish}</td>
                  <td>{delay.delayDays}d</td>
                  <td>{delay.cause}</td>
                  <td>{delay.criticalPathImpact ? "critical impact" : "non-critical"}</td>
                </tr>
              ))}
              {!state.delayEvents.length && (
                <tr>
                  <td colSpan={6}>No delays at the current data date.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {section === "recovery" && (
        <div className="viewSplit">
          <form className="adminPanel" onSubmit={handleRecoveryCreate}>
            <div className="panelHeader compactHeader">
              <h2>Recovery Planning</h2>
              <span>{state.dashboard.recoveryDays} days targeted</span>
            </div>
            <label>
              <span>Activity</span>
              <select
                onChange={(event) => setRecoveryDraft((current) => ({ ...current, activityId: event.target.value }))}
                value={recoveryDraft.activityId}
              >
                {activityOptions.map((activity) => (
                  <option key={activity.id} value={activity.id}>
                    {activity.code}
                  </option>
                ))}
              </select>
            </label>
            <div className="formColumns">
              <label>
                <span>Action Type</span>
                <select
                  onChange={(event) => setRecoveryDraft((current) => ({ ...current, actionType: event.target.value }))}
                  value={recoveryDraft.actionType}
                >
                  <option>Crashing</option>
                  <option>Fast Tracking</option>
                  <option>Overtime</option>
                  <option>Resource Loading</option>
                  <option>Resequencing</option>
                </select>
              </label>
              <label>
                <span>Days Recovered</span>
                <input
                  min="0"
                  onChange={(event) =>
                    setRecoveryDraft((current) => ({ ...current, expectedDaysRecovered: event.target.value }))
                  }
                  type="number"
                  value={recoveryDraft.expectedDaysRecovered}
                />
              </label>
            </div>
            <label>
              <span>Description</span>
              <textarea
                onChange={(event) => setRecoveryDraft((current) => ({ ...current, description: event.target.value }))}
                required
                value={recoveryDraft.description}
              />
            </label>
            <div className="formColumns">
              <label>
                <span>Responsible</span>
                <input
                  onChange={(event) => setRecoveryDraft((current) => ({ ...current, responsible: event.target.value }))}
                  value={recoveryDraft.responsible}
                />
              </label>
              <label>
                <span>Due Date</span>
                <input
                  onChange={(event) => setRecoveryDraft((current) => ({ ...current, dueDate: event.target.value }))}
                  type="date"
                  value={recoveryDraft.dueDate}
                />
              </label>
            </div>
            <button className="workflowAction primary" type="submit">
              Add Recovery Action
            </button>
          </form>
          <div className="panel">
            <div className="panelHeader compactHeader">
              <h2>Recovery Actions</h2>
              <span>{data.recoveryActions.length} records</span>
            </div>
            <div className="workList compactList">
              {data.recoveryActions.map((action) => (
                <article key={action.id}>
                  <strong>
                    {action.actionType} / {activityLabel(state.activitiesById.get(action.activityId))}
                  </strong>
                  <span>{action.description}</span>
                  <small>
                    {action.expectedDaysRecovered}d / {action.responsible || "Owner pending"} / {action.status}
                  </small>
                </article>
              ))}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function ActivityTable({
  activities,
  nodes,
  showCpm = false,
}: {
  activities: CalculatedScheduleActivity[];
  nodes: WBSNode[];
  showCpm?: boolean;
}) {
  return (
    <div className="panel wide handbookActivityTable">
      <div className="panelHeader compactHeader">
        <h2>{showCpm ? "Critical Path Register" : "Activity Table"}</h2>
        <span>{activities.length} activities</span>
      </div>
      <table aria-label="Baseline activities">
        <thead>
          <tr>
            <th>Activity</th>
            <th>WBS</th>
            <th>Dates</th>
            <th>Progress</th>
            <th>Predecessors</th>
            <th>Total Float</th>
            <th>Critical</th>
          </tr>
        </thead>
        <tbody>
          {activities.map((activity) => (
            <tr key={activity.id}>
              <td>
                <strong>{activity.code}</strong>
                <span>{activity.name}</span>
              </td>
              <td>{wbsName(nodes, activity.wbsId)}</td>
              <td>
                <strong>{activity.plannedStart}</strong>
                <span>{activity.plannedFinish}</span>
              </td>
              <td>{activity.percentComplete}%</td>
              <td>{activity.predecessors.join(", ") || "Start"}</td>
              <td>{activity.totalFloat}d</td>
              <td>{activity.isCritical ? <AlertTriangle size={15} /> : "No"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ConstraintList({
  activitiesById,
  constraints,
}: {
  activitiesById: Map<string, CalculatedScheduleActivity>;
  constraints: LookaheadConstraint[];
}) {
  return (
    <div className="panel">
      <div className="panelHeader compactHeader">
        <h2>Constraint Register</h2>
        <span>{constraints.length} records</span>
      </div>
      <div className="workList compactList">
        {constraints.map((constraint) => (
          <article key={constraint.id}>
            <strong>
              <ListChecks size={15} /> {constraint.type} / {activityLabel(activitiesById.get(constraint.activityId))}
            </strong>
            <span>{constraint.description}</span>
            <small>
              {constraint.responsible || "Owner pending"} / Due {constraint.dueDate} / {constraint.status}
            </small>
          </article>
        ))}
      </div>
    </div>
  );
}
