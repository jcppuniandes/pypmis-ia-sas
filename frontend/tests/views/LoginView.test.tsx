import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import LoginView from "../../src/views/LoginView";

vi.mock("../../src/api/auth", () => ({
  login: vi.fn(),
}));

vi.mock("../../src/store/auth", () => ({
  useAuthStore: vi.fn(() => ({ login: vi.fn() })),
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

import { login } from "../../src/api/auth";
import { useAuthStore } from "../../src/store/auth";

describe("LoginView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders email and password fields", () => {
    render(
      <MemoryRouter>
        <LoginView />
      </MemoryRouter>
    );
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
  });

  it("shows error message on failed login", async () => {
    vi.mocked(login).mockRejectedValueOnce(new Error("Invalid credentials"));

    render(
      <MemoryRouter>
        <LoginView />
      </MemoryRouter>
    );

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "user@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: "wrongpass" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it("navigates to /app on successful login", async () => {
    const mockSetAuth = vi.fn();
    vi.mocked(useAuthStore).mockReturnValue({ login: mockSetAuth } as ReturnType<typeof useAuthStore>);
    vi.mocked(login).mockResolvedValueOnce({
      access_token: "tok123",
      token_type: "bearer",
      expires_in: 3600,
      tenant_id: 1,
      user: {
        id: 1,
        email: "user@example.com",
        full_name: "Test User",
        title: "Viewer",
        status: "active",
      },
    });

    render(
      <MemoryRouter>
        <LoginView />
      </MemoryRouter>
    );

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "user@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: "correct" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(mockSetAuth).toHaveBeenCalledWith("tok123", expect.objectContaining({ email: "user@example.com" }));
    });
    expect(mockNavigate).toHaveBeenCalledWith("/app");
  });
});
