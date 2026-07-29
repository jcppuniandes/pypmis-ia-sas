import type { FormEvent } from "react";
import { X } from "lucide-react";

export type ProjectDrawerDraft = {
  authorization_date: string;
  authorization_ref: string;
  code: string;
  control_level: string;
  funding_required: boolean;
  phase: string;
  name: string;
  currency: string;
  status: string;
  owner: string;
  calendar_base: string;
  start_date: string;
  finish_date: string;
};

type Props<TDraft extends ProjectDrawerDraft> = {
  canConfigure: boolean;
  draft: TDraft;
  error: string | null;
  message: string | null;
  open: boolean;
  pending: boolean;
  onClose: () => void;
  onDraftChange: (draft: TDraft) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
};

export default function ProjectCreateDrawer<TDraft extends ProjectDrawerDraft>({
  canConfigure,
  draft,
  error,
  message,
  open,
  pending,
  onClose,
  onDraftChange,
  onSubmit,
}: Props<TDraft>) {
  if (!open) return null;
  const setField = <K extends keyof ProjectDrawerDraft>(key: K, value: ProjectDrawerDraft[K]) => {
    onDraftChange({ ...draft, [key]: value } as TDraft);
  };

  return (
    <aside className="projectCreateDrawer" aria-label="Create project">
      <div className="panelHeader">
        <h2>Create Project</h2>
        <button className="iconButton" onClick={onClose} type="button" aria-label="Close project drawer">
          <X size={16} />
        </button>
      </div>
      <form className="projectCreateForm" onSubmit={onSubmit}>
        <div className="formColumns">
          <label>
            <span>Code</span>
            <input
              disabled={!canConfigure || pending}
              onChange={(event) => setField("code", event.target.value)}
              required
              value={draft.code}
            />
          </label>
          <label>
            <span>Currency</span>
            <input
              disabled={!canConfigure || pending}
              maxLength={3}
              onChange={(event) => setField("currency", event.target.value.toUpperCase())}
              required
              value={draft.currency}
            />
          </label>
        </div>
        <label>
          <span>Name</span>
          <input
            disabled={!canConfigure || pending}
            onChange={(event) => setField("name", event.target.value)}
            placeholder="Project control name"
            required
            value={draft.name}
          />
        </label>
        <div className="formColumns">
          <label>
            <span>Phase</span>
            <select
              disabled={!canConfigure || pending}
              onChange={(event) => setField("phase", event.target.value)}
              value={draft.phase}
            >
              <option value="Planning">Planning</option>
              <option value="Execution">Execution</option>
              <option value="Closeout">Closeout</option>
            </select>
          </label>
          <label>
            <span>Owner</span>
            <input
              disabled={!canConfigure || pending}
              onChange={(event) => setField("owner", event.target.value)}
              value={draft.owner}
            />
          </label>
        </div>
        <div className="formColumns">
          <label>
            <span>Start</span>
            <input
              disabled={!canConfigure || pending}
              onChange={(event) => setField("start_date", event.target.value)}
              type="date"
              value={draft.start_date}
            />
          </label>
          <label>
            <span>Finish</span>
            <input
              disabled={!canConfigure || pending}
              onChange={(event) => setField("finish_date", event.target.value)}
              type="date"
              value={draft.finish_date}
            />
          </label>
        </div>
        <details className="advancedFields">
          <summary>Advanced project controls</summary>
          <div className="advancedFieldsBody">
            <div className="formColumns">
              <label>
                <span>Status</span>
                <select
                  disabled={!canConfigure || pending}
                  onChange={(event) => setField("status", event.target.value)}
                  value={draft.status}
                >
                  <option value="draft">Draft</option>
                  <option value="authorized">Authorized</option>
                  <option value="baseline_approved">Baseline Approved</option>
                  <option value="in_execution">In Execution</option>
                  <option value="closed">Closed</option>
                </select>
              </label>
              <label>
                <span>Base Calendar</span>
                <input
                  disabled={!canConfigure || pending}
                  onChange={(event) => setField("calendar_base", event.target.value)}
                  value={draft.calendar_base}
                />
              </label>
            </div>
            <div className="formColumns">
              <label>
                <span>Authorization Reference</span>
                <input
                  disabled={!canConfigure || pending}
                  onChange={(event) => setField("authorization_ref", event.target.value)}
                  value={draft.authorization_ref}
                />
              </label>
              <label>
                <span>Authorization Date</span>
                <input
                  disabled={!canConfigure || pending}
                  onChange={(event) => setField("authorization_date", event.target.value)}
                  type="date"
                  value={draft.authorization_date}
                />
              </label>
            </div>
            <div className="formColumns">
              <label>
                <span>Control Level</span>
                <select
                  disabled={!canConfigure || pending}
                  onChange={(event) => setField("control_level", event.target.value)}
                  value={draft.control_level}
                >
                  <option value="control_account">Control Account</option>
                  <option value="cost_code">Cost Code</option>
                  <option value="awp_package">AWP Package</option>
                </select>
              </label>
              <label className="checkboxLine">
                <input
                  checked={draft.funding_required}
                  disabled={!canConfigure || pending}
                  onChange={(event) => setField("funding_required", event.target.checked)}
                  type="checkbox"
                />
                <span>Funding Required</span>
              </label>
            </div>
          </div>
        </details>
        <button className="workflowAction primary" disabled={!canConfigure || pending} type="submit">
          {pending ? "Creating..." : "Create Project"}
        </button>
      </form>
      {message && <div className="uploadMessage success">{message}</div>}
      {error && <div className="uploadMessage error">{error}</div>}
    </aside>
  );
}
