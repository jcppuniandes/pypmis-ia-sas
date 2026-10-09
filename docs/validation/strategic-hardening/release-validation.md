# Validación de release — hardening estratégico ADMIN/USER

Fecha de consolidación: 2026-09-14. Fecha de cierre: 2026-09-15.

Esta acta compara el hardening del macroproceso estratégico con el baseline `9cb0969` y consolida evidencia durable de backend, PostgreSQL, frontend, navegador, rendimiento, bundle y matrices de compatibilidad. La aprobación usa el criterio diferencial definido para este alcance; no transforma una suite global con fallas heredadas en una suite verde.

## Decisión final

**Release aprobado dentro del alcance y del criterio diferencial definido para el hardening.**

Ya están comprobados:

- cero fallas backend nuevas frente a `9cb0969`;
- PostgreSQL dedicado 6/6 dentro de su alcance declarado;
- Browser E2E 7/7 después de corregir la carrera de cambio de modo;
- las cuatro mediciones de rendimiento sin regresión y con mejora;
- crecimiento de bundle de 0,584 %, menor al umbral de 1 %;
- matrices de clasificación, rutas, API y limpieza reconciliadas;
- Vitest definitivo 109/109 suites y 244/244 tests aprobados;
- TypeScript, build Vite, ESLint y Prettier repetidos después de la optimización final, todos con exit 0.

La corrida Vitest definitiva se ejecutó después de la corrección de `App.tsx` y de la optimización de `AppFlow.test.tsx`: aprobó 244/244 tests, sin fallos ni pendientes. Los gates estáticos se repitieron sobre el mismo árbol final y están verdes. Se cumplen las condiciones de salida sin ocultar que la suite backend global conserva ocho fallas heredadas.

## Estado por gate

| Gate | Resultado verificable | Estado |
|---|---|---|
| Backend baseline/current | 0 fallas nuevas; 8 fallas heredadas permanecen | Aprobado por diferencial |
| PostgreSQL dedicado | 6/6 aprobados; alcance limitado y explícito | Aprobado en alcance |
| Clasificación y compatibilidad | 128 controles clasificados; rutas y API preservadas | Aprobado |
| Vitest completo | 109/109 suites; 244/244 tests; 0 fallos y 0 pendientes | Aprobado |
| TypeScript/build/ESLint/Prettier | Exit 0 en los cuatro gates post-parche; 0 errores y 9 warnings ESLint | Aprobado |
| Browser E2E USER/ADMIN | 7/7 aprobados, 0 skipped/unexpected/flaky | Aprobado |
| Rendimiento | 4/4 mediciones mejoran; 0 fallas | Aprobado |
| Bundle | +42.700 bytes, +0,584 % | Aprobado con observación |
| Release integral | Todos los gates del alcance satisfechos | Aprobado |

## Corrección final: carrera USER→ADMIN

Durante el recorrido browser se detectó una carrera real: al activar ADMIN MODE desde un deep link estratégico USER, una transición de ruta todavía pendiente podía restaurar el pathname USER y reemplazar nuevamente la cinta ADMIN.

La corrección en `frontend/src/App.tsx` convierte el cambio de modo en una transición atómica:

1. calcula el modo y la vista de destino;
2. actualiza `applicationMode` y `activeControlView`;
3. reemplaza sincrónicamente el pathname por `/app` con `navigate("/app", { flushSync: true, replace: true })`;
4. impide que una navegación del modo anterior recupere su deep link.

El E2E también endureció la expansión del árbol: espera visibilidad y `aria-expanded="true"`, usa selectores directos de módulo y comprueba los cuatro controles de Investment Governance. La secuencia USER Portfolio Scorecard → ADMIN `/app` → cinta ADMIN quedó estable y forma parte del reporter 7/7.

El caso estructural de `AppFlow.test.tsx` se optimizó sin cambiar sus aserciones: aproximadamente 36 interacciones puramente estructurales pasaron de `userEvent.click` a `fireEvent.click`. La repetición focal mejoró de 256078 a 215257 ms (-15,9 %), reduciendo presión de temporización sin rebajar la validación observable.

## Backend: baseline frente al estado actual

Fuentes:

- `outputs/.qa/strategic-hardening/baseline-pytest.xml`;
- `outputs/.qa/strategic-hardening/current-pytest.xml`;
- `outputs/.qa/strategic-hardening/baseline-pytest.stdout.log`;
- `outputs/.qa/strategic-hardening/current-pytest.stdout.log`.

| Ejecución | Total | Aprobados | Omitidos | Fallidos | Errores | Duración |
|---|---:|---:|---:|---:|---:|---:|
| Baseline `9cb0969` | 609 | 572 | 27 | 10 | 0 | 2517,723 s |
| Working tree actual | 626 | 585 | 33 | 8 | 0 | 2510,651 s |
| Delta | +17 | +13 | +6 | -2 | 0 | -7,072 s |

