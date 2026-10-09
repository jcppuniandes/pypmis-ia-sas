import { LogOut, Workflow } from "lucide-react";
import type { Project, GuidedProjectContext } from "../types";

type Props = {
  project: GuidedProjectContext;
  projects: Project[];
  selectedProjectId: number;
  userEmail: string;
  userName: string;
  userTitle: string;
  onLogout: () => void;
  onProjectChange: (projectId: number) => void;
};

export default function TenantCommandBar({
  project,
  projects,
  selectedProjectId,
  userEmail,
  userName,
  userTitle,
  onLogout,
  onProjectChange,
}: Props) {
  return (
    <header className="tenantCommandBar" aria-label="Tenant command bar">
      <div className="tenantCommandIdentity">
        <Workflow size={20} />
        <div>
          <span className="tenantCommandEyebrow">Acceso de proyecto</span>
          <strong>Proyectos asignados</strong>
          <span>Cada usuario ve solo sus proyectos</span>
        </div>
      </div>
      <label>
        <span>Project</span>
        <select onChange={(event) => onProjectChange(Number(event.target.value))} value={selectedProjectId}>
          {projects.map((item) => (
            <option key={item.id} value={item.id}>
              {item.code}
            </option>
          ))}
        </select>
      </label>
      <div className="tenantCommandProject">
        <h1>{project.name}</h1>
        <span>
          {project.code} / {project.status} / {project.currency}
        </span>
      </div>
      <span className="tenantCommandUser">
        <strong>{userName || userEmail}</strong>
        <small>{userTitle ? `${userTitle} / ${userEmail}` : userEmail}</small>
      </span>
      <button className="iconButton" onClick={onLogout} type="button" aria-label="Logout">
        <LogOut size={16} />
      </button>
    </header>
  );
}
