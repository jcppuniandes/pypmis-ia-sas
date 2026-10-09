import { Search } from "lucide-react";
import type { CategoryItem, ConfigurationVersion, EnterpriseNode, ExplorerFilters } from "../types";

type Props = {
  filters: ExplorerFilters;
  nodes: EnterpriseNode[];
  objectives: CategoryItem[];
  onChange: (filters: ExplorerFilters) => void;
  workspaceTypes: ConfigurationVersion[];
};

export default function StructureFilters({ filters, nodes, objectives, onChange, workspaceTypes }: Props) {
  const businessUnits = nodes.filter((node) => node.workspace_type_code === "business-unit");
  const set = (key: keyof ExplorerFilters, value: string) => onChange({ ...filters, [key]: value });

  return (
    <div className="enterpriseFilters" aria-label="Filtros de estructura empresarial">
      <label className="enterpriseSearch">
        <Search size={16} />
        <input
          aria-label="Buscar por código o nombre"
          onChange={(event) => set("search", event.target.value)}
          placeholder="Buscar código o nombre"
          value={filters.search}
        />
      </label>
      <select
        aria-label="Filtrar por tipo"
        onChange={(event) => set("workspace_type", event.target.value)}
        value={filters.workspace_type}
      >
        <option value="">Todos los tipos</option>
        {workspaceTypes.map((item) => (
          <option key={item.code} value={item.code}>
            {item.name}
          </option>
        ))}
      </select>
      <select
        aria-label="Filtrar por unidad de negocio"
        onChange={(event) => set("business_unit_id", event.target.value)}
        value={filters.business_unit_id}
      >
        <option value="">Todas las unidades</option>
        {businessUnits.map((item) => (
          <option key={item.id} value={item.id}>
            {item.name}
          </option>
        ))}
      </select>
      <select
        aria-label="Filtrar por objetivo estratégico"
        onChange={(event) => set("strategic_objective", event.target.value)}
        value={filters.strategic_objective}
      >
        <option value="">Todos los objetivos</option>
        {objectives.map((item) => (
          <option key={item.code} value={item.code}>
            {item.label}
          </option>
        ))}
      </select>
      <input
        aria-label="Filtrar por región"
        onChange={(event) => set("region", event.target.value)}
        placeholder="Región"
        value={filters.region}
      />
      <select
        aria-label="Filtrar por estado"
        onChange={(event) => set("status", event.target.value)}
        value={filters.status}
      >
        <option value="">Todos los estados</option>
        <option value="active">Active</option>
        <option value="inactive">Inactive</option>
        <option value="draft">Draft</option>
        <option value="archived">Archived</option>
      </select>
    </div>
  );
}
