import { useState } from "react";
import { isEngineeringRow, items, recordId, rows, text, versionOf, type EngineeringRow } from "./api";
import { Facts, Input, Notes, Options, ReadState, Reason, Records, Select, SubmitForm } from "./controls";
import { useEngineeringData } from "./hooks";
import { codeOptions, profileContent } from "./profile";
import { availableReviewActions } from "./revisionLifecycle";
import type { EngineeringPanel } from "./types";

function Comments({
  scope,
  revision,
  comments,
  historical = false,
}: {
  scope: EngineeringPanel;
  revision: EngineeringRow;
  comments: EngineeringRow[];
  historical?: boolean;
}) {
  const profile = profileContent(scope.config);
  const disciplines = codeOptions(profile.disciplines).map((item) => item.code);
  const [selected, setSelected] = useState("");
  const [discipline, setDiscipline] = useState("");
  const [category, setCategory] = useState("");
  const [severity, setSeverity] = useState("MINOR");
  const [comment, setComment] = useState("");
  const [commentReason, setCommentReason] = useState("");
  const [response, setResponse] = useState("");
  const [transitionReason, setTransitionReason] = useState("");
  const [transition, setTransition] = useState("");
  const row = comments.find((entry) => recordId(entry) === selected);
  const rowVersion = versionOf(row);
  const revisionVersion = versionOf(revision);
  const reviewStatus = text(revision.review_status).toUpperCase();
  const commentState = text(row?.status).toUpperCase();
  const reviewActive = !historical && ["UNDER_REVIEW", "COMMENTS_ISSUED"].includes(reviewStatus);
  const allowedTransitions = historical
    ? []
    : [
        ...(scope.can("review.respond") && commentState === "OPEN" ? [{ code: "respond", label: "Responder" }] : []),
        ...(scope.can("review.close") && commentState === "RESPONDED" ? [{ code: "close", label: "Cerrar" }] : []),
      ];
  async function addComment() {
    if (revisionVersion === undefined || !reviewActive || !scope.can("review.comment")) return;
    const saved = await scope.command(
      `/revisions/${recordId(revision)}/comments`,
      {
        discipline,
        category: category.trim(),
        severity,
        text: comment.trim(),
        reason: commentReason.trim(),
      },
      revisionVersion
    );
    if (saved) {
      setSelected(recordId(saved));
      setComment("");
      setCommentReason("");
    }
  }
  async function updateComment() {
    if (!row || rowVersion === undefined || !allowedTransitions.some((item) => item.code === transition)) return;
    const result = await scope.command(
      `/review-comments/${recordId(row)}/transition`,
      {
        action: transition,
        ...(transition === "respond" ? { response: response.trim() } : {}),
        reason: transitionReason.trim(),
      },
      rowVersion
    );
    if (result) {
      setResponse("");
      setTransitionReason("");
      setTransition("");
    }
  }
  return (
    <section className="progressPanel" aria-label="Comentarios técnicos">
      <h3>Comentarios y respuestas</h3>
      <Records
        label="Comentarios Engineering"
        items={comments}
        columns={[
          ["id", "ID"],
          ["discipline", "Disciplina"],
          ["category", "Categoría"],
          ["severity", "Severidad"],
          ["text", "Comentario"],
          ["status", "Estado"],
          ["response", "Respuesta"],
          ["closed_by", "Cierre"],
        ]}
        select={(selectedRow) => {
          setSelected(recordId(selectedRow));
          setTransition("");
        }}
      />
      {reviewActive && scope.can("review.comment") ? (
        <SubmitForm onSubmit={addComment} disabled={scope.busy || !disciplines.length || revisionVersion === undefined}>
          <Select
            label="Disciplina del comentario"
            value={discipline}
            onChange={setDiscipline}
            values={disciplines}
            required
          />
          <Input label="Categoría del comentario" value={category} onChange={setCategory} required />
          <Select
            label="Severidad del comentario"
            value={severity}
            onChange={setSeverity}
            values={["INFO", "MINOR", "MAJOR", "BLOCKING"]}
            required
          />
          <Notes label="Texto del comentario técnico" value={comment} onChange={setComment} required />
          <Reason label="Motivo del comentario" value={commentReason} onChange={setCommentReason} />
          <button type="submit">Registrar comentario técnico</button>
        </SubmitForm>
      ) : null}
      {row && rowVersion !== undefined && allowedTransitions.length ? (
        <SubmitForm onSubmit={updateComment} disabled={scope.busy}>
          <Options
            label="Acción sobre comentario"
            value={transition}
            onChange={setTransition}
            records={allowedTransitions}
            valueKey="code"
            render={(item) => text(item.label)}
            required
          />
          {transition === "respond" ? (
            <Notes label="Respuesta al comentario" value={response} onChange={setResponse} required />
          ) : null}
          <Reason label="Motivo de respuesta o cierre" value={transitionReason} onChange={setTransitionReason} />
          <button type="submit">Registrar respuesta o cierre</button>
        </SubmitForm>
      ) : null}
    </section>
  );
}

