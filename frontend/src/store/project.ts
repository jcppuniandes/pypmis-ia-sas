import { create } from "zustand";
import type { Dashboard } from "../types";

type ProjectState = {
  selectedProjectId: number | null;
  dashboard: Dashboard | null;
  setSelectedProject: (id: number | null) => void;
  setDashboard: (d: Dashboard | null) => void;
};

export const useProjectStore = create<ProjectState>()((set) => ({
  selectedProjectId: null,
  dashboard: null,
  setSelectedProject: (id) => set({ selectedProjectId: id, dashboard: null }),
  setDashboard: (d) => set({ dashboard: d }),
}));
