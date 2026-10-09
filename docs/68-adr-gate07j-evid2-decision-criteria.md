# ADR 68 — Gate 07J-EVID-2: evidencia, criterios de decisión y revalidación estratégica

- **Estado de la decisión:** Aceptada y liberación validada
- **Fecha:** 2026-09-18
- **Incremento:** Gate 07J-EVID-2
- **Alembic esperado:** `20260916_0061 (head)`
- **Decisión de persistencia:** Reutilización de JSON versionado; sin migración

## Contexto

P&Pmis ya separa la preparación de un Gate de la decisión formal: Gate07J compone, revalida y congela el paquete de evidencia; Gate07K conserva la autoridad exclusiva sobre `GO`, `HOLD`, `RECYCLE` y `KILL`. El sistema también cuenta con una política A/B/C de evidencia, providers gobernados, resultados de Portfolio y fuentes especializadas de Business Case, FIN, Commercial, Benefits, FEL, Funding, Risk y Permit.

Faltaba una capa gobernada que expresara, sin ejecutar fórmulas arbitrarias ni duplicar cálculos de los dominios fuente, qué condiciones debe satisfacer un paquete para estar listo, qué requisitos de negocio son obligatorios, qué umbrales aplican, qué contexto de priorización debe presentarse y qué compromisos podrán congelarse como criterios de éxito en una decisión formal.

## Decisión

Se extiende en sitio la política Gate07J-EVID y se agrega una taxonomía independiente de criterios. La evaluación se realiza únicamente sobre hechos y hashes entregados por fuentes gobernadas. Gate07J prepara tres vistas separadas:

1. **Gate Readiness:** suficiencia, cobertura, vigencia y calidad de la evidencia.
2. **Business Evaluation:** evaluación determinista de requisitos y umbrales configurados.
3. **Portfolio / Resource Context:** contexto congelado de prioridad, escenarios y restricciones, sin recalcular ranking.

Gate07K consume el paquete congelado y sigue siendo el único agregado autorizado para registrar una decisión formal. No existe decisión automática ni inferencia de `GO`, `RECYCLE` o `KILL` a partir de un score.

## Reuse before create

| Necesidad | Autoridad reutilizada | Decisión |
|---|---|---|
| Política versionada y efectiva | `AdminConfiguration` | Extender `content_json`; no crear tabla nueva |
| Política A/B/C | Gate07J-EVID | Preservar sin reinterpretar revisiones publicadas legacy |
| Criteria policy | `AdminConfiguration.content_json.decision_criterion_policy` | Almacenar junto a la política de evidencia, nunca dentro de la matriz A/B/C |
| Evaluaciones y contexto congelados | `InvestmentGatePreparation.source_snapshot_json` y `evidence_summary_json` | Extender el snapshot y su hash |
| Paquete de decisión y FID histórico | `InvestmentDecision.decision_package_snapshot_json` | Congelar referencias, resultados y success criteria |
| Ciclo de publicación | clone → draft → preview → publish → supersede | Conservar ETag, idempotencia, effective dating y auditoría |
| Fuentes de evidencia | Provider registry existente | Reutilizar claves canónicas; no crear providers duplicados |
| Prioridad relativa | Portfolio | Consumir y congelar; no calcular un segundo ranking |
| Identidad de beneficios | `BEN-*` de Benefits | Congelar referencias y valores; no duplicar Benefits Register |

La estructura JSON existente permite versionar criterios, evaluaciones y snapshots sin pérdida de historial. Por ello no se justifica una migración ni entidades table-per-criterion.

## Taxonomías independientes

La clasificación de evidencia se mantiene intacta:

| Clase | Significado |
|---|---|
| A — `GOVERNED_SOURCE_REQUIRED` | La fuente gobernada es obligatoria |
| B — `GOVERNED_EVIDENCE_SUFFICIENT` | Evidencia controlada puede ser suficiente según política |
| C — `NOT_REQUIRED` | La evidencia no es requerida en el contexto aplicable |

Los criterios usan una taxonomía diferente:

| Tipo | Propósito |
|---|---|
| `READINESS_CHECK` | Comprueba que el paquete puede evaluarse |
| `MUST_MEET` | Condición obligatoria o de descarte |
| `DECISION_HURDLE` | Umbral cuantitativo o cualitativo configurado |
| `PRIORITIZATION` | Referencia no ponderada al contexto de Portfolio |
| `SUCCESS_CRITERION` | Compromiso candidato para el snapshot de decisión |

No se transforma una clase A/B/C en tipo de criterio ni se usa un criterio para reclasificar evidencia.

## Modelo de criterio y evaluación segura

Cada criterio conserva, como mínimo, código e identidad estable, nombre, tipo, Gate Profile, filtros de aplicabilidad, evidencia y campo fuente, operador, valor esperado, flags `required`/`blocking`, peso nullable, orden, versión, estado y fecha efectiva.

