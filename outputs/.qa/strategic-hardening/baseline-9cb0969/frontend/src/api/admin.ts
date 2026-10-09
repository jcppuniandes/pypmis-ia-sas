import { apiFetch } from "./client";
import type { RoleProfile, User } from "../types";

export type UserCreateInput = {
  email: string;
  full_name: string;
  title?: string;
  password?: string;
};

export type UserUpdateInput = {
  email?: string;
  full_name?: string;
  title?: string;
};

export const admin = {
  listUsers: (token: string) => apiFetch<User[]>("/api/v1/users", { token }),

  createUser: (token: string, data: UserCreateInput) =>
    apiFetch<User>("/api/v1/users", {
      method: "POST",
      token,
      body: JSON.stringify(data),
    }),

  updateUser: (token: string, userId: number, data: UserUpdateInput) =>
    apiFetch<User>(`/api/v1/users/${userId}`, {
      method: "PATCH",
      token,
      body: JSON.stringify(data),
    }),

  resetUserPassword: (token: string, userId: number, password: string) =>
    apiFetch<User>(`/api/v1/users/${userId}/reset-password`, {
      method: "POST",
      token,
      body: JSON.stringify({ password }),
    }),

  deactivateUser: (token: string, userId: number) =>
    apiFetch<User>(`/api/v1/users/${userId}`, {
      method: "DELETE",
      token,
    }),

  listRoles: (token: string) => apiFetch<RoleProfile[]>("/api/v1/roles", { token }),
};
