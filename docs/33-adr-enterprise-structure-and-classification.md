# ADR-033 — Enterprise Structure and Classification

Estado: Aceptado  
Fecha: 2026-08-06

## Contexto

P&Pmis Construction AI necesita representar Enterprise, Business Unit, Portfolio, Program, Project, Property y Facility sin duplicar la estructura de workspaces ya operativa. También requiere clasificaciones estratégicas, relaciones transversales, separación ADMIN/USER, publicación inmutable y aislamiento multi-tenant.

## Decisión

1. `enterprise_workspaces` continúa siendo la fuente de verdad de los nodos. El tipo, estado y metadatos del Nivel 2A se encapsulan mediante el adaptador de dominio; los metadatos extendidos se guardan en `defaults_json._enterprise`.
2. `admin_configurations` continúa siendo la fuente de verdad versionada para tipos de workspace, categorías y reglas de composición.
3. Se agregan únicamente dos tablas normalizadas:
   - `enterprise_workspace_classifications` para asignaciones categoría–valor.
   - `enterprise_workspace_links` para relaciones no jerárquicas.
4. La relación jerárquica se modela exclusivamente con `parent_id`. Los objetivos estratégicos son clasificaciones, nunca padres.
5. Solo existe una raíz Enterprise activa por tenant. Los pares padre–hijo se validan contra reglas publicadas o drafts seleccionados.
6. Project–Property y Project–Facility son relaciones transversales, no extensiones forzadas del árbol.
7. Las publicaciones son inmutables y llevan hash; cualquier edición posterior exige clonar una revisión draft.
8. ADMIN MODE expone comandos de configuración. USER MODE expone consultas autorizadas y no incluye mutaciones.
9. La autorización combina permiso exacto, vigencia, asignación directa/grupal, tenant y alcance organizacional.

## Consecuencias

### Positivas

- No se duplican workspaces, catálogos ni el mecanismo de publicación.
- La jerarquía y las relaciones múltiples tienen semánticas separadas y auditables.
- El frontend puede presentar formularios comunes para los siete tipos.
- La configuración puede evolucionar sin romper contratos operativos existentes.

### Costos y límites

- El adaptador de metadatos debe mantenerse mientras el modelo monolítico legacy siga vigente.
- La publicación necesita una validación completa antes de cambiar el estado de los drafts.
- Este incremento no crea operaciones de Project Creator, scheduling ni importación P6.

## Compatibilidad

El cambio es aditivo. Los routers existentes permanecen intactos; los nuevos routers se registran en `app/api/v1/router.py`. La migración no elimina ni renombra tablas o columnas previas.