Los filtros soportan `GATE_PROFILE`, `FEL_STAGE`, `PROJECT_TYPE`, `GOVERNANCE_MODEL`, `PROJECT_SIZE`, `PROJECT_RISK`, `PROJECT_COMPLEXITY` y `UNCERTAINTY_LEVEL`. El comportamiento base aplica a `CAPITAL_OWNER`; `CONTRACTOR_DELIVERY` y `DIRECT_INTERNAL` no heredan requisitos de inversión del propietario salvo inclusión expresa.

Sólo se admiten operadores controlados:

```text
EQUALS
NOT_EQUALS
GREATER_THAN
GREATER_THAN_OR_EQUAL
LESS_THAN
LESS_THAN_OR_EQUAL
IN
NOT_IN
IS_TRUE
IS_FALSE
IS_READY
IS_CURRENT
COVERAGE_AT_LEAST
```

No se evalúan expresiones libres. Cada resultado conserva la referencia y hash fuente, valor observado, operador, umbral, resultado, flags, fecha de evaluación y revisión/hash de política. Los resultados posibles son `SATISFIED`, `NOT_SATISFIED`, `NOT_APPLICABLE`, `NOT_EVALUABLE` y `STALE`.

## Providers y autoridad de dominio

Se reutilizan las claves exactas registradas:

| Dominio | Provider canónico |
|---|---|
| Portfolio Recommendation | `GATE07I_PORTFOLIO_RECOMMENDATION` |
| Budget Feasibility | `GATE07G_BUDGET_FEASIBILITY` |
| Resource Feasibility | `GATE07H_RESOURCE_FEASIBILITY` |
| Project Definition / FEL | `GATE07J_FEL_PROJECT_DEFINITION` |
| Funding | `GATE07J_FUND_FUNDING_READINESS` |
| Risk | `RISK_READINESS_PROVIDER` |
| Permit | `PERMIT_READINESS_PROVIDER` |
| Business Case | `BUSINESS_CASE_READINESS_PROVIDER` |
| Economic / Financial | `ECONOMIC_FINANCIAL_READINESS_PROVIDER` |
| Benefits | `BENEFITS_READINESS_PROVIDER` |
| Commercial | `COMMERCIAL_READINESS_PROVIDER` |

La evidencia comercial conserva el tipo histórico `CONTRACTING_STRATEGY_READINESS` y usa el provider canónico, evitando una fila duplicada. Gate07J consume Five Case, métricas FIN, cobertura de Benefits, madurez FEL, reconciliación de Funding y estados de Risk/Permit; no recalcula esos dominios.

Si una fuente futura —por ejemplo QRA— no existe, se representa como `NOT_AVAILABLE`; no se fabrica evidencia.

## Readiness y calidad

`readiness` y `quality/confidence` permanecen independientes. La primera indica suficiencia bajo política; la segunda describe robustez declarada por una fuente gobernada. Si la fuente no declara calidad, el snapshot usa `NOT_AVAILABLE` con origen explícito, sin deducir calidad desde el frontend.

Estados soportados: `VALIDATED`, `PARTIALLY_VALIDATED`, `PRELIMINARY`, `LOW_CONFIDENCE`, `NOT_VALIDATED`, `NOT_APPLICABLE` y `NOT_AVAILABLE`. La aceptación de un estado es progresiva por Gate y por contexto; un valor preliminar puede ser válido en Select y no ser suficiente en FFA.

## Proporcionalidad Select y FFA

La revisión EVID-2 se crea clonando la política publicada; nunca modifica una revisión publicada o un paquete histórico.

- **PYP-INV-SELECT:** mínimo FEL-2, madurez de Business Case apropiada a etapa y requisitos Class B/configurables para FIN, Commercial, Benefits, Funding, Risk y Permit según intención de política. No se fuerzan covenants, estructura financiera final ni profundidad FFA.
- **PYP-FFA:** mínimo FEL-3, Business Case/Five Case, FIN, Commercial, Benefits, Funding y Risk gobernados según configuración; Permit conserva su regla contextual. Los criterios requeridos y bloqueantes son estrictos.

La cobertura de Project Set usa denominador exacto. No hay promedios ocultos ni sustitución manual de una fuente Class A.

## Consistencia entre fuentes

La preparación conserva los hashes referenciados por Business Case y los compara con las fuentes actuales de FIN, Benefits, Commercial, FEL, Funding, Risk y Permit. En FFA, una incompatibilidad material bloquea la preparación; en Select puede generar advertencia según configuración. Esta comparación detecta stale/mismatch sin volver a calcular Business Case, Five Case o FIN.

## Paquete Gate07J congelado

El contrato `PPMIS.GATE07J.DECISION_PREPARATION.v2` incorpora:

- política de evidencia, revisión, hash, matriz, provider y hechos fuente;
- calidad/confianza, cobertura, vigencia, warnings y blockers;
- política de criterios, revisión/hash y evaluaciones deterministas;
- estados separados de evidencia, negocio, contexto y paquete;
- snapshot de contexto de Portfolio, Budget y Resource;
- validación de consistencia entre fuentes;
- candidatos de criterios de éxito con identidad y lineage;
- `formal_decision_authority = GATE07K` y ausencia de outcome formal.

Una preparación congelada es inmutable. Una revisión de política o fuente posterior no reinterpreta el snapshot histórico.

## Consumo y guardrails Gate07K

El contrato `PPMIS.GATE07K.DECISION_PACKAGE.v2` copia el handoff y sus hashes, criterios, contexto de Portfolio y candidatos de éxito. Gate07K conserva autoridad individual/comité, quorum, voto, límites de autoridad y segregación de funciones.

`GO` se rechaza cuando el paquete o la evidencia no están `READY`, o cuando un `MUST_MEET` o `DECISION_HURDLE` requerido y bloqueante no está satisfecho. No existe bypass silencioso. `HOLD` puede expresar restricción de Portfolio/recursos sin marcar el Business Case como fallido. `RECYCLE` exige una preparación Gate07J nueva y vigente para una ronda posterior. `KILL` sigue siendo una decisión humana y no se infiere de entregables ausentes.

Una preparación ya usada por una decisión cerrada no se recicla silenciosamente en una nueva ronda. La nueva preparación resuelve la política efectiva actual; la ronda histórica conserva su revisión capturada.

## Snapshot de criterios de éxito

Cuando una decisión formal `GO` se registra, Gate07K congela de forma determinista los candidatos elegibles y calcula su hash. El snapshot conserva la referencia al criterio, identidad estable `BEN-*` cuando aplique, métrica/KPI, baseline, target, fecha objetivo, unidad, condición, fuente, versión, hash y `as_of` disponibles.

El snapshot pertenece al paquete histórico de decisión. Una revisión posterior del Benefits Plan no lo modifica y no crea un Benefit duplicado. Benefits Realization permanece fuera del alcance.

## Ciclo, API, seguridad y auditoría

La política usa el ciclo existente DRAFT/PUBLISHED/SUPERSEDED y effective dating. El endpoint dedicado `POST /configurations/{id}/clone-gate07j-evid2` crea de manera idempotente un draft EVID-2 desde la configuración publicada. Preview continúa siendo `persisted=false`; publish respeta ETag/`If-Match` e idempotencia.

Los eventos se registran con la convención del repositorio, incluidos cambios/publicación de política, evaluación de criterios, freeze de candidatos y snapshot de criterios de éxito. Las reglas RBAC y SoD de Gate07J/Gate07K no se amplían: ADMIN configura y publica; USER prepara o decide según permisos; el decisor no edita evidencia fuente.

## UI

La pantalla ADMIN existente de Evidence Policy se amplía, sin crear otro manager, para mostrar taxonomía, operadores, tailoring, criterios por Gate, thresholds, preview y lifecycle. Gate07J USER debe presentar una matriz compacta con evidencia, calidad, criterios agrupados, estados separados, Portfolio y success candidates. Gate07K USER debe mostrar únicamente snapshots congelados y mantener los controles de decisión humana autorizada.

`READY_FOR_INVESTMENT_DECISION` significa elegibilidad para decisión gobernada; nunca `GO` automático.

## Consecuencias

### Positivas

- Una sola política versionada y una sola autoridad por dominio.
- Separación auditable entre evidencia, evaluación de negocio, prioridad y decisión formal.
- Compatibilidad histórica sin migración de datos.
- Guardrails de `GO` verificables y success criteria inmutables.
- Extensibilidad futura para `strategic_bucket`, `portfolio_review_id` y `portfolio_snapshot_hash` sin implementar esas capacidades ahora.

### Costos y riesgos

- La configuración JSON requiere validación estricta y pruebas de compatibilidad legacy.
- Los paths de campos fuente dependen de contratos estables de provider.
- Un mismatch estricto en FFA aumenta la necesidad de refresh/revalidación explícita.
- La ausencia de calidad declarada debe seguir visible como `NOT_AVAILABLE`, no convertirse en un supuesto favorable.

## Límites deliberados

Este incremento no implementa Strategic Capital Buckets, periodic Portfolio Review, Capital Demand, Basic Data, QRA, Owner Capability, Operational Readiness, Benefits Realization, Procurement execution ni Project Delivery. Tampoco introduce optimizer, winner automático, nuevo ranking, score de Gate o FID generado por IA.

## Estado de validación

El cierre del 2026-09-20 completó validación focal, regresión estratégica, PostgreSQL real, frontend, Chromium y Docker/OpenAPI. Los resultados reproducibles y las señales exclusivas constan en `docs/validation/gate07j-evid2/release-validation.md`; este ADR conserva la decisión arquitectónica y no sustituye esos artefactos de prueba.
