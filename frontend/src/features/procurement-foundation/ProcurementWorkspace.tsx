import { useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { isRow, permission, procurementProject, text, useProcurementCommands, useProcurementRead } from "./api";
import { EntityPanel, ReadState, type ProcurementScope } from "./Panels";
import { AvailabilityPanel, MappingsPanel, QueryPanel } from "./ReadPanels";
import { entities, procurementTabs, type ProcurementTab } from "./views";
import "../progress-foundation/progressFoundation.css";
import "./procurementFoundation.css";

export default function ProcurementWorkspace({
  token,
  workspaceId,
  readOnly = false,
}: {
  token: string;
  workspaceId: number;
  readOnly?: boolean;
}) {
  const base = procurementProject(workspaceId);
  const [tab, setTab] = useState<ProcurementTab>("Procurement Register");
  const controls = useProcurementCommands(token, base, readOnly);
  const config = useProcurementRead(token, base, "/configuration", controls.revision);
  const profile = isRow(config.value?.profile) ? config.value.profile : null;
  const scope: ProcurementScope = {
    ...controls,
    token,
    base,
    profile: isRow(profile?.content_json) ? profile.content_json : null,
    busy: controls.busy || config.loading,
    can: (action) => !readOnly && !config.error && permission(config.value?.allowed_actions, action),
  };
  return (
    <section
      className="progressFoundation procurementFoundation"
      aria-label="Procurement Manager"
      aria-busy={scope.busy}
    >
      <CompactModuleHeader
        eyebrow="USER MODE · O2B PROCUREMENT"
        title="Procurement Manager"
        description="Planeación de adquisiciones, abastecimiento, inspección y disponibilidad física."
        metrics={[{ label: "Perfil publicado", value: text(profile?.code) || "No configurado" }]}
        tone="user"
        actions={
          <button type="button" disabled={scope.busy} onClick={scope.reload}>
            Actualizar Procurement
          </button>
        }
      />
      <p className="progressBoundary">
        Un Award no es una orden de compra. Recibir no equivale a aceptar ni asignar. AWP conserva Readiness y Package
        Release.
      </p>
      {readOnly ? <p className="progressWarning">Workspace archivado. Solo lectura.</p> : null}
      <ReadState {...config} reload={scope.reload} />
      {config.value && !profile ? (
        <p className="progressWarning">No hay un perfil Procurement publicado aplicable a este Project.</p>
      ) : null}
      {scope.error ? (
        <p className="progressError" role="alert">
          {scope.error}
        </p>
      ) : null}
      {scope.message ? (
        <p className="progressNotice" role="status">
          {scope.message}
        </p>
      ) : null}
      <nav className="progressTabs" aria-label="Vistas Procurement Manager">
        {procurementTabs.map((name) => (
          <button key={name} type="button" aria-pressed={name === tab} onClick={() => setTab(name)}>
            {name}
          </button>
        ))}
      </nav>
      <section key={tab} aria-label={tab} className="procurementView">
        {tab === "Procurement Register" || tab === "Procurement Look-Ahead" || tab === "History" ? (
          <QueryPanel scope={scope} view={tab} />
        ) : tab === "Mappings" ? (
          <MappingsPanel scope={scope} />
        ) : tab === "Material Availability" ? (
          <AvailabilityPanel scope={scope} workspaceId={workspaceId} />
        ) : (
          entities[tab].map((entity) => <EntityPanel key={entity.path} scope={scope} entity={entity} />)
        )}
      </section>
    </section>
  );
}
