import { describe, it, expect, beforeEach } from "vitest";
import { useAuthStore } from "../src/store/auth";

describe("useAuthStore", () => {
  beforeEach(() => {
    useAuthStore.setState({ token: "", user: null });
  });

  it("starts with empty token and no user", () => {
    const state = useAuthStore.getState();
    expect(state.token).toBe("");
    expect(state.user).toBeNull();
  });

  it("login sets token and user", () => {
    const user = { id: 1, email: "a@b.com", full_name: "A", title: "Eng", status: "active" };
    useAuthStore.getState().login("tok-123", user as any);
    const state = useAuthStore.getState();
    expect(state.token).toBe("tok-123");
    expect(state.user?.email).toBe("a@b.com");
  });

  it("logout clears token and user", () => {
    useAuthStore.getState().login("tok", { id: 1, email: "a@b.com" } as any);
    useAuthStore.getState().logout();
    const state = useAuthStore.getState();
    expect(state.token).toBe("");
    expect(state.user).toBeNull();
  });
});
