import { describe, it, expect, beforeEach } from "vitest";
import { useProjectStore } from "../src/store/project";

describe("useProjectStore", () => {
  beforeEach(() => {
    useProjectStore.setState({ selectedProjectId: null, dashboard: null });
  });

  it("starts with no selected project", () => {
    const state = useProjectStore.getState();
    expect(state.selectedProjectId).toBeNull();
    expect(state.dashboard).toBeNull();
  });

  it("setSelectedProject updates id and clears dashboard", () => {
    useProjectStore.getState().setDashboard({ project_kpi: {} } as any);
    useProjectStore.getState().setSelectedProject(42);
    const state = useProjectStore.getState();
    expect(state.selectedProjectId).toBe(42);
    expect(state.dashboard).toBeNull();
  });

  it("setDashboard stores dashboard data", () => {
    const dash = { project_kpi: { spi: 0.95 } } as any;
    useProjectStore.getState().setDashboard(dash);
    expect(useProjectStore.getState().dashboard?.project_kpi.spi).toBe(0.95);
  });
});
