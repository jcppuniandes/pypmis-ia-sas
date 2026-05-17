import { LogOut, Plus, Workflow } from "lucide-react";
import type { Project, GuidedProjectContext, TenantContext } from "../types";

type Props = {
  tenant: TenantContext;
  project: GuidedProjectContext;
  projects: Project[];
  selectedProjectId: number;
  userEmail: string;
  onCreateProject: () => void;
  onLogout: () => void;
  onProjectChange: (projectId: number) => void;
};

export default function TenantCommandBar({
  tenant,
  project,
  projects,
  selectedProjectId,
  userEmail,
  onCreateProject,
  onLogout,
  onProjectChange,
}: Props) {
  return (
    <header className="tenantCommandBar" aria-label="Tenant command bar">
      <div className="tenantCommandIdentity">
        <Workflow size={20} />
        <div>
          <strong>{tenant.name}</strong>
          <span>
            {tenant.slug} / {tenant.base_currency}
          </span>
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
      <span className="tenantCommandUser">{userEmail}</span>
      <button className="iconTextButton" onClick={onCreateProject} type="button">
        <Plus size={16} />
        <span>New Project</span>
      </button>
      <button className="iconButton" onClick={onLogout} type="button" aria-label="Logout">
        <LogOut size={16} />
      </button>
    </header>
  );
}
