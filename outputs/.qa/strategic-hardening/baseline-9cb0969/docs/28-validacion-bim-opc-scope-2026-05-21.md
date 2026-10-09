# Validacion BIM / PBS / Scope Items / OPC - 2026-05-21

## Instructivos revisados

| Documento | Enfoque aplicado en la app |
| --- | --- |
| `Guia_Practica_PBS_ScopeItems_BIM_IFC_OPC_v1_1.docx` | BIM/IFC se trata como fuente de datos y evidencia, no como estructura de control copiada literalmente. |
| `Instructivo_OPC_Gestion_Scope_v1_5.docx` | El flujo se valida como `PBS -> Scope Items -> Scope Assignments`, con CBS antes del rollup de costos y WBS/Work Packages como distribucion operativa. |

## Criterios validados contra la app

| Regla del instructivo | Estado actual | Evidencia en la app |
| --- | --- | --- |
| Separar PBS de WBS | Parcialmente cubierto | El modulo BIM muestra `PBS product basis` desde ruta espacial, zona, sistema o assembly; WBS queda como mapeo operativo. |
| BIM/IFC como fuente, no como control structure | Cubierto | El visor indica que la previsualizacion sale de quantity rows y conserva `GlobalId`/Element ID como trazabilidad. |
| Scope Item candidato por familia/tipo/unidad/metodo/CBS/PBS | Cubierto | Nuevo panel `OPC Scope Validation` agrupa lineas en `Scope Item Candidate Register`. |
| No duplicar Scope Items por WBS | Cubierto en UX | El panel muestra la regla `Do not duplicate Scope Items by WBS` y orienta a usar Scope Assignments. |
| CBS hoja antes del rollup de costos | Cubierto como control visual | El panel muestra `CBS one-to-one` y marca `Needs CBS/WBS` cuando falta CBS o WBS es desconocido. |
| Balance de asignacion | Cubierto como lectura inicial | Se muestra `Pending assignment = total quantity - assigned quantity`; por ahora usa quantity con package code como cantidad asignada. |
| Trazabilidad BIM | Cubierto | El registro muestra `BIM Trace` con `GlobalId`, `Element ID` o `source_row_id`. |
| Visor BIM open source | En progreso controlado | Se agrego dependencia `web-ifc` como motor open source de parsing. El visor geometrico exacto con That Open Components queda como siguiente endurecimiento. |

## Cambios implementados

| Area | Cambio |
| --- | --- |
| Frontend BIM | Nuevo componente `BimScopeValidationPanel` con resumen OPC, reglas y registro de candidatos. |
| Visor 3D | `BimModelViewer` conserva el preview profesional basado en cantidades y ahora reporta disponibilidad del parser open source `web-ifc`. |
| Dependencias | Se agrego `web-ifc` al frontend. Se intento `web-ifc-three`, pero se descarto por conflicto de peer dependency con Three actual y porque el repo oficial esta deprecado. |
| Pruebas | `AppFlow.test.tsx` valida que el modulo BIM contiene `OPC Scope Validation`, no contiene `Schedule Intake`, y conserva visor 3D + trazabilidad `GUID`. |

## Pendientes recomendados

| Prioridad | Pendiente | Resultado esperado |
| --- | --- | --- |
| 1 | Implementar importador/visor geometrico IFC con That Open Components o stack compatible con `web-ifc`. | Cargar geometria real del modelo, no solo preview de quantity rows. |
| 2 | Persistir `Scope Item` y `Scope Assignment` como entidades backend. | Balance formal por Work Package, no calculo visual temporal. |
| 3 | Agregar diccionario de UOM y reglas de medicion por clase IFC. | Validacion de cantidades mas confiable para costos, avance y AWP. |
| 4 | Exportar registro de candidatos OPC a Excel/PDF. | Entregable auditable para revision de ingenieria/costos. |

## Resultado

La app queda alineada en esta fase con los instructivos para tomar cantidades BIM/Excel, construir candidatos de Scope Items, validar PBS/CBS/WBS/paquetes y mantener trazabilidad BIM. La geometria IFC exacta todavia no debe declararse completa: ya existe base open source (`web-ifc`), pero falta integrar un viewer geometrico completo y endurecido.
