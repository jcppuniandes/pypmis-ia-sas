import { describe, expect, it } from "vitest";
import {
  ADMIN_MODE_NAVIGATION_BLUEPRINT,
  USER_MODE_NAVIGATION_BLUEPRINT,
  flattenNavigationViews,
} from "./applicationNavigation";

describe("application navigation composition", () => {
  it("reuses canonical Workspace navigation for Operational Setup and the existing ADMIN process configuration", () => {
    const project = USER_MODE_NAVIGATION_BLUEPRINT.find((item) => item.key === "project-control-manager");
    expect(project?.modules.find((item) => item.key === "project-manager")?.submodules).toEqual(
      expect.arrayContaining([expect.objectContaining({ key: "workspace-context", label: "Operational Setup" })])
    );
    const platform = ADMIN_MODE_NAVIGATION_BLUEPRINT.find((item) => item.key === "platform-administration");
    expect(platform?.modules.find((item) => item.key === "process-configuration")?.submodules).toEqual([
      { key: "process-definitions", label: "Process & Operational Configuration" },
    ]);
  });
  it("uses one strategic source and preserves the alternate project/commercial modules", () => {
    expect(USER_MODE_NAVIGATION_BLUEPRINT.filter((item) => item.key === "enterprise-strategy-manager")).toHaveLength(1);
    expect(
      USER_MODE_NAVIGATION_BLUEPRINT.find((item) => item.key === "project-workspace-governance")?.modules.map(
        (item) => item.key
      )
    ).toEqual(["workspaces-manager", "partners", "vendors", "commitments"]);
    expect(USER_MODE_NAVIGATION_BLUEPRINT.map((item) => item.key)).toEqual([
      "enterprise-strategy-manager",
      "project-workspace-governance",
      "project-control-manager",
      "facility-manager",
      "property-manager",
    ]);
  });

  it("does not duplicate strategic configuration under platform administration", () => {
    expect(ADMIN_MODE_NAVIGATION_BLUEPRINT.filter((item) => item.key === "enterprise-strategy-manager")).toHaveLength(
      1
    );
    expect(
      ADMIN_MODE_NAVIGATION_BLUEPRINT.find((item) => item.key === "platform-administration")?.modules.map(
        (item) => item.key
      )
    ).toEqual(["organization-security", "general-configuration", "process-configuration"]);

    const platformViews = flattenNavigationViews(
      ADMIN_MODE_NAVIGATION_BLUEPRINT.filter((item) => item.key === "platform-administration")
    );
    expect(platformViews.some((item) => item.key === "business-analysis-configuration")).toBe(false);
    expect(platformViews.some((item) => item.key === "enterprise-structure-configuration")).toBe(false);
  });

  it("projects Wave 2A USER transactions and ADMIN Bucket configuration from the canonical strategic blueprint", () => {
    const userViews = flattenNavigationViews(
      USER_MODE_NAVIGATION_BLUEPRINT.filter((item) => item.key === "enterprise-strategy-manager")
    );
    const adminViews = flattenNavigationViews(
      ADMIN_MODE_NAVIGATION_BLUEPRINT.filter((item) => item.key === "enterprise-strategy-manager")
    );

    expect(userViews.map((item) => item.key)).toEqual(
      expect.arrayContaining(["strategic-capital-allocation", "strategic-capital-allocation-history"])
    );
    expect(adminViews.map((item) => item.key)).toContain("strategic-capital-bucket-configuration");
    expect(adminViews.map((item) => item.key)).not.toContain("strategic-capital-allocation");
    expect(userViews.map((item) => item.key)).not.toContain("strategic-capital-bucket-configuration");
  });
});
