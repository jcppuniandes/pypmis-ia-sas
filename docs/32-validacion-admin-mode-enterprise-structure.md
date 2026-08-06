# Validación ADMIN MODE — Nivel 2A Enterprise Structure

Fecha: 2026-08-06  
Paquete de diseño: `PPMIS_Codex_Nivel_2A_Enterprise_Structure_v1_1`

## Decisión de ubicación

- **ADMIN MODE / Enterprise Structure / Enterprise Structure Configuration** administra la estructura reusable, sus tipos, categorías, reglas de composición y publicación.
- **USER MODE / Enterprise Strategy Manager / Enterprise Structure & Workspace Manager / Enterprise Explorer** consulta la estructura publicada y autorizada.
- Project Creator, CPM, P6 XML/XER y la operación transaccional de proyectos permanecen fuera de este incremento.

## Respuestas al checklist

1. La capacidad define una estructura reusable y no una transacción operativa.
2. Se reutiliza `admin_configurations` para las versiones de tipos, categorías y reglas.
3. Se reutilizan catálogos publicados y se agregan únicamente los cinco catálogos empresariales del Nivel 2A.
4. Tipos, categorías y reglas se validan, versionan y publican.
5. Una configuración publicada es inmutable; la edición requiere clonar una nueva revisión draft.
6. Cada tipo tiene una regla de composición explícita.
7. Las categorías declaran `applicable_types` y validan su asignación.
8. Se agregan permisos exactos `admin.enterprise_structure.*`, `admin.enterprise_category.*`, `admin.composition_rule.*` y permisos de lectura/exportación USER.
9. Enterprise Explorer es estrictamente de lectura.
10. Se evitó duplicar workspaces y configuraciones: se reutilizan `enterprise_workspaces` y `admin_configurations`.
11. La jerarquía usa `parent_id`; clasificaciones y relaciones transversales usan tablas independientes.
12. Existen pruebas separadas de caracterización, configuración ADMIN, consulta USER, RBAC y aislamiento tenant.

## Evidencia técnica

- Migración aditiva `20260806_0028_enterprise_structure_level_2a.py`.
- Dominio modular `app/modules/enterprise_structure/`.
- Pantallas frontend modulares bajo `src/features/enterprise-structure/`.
- Navegación declarativa bajo `src/navigation/applicationNavigation.ts`.
- Pruebas backend `test_enterprise_structure.py` y `test_admin_configuration_characterization.py`.
- Pruebas frontend `enterprise-structure.test.tsx`.

