import { Building2, Network, RefreshCw, Table2, TreePine } from "lucide-react";
import { useEffect, useState } from "react";
import { ApiError } from "../../../api/client";
import { enterpriseStructureApi } from "../api";
import EnterpriseTable from "../components/EnterpriseTable";
import EnterpriseTree from "../components/EnterpriseTree";
import NodeDetailPanel from "../components/NodeDetailPanel";
import StructureFilters from "../components/StructureFilters";
import type { EnterpriseExplorer, EnterpriseNodeDetail, ExplorerFilters } from "../types";
import "../enterpriseStructure.css";

const initialFilters: ExplorerFilters = {
  search: "",
  workspace_type: "",
  business_unit_id: "",
  strategic_objective: "",
  region: "",
  status: "",
};

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

  return (
    <section className="enterpriseWorkspace enterpriseExplorerWorkspace">
      <header className="enterpriseHero userHero">
        <div>
          <span>USER MODE · ENTERPRISE STRATEGY MANAGER</span>
          <h2>Enterprise Explorer</h2>
          <p>Consulte la estructura autorizada, su ruta jerárquica, clasificaciones y relaciones transversales.</p>
        </div>
        <div className="enterpriseKpis">
          <article>
            <strong>{data?.summary.nodes ?? 0}</strong>
            <span>Resultados</span>
          </article>
          <article>
            <strong>{data?.summary.projects ?? 0}</strong>
            <span>Proyectos</span>
          </article>
          <article>
            <strong>{data?.summary.facilities ?? 0}</strong>
            <span>Facilities</span>
          </article>
        </div>
      </header>

      {error ? (
        <div className="enterpriseAlert error" role="alert">
          {error}
        </div>
      ) : null}

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
            <EnterpriseTable nodes={data?.nodes ?? []} onSelect={selectNode} />
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
