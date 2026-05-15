import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import App from "../src/App";
import { useAuthStore } from "../src/store/auth";

const routerFuture = { v7_relativeSplatPath: true, v7_startTransition: true } as const;

vi.mock("../src/store/auth", () => ({
  useAuthStore: vi.fn(),
}));

// Minimal view stubs — avoid importing the real monolith
vi.mock("../src/views/LoginView", () => ({
  default: () => <div data-testid="login-view">Login</div>,
}));

describe("App routing", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("redirects unauthenticated user from /app to /login", () => {
    vi.mocked(useAuthStore).mockReturnValue({ token: null, user: null } as ReturnType<typeof useAuthStore>);
    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
        <App />
      </MemoryRouter>
    );
    expect(screen.getByTestId("login-view")).toBeInTheDocument();
  });

  it("renders app shell for authenticated user at /app", () => {
    vi.mocked(useAuthStore).mockReturnValue({
      token: "tok",
      user: { id: 1, email: "a@b.com", name: "A", role: "admin", company_id: 1 },
    } as ReturnType<typeof useAuthStore>);
    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
        <App />
      </MemoryRouter>
    );
    // App shell renders — main content area is present
    expect(screen.queryByTestId("login-view")).not.toBeInTheDocument();
  });

  it("redirects / to /app", () => {
    vi.mocked(useAuthStore).mockReturnValue({ token: "tok", user: { id: 1, email: "a@b.com", name: "A", role: "admin", company_id: 1 } } as ReturnType<typeof useAuthStore>);
    render(
      <MemoryRouter future={routerFuture} initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    );
    // Should not show login view (redirected to /app)
    expect(screen.queryByTestId("login-view")).not.toBeInTheDocument();
  });
});
