# P&P Ingeniería y Proyectos — Gate de revisión y dry-run

Fecha: 2026-08-06  
Release propuesta: `ES-PYP-CORE-20260806`  
Paquete fuente: `PPMIS_Codex_Nivel_2B_Fase2_PYP_v1_0.zip`

## Resultado ejecutivo

Se completó el Prompt 01 del paquete: revisión de fuentes, resolución del tenant candidato, comparación de catálogos y validación en modo dry-run. El resultado es **BLOCKED**. No se ejecutaron `apply` ni `publish`, y no se modificaron datos de configuración en PostgreSQL.

La configuración revisada conserva las 24 unidades CORE, los 7 objetivos estratégicos y las 60 clasificaciones propuestas. El único ajuste al archivo fuente fue reemplazar el código de tenant propuesto `PYP` por el tenant real candidato `DEMO-ENERGY`; no se inventaron responsables, unidades ni aprobaciones.

## Resolución del tenant

La base local contiene un único tenant:

| Campo | Valor observado |
|---|---|
| ID | 1 |
| Slug | `demo-energy` |
| Código de importación | `DEMO-ENERGY` |
| Nombre | Demo Energy Infrastructure |
| Moneda base | COP |

El nombre observado no coincide con “P&P Ingeniería y Proyectos”. Se usó como **tenant candidato de validación**, no como confirmación de identidad ni autorización para aplicar la propuesta. No se creó un segundo tenant ni una segunda raíz empresarial.

## Alcance revisado

| Lote | Contenido | Estado en este gate |
|---|---:|---|
| CORE | 24 nodos, 7 objetivos, 60 clasificaciones | Validado; bloqueado |
| EXPERIENCE | 17 proyectos históricos, 47 clasificaciones | No aplicado; reservado para una fase opcional posterior |
| PROPERTY_FACILITY | 2 nodos opcionales | No aplicado; pendiente régimen de tenencia y denominación |
| Catálogos ADMIN | 11 propuestas | No publicadas; todas permanecen pendientes |

La plantilla Excel mantiene todas las decisiones funcionales en `PENDIENTE`. No se promovió ninguna fila a aprobada.

## Comparación de catálogos

| Propuesta | Catálogo publicado | Evaluación |
|---|---|---|
| `CONSULTORIA` | responsible-area: capital-projects, corporate, operations | Sin equivalencia exacta; requiere nuevo ítem borrador o decisión de mapeo |
| `PMO_AAS` | responsible-area: capital-projects, corporate, operations | Sin equivalencia exacta; requiere decisión funcional |
| `TECNOLOGIA` | responsible-area: capital-projects, corporate, operations | Sin equivalencia exacta; no equivale automáticamente a un área responsable existente |
| `CONSTRUCCION` | responsible-area: capital-projects, corporate, operations | Sin equivalencia exacta; `capital-projects` es candidato, no aprobación |
| `TECH_IMPLEMENTATION` | project-type: capital, operational, technology | `technology` es candidato razonable; requiere aprobación |
| `CONSTRUCTION_PROJECT` | project-type: capital, operational, technology | `capital` es candidato razonable; requiere aprobación |
| `INTERNAL_PRODUCT` | project-type: capital, operational, technology | `technology` es candidato parcial; semántica distinta |
| `CONSULTING_ASSIGNMENT` | project-type: capital, operational, technology | Sin equivalencia exacta; no se fuerza a `operational` |
| `PMO_ASSIGNMENT` | project-type: capital, operational, technology | Sin equivalencia exacta; no se fuerza a `operational` |
| `CORPORATE_OFFICE` | property-type: concession, leased, owned | Incompatible: la propuesta describe uso y el catálogo publicado describe tenencia |
| `OFFICE_SPACE` | facility-type: building, infrastructure, plant | `building` es candidato parcial; requiere decisión de taxonomía |

Los siete objetivos estratégicos propuestos son nuevos y no existen en el catálogo publicado.

## Resultado de validación

| Métrica | Resultado |
|---|---:|
| Estado | BLOCKED |
| Nodos | 24 |
| Objetivos estratégicos | 7 |
| Clasificaciones | 60 |
| Links | 0 |
| Errores | 24 |
| Advertencias | 0 |
| Información | 0 |
| Diferencias `create` | 90 |
| Diferencias `update` | 1 |
| Diferencias `unchanged` | 0 |
| Diferencias `conflict` | 0 |

Hash de entrada canónica:

`10c47aee1d159de7582c45a25a5d4be5acc04929d653fbad4287e3852513beb6`

La única actualización potencial es la adopción controlada del nodo raíz existente como `ENT-PYP`. Las 90 creaciones potenciales corresponden a 23 nodos adicionales, 7 objetivos y 60 clasificaciones. Ninguna fue persistida.

## Bloqueos detectados

1. Cuatro errores `REQUIRED_CLASSIFICATION_MISSING`: cada Business Unit requiere una clasificación `responsible-area`, pero la propuesta CORE no la asigna.
2. Veinte errores `CATEGORY_NOT_APPLICABLE`: la categoría publicada `strategic-objective` solo admite Portfolio, Program y Project, mientras la propuesta la asigna también al Enterprise y a las cuatro Business Units.

La jerarquía y su orden topológico son válidos. Los bloqueos corresponden a gobernanza de catálogos y aplicabilidad, no a ciclos o padres inexistentes.

## Prueba de no mutación

Los conteos antes y después del dry-run permanecieron iguales:

| Entidad | Antes | Después |
|---|---:|---:|
| EnterpriseWorkspace | 1 | 1 |
| Clasificaciones empresariales | 0 | 0 |
| Vínculos empresariales | 0 | 0 |
| AdminConfiguration | 21 | 21 |
| SecurityEvent | 1 | 1 |

## Decisiones requeridas para habilitar Prompt 02

- Confirmar que `demo-energy` es el tenant correcto para P&P Ingeniería y Proyectos, o indicar el tenant real.
- Aprobar, ajustar o excluir las 24 filas CORE y los 7 objetivos estratégicos.
- Aprobar el mapeo de las cuatro Business Units a `responsible-area`, o autorizar nuevos ítems ADMIN en estado borrador.
- Confirmar que las clasificaciones estratégicas inválidas en Enterprise y Business Unit deben retirarse o redefinir formalmente la aplicabilidad del catálogo.
- Identificar el usuario solicitante y los responsables/aprobadores exigidos por el flujo.
- Mantener EXPERIENCE y PROPERTY_FACILITY fuera del primer apply salvo autorización separada.

## Gate de ejecución

El Prompt 01 queda completo. El Prompt 02 (`apply` a borrador) y el Prompt 03 (`publish`) permanecen sin ejecutar por diseño. La siguiente operación permitida es ajustar la propuesta con decisiones explícitas y repetir el dry-run hasta obtener cero errores; después se requiere aprobación explícita para aplicar.

## Evidencias

- Configuración revisada: `backend/config/enterprise_structure.pyp_core_reviewed.yaml`
- Reporte humano: `artifacts/enterprise_structure/pyp_core/pyp_core_dry_run.txt`
- Reporte estructurado: `artifacts/enterprise_structure/pyp_core/pyp_core_dry_run.json`
- Hash: `artifacts/enterprise_structure/pyp_core/pyp_core_dry_run.sha256`
