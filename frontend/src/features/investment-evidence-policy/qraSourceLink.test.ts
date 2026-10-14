import { describe, expect, it } from "vitest";
import { qraEvidenceSourceHref } from "./qraSourceLink";

describe("governed QRA evidence source link", () => {
  it("preserves the exact Project/run pair rather than choosing the current or latest run", () => {
    expect(qraEvidenceSourceHref({ project_id: 14, run_id: 16 })).toBe(
      "/app/strategy/qra-run-overview?project_id=14&run_id=16"
    );
    expect(qraEvidenceSourceHref({ project_workspace_id: 33, qra_run_id: 130 })).toBe(
      "/app/strategy/qra-run-overview?project_id=33&run_id=130"
    );
  });

  it.each([
    {},
    { project_id: 14 },
    { run_id: 16 },
    { project_id: -1, run_id: 16 },
    { project_id: 14, run_id: "not-a-run" },
    { project_id: 14, run_id: 1.5 },
    { project_id: Number.MAX_SAFE_INTEGER + 1, run_id: 16 },
  ])("does not fabricate a source identity when the Project/run pair is incomplete or invalid: %j", (source) => {
    expect(qraEvidenceSourceHref(source)).toBeUndefined();
  });
});