Comprobaciones sobre los identificadores JUnit:

- los 609 casos del baseline siguen presentes;
- se añadieron 17 casos;
- las 8 fallas actuales son un subconjunto exacto de las 10 del baseline;
- no existe una firma de falla nueva atribuible al hardening;
- no aparecen `PermissionError`, `Access is denied` ni `WinError 5` en los logs baseline/current.

Las ocho fallas heredadas son una de Enterprise Structure (`test_configuration_drafts_validate_publish_and_remain_immutable`) y siete de Gate07K con `MANUAL_REFERENCE_NOT_ALLOWED`. Deben permanecer visibles como deuda; la aprobación diferencial del hardening no equivale a una suite backend global verde.

Las otras dos fallas del baseline correspondían a Permit y Risk PostgreSQL ejecutados bajo SQLite. En la suite global actual se omiten por requisito de dialecto y se validan en la corrida PostgreSQL dedicada.

## PostgreSQL dedicado

Fuente: `outputs/.qa/strategic-hardening/postgres-gates-clean.xml`.

Resultado: 6 casos, 6 aprobados, 0 omitidos, 0 fallidos y 0 errores en 253,532 s.

Cobertura exacta:

1. Gate07A-BA upgrade/downgrade/upgrade;
2. Gate07A-BA tablas, constraints, índices y lineage de Proposal;
3. Gate07A-BA schema, lineage y constraints funcionales;
4. Gate07A-BA snapshot feliz y rechazo de duplicado activo;
5. Permit Readiness: índice parcial y checks;
6. Risk Readiness: índice parcial y checks.

Límite: el JUnit global contiene 22 casos bajo `tests.postgres` omitidos cuando corre con SQLite. El 6/6 valida solo el subconjunto anterior, no todo el inventario PostgreSQL.

## Frontend unitario y estático

Fuentes:

- `outputs/.qa/strategic-hardening/frontend-vitest-current.json`;
- `outputs/.qa/strategic-hardening/frontend-static-gates.json`.

El reporter Vitest definitivo comenzó el 2026-09-15 a las 02:41:24 UTC y terminó a las 02:54:43 UTC. Registra 54 archivos, 109 suites lógicas y 244 tests: 244 aprobados, 0 fallidos, 0 pendientes y `success=true`.

Antes de este cierre, el caso `served project control flow uses a simplified project information flow instead of scattered navigation`, en `frontend/tests/AppFlow.test.tsx`, había agotado un límite de 300000 ms sin una aserción funcional fallida. Su repetición focal aprobó en 256078 ms y, después de optimizar interacciones estructurales sin cambiar aserciones, aprobó en 215256,5408 ms (-15,9 %). En la corrida completa definitiva volvió a aprobar en 278035,3453 ms, dentro del límite. El reporter completo —no el focal— es la evidencia que cierra el gate.

La evidencia estática posterior al parche registra:

- TypeScript: exit 0;
- Vite build: exit 0;
- ESLint: exit 0, 0 errores y 9 warnings;
- Prettier: exit 0;
- Gate07K focal: 3/3 tests aprobados.

Los nueve warnings están confinados al visor BIM IFC preexistente y permanecen por debajo del presupuesto CI de diez. El artefacto final fue consolidado el 2026-09-15 a las 07:35 -05:00, después del cambio de `App.tsx` y de la optimización de `AppFlow.test.tsx`, e incluye este último archivo en el check de Prettier.

## Browser E2E USER/ADMIN

Fuente: `outputs/.qa/strategic-hardening/playwright-strategic.json`.

Resultado Playwright: 7 esperados, 7 aprobados, 0 omitidos, 0 inesperados, 0 flaky; duración 89,853 s.

Casos cubiertos:

1. separación de navegación BA USER y ADMIN;
2. ciclo BA USER hasta `READY_FOR_PROJECT_PROPOSAL`;
3. configuración BA ADMIN: clonar, editar, previsualizar y publicar;
4. flujo estratégico USER→ADMIN, incluida la transición corregida;
5. orden de landing en tablet y móvil;
6. ausencia de controles de la responsabilidad opuesta;
7. denegación de ruta ADMIN directa sin `can_configure`.

Este gate sí es posterior al parche y aprueba la protección de deep links y la ausencia de contaminación cruzada visible.

## Rendimiento y bundle

Fuentes:

- `outputs/.qa/strategic-hardening/performance-before.json`;
- `outputs/.qa/strategic-hardening/performance-after.json`;
- build productivo actual en `frontend/dist`.

| Medición, viewport 1440×900 | Antes | Después | Variación |
|---|---:|---:|---:|
| Navegación estratégica | 195,4 ms | 93,7 ms | -52,0 % |
| Landing Enterprise Strategy | 1099,3 ms | 751,3 ms | -31,7 % |
| Primera página Business Analysis | 11688,4 ms | 3688,0 ms | -68,4 % |
| Vista de evidencia Gate07J | 12724,1 ms | 3840,4 ms | -69,8 % |

