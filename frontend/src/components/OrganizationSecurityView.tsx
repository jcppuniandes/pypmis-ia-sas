import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { Building2, KeyRound, LockKeyhole, RefreshCw, ShieldCheck, UserRoundCog, Users } from "lucide-react";
import { organizationSecurity } from "../api/organizationSecurity";
import type { EffectiveAccess, OrganizationSecurityOverview, OrganizationUnit } from "../types";

export type OrganizationSecurityViewKey =
  | "company-organization"
  | "authentication-sessions"
  | "group-creator"
  | "permissions"
  | "access-control";

type Props = {
  canConfigure: boolean;
  token: string;
  view: OrganizationSecurityViewKey;
};

const pageMetadata: Record<OrganizationSecurityViewKey, { title: string; description: string }> = {
  "company-organization": {
    title: "Company & Organization Manager",
    description: "Empresa, configuración regional y jerarquía de unidades organizacionales.",
  },
  "authentication-sessions": {
    title: "Authentication & Session Management",
    description: "Postura de autenticación, vigencia de tokens y eventos mínimos de seguridad.",
  },
  "group-creator": {
    title: "Group Creator",
    description: "Grupos empresariales y membresías reutilizables para asignar acceso colectivo.",
  },
  permissions: {
    title: "Permissions",
    description: "Catálogo de acciones autorizables y roles de seguridad reutilizables.",
  },
  "access-control": {
    title: "Access Control",
    description: "Asignaciones por usuario o grupo, alcance organizacional y acceso efectivo.",
  },
};

