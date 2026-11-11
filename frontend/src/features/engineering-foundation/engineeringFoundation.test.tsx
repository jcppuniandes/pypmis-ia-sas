import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiFetch } from "../../api/client";
import { permission } from "./api";
import QueuePanel from "./QueuePanel";
import { profileDraft, profilePayload } from "./profile";
import { availableReviewActions, canEditRevision } from "./revisionLifecycle";
import type { EngineeringPanel } from "./types";

vi.mock("../../api/client", () => ({ apiFetch: vi.fn(), ApiError: Error }));

const items = [
  { deliverable_id: 1, revision_id: 4, deliverable_code: "ENG-R", revision_code: "A", status: "UNDER_REVIEW" },
  {
    deliverable_id: 2,
    revision_id: 5,
    deliverable_code: "ENG-Q",
    revision_code: "B",
    status: "APPROVED",
    effective_ifc_revision_id: 3,
  },
  {
    deliverable_id: 3,
    revision_id: 6,
    deliverable_code: "ENG-IFC",
    revision_code: "A",
    status: "APPROVED",
    effective_ifc_revision_id: 6,
  },
];

const scope = (): EngineeringPanel => ({
  base: "/engineering/projects/7",
  token: "test",
  refreshKey: 0,
  busy: false,
  can: () => false,
  reload: vi.fn(),
  command: vi.fn(),
  config: null,
  deliverable: null,
  revision: null,
  setDeliverableId: vi.fn(),
  setRevisionId: vi.fn(),
});

describe("Engineering technical boundaries", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(apiFetch).mockResolvedValue({ items });
  });

  it("does not treat a prior changes request as permission to edit a terminal revision", () => {
    expect(canEditRevision({ status: "CHANGES_REQUESTED" })).toBe(true);
    expect(canEditRevision({ status: "APPROVED", review_status: "REVISE_AND_RESUBMIT" })).toBe(false);
    expect(canEditRevision({ status: "REJECTED" })).toBe(false);
  });

  it("separates the reviewer, checker and approver decision controls", () => {
    const actor = (action: string) => (key: string) => permission([`engineering.${action}`], key);
    const revision = { status: "UNDER_REVIEW", review_status: "ACCEPTED" };
    expect(availableReviewActions(revision, actor("review.perform"))).toEqual([]);
    expect(availableReviewActions(revision, actor("review.check")).map(({ action }) => action)).toEqual(["check"]);
    expect(availableReviewActions({ ...revision, checked_by: 19 }, actor("review.check"))).toEqual([]);
    expect(availableReviewActions(revision, actor("review.approve")).map(({ action }) => action)).toEqual([
      "reject",
      "approve",
    ]);
  });

  it("preserves scoped published policy input and rejects an unsupported IFC purpose", () => {
    const draft = profileDraft({
      scope: { type: "workspace", workspace_id: 7 },
      deliverable_types: ["DRAWING"],
      disciplines: ["MECHANICAL"],
      purposes_of_issue: ["FOR_CONSTRUCTION"],
      review_rules: { require_technical_check: true, require_document_before_submit: true },
      ifc_release_rules: { eligible_purposes: ["FOR_CONSTRUCTION"], releaser_distinct_from_approver: true },
    });
    expect(profilePayload(draft)).toMatchObject({
      scope: { type: "workspace", workspace_id: 7 },
      review_rules: { require_technical_check: true, require_document_before_submit: true },
      ifc_release_rules: { eligible_purposes: ["FOR_CONSTRUCTION"], releaser_distinct_from_approver: true },
    });
    expect(() => profilePayload({ ...draft, releasePurposes: ["UNCONFIGURED"] })).toThrow(/propósitos elegibles/i);
  });

  it("shows each real-status queue separately, selects its revision, and never writes on selection", async () => {
    const active = scope();
    const view = render(<QueuePanel scope={active} kind="review" />);
    const reviews = within(await screen.findByRole("table", { name: "Cola de revisión Engineering" }));
    expect(reviews.getByText("ENG-R")).toBeInTheDocument();
    expect(reviews.queryByText("ENG-Q")).not.toBeInTheDocument();
    fireEvent.click(reviews.getByRole("button", { name: /ENG-R/ }));
    expect(active.setDeliverableId).toHaveBeenCalledWith("1");
    expect(active.setRevisionId).toHaveBeenCalledWith("4");
    view.rerender(<QueuePanel scope={active} kind="ifc" />);
    const release = within(await screen.findByRole("table", { name: "Cola de liberación IFC" }));
    expect(release.getByText("ENG-Q")).toBeInTheDocument();
    expect(release.queryByText("ENG-IFC")).not.toBeInTheDocument();
    expect(active.command).not.toHaveBeenCalled();
  });
});
