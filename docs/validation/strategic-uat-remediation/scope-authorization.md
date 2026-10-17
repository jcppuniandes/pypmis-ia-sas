# Minimal strategic USER shell correction — explicit scope amendment

On 15 October 2026 the user was asked:

> El prompt exige mantener App.tsx intacto, pero Chromium confirma que una
> condición en ese archivo impide abrir el flujo estratégico del tenant nuevo.
> ¿Autorizas un ajuste mínimo para corregir ese bloqueo, sin rediseñar la
> navegación?

The user's explicit answer was: **“Sí, autorizar el ajuste mínimo”**.

This supersedes only the prompt's App.tsx-unchanged restriction for the minimal
USER fallback. Existing `WorkspaceNavigation`, the canonical navigation
blueprint and `StrategicViewOutlet` are reused. Without a legacy dashboard the
fallback displays strategic routes before the operational loading/empty/error
guards. It grants no ADMIN capability (`canConfigure=false`), invents no Project
and displays no fabricated EVM measurements. Operational routes retain their
existing guards; no strategic module, business engine or identity is added.

The new shell retains a hide/show module rail and a link back to Project
Controls. It does not claim new support for tenant-only ADMIN mode or change
backend RBAC. Its 29 focused tests and the real Chromium screenshots are scoped
UI evidence, not proof of the complete fresh A0–A31 or business release.