export function ReviewsPanel(scope: EngineeringPanel) {
  const revision = scope.revision;
  const id = recordId(revision);
  const version = versionOf(revision);
  const [decision, setDecision] = useState("");
  const [reason, setReason] = useState("");
  const [selectedRoundId, setSelectedRoundId] = useState("");
  const reviews = useEngineeringData(scope.token, scope.base, id ? `/revisions/${id}/reviews` : null, scope.refreshKey);
  if (!revision)
    return (
      <section className="progressPanel">
        <h3>Reviews &amp; Approvals</h3>
        <p>Seleccione una revisión.</p>
      </section>
    );
  const rounds = items(reviews.value);
  const latest = rounds.find((row) => recordId(row) === text(revision.review_id)) ?? rounds[rounds.length - 1];
  const review = rounds.find((row) => recordId(row) === selectedRoundId) ?? latest;
  const historical = Boolean(review && latest && recordId(review) !== recordId(latest));
  const comments = rows(review?.comments);
  const actions = availableReviewActions(revision, scope.can);
  async function transition() {
    if (version === undefined || !actions.some((item) => item.action === decision)) return;
    const result = await scope.command(
      `/revisions/${id}/review-action`,
      { action: decision, reason: reason.trim() },
      version
    );
    if (result) {
      setDecision("");
      setReason("");
    }
  }
  return (
    <>
      <section className="progressPanel" aria-label="Reviews & Approvals">
        <h3>Reviews &amp; Approvals</h3>
        <p>Completar una revisión, verificar técnicamente y aprobar son decisiones distintas.</p>
        <Facts
          values={[
            ["Revisión seleccionada", revision.revision_code],
            ["Estado técnico", revision.status],
            ["Estado de revisión", revision.review_status],
            ["Preparó", revision.prepared_by],
            ["Verificó", revision.checked_by],
            ["Aprobó", revision.approved_by],
          ]}
        />
        <ReadState {...reviews} reload={scope.reload} />
        {reviews.value ? (
          <>
            <Records
              label="Rondas de revisión"
              items={rounds}
              columns={[
                ["id", "ID"],
                ["round_number", "Ronda"],
                ["status", "Estado"],
                ["created_by", "Envió"],
                ["reviewer_id", "Revisor"],
                ["decision_at", "Decisión"],
              ]}
              select={(round) => setSelectedRoundId(recordId(round))}
            />
            {historical ? (
              <button type="button" onClick={() => setSelectedRoundId("")}>
                Volver a la ronda vigente
              </button>
            ) : null}
          </>
        ) : null}
        {!historical && version !== undefined && actions.length ? (
          <SubmitForm onSubmit={transition} disabled={scope.busy}>
            <Options
              label="Decisión de revisión"
              value={decision}
              onChange={setDecision}
              records={actions}
              valueKey="action"
              render={(row) => text(row.label)}
              required
            />
            <Reason label="Motivo de decisión de revisión" value={reason} onChange={setReason} />
            <button type="submit">Registrar decisión de revisión</button>
          </SubmitForm>
        ) : null}
      </section>
      {review ? (
        <Comments
          key={recordId(review)}
          scope={scope}
          revision={revision}
          comments={comments}
          historical={historical}
        />
      ) : null}
    </>
  );
}

export function IfcReleasePanel(scope: EngineeringPanel) {
  const revision = scope.revision;
  const release = isEngineeringRow(revision?.release) ? revision.release : null;
  const [effective, setEffective] = useState("");
  const [reference, setReference] = useState("");
  const [reason, setReason] = useState("");
  const policy = profileContent(scope.config).ifc_release_rules;
  const eligible = isEngineeringRow(policy) ? codeOptions(policy.eligible_purposes).map((item) => item.code) : [];
  const canRelease =
    Boolean(
      revision &&
      !release &&
      text(revision.status).toUpperCase() === "APPROVED" &&
      revision.document_hash &&
      (!eligible.length || eligible.includes(text(revision.purpose_of_issue)))
    ) &&
    scope.can("ifc.release") &&
    versionOf(revision) !== undefined;
  async function publish() {
    if (!canRelease || !revision) return;
    const saved = await scope.command(
      `/revisions/${recordId(revision)}/ifc-release`,
      {
        effective_date: effective,
        release_reference: reference.trim(),
        reason: reason.trim(),
      },
      versionOf(revision)
    );
    if (saved) {
      setReason("");
      setReference("");
    }
  }
  return (
    <section className="progressPanel" aria-label="IFC Release">
      <h3>IFC Release</h3>
      <p>
        El propósito FOR_CONSTRUCTION y un documento vinculado no liberan IFC. La liberación requiere una aprobación y
        un comando autorizado.
      </p>
      {!revision ? (
        <p>Seleccione una revisión para consultar su liberación.</p>
      ) : (
        <>
          <Facts
            values={[
              ["Revisión", revision.revision_code],
              ["Estado", revision.status],
              ["IFC", revision.ifc_release_status],
              ["Propósito", revision.purpose_of_issue],
              ["Hash documento", revision.document_hash],
            ]}
          />
          {release ? (
            <Facts
              values={[
                ["Fecha efectiva", release.effective_date],
                ["Liberó", release.released_by],
                ["Fecha de registro", release.released_at],
                ["Referencia IFC", release.release_reference],
                ["Hash IFC", release.release_hash],
              ]}
            />
          ) : (
            <p className="engineeringRoles">No existe una liberación registrada para esta revisión.</p>
          )}
          {canRelease ? (
            <SubmitForm onSubmit={publish} disabled={scope.busy}>
              <Input label="Fecha efectiva IFC" type="date" value={effective} onChange={setEffective} required />
              <Input label="Referencia de liberación IFC" value={reference} onChange={setReference} required />
              <Reason label="Motivo de liberación IFC" value={reason} onChange={setReason} />
              <button type="submit">Liberar IFC explícitamente</button>
            </SubmitForm>
          ) : null}
        </>
      )}
    </section>
  );
}
