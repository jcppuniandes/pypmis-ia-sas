import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import ProductLogo from "../../components/ProductLogo";
import type { ControlFlowView } from "../../navigation/applicationNavigation";
import { useAuthStore } from "../../store/auth";
import StrategicViewOutlet from "./StrategicViewOutlet";

// Reuses the canonical navigator and outlet. It grants no ADMIN permission and
// creates no operational Project or dashboard merely to display USER strategy.
export default function StrategicWorkspaceShell({
  children,
  onNavigate,
  token,
  view,
}: {
  children: ReactNode;
  onNavigate: (view: ControlFlowView) => void;
  token: string;
  view: ControlFlowView;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const { user, logout } = useAuthStore();
  return (
    <main>
      <header className="appBrandBar" aria-label="Application brand">
        <ProductLogo compact />
        <span>USER MODE · Enterprise Strategy Manager</span>
        <Link to="/app">Project Controls</Link>
        <span>{user?.email}</span>
        <button className="quickNavButton" onClick={logout} type="button">
          Logout
        </button>
      </header>
      <section
        className={`projectWorkspace${collapsed ? " moduleRailCollapsed" : ""}`}
        aria-label="Strategic Workspace"
      >
        <div className="projectWorkspaceRailDock">
          <div className="projectWorkspaceRailToggleDock">
            <button
              aria-controls="strategic-module-navigation"
              aria-expanded={!collapsed}
              aria-label={collapsed ? "Mostrar barra de módulos" : "Ocultar barra de módulos"}
              className="projectWorkspaceRailToggle"
              onClick={() => setCollapsed((current) => !current)}
              type="button"
            >
              {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
            </button>
          </div>
          <aside className="projectWorkspaceRail" hidden={collapsed} id="strategic-module-navigation">
            {children}
          </aside>
        </div>
        <section className="projectDashboardArea" aria-label="Strategic business workflow">
          <section aria-live="polite" className="viewPanel workspaceSection" id="control-flow-content">
            <StrategicViewOutlet canConfigure={false} mode="user" onNavigate={onNavigate} token={token} view={view} />
          </section>
        </section>
      </section>
    </main>
  );
}
