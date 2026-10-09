# Diferencial de suite global — baseline `9cb0969` vs. hardening actual

Fecha de corte: 2026-09-11. Reconciliación de evidencia: 2026-09-14.

## Resultado

| Ejecución | Casos | Aprobados | Omitidos | Fallidos | Errores | Duración |
|---|---:|---:|---:|---:|---:|---:|
| Baseline `9cb0969` | 609 | 572 | 27 | 10 | 0 | 2517.723 s |
| Working tree actual | 626 | 585 | 33 | 8 | 0 | 2510.651 s |
| Diferencia | +17 | +13 | +6 | -2 | 0 | -7.072 s |

La comparación es válida: no falta ningún caso del baseline en la suite actual, no aparecieron fallas nuevas y los ocho fallos actuales son subconjunto exacto de los diez del baseline. El tiempo total disminuyó 7.072 segundos (0.28 %), una variación no material para una suite de aproximadamente 42 minutos.

Fuentes primarias:

- `outputs/.qa/strategic-hardening/baseline-pytest.xml`;
- `outputs/.qa/strategic-hardening/current-pytest.xml`;
- `outputs/.qa/strategic-hardening/postgres-gates-clean.xml`.

Los archivos `baseline-pytest.stderr.log` y `current-pytest.stderr.log` están vacíos. Tampoco aparecen `PermissionError`, `Access is denied` ni `WinError 5` en las salidas estándar, por lo que el aislamiento de temporales evitó la contaminación por ACL observada antes del hardening.

## Diez fallas exactas del baseline

| # | Test | Evidencia de falla | Clasificación inicial |
|---:|---|---|---|
| 1 | `tests.postgres.test_permit_readiness_postgres::test_permit_readiness_partial_unique_index_and_checks_exist` | `AssertionError: assert 'sqlite' == 'postgresql'` | Entorno/dialecto: test PostgreSQL ejecutado dentro de la suite SQLite. |
| 2 | `tests.postgres.test_risk_readiness_postgres::test_risk_readiness_partial_unique_index_and_checks_exist` | `AssertionError: assert 'sqlite' == 'postgresql'` | Entorno/dialecto: test PostgreSQL ejecutado dentro de la suite SQLite. |
| 3 | `tests.test_enterprise_structure::test_configuration_drafts_validate_publish_and_remain_immutable` | `assert validation.json()["valid"] is True`; valor observado `False` | Regresión o desalineación funcional de validación; requiere comparación current. |
| 4 | `tests.test_investment_decision_gate07k::test_investment_selection_go_is_not_fid_and_has_no_project_activation` | HTTP 409 `MANUAL_REFERENCE_NOT_ALLOWED` en `_add_fel` | Fixture/contrato de evidencia manual Gate07J–07K. |
| 5 | `tests.test_investment_decision_gate07k::test_pyp_ffa_go_is_single_fid_and_duplicate_decide_is_idempotent` | HTTP 409 `MANUAL_REFERENCE_NOT_ALLOWED` en `_add_fel` | Fixture/contrato de evidencia manual Gate07J–07K. |
| 6 | `tests.test_investment_decision_gate07k::test_alternate_outcomes_are_closed_without_fid[HOLD-extra0-INVESTMENT_SELECTION_HELD]` | HTTP 409 `MANUAL_REFERENCE_NOT_ALLOWED` en `_add_fel` | Fixture/contrato de evidencia manual Gate07J–07K. |
| 7 | `tests.test_investment_decision_gate07k::test_alternate_outcomes_are_closed_without_fid[RECYCLE-extra1-INVESTMENT_SELECTION_RECYCLE_REQUIRED]` | HTTP 409 `MANUAL_REFERENCE_NOT_ALLOWED` en `_add_fel` | Fixture/contrato de evidencia manual Gate07J–07K. |
| 8 | `tests.test_investment_decision_gate07k::test_alternate_outcomes_are_closed_without_fid[KILL-extra2-INVESTMENT_SELECTION_KILLED]` | HTTP 409 `MANUAL_REFERENCE_NOT_ALLOWED` en `_add_fel` | Fixture/contrato de evidencia manual Gate07J–07K. |
| 9 | `tests.test_investment_decision_gate07k::test_ffa_segregation_of_duties_and_stale_policy_block_decision` | HTTP 409 `MANUAL_REFERENCE_NOT_ALLOWED` en `_add_fel` | Fixture/contrato de evidencia manual Gate07J–07K. |
| 10 | `tests.test_investment_decision_gate07k::test_committee_quorum_and_voting_rule_govern_decision` | HTTP 409 `MANUAL_REFERENCE_NOT_ALLOWED` en `_add_fel` | Fixture/contrato de evidencia manual Gate07J–07K. |

Comprobación aritmética: 572 aprobados + 27 omitidos + 10 fallidos = 609 casos.

## Reconciliación de las diez fallas del baseline

| Estado actual | Cantidad | Casos | Interpretación |
|---|---:|---|---|
| Falla heredada, sin cambio | 8 | `test_configuration_drafts_validate_publish_and_remain_immutable` y los siete casos `test_investment_decision_gate07k` listados arriba | Las firmas de error son las mismas del baseline. No son regresiones nuevas del hardening, pero siguen impidiendo considerar verde la suite global. |
| `FAIL → SKIP` en suite SQLite | 2 | `test_permit_readiness_partial_unique_index_and_checks_exist`; `test_risk_readiness_partial_unique_index_and_checks_exist` | La suite actual reconoce correctamente que requieren PostgreSQL. No se contabilizan como “corregidos” por el solo hecho de quedar omitidos. |
| Falla nueva | 0 | Ninguno | No existe regresión global nueva atribuible al hardening. |
| Caso baseline ausente | 0 | Ninguno | Los 609 identificadores del baseline están presentes en la ejecución actual. |

