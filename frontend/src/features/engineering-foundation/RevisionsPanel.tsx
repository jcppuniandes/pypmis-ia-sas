import { useState } from "react";
import { isEngineeringRow, items, optionalId, recordId, text, versionOf, type EngineeringRow } from "./api";
import { Facts, Input, Notes, Options, ReadState, Reason, Records, Select, SubmitForm } from "./controls";
import { useEngineeringData } from "./hooks";
import { MappingsPanel } from "./MappingsPanel";
import { codeOptions, profileContent } from "./profile";
import { canEditRevision } from "./revisionLifecycle";
import type { EngineeringPanel } from "./types";

function RevisionEditor({
  scope,
  mode,
  onSaved,
}: {
  scope: EngineeringPanel;
  mode: "new" | "edit" | "successor";
  onSaved: () => void;
}) {
  const profile = profileContent(scope.config);
  const row = mode === "new" ? null : scope.revision;
  const [draft, setDraft] = useState(() => ({
    revision_code: mode === "successor" ? "" : text(row?.revision_code),
    purpose_of_issue: text(row?.purpose_of_issue),
    planned_issue_date: text(row?.planned_issue_date ?? scope.deliverable?.planned_issue_date),
    forecast_issue_date: text(row?.forecast_issue_date ?? scope.deliverable?.current_forecast_date),
    description: text(row?.description),
    reason: "",
  }));
  const set = (key: keyof typeof draft) => (value: string) => setDraft((current) => ({ ...current, [key]: value }));
  const purposes = codeOptions(profile.purposes_of_issue).map((item) => item.code);
  const parent = mode === "new" ? scope.deliverable : scope.revision;
  const version = versionOf(parent);
  const action = mode === "new" ? "revision.create" : mode === "edit" ? "revision.edit" : "revision.supersede";
  async function save() {
    if (!parent || version === undefined || !scope.can(action)) return;
    const path =
      mode === "new"
        ? `/deliverables/${recordId(parent)}/revisions`
        : `/revisions/${recordId(parent)}${mode === "successor" ? "/successor" : ""}`;
    const result = await scope.command(
      path,
      {
        ...draft,
        revision_code: draft.revision_code.trim(),
        planned_issue_date: draft.planned_issue_date || null,
        forecast_issue_date: draft.forecast_issue_date || null,
        description: draft.description.trim(),
        reason: draft.reason.trim(),
      },
      version,
      mode === "edit" ? "PUT" : "POST"
    );
    if (result) {
      scope.setRevisionId(recordId(result));
      onSaved();
    }
  }
  return (
    <section className="progressPanel" aria-label="Editor de revisión">
      <h3>{mode === "new" ? "Nueva revisión" : mode === "edit" ? "Editar revisión" : "Revisión sucesora"}</h3>
      {mode === "successor" ? <p>La revisión original conserva sus decisiones y evidencia IFC.</p> : null}
      <SubmitForm
        onSubmit={save}
        disabled={scope.busy || !scope.can(action) || !purposes.length || version === undefined}
      >
        <Input
          label="Código de revisión"
          value={draft.revision_code}
          onChange={set("revision_code")}
          required
          disabled={mode === "edit"}
        />
        <Select
          label="Propósito de emisión"
          value={draft.purpose_of_issue}
          onChange={set("purpose_of_issue")}
          values={purposes}
          required
        />
        <Input
          label="Emisión planificada de revisión"
          type="date"
          value={draft.planned_issue_date}
          onChange={set("planned_issue_date")}
        />
        <Input
          label="Emisión pronosticada de revisión"
          type="date"
          value={draft.forecast_issue_date}
          onChange={set("forecast_issue_date")}
        />
        <Notes label="Descripción de revisión" value={draft.description} onChange={set("description")} />
        <Reason label="Motivo de revisión" value={draft.reason} onChange={set("reason")} />
        <button type="submit">
          {mode === "edit" ? "Guardar revisión" : mode === "successor" ? "Crear revisión sucesora" : "Crear revisión"}
        </button>
      </SubmitForm>
    </section>
  );
}

