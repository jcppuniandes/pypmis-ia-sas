import { GitBranch, Link2, Tags } from "lucide-react";
import type { EnterpriseNodeDetail } from "../types";

export default function NodeDetailPanel({ detail }: { detail: EnterpriseNodeDetail | null }) {
  if (!detail) {
    return (
      <aside className="enterpriseDetail empty">
        <strong>Seleccione un nodo</strong>
        <span>La ficha mostrará ruta, categorías y relaciones persistentes.</span>
      </aside>
    );
  }
  return (
    <aside className="enterpriseDetail">
      <div className="enterpriseBreadcrumb" aria-label="Ruta jerárquica">
        <GitBranch size={15} />
        {detail.path.map((item, index) => (
          <span key={item.id}>
            {index ? " / " : ""}
            {item.name}
          </span>
        ))}
      </div>
      <header>
        <span>{detail.node.workspace_type_code}</span>
        <h3>{detail.node.name}</h3>
        <strong>{detail.node.code}</strong>
      </header>
      <dl>
        <div>
          <dt>Estado</dt>
          <dd>{detail.node.status}</dd>
        </div>
        <div>
          <dt>Región</dt>
          <dd>{detail.node.region_code || "Sin definir"}</dd>
        </div>
        <div>
          <dt>Descripción</dt>
          <dd>{detail.node.description || "Sin descripción"}</dd>
        </div>
        <div>
          <dt>Versión</dt>
          <dd>{detail.node.version}</dd>
        </div>
      </dl>
      <section>
        <h4>
          <Tags size={15} /> Categorías
        </h4>
        {detail.classifications.length ? (
          detail.classifications.map((item) => (
            <span className="enterpriseTag" key={item.id}>
              {item.category_set_code}: {item.category_item_code}
            </span>
          ))
        ) : (
          <p>Sin clasificaciones asignadas.</p>
        )}
      </section>
      <section>
        <h4>
          <Link2 size={15} /> Relaciones
        </h4>
        {detail.links.length ? (
          detail.links.map((item) => (
            <article key={item.id}>
              <strong>{item.relationship_type}</strong>
              <span>
                {item.source_workspace_id} → {item.target_workspace_id}
              </span>
            </article>
          ))
        ) : (
          <p>Sin relaciones transversales.</p>
        )}
      </section>
    </aside>
  );
}
