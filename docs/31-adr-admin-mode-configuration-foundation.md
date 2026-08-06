# ADR 31 — Base de configuración versionada para ADMIN MODE

- Estado: aceptado para la primera entrega
- Fecha: 2026-08-06
- Alcance: ADMIN MODE, reutilizando Organización y Seguridad Nivel 1

## Contexto

La especificación `PPMIS_Codex_Admin_Mode_v1_0` separa la configuración empresarial reutilizable de la operación diaria. ADMIN MODE debe gobernar estructuras, catálogos, plantillas, reglas y procesos; USER MODE debe consumir versiones publicadas al operar instancias de portafolios, programas y proyectos.

El repositorio ya usa React/Vite, FastAPI, SQLAlchemy, Alembic y PostgreSQL, y dispone de tenant, usuarios, unidades organizacionales, grupos, roles, permisos, asignaciones y eventos de seguridad. La ampliación no debe reemplazar ese nivel ni interrumpir los módulos operativos ya construidos.

## Decisión

Se adopta una base aditiva con cuatro entidades:

1. `AdminConfiguration`: revisiones de tipo `workspace_type`, `module_definition`, `catalog`, `numbering_rule` o `process_definition`.
2. `EnterpriseWorkspace`: árbol empresarial tipado y aislado por tenant.
3. `WorkspaceModuleSetting`: activación explícita de módulos por workspace.
4. `AdminNumberSequence`: consecutivos por regla y alcance.

Las configuraciones se crean en borrador, se validan según su tipo y se publican con una huella SHA-256. Una revisión publicada es inmutable; cualquier cambio empieza clonando una nueva revisión en borrador.

La herencia se calcula recorriendo la jerarquía desde la raíz hasta el workspace solicitado. Los valores y activaciones definidos en niveles inferiores prevalecen. El movimiento de nodos evita ciclos y la activación valida dependencias declaradas en el catálogo de módulos.

Durante la transición, las operaciones administrativas reutilizan `require_tenant_configurator`. El catálogo de seguridad incorpora permisos `admin.*` y un rol semilla `configuration_admin`, preparando el paso posterior hacia autorización fina por endpoint.

## Consecuencias

- Se conserva toda la configuración y navegación existente de USER MODE y Organización y Seguridad.
- La migración es aditiva y reversible mediante Alembic `20260806_0027`.
- Nuevos tipos de configuración pueden incorporarse sin crear una tabla distinta por cada catálogo en la primera etapa.
- El contenido declarativo se almacena en JSON, pero su forma se valida en la API antes de publicar.
- La autorización fina por permiso, los releases coordinados y los módulos administrativos avanzados quedan para entregas posteriores.

## Fuera de alcance de esta entrega

- Diseñador visual drag-and-drop.
- Configuración avanzada de costos, riesgos, proveedores, activos o mantenimiento.
- Integraciones operativas automáticas con P6 u otros sistemas externos.
- Conversión de la arquitectura actual a Next.js/pnpm.

