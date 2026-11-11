import { useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import {
  engineeringProjectRoot,
  engineeringQuery,
  isEngineeringRow,
  items,
  labelOf,
  permission,
  recordId,
  text,
} from "./api";
import { Facts, Options, ReadState } from "./controls";
import { DesignGroupsPanel, InterfacesPanel } from "./GroupPanels";
import { useEngineeringCommands, useEngineeringData } from "./hooks";
import QueuePanel from "./QueuePanel";
import { HistoryPanel, LookAheadPanel, ProgressPanel, ReadinessPanel } from "./ReadPanels";
import RegisterPanel from "./RegisterPanel";
import { IfcReleasePanel, ReviewsPanel } from "./ReviewPanels";
import RevisionsPanel from "./RevisionsPanel";
import { engineeringTabs, type EngineeringPanel } from "./types";
import "../progress-foundation/progressFoundation.css";
import "./engineeringFoundation.css";

type Tab = (typeof engineeringTabs)[number];

export default function EngineeringWorkspace({
  token,
  workspaceId,
  readOnly = false,
}: {
  token: string;
  workspaceId: number;
  readOnly?: boolean;
}) {
  const base = engineeringProjectRoot(workspaceId);
  const [tab, setTab] = useState<Tab>("Deliverable Register");
  const [deliverableId, chooseDeliverable] = useState("");
  const [revisionId, setRevisionId] = useState("");
  const [revisionCursors, setRevisionCursors] = useState<string[]>([]);
  const revisionCursor = revisionCursors[revisionCursors.length - 1] ?? "";
  const controls = useEngineeringCommands(token, base, readOnly);
  const config = useEngineeringData(token, base, "/configuration", controls.refreshKey);
  const deliverable = useEngineeringData(
    token,
    base,
    deliverableId ? `/deliverables/${deliverableId}` : null,
    controls.refreshKey
  );
  const revisions = useEngineeringData(
    token,
    base,
    deliverableId
      ? engineeringQuery(`/deliverables/${deliverableId}/revisions`, { limit: 50, after_id: revisionCursor })
      : null,
    controls.refreshKey
  );
  const revisionRows = items(revisions.value);
  const currentRevision = text(deliverable.value?.current_revision_id);
  const selectedRevisionId = revisionId || currentRevision || recordId(revisionRows[0]);
  const revision = useEngineeringData(
    token,
    base,
    selectedRevisionId ? `/revisions/${selectedRevisionId}` : null,
    controls.refreshKey
  );
  const revisionOptions =
    revision.value && !revisionRows.some((row) => recordId(row) === selectedRevisionId)
      ? [revision.value, ...revisionRows]
      : revisionRows;
  const nextRevisionCursor = text(revisions.value?.next_cursor);
  const profile = isEngineeringRow(config.value?.profile) ? config.value.profile : null;
  const can = (action: string) => !readOnly && !config.error && permission(config.value?.allowed_actions, action);
  const scope: EngineeringPanel = {
    ...controls,
    config: config.value,
    busy: controls.busy || config.loading || deliverable.loading || revisions.loading || revision.loading,
    token,
    base,
    can,
    deliverable: deliverable.value,
    revision: revision.value,
    setDeliverableId: (id) => {
      chooseDeliverable(id);
      setRevisionId("");
      setRevisionCursors([]);
    },
    setRevisionId,
  };

  return (
    <section
      className="progressFoundation engineeringFoundation"
      aria-label="Engineering Manager"
      aria-busy={scope.busy}
    >
      <CompactModuleHeader
        eyebrow="USER MODE · O2A ENGINEERING"
        title="Engineering Manager"
        description="Registro técnico, revisiones, aprobación y liberación IFC con trazabilidad de fuentes."
        metrics={[
          { label: "Perfil publicado", value: text(profile?.code) || "No configurado" },
          { label: "Revisiones en página", value: revisionRows.length },
        ]}
        tone="user"
        actions={
          <button type="button" onClick={controls.reload} disabled={scope.busy}>
            Actualizar Ingeniería
          </button>
        }
      />
      <p className="progressBoundary">
        Engineering gobierna el entregable técnico. AWP conserva EWP y Readiness; Scope, Schedule/P6, Cost, Progress y
        Forecast conservan sus fuentes.
      </p>
      {readOnly ? <p className="progressWarning">Workspace archivado. Ingeniería es de solo lectura.</p> : null}
      <ReadState {...config} reload={controls.reload} />
      {config.value && !profile ? (
        <p className="progressWarning">No hay un perfil de Ingeniería publicado aplicable a este Project.</p>
      ) : null}
      {controls.error ? (
        <p className="progressError" role="alert">
          {controls.error}
        </p>
      ) : null}
      {controls.notice ? (
        <p className="progressNotice" role="status">
          {controls.notice}
        </p>
      ) : null}
      <nav aria-label="Vistas Engineering Manager" className="progressTabs">
        {engineeringTabs.map((name) => (
          <button key={name} type="button" aria-pressed={tab === name} onClick={() => setTab(name)}>
            {name}
          </button>
        ))}
      </nav>
      {deliverableId ? (
        <section className="progressPanel engineeringSelected" aria-label="Entregable seleccionado">
          <ReadState {...deliverable} reload={controls.reload} />
          <ReadState {...revisions} reload={controls.reload} />
          {selectedRevisionId ? <ReadState {...revision} reload={controls.reload} /> : null}
          {deliverable.value ? (
            <Facts
              values={[
                ["Entregable seleccionado", labelOf(deliverable.value)],
                ["Estado del entregable", deliverable.value.status],
                ["Estado IFC", deliverable.value.ifc_release_status],
              ]}
            />
          ) : null}
          {revisionOptions.length ? (
            <Options
              label="Revisión Engineering seleccionada"
              records={revisionOptions}
              value={selectedRevisionId}
              onChange={setRevisionId}
              render={(row) => `${text(row.revision_code)} · ${text(row.status)}`}
            />
          ) : null}
          <div className="progressActions">
            <button type="button" onClick={() => scope.setDeliverableId("")}>
              Deseleccionar entregable
            </button>
          </div>
        </section>
      ) : null}
      {tab === "Deliverable Register" ? (
        <RegisterPanel {...scope} />
      ) : tab === "Revisions" ? (
        <>
          <RevisionsPanel scope={scope} revisions={revisionRows} />
          {revisionCursors.length || nextRevisionCursor ? (
            <div className="progressActions" aria-label="Paginación de revisiones Engineering">
              <button
                type="button"
                disabled={scope.busy || !revisionCursors.length}
                onClick={() => setRevisionCursors((current) => current.slice(0, -1))}
              >
                Revisiones anteriores
              </button>
              <button
                type="button"
                disabled={scope.busy || !nextRevisionCursor}
                onClick={() => setRevisionCursors((current) => [...current, nextRevisionCursor])}
              >
                Revisiones siguientes
              </button>
            </div>
          ) : null}
        </>
      ) : tab === "Reviews & Approvals" ? (
        <>
          <ReviewsPanel key={selectedRevisionId} {...scope} />
          <QueuePanel key="review-queue" kind="review" scope={scope} />
        </>
      ) : tab === "IFC Release" ? (
        <>
          <IfcReleasePanel key={selectedRevisionId} {...scope} />
          <QueuePanel key="ifc-queue" kind="ifc" scope={scope} />
        </>
      ) : tab === "Engineering Groups" ? (
        <DesignGroupsPanel {...scope} />
      ) : tab === "Interfaces" ? (
        <InterfacesPanel {...scope} />
      ) : tab === "Engineering Readiness" ? (
        <ReadinessPanel scope={scope} workspaceId={workspaceId} />
      ) : tab === "Engineering Progress" ? (
        <ProgressPanel {...scope} />
      ) : tab === "Engineering Look-Ahead" ? (
        <LookAheadPanel {...scope} />
      ) : (
        <HistoryPanel key={deliverableId} {...scope} />
      )}
    </section>
  );
}
