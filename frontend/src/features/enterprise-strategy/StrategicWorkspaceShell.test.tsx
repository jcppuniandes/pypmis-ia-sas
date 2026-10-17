import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import StrategicWorkspaceShell from "./StrategicWorkspaceShell";

vi.mock("./StrategicViewOutlet", () => ({
  default: ({
    canConfigure,
    mode,
    token,
    view,
  }: {
    canConfigure: boolean;
    mode: string;
    token: string;
    view: string;
  }) => <div data-testid="outlet">{`${view}:${mode}:${canConfigure}:${Boolean(token)}`}</div>,
}));

describe("StrategicWorkspaceShell", () => {
  it("renders the canonical USER outlet without an operational dashboard or fabricated ADMIN authority", () => {
    render(
      <MemoryRouter>
        <StrategicWorkspaceShell onNavigate={vi.fn()} token="actual-session" view="idea-lifecycle">
          <nav>Canonical navigation</nav>
        </StrategicWorkspaceShell>
      </MemoryRouter>
    );
    expect(screen.getByTestId("outlet")).toHaveTextContent("idea-lifecycle:user:false:true");
    expect(screen.queryByRole("heading", { name: "Create your first project" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New Project" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Project Controls" })).toHaveAttribute("href", "/app");
  });
  it("keeps the existing rail toggle available while the rail is collapsed", () => {
    render(
      <MemoryRouter>
        <StrategicWorkspaceShell onNavigate={vi.fn()} token="actual-session" view="idea-lifecycle">
          <nav>Canonical navigation</nav>
        </StrategicWorkspaceShell>
      </MemoryRouter>
    );
    fireEvent.click(screen.getByRole("button", { name: "Ocultar barra de módulos" }));
    expect(screen.getByRole("button", { name: "Mostrar barra de módulos" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
    expect(screen.getByTestId("outlet")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Mostrar barra de módulos" }));
    expect(screen.getByRole("navigation")).toBeVisible();
  });
});
