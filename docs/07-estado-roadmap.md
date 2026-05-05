# Estado Actual Del Roadmap

Fecha de evaluacion: 2026-05-05

## Calificacion global

La app esta en estado de demo funcional avanzada, no lista para produccion empresarial.

- Madurez global roadmap: 56/100.
- Conformidad TCM / Control Core: 7/10.
- Experiencia Project Controls SaaS: 6.5/10.
- Integracion AWP: 4/10.
- Preparacion SaaS productiva: 3/10.

## Evaluacion por fase

| Fase | Alcance | Estado | Calificacion |
| --- | --- | --- | --- |
| Fase 1 | Parser XER/XML robusto, DCMA/AACE, log de errores | Parcial funcional | 65% |
| Fase 2 | BP Engine configurable tipo uDesigner | MVP configurable | 68% |
| Fase 3 | Control accounts automaticos, WBS/CBS/Activity, cost loading | MVP automatico | 58% |
| Fase 4 | EVM historico, curvas reales, productividad, forecast | MVP historico | 62% |
| Fase 5 | Contract & claims, notices, causalidad, impacto, evidencia | MVP metodologico | 55% |
| Fase 6 | SaaS empresarial, colaboracion multiusuario, auth, RBAC, tenants, auditoria, hardening | SaaS-ready tecnico | 34% |

## Avance implementado

- Multi-proyecto, multiusuario y multirrol inicial.
- Schedule Intake como disparador del workflow.
- Data Quality Gate antes de operar el Control Core.
- BP Engine configurable: plantillas persistentes, formularios, pasos, transiciones, permisos basicos, ball-in-court y endpoint API-first.
- BP Designer frontend para crear nuevas plantillas de proceso sin tocar codigo.
- Fase 3 MVP: mapeo WBS/CBS/Activity desde el cronograma, trazabilidad por actividad, cost loading ponderado, resumen de cobertura y aprobacion formal del baseline.
- Fase 4 MVP: snapshots EVM por periodo, curva historica PV/EV/AC, resumen de productividad y escenarios EAC Current/Recovery/Pessimistic.
- EVM actual con PV, EV, AC, SPI, CPI, SV, CV, EAC, ETC y VAC.
- Cambios, reclamos, contratos, comunicaciones y documentos vinculados.
- AWP MVP: WorkPackage, WorkPackageConstraint, CWA/CWP/EWP/PWP/IWP, path of construction, readiness, constraint log y BP AWP Readiness.
- Claims entitlement MVP: ClaimEntitlementItem, matriz RP120R-21, cumulative impact RP130R-23, puntaje de entitlement, brechas y evidencia.
- Vista frontend AWP Workface Readiness.
- Vista frontend Claims / Forensic Entitlement.
- Vista frontend Roadmap Maturity Assessment.

## Brechas principales

- Fase 1: falta parser XER completo, XML mas robusto, validaciones DCMA/AACE exhaustivas y log de errores consumible por usuario.
- Fase 2: falta editor visual completo, versionado/aprobacion de plantillas, condiciones avanzadas, reglas por campo y migraciones de instancia entre versiones.
- Fase 3: falta reglas avanzadas de agrupacion, revision masiva asistida, split de actividades entre cuentas de control, CBS contractual detallado y conciliacion con ERP.
- Fase 4: falta curva de caja real, escenarios configurables por usuario, tendencia por disciplina, integracion forecast con lookahead y versionado de proyecciones.
- Fase 5: falta modulo formal de notices, matriz contractual completa, analisis causa-efecto automatizado, measured mile/productividad avanzada y paquetes forenses.
- Fase 6: autenticacion JWT local, base Alembic inicial, readiness DB/Redis, request id/logging, smoke tests backend y control de acceso por membresia de proyecto implementados; faltan OIDC/SSO, API tokens, concurrencia optimista, realtime, notificaciones, observabilidad avanzada, hardening completo y pruebas automatizadas amplias.

## Siguiente paso recomendado

Prioridad inmediata: Fase 6 colaborativa + Fase 1.

1. Implementar columna `version`/`updated_at` y control de concurrencia optimista en registros colaborativos.
2. Agregar canal realtime para workflows, alertas, equipo de proyecto y ball-in-court.
3. Fortalecer ingestion de cronograma con validaciones DCMA/AACE y log de errores consumible por usuario.
