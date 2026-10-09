import { apiFetch } from "./client";
import type { AuthSession, User } from "../types";

export async function login(email: string, password: string): Promise<AuthSession> {
  return apiFetch<AuthSession>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function me(token: string): Promise<User> {
  return apiFetch<User>("/api/v1/auth/me", { token });
}
