import { text, type EngineeringRow } from "./api";

const editableStates = ["DRAFT", "CHANGES_REQUESTED"];

export function canEditRevision(revision: EngineeringRow | null) {
  return Boolean(revision && editableStates.includes(text(revision.status).toUpperCase()));
}

const reviewActions = [
  {
    action: "submit",
    permission: "review.submit",
    label: "Enviar a revisión",
    states: ["NOT_SUBMITTED", "REVISE_AND_RESUBMIT"],
  },
  { action: "start", permission: "review.perform", label: "Iniciar revisión", states: ["SUBMITTED"] },
  {
    action: "request_changes",
    permission: "review.perform",
    label: "Solicitar correcciones",
    states: ["UNDER_REVIEW", "COMMENTS_ISSUED"],
  },
  {
    action: "accept",
    permission: "review.perform",
    label: "Completar revisión técnica",
    states: ["UNDER_REVIEW", "COMMENTS_ISSUED"],
  },
  {
    action: "reject",
    permission: "review.approve",
    label: "Rechazar revisión",
    states: ["UNDER_REVIEW", "COMMENTS_ISSUED", "ACCEPTED"],
  },
  { action: "check", permission: "review.check", label: "Registrar verificación técnica", states: ["ACCEPTED"] },
  { action: "approve", permission: "review.approve", label: "Aprobar revisión", states: ["ACCEPTED"] },
  { action: "close", permission: "review.close", label: "Cerrar revisión", states: ["APPROVED", "REJECTED"] },
];

export function availableReviewActions(revision: EngineeringRow, can: (action: string) => boolean) {
  const status = text(revision.review_status).toUpperCase() || "NOT_SUBMITTED";
  return reviewActions.filter(
    (item) =>
      can(item.permission) &&
      item.states.includes(status) &&
      (item.action !== "check" || !revision.checked_by) &&
      (item.action !== "submit" || canEditRevision(revision))
  );
}
