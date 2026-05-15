import { apiFetch } from "./client";
import type { RoleProfile, User } from "../types";

export type UserCreateInput = {
  email: string;
  full_name: string;
  title?: string;
  password?: string;
};

export const admin = {
  listUsers: (token: string) => apiFetch<User[]>("/api/v1/users", { token }),

  createUser: (token: string, data: UserCreateInput) =>
    apiFetch<User>("/api/v1/users", {
      method: "POST",
      token,
      body: JSON.stringify(data),
    }),

  listRoles: (token: string) => apiFetch<RoleProfile[]>("/api/v1/roles", { token }),
};
