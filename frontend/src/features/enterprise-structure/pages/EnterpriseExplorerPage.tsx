import { Building2, ClipboardList, Eye, Network, Plus, RefreshCw, ShieldCheck, Table2, TreePine } from "lucide-react";
import { useEffect, useState } from "react";
import { ApiError } from "../../../api/client";
import { enterpriseStructureApi } from "../api";
import CompactModuleHeader from "../components/CompactModuleHeader";
import EnterpriseTable from "../components/EnterpriseTable";
import EnterpriseTree from "../components/EnterpriseTree";
import NodeDetailPanel from "../components/NodeDetailPanel";
import ProjectCreationWorkspace, { type ProjectCreationView } from "../components/ProjectCreationWorkspace";
import StructureFilters from "../components/StructureFilters";
import type {
  EnterpriseExplorer,
  EnterpriseNode,
  EnterpriseNodeDetail,
  EnterpriseTreeNode,
  ExplorerFilters,
} from "../types";
import "../enterpriseStructure.css";

const initialFilters: ExplorerFilters = {
  search: "",
  workspace_type: "",
  business_unit_id: "",
  strategic_objective: "",
  region: "",
  status: "",
};

function flattenTree(nodes: EnterpriseTreeNode[]): EnterpriseNode[] {
  return nodes.flatMap((node) => [node, ...flattenTree(node.children)]);
}

function messageFrom(error: unknown) {
  if (!(error instanceof ApiError))
    return error instanceof Error ? error.message : "No fue posible consultar la estructura.";
  try {
    const body = JSON.parse(error.message) as { detail?: string };
    return body.detail || error.message;
  } catch {
    return error.message;
  }
}

export default function EnterpriseExplorerPage({ token }: { token: string }) {
  const [filters, setFilters] = useState<ExplorerFilters>(initialFilters);
  const [data, setData] = useState<EnterpriseExplorer | null>(null);
  const [detail, setDetail] = useState<EnterpriseNodeDetail | null>(null);
  const [view, setView] = useState<"tree" | "table">("tree");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [projectView, setProjectView] = useState<ProjectCreationView | null>(null);

  useEffect(() => {
    let active = true;
    const timer = window.setTimeout(() => {
      setBusy(true);
      enterpriseStructureApi
        .explorer(token, filters)
        .then((response) => {
          if (!active) return;
          setData(response);
          setError("");
          setDetail((current) =>
            current && !response.nodes.some((item) => item.id === current.node.id) ? null : current
          );
        })
        .catch((caught) => active && setError(messageFrom(caught)))
        .finally(() => active && setBusy(false));
    }, 250);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [token, filters]);

  async function selectNode(nodeId: number) {
    setBusy(true);
    try {
      setDetail(await enterpriseStructureApi.nodeDetail(token, nodeId));
      setError("");
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(false);
    }
  }

  if (projectView) {
    return (
      <ProjectCreationWorkspace
        initialParentId={
          projectView === "create" && detail && ["portfolio", "program"].includes(detail.node.workspace_type_code)
            ? detail.node.id
            : undefined
        }
        onBack={() => setProjectView(null)}
        onCreated={() => setFilters({ ...filters })}
        projectWorkspaceId={projectView === "overview" ? detail?.node.id : undefined}
        token={token}
        view={projectView}
      />
    );
  }

  return (
    <section className="enterpriseWorkspace enterpriseExplorerWorkspace">
      <CompactModuleHeader
        description="Consulte la estructura autorizada, su ruta jerárquica, clasificaciones y relaciones transversales."
        eyebrow="USER MODE · ENTERPRISE STRATEGY MANAGER"
        metrics={[
          { label: "Resultados", value: data?.summary.nodes ?? 0 },
          { label: "Proyectos", value: data?.summary.projects ?? 0 },
          { label: "Facilities", value: data?.summary.facilities ?? 0 },
        ]}
        title="Enterprise Explorer"
        tone="user"
      />

      {data?.published_release ? (
        <section className="coreReleaseBanner user" aria-label="Estructura publicada">
          <Network size={20} />
          <div>
            <strong>Estructura publicada · {data.published_release.release_code}</strong>
            <span>
              {data.published_release.workspace_count} nodos · publicada el{" "}
              {data.published_release.published_at
                ? new Date(data.published_release.published_at).toLocaleDateString("es-CO")
                : "sin fecha"}
            </span>
          </div>
          <code title={data.published_release.content_fingerprint}>
            {data.published_release.content_fingerprint.slice(0, 16)}…
          </code>
        </section>
      ) : null}

      {error ? (
        <div className="enterpriseAlert error" role="alert">
          {error}
        </div>
      ) : null}

      <nav className="projectCreationActions" aria-label="Acciones de creación de proyectos">
        <button onClick={() => setProjectView("create")} type="button">
          <Plus size={15} /> Create Project
        </button>
        <button className="ghost" onClick={() => setProjectView("requests")} type="button">
          <ClipboardList size={15} /> My Project Requests
        </button>
        <button className="ghost" onClick={() => setProjectView("review")} type="button">
          <ShieldCheck size={15} /> Review Queue
        </button>
        {detail && ["portfolio", "program"].includes(detail.node.workspace_type_code) ? (
          <button className="contextual" onClick={() => setProjectView("create")} type="button">
            <Plus size={15} /> Crear proyecto en {detail.node.name}
          </button>
        ) : null}
        {detail?.node.workspace_type_code === "project" ? (
          <button className="contextual" onClick={() => setProjectView("overview")} type="button">
            <Eye size={15} /> Project Overview
          </button>
        ) : null}
      </nav>

      <section className="enterprisePanel explorerToolbar">
        <StructureFilters
          filters={filters}
          nodes={data?.nodes ?? []}
          objectives={data?.objectives ?? []}
          onChange={setFilters}
          workspaceTypes={data?.workspace_types ?? []}
        />
        <div className="viewSwitch" aria-label="Vista del explorador">
          <button className={view === "tree" ? "active" : ""} onClick={() => setView("tree")} type="button">
            <TreePine size={15} /> Árbol
          </button>
          <button className={view === "table" ? "active" : ""} onClick={() => setView("table")} type="button">
            <Table2 size={15} /> Tabla
          </button>
          <button disabled={busy} onClick={() => setFilters({ ...filters })} type="button">
            <RefreshCw className={busy ? "spin" : ""} size={15} /> Actualizar
          </button>
        </div>
      </section>

      <div className="enterpriseExplorerGrid">
        <section className="enterprisePanel explorerResults">
          <header>
            <div>
              <span>Estructura publicada</span>
              <h3>{view === "tree" ? "Árbol empresarial" : "Inventario de nodos"}</h3>
            </div>
            <span className="resultCount">{busy ? "Consultando…" : `${data?.nodes.length ?? 0} resultado(s)`}</span>
          </header>
          {view === "tree" ? (
            <EnterpriseTree nodes={data?.tree ?? []} onSelect={selectNode} selectedNodeId={detail?.node.id ?? null} />
          ) : (
            <EnterpriseTable
              allNodes={flattenTree(data?.tree ?? [])}
              classifications={data?.classifications ?? []}
              nodes={data?.nodes ?? []}
              onSelect={selectNode}
            />
          )}
        </section>
        <NodeDetailPanel detail={detail} />
      </div>

      <footer className="enterpriseExplorerFooter">
        <Network size={16} />
        <span>{data?.summary.active ?? 0} nodos activos</span>
        <Building2 size={16} />
        <span>{data?.summary.properties ?? 0} propiedades</span>
      </footer>
    </section>
  );
}
