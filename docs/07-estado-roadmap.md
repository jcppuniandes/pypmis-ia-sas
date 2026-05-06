# Estado Actual Del Roadmap

Fecha de evaluacion: 2026-05-06

## Calificacion global

La app esta en estado de demo funcional avanzada, no lista para produccion empresarial.

- Madurez global roadmap: 76/100 para piloto controlado cercano a pre-produccion.
- Conformidad TCM / Control Core: 7/10.
- Experiencia Project Controls SaaS: 6.5/10.
- Integracion AWP: 4/10.
- Preparacion SaaS productiva: 5.8/10.

## Evaluacion por fase

| Fase | Alcance | Estado | Calificacion |
| --- | --- | --- | --- |
| Fase 1 | Parser XER/XML robusto, DCMA/AACE, log de errores | Parcial funcional | 65% |
| Fase 2 | BP Engine configurable y Plan de Control / PEP | MVP piloto | 75% |
| Fase 3 | Control accounts automaticos, WBS/CBS/Activity, cost loading | MVP automatico | 58% |
| Fase 4 | EVM historico, Cost Manager, cash flow, productividad, forecast | MVP piloto | 70% |
| Fase 5 | Contract & claims, Aconex-style document control, notices, causalidad, impacto, evidencia | MVP cercano a produccion | 70% |
| Fase 6 | SaaS empresarial, colaboracion multiusuario, auth, RBAC, tenants, auditoria, hardening | Piloto colaborativo | 58% |

## Avance implementado

- Multi-proyecto, multiusuario y multirrol inicial.
- Schedule Intake como disparador del workflow.
- Data Quality Gate antes de operar el Control Core.
- BP Engine configurable: plantillas persistentes, formularios, pasos, transiciones, permisos basicos, ball-in-court y endpoint API-first.
- Plan de Control / PEP por proyecto: estrategia de ejecucion, estrategia de control, medicion de progreso, medicion de costo, cambios, riesgos, adquisiciones, control documental y cadencia de reportes.
- BP Designer frontend para crear nuevas plantillas de proceso sin tocar codigo.
- Fase 3 MVP: mapeo WBS/CBS/Activity desde el cronograma, trazabilidad por actividad, cost loading ponderado, resumen de cobertura y aprobacion formal del baseline.
- Fase 4 MVP: snapshots EVM por periodo, curva historica PV/EV/AC, resumen de productividad y escenarios EAC Current/Recovery/Pessimistic.
- Cost Manager MVP: Cost Sheet por cuenta de control, incurrido desde actas de pago, comprometido desde contratos/ordenes de compra, funding sources, cash flow periodico, resumen de cobertura de fondos y variacion de caja.
- Document Control tipo Aconex MVP: registro documental con numero/revision/estado, transmittals, project mail, revisiones, score documental y trazabilidad con BP/auditoria.
- EVM actual con PV, EV, AC, SPI, CPI, SV, CV, EAC, ETC y VAC.
- Cambios, reclamos, contratos, comunicaciones y documentos vinculados.
- AWP MVP: WorkPackage, WorkPackageConstraint, CWA/CWP/EWP/PWP/IWP, path of construction, readiness, constraint log y BP AWP Readiness.
- Claims entitlement MVP: ClaimEntitlementItem, matriz RP120R-21, cumulative impact RP130R-23, puntaje de entitlement, brechas y evidencia.
- Vista frontend AWP Workface Readiness.
- Vista frontend Claims / Forensic Entitlement.
- Vista frontend Roadmap Maturity Assessment.

## Brechas principales

- Fase 1: falta parser XER completo, XML mas robusto, validaciones DCMA/AACE exhaustivas y log de errores consumible por usuario.
- Fase 2: falta editor visual completo, versionado/aprobacion de plantillas, condiciones avanzadas, reglas por campo y migraciones de instancia entre versiones; el Plan de Control / PEP ya cubre la formalizacion minima para piloto.
- Fase 3: falta reglas avanzadas de agrupacion, revision masiva asistida, split de actividades entre cuentas de control, CBS contractual detallado y conciliacion con ERP.
- Fase 4: falta versionado/aprobacion de cash flow, escenarios configurables por usuario, tendencia por disciplina, integracion forecast con lookahead y conciliacion ERP.
- Fase 5: Document Control ya cubre registro, transmittals, project mail y reviews; faltan repositorio corporativo real, adjuntos binarios, permisos por carpeta, retencion legal, distribucion masiva, matriz contractual completa, analisis causa-efecto automatizado, measured mile/productividad avanzada y paquetes forenses.
- Fase 6: autenticacion JWT local, base Alembic inicial, readiness DB/Redis, request id/logging, smoke tests backend, CI inicial, control de acceso por membresia de proyecto, readiness de piloto y concurrencia optimista implementados; faltan OIDC/SSO, API tokens, realtime, notificaciones, observabilidad avanzada, hardening completo, backups/restore y pruebas automatizadas amplias.

## Siguiente paso recomendado

Prioridad inmediata: ejecutar piloto controlado.

1. Seguir `docs/08-guia-piloto.md` con un proyecto real o dataset semilla validado.
2. Medir readiness con `tools/pilot_check.ps1` antes y despues de cada ciclo.
3. Usar `docs/09-resumen-analisis-manual-piloto.md` como manual ejecutivo y operativo del piloto.
4. Registrar brechas para la siguiente ola: realtime, SSO/OIDC, integraciones ERP/P6, Document Manager avanzado y parser XER industrial.
