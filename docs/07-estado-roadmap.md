# Estado Actual Del Roadmap

Fecha de evaluacion: 2026-05-08

## Calificacion global

La app esta en estado de piloto productivo controlado, cercana a produccion no critica.

- Madurez global roadmap: 82/100 para piloto productivo controlado.
- Conformidad TCM / Control Core: 7/10.
- Experiencia Project Controls SaaS: 7.8/10.
- Integracion AWP: 6/10.
- Preparacion SaaS productiva: 8/10 para produccion controlada.

## Evaluacion por fase

| Fase | Alcance | Estado | Calificacion |
| --- | --- | --- | --- |
| Fase 1 | Parser XER/XML robusto, DCMA/AACE, log de errores | Parcial funcional para piloto | 70% |
| Fase 2 | BP Engine configurable y Plan de Control / PEP | MVP piloto | 75% |
| Fase 3 | Control accounts automaticos, WBS/CBS/Activity, cost loading | Cerrada para piloto | 100% |
| Fase 4 | EVM historico, Cost Manager, cash flow, productividad, forecast | Cercano a produccion controlada | 82% |
| Fase 5 | RFQ, Contract & claims, Aconex-style document control, notices, causalidad, impacto, evidencia | MVP cercano a produccion con adjuntos | 86% |
| Fase 6 | SaaS empresarial, colaboracion multiusuario, auth, RBAC, tenants, auditoria, hardening | Piloto productivo controlado | 80% |

## Avance implementado

- Multi-proyecto, multiusuario y multirrol inicial.
- Schedule Intake como disparador del workflow.
- Data Quality Gate antes de operar el Control Core.
- BP Engine configurable: plantillas persistentes, formularios, pasos, transiciones, permisos basicos, ball-in-court y endpoint API-first.
- Plan de Control / PEP por proyecto: estrategia de ejecucion, estrategia de control, medicion de progreso, medicion de costo, cambios, riesgos, adquisiciones, control documental y cadencia de reportes.
- BP Designer frontend para crear nuevas plantillas de proceso sin tocar codigo.
- Fase 3 MVP: mapeo WBS/CBS/Activity desde el cronograma, trazabilidad por actividad, cost loading ponderado, resumen de cobertura y aprobacion formal del baseline.
- Fase 4 MVP: snapshots EVM por periodo, curva historica PV/EV/AC, resumen de productividad y escenarios EAC Current/Recovery/Pessimistic.
- Cost Manager MVP: Cost Sheet por cuenta de control, incurrido desde actas de pago y entradas de almacen, comprometido desde contratos/ordenes de compra, funding sources, cash flow periodico, resumen de cobertura de fondos y variacion de caja.
- RFQ / Bid Evaluation MVP: paquetes de licitacion, ofertas, score tecnico/comercial/cronograma/riesgo, weighted score y recommended bidder.
- Document Control tipo Aconex MVP: registro documental con numero/revision/estado, transmittals, project mail, revisiones, adjuntos binarios PDF/DOCX/XLSX/XML/XER/ZIP, hash SHA-256, descarga autenticada, score documental y trazabilidad con BP/auditoria.
- EVM actual con PV, EV, AC, SPI, CPI, SV, CV, EAC, ETC y VAC.
- Cambios, reclamos, contratos, comunicaciones y documentos vinculados.
- AWP MVP: WorkPackage, WorkPackageConstraint, CWA/CWP/EWP/PWP/IWP, path of construction, readiness, constraint log y BP AWP Readiness.
- Claims entitlement MVP: ClaimEntitlementItem, matriz RP120R-21, cumulative impact RP130R-23, puntaje de entitlement, brechas y evidencia.
- Vista frontend AWP Workface Readiness.
- Vista frontend Claims / Forensic Entitlement.
- Vista frontend Roadmap Maturity Assessment.
- Integraciones gobernadas read-only con manifiesto, CSV/JSON, ZIP con manifiesto y SHA-256, XLSX ejecutivo, tokens con expiracion/revocacion/alcance y alertas de rotacion.

## Brechas principales

- Fase 1: falta parser XER completo, XML mas robusto para cronogramas complejos, validaciones DCMA/AACE exhaustivas y log de errores consumible por usuario. La ingesta documental ya acepta XML/XER como evidencia controlada.
- Fase 2: falta editor visual completo, versionado/aprobacion de plantillas, condiciones avanzadas, reglas por campo y migraciones de instancia entre versiones; el Plan de Control / PEP ya cubre la formalizacion minima para piloto.
- Fase 3: falta reglas avanzadas de agrupacion, revision masiva asistida, split de actividades entre cuentas de control, CBS contractual detallado y conciliacion con ERP.
- Fase 4: falta versionado/aprobacion de cash flow, escenarios configurables por usuario, tendencia por disciplina, integracion forecast con lookahead, recepcion contra ERP/almacen real y conciliacion ERP.
- Fase 5: RFQ ya cubre paquete, ofertas, score y recomendacion; faltan portal de proveedores, invitaciones, RFI/addenda, directorio de subcontratistas y bid leveling avanzado. Document Control ya cubre registro, transmittals, project mail, reviews, adjuntos binarios, ZIP seguro y descarga autenticada; faltan repositorio corporativo real, permisos por carpeta, retencion legal, distribucion masiva, antivirus integrado, matriz contractual completa, analisis causa-efecto automatizado, measured mile/productividad avanzada y paquetes forenses.
- Fase 6: autenticacion JWT local, base Alembic inicial, readiness DB/Redis, request id/logging, smoke tests backend, CI inicial, control de acceso por membresia de proyecto, readiness de piloto, concurrencia optimista y tokens de integracion gobernados implementados; faltan OIDC/SSO, realtime, notificaciones, observabilidad avanzada, hardening completo, backups/restore productivo y pruebas automatizadas amplias.

## Siguiente paso recomendado

Prioridad inmediata: ejecutar piloto controlado.

1. Seguir `docs/08-guia-piloto.md` con un proyecto real o dataset semilla validado.
2. Medir readiness con `tools/pilot_check.ps1` antes y despues de cada ciclo.
3. Usar `docs/09-resumen-analisis-manual-piloto.md` como manual ejecutivo y operativo del piloto.
4. Registrar brechas para la siguiente ola: realtime, SSO/OIDC, integraciones ERP/P6, Document Manager avanzado y parser XER industrial.