export default function OrganizationSecurityView({ canConfigure, token, view }: Props) {
  const [overview, setOverview] = useState<OrganizationSecurityOverview | null>(null);
  const [effectiveAccess, setEffectiveAccess] = useState<EffectiveAccess | null>(null);
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [organizationDraft, setOrganizationDraft] = useState({ display_name: "", base_currency: "COP" });
  const [unitDraft, setUnitDraft] = useState({ code: "", name: "", unit_type: "department", parent_id: "" });
  const [groupDraft, setGroupDraft] = useState({ code: "", name: "", description: "" });
  const [groupMemberDraft, setGroupMemberDraft] = useState({ group_id: "", user_id: "" });
  const [roleDraft, setRoleDraft] = useState({ code: "", name: "", description: "", permission_keys: [] as string[] });
  const [assignmentDraft, setAssignmentDraft] = useState({
    subject_type: "user" as "user" | "group",
    subject_id: "",
    role_id: "",
    scope_type: "organization" as "organization" | "organization_unit",
    scope_unit_id: "",
  });
  const [effectiveUserId, setEffectiveUserId] = useState("");

  async function loadOverview() {
    setLoading(true);
    setError(null);
    try {
      const payload = await organizationSecurity.overview(token);
      setOverview(payload);
      setOrganizationDraft({
        display_name: payload.organization.display_name,
        base_currency: payload.organization.base_currency,
      });
      setGroupMemberDraft((current) => ({
        group_id: current.group_id || String(payload.groups[0]?.id ?? ""),
        user_id: current.user_id || String(payload.users[0]?.id ?? ""),
      }));
      setAssignmentDraft((current) => ({
        ...current,
        subject_id:
          current.subject_id ||
          String((current.subject_type === "user" ? payload.users[0]?.id : payload.groups[0]?.id) ?? ""),
        role_id: current.role_id || String(payload.roles[0]?.id ?? ""),
      }));
      setEffectiveUserId((current) => current || String(payload.users[0]?.id ?? ""));
    } catch (loadError) {
      setError(errorDetail(loadError));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    void organizationSecurity
      .overview(token)
      .then((payload) => {
        if (!active) return;
        setOverview(payload);
        setOrganizationDraft({
          display_name: payload.organization.display_name,
          base_currency: payload.organization.base_currency,
        });
        setGroupMemberDraft((current) => ({
          group_id: current.group_id || String(payload.groups[0]?.id ?? ""),
          user_id: current.user_id || String(payload.users[0]?.id ?? ""),
        }));
        setAssignmentDraft((current) => ({
          ...current,
          subject_id:
            current.subject_id ||
            String((current.subject_type === "user" ? payload.users[0]?.id : payload.groups[0]?.id) ?? ""),
          role_id: current.role_id || String(payload.roles[0]?.id ?? ""),
        }));
        setEffectiveUserId((current) => current || String(payload.users[0]?.id ?? ""));
      })
      .catch((loadError) => {
        if (active) setError(errorDetail(loadError));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [token]);

  const unitRows = useMemo(() => organizationUnitRows(overview?.units ?? []), [overview?.units]);
  const currentPage = pageMetadata[view];

  async function runAction(key: string, task: () => Promise<unknown>, successMessage: string) {
    setAction(key);
    setMessage(null);
    setError(null);
    try {
      await task();
      setMessage(successMessage);
      await loadOverview();
    } catch (actionError) {
      setError(errorDetail(actionError));
    } finally {
      setAction(null);
    }
  }

  function handleOrganizationSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void runAction(
      "organization",
      () => organizationSecurity.updateOrganization(token, organizationDraft),
      "Información de la empresa actualizada."
    );
  }

  function handleUnitSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void runAction(
      "unit",
      () =>
        organizationSecurity.createUnit(token, {
          code: unitDraft.code,
          name: unitDraft.name,
          unit_type: unitDraft.unit_type,
          parent_id: unitDraft.parent_id ? Number(unitDraft.parent_id) : null,
        }),
      "Unidad organizacional creada."
    ).then(() => setUnitDraft({ code: "", name: "", unit_type: "department", parent_id: "" }));
  }

  function handleGroupSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void runAction(
      "group",
      () => organizationSecurity.createGroup(token, groupDraft),
      "Grupo creado y disponible para asignaciones."
    ).then(() => setGroupDraft({ code: "", name: "", description: "" }));
  }

  function handleGroupMemberSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!groupMemberDraft.group_id || !groupMemberDraft.user_id) return;
    void runAction(
      "group-member",
      () =>
        organizationSecurity.addGroupMember(token, Number(groupMemberDraft.group_id), Number(groupMemberDraft.user_id)),
      "Usuario agregado al grupo."
    );
  }

  function handleRoleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void runAction("role", () => organizationSecurity.createRole(token, roleDraft), "Rol personalizado creado.").then(
      () => setRoleDraft({ code: "", name: "", description: "", permission_keys: [] })
    );
  }

  function handleAssignmentSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!assignmentDraft.subject_id || !assignmentDraft.role_id) return;
    void runAction(
      "assignment",
      () =>
        organizationSecurity.createAssignment(token, {
          subject_type: assignmentDraft.subject_type,
          subject_id: Number(assignmentDraft.subject_id),
          role_id: Number(assignmentDraft.role_id),
          scope_type: assignmentDraft.scope_type,
          scope_unit_id:
            assignmentDraft.scope_type === "organization_unit" && assignmentDraft.scope_unit_id
              ? Number(assignmentDraft.scope_unit_id)
              : null,
        }),
      "Acceso asignado."
    );
  }

  async function handleEffectiveAccess() {
    if (!effectiveUserId) return;
    setAction("effective");
    setError(null);
    try {
      setEffectiveAccess(await organizationSecurity.effectiveAccess(token, Number(effectiveUserId)));
    } catch (effectiveError) {
      setError(errorDetail(effectiveError));
    } finally {
      setAction(null);
    }
  }

  if (loading && !overview) {
    return (
      <section aria-label={`${currentPage.title} Module`} className="organizationSecurityLoading">
        <RefreshCw aria-hidden="true" className="spin" size={22} />
        <span>Cargando configuración de organización y seguridad…</span>
      </section>
    );
  }

  if (!overview) {
    return (
      <section aria-label={`${currentPage.title} Module`} className="organizationSecurityLoading error">
        <ShieldCheck aria-hidden="true" size={22} />
        <strong>No fue posible cargar la configuración.</strong>
        <span>{error}</span>
        <button className="workflowAction" onClick={() => void loadOverview()} type="button">
          Reintentar
        </button>
      </section>
    );
  }

  return (
    <section aria-label={`${currentPage.title} Module`} className="organizationSecurityModule">
      <header className="organizationSecurityHeader">
        <div>
          <span>ADMIN MODE / ORGANIZATION & SECURITY</span>
          <h2>{currentPage.title}</h2>
          <p>{currentPage.description}</p>
        </div>
        <div className="securityStatusBadge">
          <ShieldCheck aria-hidden="true" size={19} />
          <strong>Tenant isolated</strong>
          <span>Default scope: organization</span>
        </div>
      </header>

      {message ? (
        <div className="uploadMessage success" role="status">
          {message}
        </div>
      ) : null}
      {error ? (
        <div className="uploadMessage error" role="alert">
          {error}
        </div>
      ) : null}

      {view === "company-organization" ? (
        <div className="organizationSecurityGrid">
          <form className="securityFormCard" onSubmit={handleOrganizationSubmit}>
            <div className="panelHeader compactHeader">
              <h3>
                <Building2 aria-hidden="true" size={18} /> Empresa
              </h3>
              <span>{overview.organization.status}</span>
            </div>
            <label>
              <span>Nombre visible</span>
              <input
                disabled={!canConfigure || action !== null}
                onChange={(event) =>
                  setOrganizationDraft((current) => ({ ...current, display_name: event.target.value }))
                }
                required
                value={organizationDraft.display_name}
              />
            </label>
            <div className="formColumns">
              <label>
                <span>Código</span>
                <input disabled value={overview.organization.code} />
              </label>
              <label>
                <span>Moneda base</span>
                <input
                  disabled={!canConfigure || action !== null}
                  maxLength={3}
                  onChange={(event) =>
                    setOrganizationDraft((current) => ({ ...current, base_currency: event.target.value.toUpperCase() }))
                  }
                  required
                  value={organizationDraft.base_currency}
                />
              </label>
            </div>
            <div className="securityFactStrip">
              <span>{overview.organization.country_code}</span>
              <span>{overview.organization.timezone}</span>
              <span>{overview.organization.default_locale}</span>
            </div>
            <button className="workflowAction primary" disabled={!canConfigure || action !== null} type="submit">
              {action === "organization" ? "Guardando…" : "Guardar empresa"}
            </button>
          </form>

          <form className="securityFormCard" onSubmit={handleUnitSubmit}>
            <div className="panelHeader compactHeader">
              <h3>Crear unidad organizacional</h3>
              <span>{overview.units.length} unidades</span>
            </div>
            <div className="formColumns">
              <label>
                <span>Código</span>
                <input
                  disabled={!canConfigure || action !== null}
                  onChange={(event) =>
                    setUnitDraft((current) => ({ ...current, code: event.target.value.toUpperCase() }))
                  }
                  required
                  value={unitDraft.code}
                />
              </label>
              <label>
                <span>Tipo</span>
                <select
                  disabled={!canConfigure || action !== null}
                  onChange={(event) => setUnitDraft((current) => ({ ...current, unit_type: event.target.value }))}
                  value={unitDraft.unit_type}
                >
                  <option value="division">División</option>
                  <option value="department">Departamento</option>
                  <option value="office">Oficina</option>
                  <option value="region">Región</option>
                </select>
              </label>
            </div>
            <label>
              <span>Nombre</span>
              <input
                disabled={!canConfigure || action !== null}
                onChange={(event) => setUnitDraft((current) => ({ ...current, name: event.target.value }))}
                required
                value={unitDraft.name}
              />
            </label>
            <label>
              <span>Unidad superior</span>
              <select
                disabled={!canConfigure || action !== null}
                onChange={(event) => setUnitDraft((current) => ({ ...current, parent_id: event.target.value }))}
                value={unitDraft.parent_id}
              >
                <option value="">Empresa (raíz)</option>
                {unitRows
                  .filter((item) => item.unit.status === "active")
                  .map((item) => (
                    <option
                      key={item.unit.id}
                      value={item.unit.id}
                    >{`${"— ".repeat(item.depth)}${item.unit.name}`}</option>
                  ))}
              </select>
            </label>
            <button className="workflowAction primary" disabled={!canConfigure || action !== null} type="submit">
              {action === "unit" ? "Creando…" : "Crear unidad"}
            </button>
          </form>

          <section aria-label="Árbol organizacional" className="securityListCard wide">
            <div className="panelHeader compactHeader">
              <h3>Árbol organizacional</h3>
              <span>Sin ciclos / control por tenant</span>
            </div>
            {unitRows.length ? (
              <div aria-label="Árbol organizacional" className="organizationTree" role="tree">
                {unitRows.map(({ unit, depth }) => (
                  <article
                    aria-level={depth + 1}
                    className="organizationTreeNode"
                    key={unit.id}
                    role="treeitem"
                    style={{ paddingLeft: `${14 + depth * 26}px` }}
                  >
                    <span>{unit.code}</span>
                    <strong>{unit.name}</strong>
                    <small>
                      {unit.unit_type} / {unit.status}
                    </small>
                  </article>
                ))}
              </div>
            ) : (
              <p className="securityEmptyState">Cree la primera unidad para iniciar la jerarquía de la empresa.</p>
            )}
          </section>
        </div>
      ) : null}

      {view === "authentication-sessions" ? (
        <div className="organizationSecurityGrid">
          <section className="securityMetricGrid wide" aria-label="Postura de autenticación">
            <SecurityMetric
              icon={<KeyRound size={18} />}
              label="Autenticación local"
              value={overview.authentication.local_authentication ? "Activa" : "Inactiva"}
            />
            <SecurityMetric
              icon={<LockKeyhole size={18} />}
              label="Access token"
              value={`${overview.authentication.access_token_minutes} min`}
            />
            <SecurityMetric
              icon={<ShieldCheck size={18} />}
              label="OIDC"
              value={overview.authentication.oidc_available ? "Disponible" : "No configurado"}
            />
            <SecurityMetric
              icon={<Users size={18} />}
              label="Usuarios activos"
              value={String(overview.authentication.active_user_count)}
            />
          </section>
          <section className="securityListCard wide">
            <div className="panelHeader compactHeader">
              <h3>Política de credenciales y sesiones</h3>
              <span>Estado de transición</span>
            </div>
            <div className="securityPolicyList">
              <article>
                <strong>Hash de contraseña</strong>
                <span>{overview.authentication.password_hash_policy}</span>
              </article>
              <article>
                <strong>Refresh token rotatorio</strong>
                <span>{overview.authentication.refresh_sessions ? "Activo" : "Pendiente de implementación"}</span>
              </article>
              <article>
                <strong>Almacenamiento del token</strong>
                <span>Bearer token actual; migración a cookie HttpOnly incluida en la siguiente etapa.</span>
              </article>
            </div>
          </section>
          <section className="securityListCard wide">
            <div className="panelHeader compactHeader">
              <h3>Eventos mínimos de seguridad</h3>
              <span>{overview.security_events.length} recientes</span>
            </div>
            <div className="securityEventList">
              {overview.security_events.map((event) => (
                <article key={event.id}>
                  <ShieldCheck aria-hidden="true" size={16} />
                  <strong>{event.event_type}</strong>
                  <span>{event.outcome}</span>
                  <small>{new Date(event.occurred_at).toLocaleString("es-CO")}</small>
                </article>
              ))}
            </div>
          </section>
        </div>
      ) : null}

      {view === "group-creator" ? (
        <div className="organizationSecurityGrid">
          <form className="securityFormCard" onSubmit={handleGroupSubmit}>
            <div className="panelHeader compactHeader">
              <h3>
                <Users size={18} /> Crear grupo
              </h3>
              <span>{overview.groups.length} grupos</span>
            </div>
            <label>
              <span>Código</span>
              <input
                disabled={!canConfigure || action !== null}
                onChange={(event) =>
                  setGroupDraft((current) => ({ ...current, code: event.target.value.toUpperCase() }))
                }
                required
                value={groupDraft.code}
              />
            </label>
            <label>
              <span>Nombre</span>
              <input
                disabled={!canConfigure || action !== null}
                onChange={(event) => setGroupDraft((current) => ({ ...current, name: event.target.value }))}
                required
                value={groupDraft.name}
              />
            </label>
            <label>
              <span>Descripción</span>
              <textarea
                disabled={!canConfigure || action !== null}
                onChange={(event) => setGroupDraft((current) => ({ ...current, description: event.target.value }))}
                value={groupDraft.description}
              />
            </label>
            <button className="workflowAction primary" disabled={!canConfigure || action !== null} type="submit">
              {action === "group" ? "Creando…" : "Crear grupo"}
            </button>
          </form>
          <form className="securityFormCard" onSubmit={handleGroupMemberSubmit}>
            <div className="panelHeader compactHeader">
              <h3>Agregar miembro</h3>
              <span>Herencia por grupo</span>
            </div>
            <label>
              <span>Grupo</span>
              <select
                disabled={!canConfigure || action !== null || !overview.groups.length}
                onChange={(event) => setGroupMemberDraft((current) => ({ ...current, group_id: event.target.value }))}
                value={groupMemberDraft.group_id}
              >
                <option value="">Seleccione</option>
                {overview.groups.map((group) => (
                  <option key={group.id} value={group.id}>
                    {group.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Usuario</span>
              <select
                disabled={!canConfigure || action !== null || !overview.users.length}
                onChange={(event) => setGroupMemberDraft((current) => ({ ...current, user_id: event.target.value }))}
                value={groupMemberDraft.user_id}
              >
                <option value="">Seleccione</option>
                {overview.users.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.full_name}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="workflowAction primary"
              disabled={!canConfigure || action !== null || !groupMemberDraft.group_id || !groupMemberDraft.user_id}
              type="submit"
            >
              {action === "group-member" ? "Asignando…" : "Agregar al grupo"}
            </button>
          </form>
          <section className="securityListCard wide">
            <div className="panelHeader compactHeader">
              <h3>Grupos de la empresa</h3>
              <span>Códigos únicos por tenant</span>
            </div>
            <div className="securityCardCollection">
              {overview.groups.map((group) => (
                <article key={group.id}>
                  <span>{group.code}</span>
                  <strong>{group.name}</strong>
                  <p>{group.description || "Sin descripción"}</p>
                  <small>
                    {group.member_ids.length} miembro(s) / {group.status}
                  </small>
                </article>
              ))}
            </div>
          </section>
        </div>
      ) : null}

      {view === "permissions" ? (
        <div className="organizationSecurityGrid">
          <form className="securityFormCard" onSubmit={handleRoleSubmit}>
            <div className="panelHeader compactHeader">
              <h3>
                <UserRoundCog size={18} /> Crear rol
              </h3>
              <span>Mínimo privilegio</span>
            </div>
            <div className="formColumns">
              <label>
                <span>Código</span>
                <input
                  disabled={!canConfigure || action !== null}
                  onChange={(event) => setRoleDraft((current) => ({ ...current, code: event.target.value }))}
                  required
                  value={roleDraft.code}
                />
              </label>
              <label>
                <span>Nombre</span>
                <input
                  disabled={!canConfigure || action !== null}
                  onChange={(event) => setRoleDraft((current) => ({ ...current, name: event.target.value }))}
                  required
                  value={roleDraft.name}
                />
              </label>
            </div>
            <label>
              <span>Descripción</span>
              <textarea
                disabled={!canConfigure || action !== null}
                onChange={(event) => setRoleDraft((current) => ({ ...current, description: event.target.value }))}
                value={roleDraft.description}
              />
            </label>
            <fieldset className="permissionChecklist">
              <legend>Permisos concedidos</legend>
              {overview.permissions.map((permission) => (
                <label key={permission.key}>
                  <input
                    checked={roleDraft.permission_keys.includes(permission.key)}
                    disabled={!canConfigure || action !== null}
                    onChange={(event) =>
                      setRoleDraft((current) => ({
                        ...current,
                        permission_keys: event.target.checked
                          ? [...current.permission_keys, permission.key]
                          : current.permission_keys.filter((item) => item !== permission.key),
                      }))
                    }
                    type="checkbox"
                  />
                  <span>
                    <strong>{permission.key}</strong>
                    <small>{permission.description}</small>
                  </span>
                </label>
              ))}
            </fieldset>
            <button className="workflowAction primary" disabled={!canConfigure || action !== null} type="submit">
              {action === "role" ? "Creando…" : "Crear rol"}
            </button>
          </form>
          <section className="securityListCard securityRoleCatalog">
            <div className="panelHeader compactHeader">
              <h3>Roles</h3>
              <span>{overview.roles.length} configurados</span>
            </div>
            {overview.roles.map((role) => (
              <article key={role.id}>
                <span>{role.is_system ? "Sistema" : "Personalizado"}</span>
                <strong>{role.name}</strong>
                <small>
                  {role.code} / {role.permission_keys.length} permiso(s)
                </small>
                <div className="permissionStrip">
                  {role.permission_keys.slice(0, 5).map((permission) => (
                    <span key={permission}>{permission}</span>
                  ))}
                </div>
              </article>
            ))}
          </section>
        </div>
      ) : null}

      {view === "access-control" ? (
        <div className="organizationSecurityGrid">
          <form className="securityFormCard" onSubmit={handleAssignmentSubmit}>
            <div className="panelHeader compactHeader">
              <h3>
                <LockKeyhole size={18} /> Asignar acceso
              </h3>
              <span>Usuario o grupo</span>
            </div>
            <div className="formColumns">
              <label>
                <span>Tipo de sujeto</span>
                <select
                  disabled={!canConfigure || action !== null}
                  onChange={(event) => {
                    const subjectType = event.target.value as "user" | "group";
                    setAssignmentDraft((current) => ({
                      ...current,
                      subject_type: subjectType,
                      subject_id: String(
                        (subjectType === "user" ? overview.users[0]?.id : overview.groups[0]?.id) ?? ""
                      ),
                    }));
                  }}
                  value={assignmentDraft.subject_type}
                >
                  <option value="user">Usuario</option>
                  <option value="group">Grupo</option>
                </select>
              </label>
              <label>
                <span>Sujeto</span>
                <select
                  disabled={!canConfigure || action !== null}
                  onChange={(event) =>
                    setAssignmentDraft((current) => ({ ...current, subject_id: event.target.value }))
                  }
                  value={assignmentDraft.subject_id}
                >
                  <option value="">Seleccione</option>
                  {assignmentDraft.subject_type === "user"
                    ? overview.users.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.full_name}
                        </option>
                      ))
                    : overview.groups.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.name}
                        </option>
                      ))}
                </select>
              </label>
            </div>
            <label>
              <span>Rol</span>
              <select
                disabled={!canConfigure || action !== null}
                onChange={(event) => setAssignmentDraft((current) => ({ ...current, role_id: event.target.value }))}
                value={assignmentDraft.role_id}
              >
                <option value="">Seleccione</option>
                {overview.roles.map((role) => (
                  <option key={role.id} value={role.id}>
                    {role.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="formColumns">
              <label>
                <span>Tipo de alcance</span>
                <select
                  disabled={!canConfigure || action !== null}
                  onChange={(event) =>
                    setAssignmentDraft((current) => ({
                      ...current,
                      scope_type: event.target.value as "organization" | "organization_unit",
                      scope_unit_id: "",
                    }))
                  }
                  value={assignmentDraft.scope_type}
                >
                  <option value="organization">Empresa</option>
                  <option value="organization_unit">Unidad organizacional</option>
                </select>
              </label>
              <label>
                <span>Unidad</span>
                <select
                  disabled={!canConfigure || action !== null || assignmentDraft.scope_type === "organization"}
                  onChange={(event) =>
                    setAssignmentDraft((current) => ({ ...current, scope_unit_id: event.target.value }))
                  }
                  value={assignmentDraft.scope_unit_id}
                >
                  <option value="">Seleccione</option>
                  {unitRows.map(({ unit, depth }) => (
                    <option key={unit.id} value={unit.id}>{`${"— ".repeat(depth)}${unit.name}`}</option>
                  ))}
                </select>
              </label>
            </div>
            <button
              className="workflowAction primary"
              disabled={
                !canConfigure ||
                action !== null ||
                !assignmentDraft.subject_id ||
                !assignmentDraft.role_id ||
                (assignmentDraft.scope_type === "organization_unit" && !assignmentDraft.scope_unit_id)
              }
              type="submit"
            >
              {action === "assignment" ? "Asignando…" : "Asignar acceso"}
            </button>
          </form>
          <section className="securityFormCard">
            <div className="panelHeader compactHeader">
              <h3>Acceso efectivo</h3>
              <span>Directo + heredado por grupo</span>
            </div>
            <label>
              <span>Usuario</span>
              <select onChange={(event) => setEffectiveUserId(event.target.value)} value={effectiveUserId}>
                <option value="">Seleccione</option>
                {overview.users.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.full_name}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="workflowAction"
              disabled={action !== null || !effectiveUserId}
              onClick={() => void handleEffectiveAccess()}
              type="button"
            >
              {action === "effective" ? "Calculando…" : "Calcular acceso efectivo"}
            </button>
            {effectiveAccess ? (
              <div className="effectiveAccessResult" aria-live="polite">
                <strong>{effectiveAccess.user_name}</strong>
                <span>{effectiveAccess.permission_keys.length} permiso(s) efectivos</span>
                <div className="permissionStrip">
                  {effectiveAccess.permission_keys.map((permission) => (
                    <span key={permission}>{permission}</span>
                  ))}
                </div>
              </div>
            ) : null}
          </section>
          <section className="securityListCard wide">
            <div className="panelHeader compactHeader">
              <h3>Asignaciones</h3>
              <span>{overview.assignments.filter((item) => item.status === "active").length} activas</span>
            </div>
            <div className="securityAssignmentList">
              {overview.assignments.map((assignment) => (
                <article key={assignment.id}>
                  <div>
                    <span>{assignment.subject_type}</span>
                    <strong>{assignment.subject_name}</strong>
                    <small>
                      {assignment.role_name} / {assignment.scope_name}
                    </small>
                  </div>
                  <em className={assignment.status === "active" ? "active" : "revoked"}>{assignment.status}</em>
                  {assignment.status === "active" && canConfigure ? (
                    <button
                      className="workflowAction danger"
                      disabled={action !== null}
                      onClick={() =>
                        void runAction(
                          `revoke-${assignment.id}`,
                          () => organizationSecurity.revokeAssignment(token, assignment.id),
                          "Acceso revocado."
                        )
                      }
                      type="button"
                    >
                      {action === `revoke-${assignment.id}` ? "Revocando…" : "Revocar"}
                    </button>
                  ) : null}
                </article>
              ))}
            </div>
          </section>
        </div>
      ) : null}
    </section>
  );
}

function SecurityMetric({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <article className="securityMetric">
      <span>
        {icon}
        {label}
      </span>
      <strong>{value}</strong>
    </article>
  );
}

function organizationUnitRows(units: OrganizationUnit[]) {
  const rows: Array<{ unit: OrganizationUnit; depth: number }> = [];
  const byParent = new Map<number | null, OrganizationUnit[]>();
  for (const unit of units) {
    const siblings = byParent.get(unit.parent_id) ?? [];
    siblings.push(unit);
    byParent.set(unit.parent_id, siblings);
  }
  for (const siblings of byParent.values())
    siblings.sort((left, right) => left.sort_order - right.sort_order || left.name.localeCompare(right.name));
  const visited = new Set<number>();
  function visit(parentId: number | null, depth: number) {
    for (const unit of byParent.get(parentId) ?? []) {
      if (visited.has(unit.id)) continue;
      visited.add(unit.id);
      rows.push({ unit, depth });
      visit(unit.id, depth + 1);
    }
  }
  visit(null, 0);
  for (const unit of units) if (!visited.has(unit.id)) rows.push({ unit, depth: 0 });
  return rows;
}

function errorDetail(error: unknown) {
  if (error instanceof Error) return error.message;
  return "No fue posible completar la operación.";
}
