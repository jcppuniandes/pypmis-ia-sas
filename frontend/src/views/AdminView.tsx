import { Building2, Settings, UserPlus, Users } from "lucide-react";
import type { AppShellCtx } from "../components/AppShellCtx";

export default function AdminView({ ctx }: { ctx: AppShellCtx }) {
  const {
    activeView,
    dashboard,
    projects,
    users,
    roles,
    canConfigure,
    captureAction,
    projectDraft,
    setProjectDraft,
    userDraft,
    setUserDraft,
    teamDraft,
    setTeamDraft,
    processDraft,
    setProcessDraft,
    handleProjectCreate,
    handleUserCreate,
    handleTeamAssign,
    handleProcessTemplateCreate,
  } = ctx;
  return (
    <details
      className={activeView === "admin" ? "adminDrawer workspaceSection" : "adminDrawer workspaceSection hidden"}
      id="admin-setup"
      open={activeView === "admin"}
    >
      <summary>
        <span>Projects, Users & Roles</span>
        <strong>Create project shells, tenant users and project role assignments</strong>
      </summary>
      <section className="workspaceAdmin">
        <form className="adminPanel" onSubmit={handleProjectCreate}>
          <div className="panelHeader">
            <h2>
              <Building2 size={18} /> Project Shell
            </h2>
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
                disabled={!canConfigure}
                onChange={(event) =>
                  setProjectDraft((current) => ({ ...current, finish_date: event.target.value }))
                }
                type="date"
                value={projectDraft.finish_date}
              />
            </label>
          </div>
          <button
            className="workflowAction primary"
            disabled={!canConfigure || captureAction !== null}
            type="submit"
          >
            {captureAction === "project" ? "Creating..." : "Create Project Shell"}
          </button>
        </form>

        <form className="adminPanel" onSubmit={handleUserCreate}>
          <div className="panelHeader">
            <h2>
              <UserPlus size={18} /> Users
            </h2>
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
          <button
            className="workflowAction primary"
            disabled={!canConfigure || captureAction !== null}
            type="submit"
          >
            {captureAction === "user" ? "Creating..." : "Create User"}
          </button>
        </form>

        <form className="adminPanel" onSubmit={handleTeamAssign}>
          <div className="panelHeader">
            <h2>
              <Users size={18} /> Roles
            </h2>
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
                <option key={user.id} value={user.id}>
                  {user.full_name}
                </option>
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
                <option key={role.role} value={role.role}>
                  {role.role}
                </option>
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
          <button
            className="workflowAction primary"
            disabled={!canConfigure || captureAction !== null}
            type="submit"
          >
            {captureAction === "team" ? "Assigning..." : "Assign Role"}
          </button>
        </form>

        <form className="adminPanel bpDesignerPanel" onSubmit={handleProcessTemplateCreate}>
          <div className="panelHeader">
            <h2>
              <Settings size={18} /> BP Designer
            </h2>
            <span>{dashboard.process_templates.length} templates</span>
          </div>
          <div className="formColumns">
            <label>
              <span>Code</span>
              <input
                disabled={!canConfigure}
                onChange={(event) =>
                  setProcessDraft((current) => ({ ...current, code: event.target.value.toUpperCase() }))
                }
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
              onChange={(event) =>
                setProcessDraft((current) => ({ ...current, description: event.target.value }))
              }
              placeholder="Control purpose and decision point"
              value={processDraft.description}
            />
          </label>
          <label>
            <span>Form Fields</span>
            <textarea
              disabled={!canConfigure}
              onChange={(event) =>
                setProcessDraft((current) => ({ ...current, form_schema: event.target.value }))
              }
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
              onChange={(event) =>
                setProcessDraft((current) => ({ ...current, transitions: event.target.value }))
              }
              value={processDraft.transitions}
            />
          </label>
          <button
            className="workflowAction primary"
            disabled={!canConfigure || captureAction !== null}
            type="submit"
          >
            {captureAction === "process-template" ? "Saving..." : "Create BP Template"}
          </button>
        </form>
      </section>
    </details>
  );
}
