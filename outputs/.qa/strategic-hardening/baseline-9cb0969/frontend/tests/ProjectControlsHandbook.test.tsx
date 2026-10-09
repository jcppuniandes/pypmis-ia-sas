import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import ProjectControlsHandbook, {
  calculateScheduleControlState,
  createDefaultScheduleControlData,
  type ScheduleControlData,
} from "../src/components/ProjectControlsHandbook";

afterEach(() => cleanup());

describe("ProjectControlsHandbook", () => {
  it("uses imported schedule data instead of handbook example data", () => {
    const importedWbs = [
      {
        code: "P8Pmis-PY-1",
        description: "",
        dictionary: "",
        id: 1,
        level: 1,
        name: "Proyecto Piloto",
        parent_id: null,
        responsible: "",
        status: "active",
      },
      {
        code: "P8Pmis-PY-1-1",
        description: "",
        dictionary: "",
        id: 2,
        level: 2,
        name: "Ingenieria",
        parent_id: 1,
        responsible: "",
        status: "active",
      },
    ];
    const importedActivities = [
      {
        activity_id: null,
        activity_name: "Review engineering package",
        critical_path: true,
        external_activity_id: "A1000",
        id: 10,
        planned_finish: "2026-05-10",
        planned_start: "2026-05-07",
        schedule_import_id: 5,
        total_float_days: 0,
        wbs_code: "P8Pmis-PY-1-1",
      },
    ];

    render(
      <ProjectControlsHandbook
        currencyCode="USD"
        projectCode="P8Pmis-PY-1"
        projectId={88}
        scheduleActivities={importedActivities}
        wbsCatalog={importedWbs}
      />
    );

    const module = screen.getByRole("region", { name: /schedule/i });
    expect(within(module).getByText(/Review engineering package/i)).toBeInTheDocument();
    expect(within(module).getAllByText(/A1000/i).length).toBeGreaterThan(0);
    expect(within(module).queryByText(/Issue IFC design package/i)).not.toBeInTheDocument();
  });

  it("calculates a basic CPM critical path, delayed activities and module dashboard", () => {
    const data: ScheduleControlData = {
      ...createDefaultScheduleControlData(88, "CTRL-DEMO-001"),
      activities: [
        {
          actualFinish: "",
          actualStart: "2026-06-03",
          code: "A100",
          duration: 5,
          id: "a100",
          isCritical: false,
          lag: 0,
          name: "Foundations",
          percentComplete: 100,
          plannedFinish: "2026-06-07",
          plannedStart: "2026-06-03",
          predecessors: [],
          relationshipType: "FS",
          remainingDuration: 0,
          responsible: "Civil",
          totalFloat: 0,
          wbsId: "wbs-civ",
        },
        {
          actualFinish: "",
          actualStart: "",
          code: "A110",
          duration: 6,
          id: "a110",
          isCritical: false,
          lag: 0,
          name: "Steel frame",
          percentComplete: 20,
          plannedFinish: "2026-06-13",
          plannedStart: "2026-06-08",
          predecessors: ["A100"],
          relationshipType: "FS",
          remainingDuration: 5,
          responsible: "Structural",
          totalFloat: 0,
          wbsId: "wbs-str",
        },
        {
          actualFinish: "",
          actualStart: "",
          code: "A120",
          duration: 3,
          id: "a120",
          isCritical: false,
          lag: 0,
          name: "Facade mockup",
          percentComplete: 0,
          plannedFinish: "2026-06-10",
          plannedStart: "2026-06-08",
          predecessors: ["A100"],
          relationshipType: "FS",
          remainingDuration: 3,
          responsible: "Architectural",
          totalFloat: 0,
          wbsId: "wbs-arc",
        },
      ],
      dataDate: "2026-06-15",
    };

    const state = calculateScheduleControlState(data);

    expect(state.activitiesByCode.get("A100")?.isCritical).toBe(true);
    expect(state.activitiesByCode.get("A110")?.isCritical).toBe(true);
    expect(state.activitiesByCode.get("A120")?.isCritical).toBe(false);
    expect(state.activitiesByCode.get("A120")?.totalFloat).toBeGreaterThan(0);
    expect(state.delayEvents).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ activityId: "a110", delayDays: 2, criticalPathImpact: true }),
        expect.objectContaining({ activityId: "a120", delayDays: 5, criticalPathImpact: false }),
      ])
    );
    expect(state.dashboard.criticalActivities).toBe(2);
    expect(state.dashboard.delayedActivities).toBe(2);
  });

  it("renders every handbook section and stores local project data", async () => {
    const user = userEvent.setup();
    window.localStorage.clear();

    render(<ProjectControlsHandbook currencyCode="USD" projectCode="CTRL-DEMO-001" projectId={88} />);

    const module = screen.getByRole("region", { name: /schedule/i });
    expect(within(module).getByRole("heading", { name: /schedule/i })).toBeInTheDocument();
    expect(within(module).getByText(/Critical Activities/i)).toBeInTheDocument();

    await user.click(within(module).getByRole("tab", { name: /wbs/i }));
    expect(within(module).getByRole("heading", { name: /^wbs$/i })).toBeInTheDocument();
    expect(within(within(module).getByRole("tree")).getByText(/CTRL-DEMO-001.01/i)).toBeInTheDocument();

    await user.click(within(module).getByRole("tab", { name: /baseline schedule/i }));
    expect(within(module).getByRole("heading", { name: /baseline schedule/i })).toBeInTheDocument();
    expect(within(module).getByRole("table", { name: /baseline activities/i })).toBeInTheDocument();

    await user.click(within(module).getByRole("tab", { name: /cpm \/ critical path/i }));
    expect(within(module).getByRole("heading", { name: /cpm \/ critical path/i })).toBeInTheDocument();
    expect(within(module).getByText(/total float/i)).toBeInTheDocument();

    await user.click(within(module).getByRole("tab", { name: /progress update/i }));
    expect(within(module).getByRole("heading", { name: /progress update/i })).toBeInTheDocument();

    await user.click(within(module).getByRole("tab", { name: /lookahead planning/i }));
    expect(within(module).getByRole("heading", { name: /lookahead planning/i })).toBeInTheDocument();
    expect(within(module).getByText(/Confirm steel delivery sequence/i)).toBeInTheDocument();

    await user.click(within(module).getByRole("tab", { name: /delay identification/i }));
    expect(within(module).getByRole("heading", { name: /delay identification/i })).toBeInTheDocument();
    expect(within(module).getByText(/critical impact/i)).toBeInTheDocument();

    await user.click(within(module).getByRole("tab", { name: /recovery planning/i }));
    expect(within(module).getByRole("heading", { name: /recovery planning/i })).toBeInTheDocument();
    expect(within(module).getByText(/recover steel erection sequence/i)).toBeInTheDocument();
  });
});
