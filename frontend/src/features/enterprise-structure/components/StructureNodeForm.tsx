import type { FormEvent } from "react";
import type { ConfigurationVersion, EnterpriseNode, NodePayload } from "../types";

type Props = {
  busy: boolean;
  draft: NodePayload;
  mode: "create" | "edit";
  nodes: EnterpriseNode[];
  onChange: (draft: NodePayload) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  workspaceTypes: ConfigurationVersion[];
};

export default function StructureNodeForm({ busy, draft, mode, nodes, onChange, onSubmit, workspaceTypes }: Props) {
  return (
    <form className="enterpriseNodeForm" onSubmit={onSubmit}>
      <div className="formColumns">
        <label>
          <span>Código</span>
          <input
            disabled={busy || mode === "edit"}
            required
            value={draft.code}
            onChange={(event) => onChange({ ...draft, code: event.target.value })}
          />
        </label>
        <label>
          <span>Tipo</span>
          <select
            disabled={busy || mode === "edit"}
            value={draft.workspace_type_code}
            onChange={(event) => onChange({ ...draft, workspace_type_code: event.target.value })}
          >
            {workspaceTypes.map((item) => (
              <option key={item.code} value={item.code}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label>
        <span>Nombre</span>
        <input
          disabled={busy}
          required
          value={draft.name}
          onChange={(event) => onChange({ ...draft, name: event.target.value })}
        />
      </label>
      <label>
        <span>Nodo superior</span>
        <select
          disabled={busy}
          value={draft.parent_id ?? ""}
          onChange={(event) =>
            onChange({ ...draft, parent_id: event.target.value ? Number(event.target.value) : null })
          }
        >
          <option value="">Raíz empresarial</option>
          {nodes.map((node) => (
            <option key={node.id} value={node.id}>
              {node.code} · {node.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>Descripción</span>
        <textarea
          disabled={busy}
          value={draft.description}
          onChange={(event) => onChange({ ...draft, description: event.target.value })}
        />
      </label>
      <div className="formColumns">
        <label>
          <span>Región</span>
          <input
            disabled={busy}
            value={draft.region_code}
            onChange={(event) => onChange({ ...draft, region_code: event.target.value })}
          />
        </label>
        <label>
          <span>Estado</span>
          <select
            disabled={busy}
            value={draft.status}
            onChange={(event) => onChange({ ...draft, status: event.target.value as NodePayload["status"] })}
          >
            <option value="draft">Draft</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </select>
        </label>
      </div>
      <button className="workflowAction primary" disabled={busy} type="submit">
        {busy ? "Guardando…" : mode === "create" ? "Crear nodo" : "Guardar cambios"}
      </button>
    </form>
  );
}
