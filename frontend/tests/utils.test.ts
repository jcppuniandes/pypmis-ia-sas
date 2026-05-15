import { describe, expect, it } from "vitest";
import { neutralProjectText, statusLabel } from "../src/components/utils";

describe("ui text utilities", () => {
  it("does not expose legacy project shell wording", () => {
    expect(statusLabel("create_project_shell")).toBe("Create Project");
    expect(neutralProjectText("PJ-SHELL / Project Shell Creation")).toBe("PJ-CREATE / Project Creation");
    expect(neutralProjectText("Creates the project control shell.")).toBe("Creates the project control.");
  });
});