Ambos artefactos registran cero fallas de medición. No se observa regresión material en las cuatro referencias.

| Bundle | Archivos | Bytes | Delta |
|---|---:|---:|---:|
| Referencia | 10 | 7.309.830 | — |
| Actual | 13 | 7.352.530 | +42.700 (+0,584 %) |

El incremento permanece por debajo de 1 %. Se conserva el lazy load del motor IFC; el tamaño de ese componente es una observación preexistente, no una regresión atribuible al hardening.

## Matrices auditables

| Matriz | Filas | Resultado verificable |
|---|---:|---|
| ADMIN/USER | 128 | 100 USER, 28 ADMIN; 92 `USER_TRANSACTION`, 27 `ADMIN_CONFIGURATION`, 9 `READ_ONLY_SHARED`; 128 `IMPLEMENTED` |
| Compatibilidad de rutas | 27 | 27 `KEEP`; 25 `IMPLEMENTED`, 2 `PRESERVED` |
| Compatibilidad API | 24 | 21 `IMPLEMENTED`, 3 `PRESERVED` |
| Cleanup de código | 28 | 3 `ADD`, 2 `EXTEND`, 9 `KEEP`, 10 `REFACTOR`, 4 `REMOVE`; 22 `IMPLEMENTED`, 6 `PRESERVED` |

Las 128 rutas son únicas y cada control estratégico tiene exactamente una clasificación cerrada. Las matrices respaldan trazabilidad y compatibilidad, pero no sustituyen los gates runtime.

## Compatibilidad y límites

- Se conservan `CAPITAL_OWNER`, `CONTRACTOR_DELIVERY`, `DIRECT_INTERNAL` y `LEGACY_UNCLASSIFIED` sin reinterpretación histórica.
- Se preservan estados, decisiones, evidencias, snapshots, revisiones y contratos API existentes.
- No se añadió una migración posterior a `0059`.
- Five Case Model, activación operacional y nuevos dominios permanecen fuera de alcance.
- La siguiente frontera autorizada, solo después del cierre, es `ENHANCE_GATE07M_BC_WITH_FIVE_CASE_MODEL`.

## Señales de cierre

- `STRATEGIC_MACROPROCESS_ADMIN_USER_AND_CODE_HARDENING_VALIDATED`
- `STRATEGIC_MACROPROCESS_CLEAN_SEPARATED_AND_OPTIMIZED`
- `GATE07A_BA_BUSINESS_ANALYSIS_RELEASE_VALIDATED`

`NEXT = ENHANCE_GATE07M_BC_WITH_FIVE_CASE_MODEL`

## Huellas de evidencia confirmada

Algoritmo: SHA-256.

| Artefacto | Bytes | SHA-256 |
|---|---:|---|
| `baseline-pytest.xml` | 97.650 | `8ca77e1b6840fe59bfadf8494d6e480a5d5067cc7aa1fca4dd17b2b4c937e06c` |
| `current-pytest.xml` | 99.910 | `cfa162085376e4818e2970e3ed676c0efd2ea901f9d6660081ef2afd9c276581` |
| `postgres-gates-clean.xml` | 1.191 | `865f0313f6fe8b9f98732121755049fffafa5e122a215d0c5ec4ad82c1b1cac3` |
| `frontend-vitest-current.json` | 86.168 | `351a1334bfe8f8fce793cf110262d1eff20dd75f14b07473e4862252c9815b74` |
| `frontend-vitest-appflow-simplified-retry.json` | 8.639 | `97408f54d80effa2fdbdef54899ccd011710126d96b811357a11dd6dc50913f4` |
| `frontend-vitest-appflow-optimized-retry.json` | 8.639 | `804aa66a8b6e2883c54e98f9b01e378e3122b9e3ce8f8e6679d19b451a7612db` |
| `frontend-static-gates.json` | 1.115 | `5f8e6bbcd28025baa43656c91b4dc8af8cb24a3052594b8aee79841c906dc967` |
| `playwright-strategic.json` | 9.625 | `1171adc0b059861510d90559142084f170b9a1ae1a6093dc86d4600178df4498` |
| `performance-before.json` | 552 | `faed99415ec316ab1a98d7ceb7070ee28e97f5d1f0efb6d3265152a64c9ef673` |
| `performance-after.json` | 546 | `910a5a82e1c979bf2fba93d91e209c9aad2fbc93d88a1a8eae30d9a8630151b1` |

Las huellas de Vitest y estáticos identifican las corridas verdes ejecutadas sobre el árbol final. Los focales de AppFlow se conservan como trazabilidad del diagnóstico y de la optimización, no como sustitutos del reporter completo.
