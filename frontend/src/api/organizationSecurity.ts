import { apiFetch } from "./client";
import type {
  EffectiveAccess,
  OrganizationSecurityOrganization,
  OrganizationSecurityOverview,
  OrganizationUnit,
  SecurityAccessAssignment,
  SecurityGroup,
  SecurityRole,
} from "../types";

const root = "/api/v1/organization-security";

export const organizationSecurity = {
  overview: (token: string) => apiFetch<OrganizationSecurityOverview>(`${root}/overview`, { token }),

  updateOrganization: (token: string, data: { display_name: string; base_currency: string }) =>
    apiFetch<OrganizationSecurityOrganization>(`${root}/organization`, {
      method: "PATCH",
      token,
      body: JSON.stringify(data),
    }),

  createUnit: (token: string, data: { code: string; name: string; unit_type: string; parent_id: number | null }) =>
    apiFetch<OrganizationUnit>(`${root}/units`, {
      method: "POST",
      token,
      body: JSON.stringify(data),
    }),

  createGroup: (token: string, data: { code: string; name: string; description: string }) =>
    apiFetch<SecurityGroup>(`${root}/groups`, {
      method: "POST",
      token,
      body: JSON.stringify(data),
    }),

  addGroupMember: (token: string, groupId: number, userId: number) =>
    apiFetch<SecurityGroup>(`${root}/groups/${groupId}/members/${userId}`, {
      method: "POST",
      token,
    }),

  removeGroupMember: (token: string, groupId: number, userId: number) =>
    apiFetch<SecurityGroup>(`${root}/groups/${groupId}/members/${userId}`, {
      method: "DELETE",
      token,
    }),

  createRole: (token: string, data: { code: string; name: string; description: string; permission_keys: string[] }) =>
    apiFetch<SecurityRole>(`${root}/roles`, {
      method: "POST",
      token,
      body: JSON.stringify(data),
    }),

  createAssignment: (
    token: string,
    data: {
      subject_type: "user" | "group";
      subject_id: number;
      role_id: number;
      scope_type: "organization" | "organization_unit";
      scope_unit_id: number | null;
    }
  ) =>
    apiFetch<SecurityAccessAssignment>(`${root}/assignments`, {
      method: "POST",
      token,
      body: JSON.stringify(data),
    }),

  revokeAssignment: (token: string, assignmentId: number) =>
    apiFetch<SecurityAccessAssignment>(`${root}/assignments/${assignmentId}`, {
      method: "DELETE",
      token,
    }),

  effectiveAccess: (token: string, userId: number) =>
    apiFetch<EffectiveAccess>(`${root}/effective/${userId}`, { token }),
};
