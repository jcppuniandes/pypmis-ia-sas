# P&P Ingeniería y Proyectos — Core Correction Gate 00

Fecha: 2026-08-06  
Paquete: `PPMIS_Codex_Nivel_2B_Core_Correction_v1_0.zip`  
Resultado: `READY_FOR_ADMIN_PUBLISH_APPROVAL`

## Alcance ejecutado

Se completó únicamente el Prompt 00 del paquete de corrección:

- inspección del tenant, raíz, usuarios, RBAC y configuraciones;
- validación del hash de la revisión publicada de `responsible-area`;
- clonación de una nueva revisión en estado `draft`;
- conservación de todos los valores existentes;
- incorporación de cuatro valores PYP;
- validación de códigos, duplicados y aplicabilidad;
- generación de diff, hash candidato y evidencias;
- pruebas focalizadas de backend y frontend.

No se publicó el catálogo, no se ejecutó el dry-run del CORE simplificado y no se ejecutaron `apply` ni `publish` del CORE.

## Tenant observado

| Campo | Valor |
|---|---|
| ID | 1 |
| Slug | `demo-energy` |
| Nombre | Demo Energy Infrastructure |
| Moneda | COP |
| Tenants activos observados | 1 |
| Raíces empresariales | 1 |
| Identidad P&P confirmada | No |

El tenant no fue renombrado ni modificado. `demo-energy` continúa siendo candidato técnico y requiere confirmación antes de `apply`.

## Identidad y autorización

La operación fue ejecutada mediante la cuenta existente `admin@demo.local`, ID 1. La cuenta tiene una asignación activa `organization_admin` con alcance `organization` y los permisos:

- `admin.enterprise_category.manage`;
- `admin.enterprise_category.publish`;
- `admin.enterprise_structure.publish`.

No se creó ni se inventó ningún usuario o aprobador.

## Revisión publicada preservada

| Campo | Valor |
|---|---|
| Configuración | `catalog / responsible-area` |
| ID | 18 |
| Revisión | 1 |
| Estado | `published` |
| Hash esperado y observado | `8cfcc66700593a8f38b63a27e4ee9d2cebadd10198e8d528652d138a359c08be` |

Valores publicados conservados:

- `corporate` — Corporate;
- `capital-projects` — Capital Projects;
- `operations` — Operations.

La revisión publicada permaneció inmutable.

## Revisión draft preparada

| Campo | Valor |
|---|---|
| ID | 22 |
| Revisión | 2 |
| Versión | 2 |
| Estado | `draft` |
| Hash candidato | `ccfdccd6367a3d9de68e7e5d2b38c521e92ef90a1971236da5b4fe16f4d3ddb7` |

Valores agregados:

| Código | Nombre |
|---|---|
| `consulting` | Consultoría en Gestión de Proyectos y Activos |
| `pmo-aas` | PMO como Servicio (PMO aaS) |
| `technology` | Tecnología e Innovación |
| `construction` | Gerencia de Construcción |

## Diff controlado

| Acción | Resultado |
|---|---|
| Preservados | 3 |
| Agregados | 4 |
| Eliminados | 0 |
| Modificados | 0 |
| Aplicabilidad modificada | No |

La aplicabilidad se conservó exactamente como estaba publicada:

`business-unit`, `portfolio`, `program`, `project`, `property`, `facility`.

Por tanto, `BUSINESS_UNIT` está soportado sin ampliar silenciosamente la regla publicada.

## Validación y auditoría

- Validación de configuración: `valid = true`.
- Issues: 0.
- Warnings: 0.
- Duplicados: 0.
- Eventos creados: `enterprise_structure.configuration_cloned` y `enterprise_structure.category_updated`.
- Usuario registrado en ambos eventos: ID 1.

## Conteos antes y después

| Entidad | Antes | Después | Interpretación |
|---|---:|---:|---|
| Tenants | 1 | 1 | Sin cambio |
| Raíces | 1 | 1 | Sin cambio |
| Enterprise workspaces | 1 | 1 | Sin cambio |
| Admin configurations | 21 | 22 | Nueva revisión draft |
| `responsible-area` published | 1 | 1 | Revisión publicada intacta |
| `responsible-area` draft | 0 | 1 | Revisión 2 preparada |
| Security events | 1 | 3 | Clonación y actualización auditadas |

## Pruebas

| Suite | Resultado |
|---|---|
| Backend Enterprise Structure + importer | 12 aprobadas |
| Frontend Enterprise Structure | 4 aprobadas |

## Gate de aprobación

El Prompt 00 queda completo. Para ejecutar el Prompt 01 se requiere aprobación explícita de:

1. publicar la revisión 2 de `responsible-area` con hash candidato `ccfdccd6367a3d9de68e7e5d2b38c521e92ef90a1971236da5b4fe16f4d3ddb7`;
2. aprobar los cuatro valores agregados;
3. aprobar los 14 nodos CORE simplificados y los 7 objetivos estratégicos;
4. autorizar el uso de `demo-energy` exclusivamente para el siguiente `validate` o indicar otro tenant.

Después de esa aprobación se podrá publicar el catálogo y ejecutar el dry-run del CORE simplificado. No se ejecutará `apply` en ese gate.

## Evidencias

- `backend/config/admin_responsible_area.pyp_patch.yaml`
- `artifacts/enterprise_structure/pyp_core_correction/gate00_admin_responsible_area_draft.json`
- `artifacts/enterprise_structure/pyp_core_correction/gate00_admin_responsible_area_draft.txt`
- `artifacts/enterprise_structure/pyp_core_correction/gate00_admin_responsible_area_draft.sha256`