function DocumentLink({ scope, revision }: { scope: EngineeringPanel; revision: EngineeringRow }) {
  const editable = scope.can("document.link") && canEditRevision(revision);
  const targets = useEngineeringData(scope.token, scope.base, editable ? "/document-targets" : null, scope.refreshKey);
  const [selection, setSelection] = useState("");
  const [reason, setReason] = useState("");
  const ref = isEngineeringRow(revision.document_ref_json) ? revision.document_ref_json : null;
  const available = items(targets.value).map<EngineeringRow>((row) => ({
    ...row,
    key: `${text(row.document_id)}:${text(row.attachment_id)}`,
  }));
  const chosen = available.find((row) => row.key === selection);
  const version = versionOf(revision);
  async function link() {
    const documentId = optionalId(text(chosen?.document_id));
    const attachmentId = optionalId(text(chosen?.attachment_id));
    if (!documentId || !attachmentId || version === undefined || !editable) return;
    const result = await scope.command(
      `/revisions/${recordId(revision)}/document`,
      {
        document_id: documentId,
        attachment_id: attachmentId,
        reason: reason.trim(),
      },
      version
    );
    if (result) {
      setSelection("");
      setReason("");
    }
  }
  return (
    <section className="progressPanel" aria-label="Vínculo documental">
      <h3>Documento CDE</h3>
      <p>El vínculo identifica una versión y un adjunto existentes. Cargar un archivo no aprueba ni libera IFC.</p>
      {ref && Object.keys(ref).length ? (
        <Facts
          values={[
            ["Documento CDE", ref.document_number ?? ref.document_id],
            ["Revisión CDE", ref.document_revision ?? ref.revision],
            ["Adjunto", ref.attachment_id],
            ["Hash documento", revision.document_hash ?? ref.sha256],
          ]}
        />
      ) : (
        <p>No se ha vinculado un documento a la revisión.</p>
      )}
      {editable ? (
        <>
          <ReadState {...targets} reload={scope.reload} />
          <SubmitForm onSubmit={link} disabled={scope.busy || targets.loading || version === undefined}>
            <Options
              label="Adjunto CDE existente"
              value={selection}
              onChange={setSelection}
              records={available}
              valueKey="key"
              render={(row) =>
                `${text(row.document_number || row.document_id)} · ${text(row.document_revision)} · ${text(row.title)} · adjunto ${text(row.attachment_id)}`
              }
              required
            />
            <Reason label="Motivo de vínculo CDE" value={reason} onChange={setReason} />
            <button type="submit" disabled={!chosen}>
              Vincular documento CDE
            </button>
          </SubmitForm>
        </>
      ) : null}
    </section>
  );
}

export default function RevisionsPanel({ scope, revisions }: { scope: EngineeringPanel; revisions: EngineeringRow[] }) {
  const [editor, setEditor] = useState<"new" | "edit" | "successor" | null>(null);
  const revision = scope.revision;
  const terminalLatest =
    revision &&
    ["APPROVED", "REJECTED"].includes(text(revision.status).toUpperCase()) &&
    recordId(revision) === text(scope.deliverable?.current_revision_id);
  return (
    <>
      <section className="progressPanel" aria-label="Revisions">
        <h3>Revisions</h3>
        {!scope.deliverable ? (
          <p>Seleccione un entregable para consultar y registrar revisiones.</p>
        ) : (
          <>
            <Records
              label="Revisiones"
              items={revisions.map((row) => ({ ...row, code: row.revision_code }))}
              columns={[
                ["revision_code", "Código"],
                ["status", "Estado técnico"],
                ["review_status", "Revisión"],
                ["purpose_of_issue", "Propósito"],
                ["supersedes_revision_id", "Antecesora"],
                ["ifc_release_status", "IFC"],
              ]}
              select={(row) => {
                scope.setRevisionId(recordId(row));
                setEditor(null);
              }}
            />
            <div className="progressActions">
              {!scope.deliverable.current_revision_id && !revisions.length && scope.can("revision.create") ? (
                <button type="button" disabled={scope.busy} onClick={() => setEditor("new")}>
                  Nueva revisión
                </button>
              ) : null}
              {canEditRevision(revision) && scope.can("revision.edit") ? (
                <button type="button" disabled={scope.busy} onClick={() => setEditor("edit")}>
                  Editar revisión seleccionada
                </button>
              ) : null}
              {terminalLatest && scope.can("revision.supersede") ? (
                <button type="button" disabled={scope.busy} onClick={() => setEditor("successor")}>
                  Nueva revisión sucesora
                </button>
              ) : null}
            </div>
          </>
        )}
      </section>
      {editor && scope.deliverable ? (
        <RevisionEditor
          key={`${editor}-${recordId(scope.deliverable)}-${recordId(revision)}`}
          scope={scope}
          mode={editor}
          onSaved={() => setEditor(null)}
        />
      ) : null}
      {revision ? (
        <>
          <DocumentLink key={recordId(revision)} scope={scope} revision={revision} />
          <MappingsPanel
            key={`map-${recordId(revision)}`}
            scope={scope}
            parent={revision}
            mode="revisions"
            editable={canEditRevision(revision)}
          />
        </>
      ) : null}
    </>
  );
}
