# ADR 30 — Organización y Seguridad Nivel 1

## Estado

Aceptado para implementación incremental el 6 de agosto de 2026.

## Contexto

La aplicación ya dispone de `Tenant`, `UserAccount`, credenciales locales, membresías y permisos de proyecto. La especificación Nivel 1 agrega organización jerárquica, grupos, roles de seguridad, permisos atómicos, asignaciones por alcance y eventos mínimos sin autorizar una reescritura de los módulos funcionales existentes.

## Decisión

1. `Tenant` continúa siendo la empresa durante la transición y se expone como organización en la API administrativa.
2. Se agregan tablas tenant-scoped para unidades, grupos, roles, relaciones rol–permiso, asignaciones y eventos.
3. El catálogo de permisos es global y controlado por seed idempotente; los roles son propios de cada empresa.
4. Las asignaciones soportan sujeto `user` o `group` y alcance `organization` u `organization_unit`.
5. El acceso efectivo combina asignaciones directas y heredadas por grupo.
6. Durante la transición, las operaciones nuevas exigen el configurador tenant existente. El primer configurador obtiene de forma idempotente el rol `organization_admin` cuando aún no existe un administrador de organización.
7. La pantalla `User Creator` existente se conserva. ADMIN MODE se amplía con las otras cinco pantallas del flujo Nivel 1.
8. No se afirma que autenticación y sesiones estén terminadas: la interfaz muestra explícitamente la política heredada y los controles pendientes.

## Consecuencias

- La migración preserva datos y flujos actuales.
- La autorización Nivel 1 puede desplegarse y probarse sin cambiar todavía todos los endpoints de proyecto.
- La siguiente etapa debe convertir la evaluación RBAC en dependencia común de cada endpoint y completar invitaciones, refresh token rotatorio, recuperación, Argon2id y RLS PostgreSQL.