Los dos casos PostgreSQL que cambiaron de falla a omitido se ejecutaron después en el dialecto correcto y aprobaron dentro de `postgres-gates-clean.xml`. Esa suite aislada contiene seis casos, seis aprobados, cero omitidos, cero fallidos y cero errores en 253.532 segundos:

1. upgrade/downgrade/upgrade de Gate07A-BA;
2. tablas, constraints, índices y lineage de proposal para Gate07A-BA;
3. schema, lineage y constraints funcionales de Gate07A-BA;
4. snapshot feliz y rechazo de duplicado activo de Gate07A-BA;
5. índice parcial y checks de Permit Readiness;
6. índice parcial y checks de Risk Readiness.

Por tanto, Permit y Risk tienen evidencia PostgreSQL verde independiente, mientras la suite global conserva ocho fallas heredadas no relacionadas con la separación ADMIN/USER ni con Gate07A-BA.

## Cobertura nueva observada en la suite actual

Se agregaron 17 casos respecto del baseline. Trece aprobaron en la suite SQLite:

- 12 casos funcionales de Business Analysis Gate07A-BA: preview ADMIN no persistente, inmutabilidad publicada, separación de configuración/transacción, paginación por cursor y límites, validación de rating, seed concurrente idempotente, recorrido completo con SoD/lineage/snapshots, cuatro variantes de modelo de gobierno, rechazo de configuración inválida, restricción de rol USER y liberación auditada del slot activo mediante void;
- 1 caso de migración SQLite upgrade/downgrade/upgrade.

Los cuatro casos PostgreSQL nuevos quedaron omitidos en la suite SQLite con razones explícitas de entorno, y los cuatro aprobaron posteriormente dentro de la suite PostgreSQL aislada descrita arriba.

## Evidencia frontend reconciliada al corte

El reporter durable `outputs/.qa/strategic-hardening/frontend-vitest-current.json` corresponde a la corrida definitiva posterior al parche de transición USER→ADMIN de `App.tsx` y a la optimización del test estructural: inició el 2026-09-15 a las 02:41:24 UTC y terminó a las 02:54:43 UTC. Registra 54 archivos, 109 suites lógicas y 244 tests: 244 aprobados, 0 fallidos, 0 pendientes y `success=true`.

El caso `served project control flow uses a simplified project information flow instead of scattered navigation`, de `frontend/tests/AppFlow.test.tsx`, había agotado previamente 300000 ms sin una aserción funcional fallida. Su repetición focal aprobó en 256078 ms y una segunda repetición, tras optimizar interacciones estructurales sin cambiar aserciones, aprobó en 215256,5408 ms (-15,9 %). En el full definitivo aprobó en 278035,3453 ms. El gate se cierra con el reporter completo 244/244.

El consolidado post-parche `frontend-static-gates.json` registra TypeScript, build Vite, ESLint y Prettier con exit 0, además de 0 errores y 9 warnings ESLint confinados al visor BIM preexistente, por debajo del presupuesto CI de 10. Este gate está aprobado.

La evidencia browser sí está cerrada después de la corrección. `playwright-strategic.json` registra 7/7 casos aprobados, 0 omitidos, 0 inesperados y 0 flaky en 89.853 segundos. Los escenarios cubren separación BA USER/ADMIN, ciclo BA USER, configuración BA ADMIN, flujo USER→ADMIN, responsividad, ausencia de contaminación cruzada y denegación de deep link ADMIN sin `can_configure`.

La comparación `performance-before.json` frente a `performance-after.json` tiene cero fallas y mejora las cuatro referencias: navegación estratégica 195,4→93,7 ms; landing 1099,3→751,3 ms; primera página BA 11688,4→3688,0 ms; y evidencia Gate07J 12724,1→3840,4 ms. El bundle productivo actual suma 13 archivos y 7.352.530 bytes frente a 10 y 7.309.830 bytes de referencia: +42.700 bytes (+0,584 %), por debajo del umbral de 1 %.

En consecuencia, Vitest, E2E, rendimiento/bundle y gates estáticos post-optimización están reconciliados y verdes dentro del alcance.

## Estado del cleanup relacionado

- La duplicación estratégica heredada fue eliminada físicamente de `applicationNavigation.ts`.
- USER se deriva de `buildStrategicMacroprocess("user")`; ADMIN se deriva de `buildStrategicMacroprocess("admin")`.
- Las capacidades alternativas se mantienen en `PROJECT_WORKSPACE_GOVERNANCE_MODULES` y las no estratégicas en `NON_STRATEGIC_USER_MODE_NAVIGATION_BLUEPRINT`.
- La administración de plataforma se mantiene en `PLATFORM_ADMINISTRATION_MODULES`.
- `StrategicViewOutlet.tsx` centraliza el render y ejecuta `canAccessStrategicNode` antes de mostrar una vista; sus pruebas cubren denegación y autorización de una ruta ADMIN.

Estas confirmaciones de cleanup y el diferencial sin fallas nuevas satisfacen el criterio de no regresión backend atribuible al hardening. No convierten la suite global en verde: permanecen ocho fallas heredadas. Vitest, Browser E2E, rendimiento/bundle y estáticos están validados sobre el árbol final.

Se emiten:

- `STRATEGIC_MACROPROCESS_ADMIN_USER_AND_CODE_HARDENING_VALIDATED`
- `STRATEGIC_MACROPROCESS_CLEAN_SEPARATED_AND_OPTIMIZED`
- `GATE07A_BA_BUSINESS_ANALYSIS_RELEASE_VALIDATED`

`NEXT = ENHANCE_GATE07M_BC_WITH_FIVE_CASE_MODEL`
