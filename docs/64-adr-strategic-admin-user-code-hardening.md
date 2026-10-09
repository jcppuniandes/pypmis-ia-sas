# ADR 64 — Hardening del macroproceso estratégico: separación ADMIN/USER y optimización de código

- Estado: Aceptado y validado.
- Fecha: 2026-09-11; revisión de cierre: 2026-09-15.
- Alcance: Enterprise Strategy Manager, fases 0–7, navegación, composición de vistas, permisos y contratos HTTP asociados.
- Fuera de alcance: nuevos dominios funcionales, Five Case Model, activación operativa de proyectos y expansión de macroprocesos operacionales.

## Contexto

El macroproceso estratégico creció de forma incremental hasta cubrir Enterprise Foundation, Idea & Demand, Project Proposal, Strategic Gate, Portfolio Planning, Portfolio Scenario Planning, Project Definition & Investment Case e Investment Governance. Ese crecimiento dejó dos riesgos arquitectónicos: responsabilidades de configuración y transacción mezcladas en la navegación, y múltiples listas/renderizadores de rutas estratégicas dentro de `App.tsx` y `applicationNavigation.ts`.

La solución conserva los dominios y contratos backend existentes. El hardening es una reorganización de responsabilidad, autorización y composición; no modifica el significado de los estados, decisiones, evidencias, snapshots ni reglas de readiness ya persistidas.

## Decisiones

### 1. Clasificación exhaustiva y cerrada

Todo nodo/control estratégico se clasifica con uno y solo uno de estos valores:

- `USER_TRANSACTION`: operación viva del ciclo de inversión; requiere usuario autenticado y los permisos de dominio aplicables en backend.
- `ADMIN_CONFIGURATION`: definición, edición, clonación, previsualización, publicación o archivo de configuración; requiere `can_configure` en frontend y permisos `*.admin.configure`/`*.admin.publish` en backend.
- `READ_ONLY_SHARED`: consulta compartida sin mutación; requiere autenticación y mantiene autorización contextual/tenant del backend.

El mapeo frontend mínimo es `USER_TRANSACTION → authenticated`, `ADMIN_CONFIGURATION → can_configure` y `READ_ONLY_SHARED → authenticated`. La matriz persistida en `docs/validation/strategic-hardening/admin-user-control-matrix.csv` es la evidencia auditable de esta decisión.

### 2. Separación estricta de modos

USER MODE no contiene controles `ADMIN_CONFIGURATION`. ADMIN MODE no contiene controles `USER_TRANSACTION`. La navegación no sustituye la autorización backend: una ruta ADMIN directa se resuelve contra el registro canónico y se niega si el usuario no tiene `can_configure`; cada endpoint conserva su permiso de dominio.

Las pantallas USER consumen configuración publicada y ejecutan transacciones. Las pantallas ADMIN gestionan configuración y no exponen acciones transaccionales vivas. Las previsualizaciones ADMIN son no destructivas.

El cambio de modo es una transición atómica de aplicación. Al pasar de USER a ADMIN (o viceversa), `App.tsx` actualiza el modo y la vista de destino y reemplaza sincrónicamente la ruta por `/app` mediante `navigate(..., { flushSync: true, replace: true })`. Esto corrige una carrera observada cuando una navegación estratégica USER todavía pendiente restauraba su pathname después de activar ADMIN MODE. La transición ya no hereda deep links del modo anterior y la cinta correspondiente permanece estable.

### 3. Fuente única de verdad para navegación y rutas

`frontend/src/features/enterprise-strategy/navigation/strategicNavigationBlueprint.ts` es la fuente canónica de fases, jerarquía, orden, rutas, clasificación, permisos, contextos, precedencias y aplicabilidad por modelo de gobierno. De ella se derivan:

- los macroprocesos USER y ADMIN;
- rutas `/app/strategy/{view}` y `/app/admin/strategy/{view}`;
- breadcrumbs y registro de deep links;
- evaluación de acceso y orden del Workspace Navigator.

`App.tsx` se limita a orquestar estado global, navegación y layout. `StrategicViewOutlet.tsx` concentra la resolución de una vista estratégica hacia su componente y aplica la guarda de acceso del nodo antes de renderizarlo. Las listas estratégicas heredadas fueron retiradas físicamente de `applicationNavigation.ts`; solo sobreviven colecciones explícitas de capacidades no estratégicas y rutas alternativas vigentes (`PROJECT_WORKSPACE_GOVERNANCE_MODULES`, `NON_STRATEGIC_USER_MODE_NAVIGATION_BLUEPRINT` y `PLATFORM_ADMINISTRATION_MODULES`).

### 4. Compatibilidad sin reinterpretación histórica

Se preservan los modelos de gobierno:

- `CAPITAL_OWNER`: habilita las fases owner-only de Portfolio, Project Definition/Investment Case e Investment Governance.
- `CONTRACTOR_DELIVERY`: conserva Foundation e Idea/Proposal/Gate cuando corresponda, sin forzar el flujo owner-only.
- `DIRECT_INTERNAL`: conserva el flujo alternativo existente sin convertirlo implícitamente en Capital Owner.
- `LEGACY_UNCLASSIFIED`: mantiene legibilidad y navegación básica de registros históricos aún no reconciliados.

No se reescriben estados históricos, snapshots, decisiones FID, revisiones de Business Case, versiones financieras ni trazabilidad. La aplicabilidad se evalúa en lectura/navegación; no se migra silenciosamente el modelo de gobierno de un registro.

### 5. Contratos HTTP y permisos de dominio

Las familias transaccionales conservan sus endpoints y permisos específicos (`*.read`, `*.create`, `*.edit`, transiciones y acciones). Las familias ADMIN conservan endpoints separados bajo `/admin/configuration...` o `/admin/configurations...`, protegidos por `*.admin.configure` y `*.admin.publish`.

Para Business Analysis, el listado admite paginación acotada por cursor sin cambiar el contrato de cada elemento. Las reglas de escala y criterios se validan en backend; el formulario ADMIN estructurado sigue enviando el `content_json` gobernado. El JSON crudo queda como evidencia avanzada de solo lectura, no como editor primario.

### 6. Limpieza y optimización segura

La eliminación de duplicación sigue estas reglas:

1. no borrar rutas o controles con uso activo demostrado;
2. mover renderizado repetitivo de `App.tsx` al outlet estratégico;
3. derivar navegación, rutas y breadcrumbs desde el blueprint;
4. mantener capacidades comerciales/Workspace alternativas fuera del flujo universal de Ideas;
5. aislar temporales de pytest dentro del repositorio para evitar contaminación por ACL de Windows;
6. no reescribir la migración `0059`; crear un índice adicional únicamente si un plan de ejecución demuestra su necesidad.

Los tests estructurales de navegación pueden usar `fireEvent.click` cuando solo verifican cambio de estado/render y no semántica avanzada de interacción. En `AppFlow.test.tsx` esta sustitución preservó todas las aserciones y redujo el focal afectado de 256078 a 215257 ms (-15,9 %); los recorridos de usuario críticos permanecen cubiertos por Playwright.

La matriz `code-cleanup-matrix.csv` distingue lo retirado, consolidado, preservado o pendiente. No se considera “código muerto” a una ruta por no aparecer en una captura de navegación: debe verificarse consumo, deep links, pruebas y contrato backend.

## Invariantes de seguridad

- Un usuario autenticado sin `can_configure` no puede abrir una ruta ADMIN directa.
- Ocultar un botón no constituye autorización; el backend vuelve a comprobar tenant, rol y permiso.
- USER MODE no publica ni modifica configuración.
- ADMIN MODE no ejecuta decisiones, transiciones o creación de transacciones vivas.
- Las consultas compartidas no mutan datos.
- Ninguna optimización elimina auditoría, historial, snapshots, hashes de evidencia o trazabilidad de fuentes.

## Evidencia y trazabilidad

| Evidencia | Propósito |
|---|---|
| `admin-user-control-matrix.csv` | Inventario canónico de superficies, clasificación, permiso y endpoint relacionado. |
| `code-cleanup-matrix.csv` | Decisiones sobre duplicación, código heredado, temporales y separación de responsabilidades. |
| `route-compatibility-matrix.csv` | Compatibilidad de deep links, rutas canónicas y fallback heredado. |
| `api-compatibility-matrix.csv` | Familias de API, permisos USER/ADMIN y preservación contractual. |
| `baseline-differential.md` | Resultado completo del baseline `9cb0969` y estado del diferencial con la suite actual. |
| `strategicNavigationBlueprint.test.ts` | Invariantes de orden, clasificación, rutas, acceso directo y modelos alternativos. |
| `StrategicViewOutlet.test.tsx` | Denegación de ruta ADMIN sin `can_configure` y render autorizado con la guarda central. |
| `playwright-strategic.json` | Siete escenarios browser aprobados: separación BA, flujo USER/ADMIN, responsividad, no contaminación y denegación de deep link ADMIN. |
| `performance-before.json` / `performance-after.json` | Comparación reproducible de navegación, landing, primera página BA y evidencia Gate07J. |
| `frontend-static-gates.json` | Resultado post-parche confirmado de TypeScript, build, ESLint y Prettier: exit 0 en los cuatro gates, 0 errores y 9 warnings ESLint dentro del presupuesto. |

## Baseline de regresión `9cb0969`

La suite completa del baseline terminó con 609 casos: 572 aprobados, 27 omitidos y 10 fallidos en 2517.78 segundos. El resultado está respaldado por `outputs/.qa/strategic-hardening/baseline-pytest.xml` y no se interpreta como un gate verde.

Las diez fallas exactas son:

1. `tests.postgres.test_permit_readiness_postgres::test_permit_readiness_partial_unique_index_and_checks_exist`: el test PostgreSQL fue ejecutado con dialecto SQLite.
2. `tests.postgres.test_risk_readiness_postgres::test_risk_readiness_partial_unique_index_and_checks_exist`: el test PostgreSQL fue ejecutado con dialecto SQLite.
3. `tests.test_enterprise_structure::test_configuration_drafts_validate_publish_and_remain_immutable`: la respuesta de validación produjo `valid = false` cuando el test esperaba `true`.
4. `tests.test_investment_decision_gate07k::test_investment_selection_go_is_not_fid_and_has_no_project_activation`: `MANUAL_REFERENCE_NOT_ALLOWED` durante la preparación de evidencia FEL.
5. `tests.test_investment_decision_gate07k::test_pyp_ffa_go_is_single_fid_and_duplicate_decide_is_idempotent`: `MANUAL_REFERENCE_NOT_ALLOWED` durante la preparación de evidencia FEL.
6. `tests.test_investment_decision_gate07k::test_alternate_outcomes_are_closed_without_fid[HOLD-extra0-INVESTMENT_SELECTION_HELD]`: `MANUAL_REFERENCE_NOT_ALLOWED` durante la preparación de evidencia FEL.
7. `tests.test_investment_decision_gate07k::test_alternate_outcomes_are_closed_without_fid[RECYCLE-extra1-INVESTMENT_SELECTION_RECYCLE_REQUIRED]`: `MANUAL_REFERENCE_NOT_ALLOWED` durante la preparación de evidencia FEL.
8. `tests.test_investment_decision_gate07k::test_alternate_outcomes_are_closed_without_fid[KILL-extra2-INVESTMENT_SELECTION_KILLED]`: `MANUAL_REFERENCE_NOT_ALLOWED` durante la preparación de evidencia FEL.
9. `tests.test_investment_decision_gate07k::test_ffa_segregation_of_duties_and_stale_policy_block_decision`: `MANUAL_REFERENCE_NOT_ALLOWED` durante la preparación de evidencia FEL.
10. `tests.test_investment_decision_gate07k::test_committee_quorum_and_voting_rule_govern_decision`: `MANUAL_REFERENCE_NOT_ALLOWED` durante la preparación de evidencia FEL.

La suite actual terminó con 626 casos: 585 aprobados, 33 omitidos y 8 fallidos, sin errores, en 2510.651 segundos. Los 609 casos del baseline siguen presentes, no existe ninguna falla nueva y los ocho fallos actuales son heredados: uno de Enterprise Structure y siete del fixture/contrato de evidencia Gate07J–07K con `MANUAL_REFERENCE_NOT_ALLOWED`.

Los dos tests PostgreSQL que fallaban en el baseline por ejecutarse con SQLite ahora se omiten explícitamente cuando no existe URL PostgreSQL. Esto no se contabiliza como corrección por omisión. Ambos aprobaron en una ejecución PostgreSQL aislada que, en conjunto con cuatro gates Gate07A-BA, terminó con 6/6 casos aprobados, cero omitidos, cero fallidos y cero errores en 253.532 segundos. Los temporales controlados no produjeron errores ACL. El detalle trazable está en `baseline-differential.md`.

La corrida Browser E2E posterior a la corrección de la transición de modo terminó con 7/7 escenarios aprobados, 0 omitidos, 0 inesperados y 0 flaky en 89,853 segundos. Incluye el recorrido USER→ADMIN que antes exponía la carrera, la separación de controles por responsabilidad y la denegación de una ruta ADMIN directa cuando la membresía carece de `can_configure`.

La medición posterior no registró fallas y mejoró las cuatro referencias frente al baseline: navegación estratégica de 195,4 a 93,7 ms; landing de 1099,3 a 751,3 ms; primera página BA de 11688,4 a 3688,0 ms; y evidencia Gate07J de 12724,1 a 3840,4 ms. El bundle productivo actual contiene 13 archivos y 7.352.530 bytes frente a 10 archivos y 7.309.830 bytes en la referencia: +42.700 bytes (+0,584 %), dentro del umbral menor a 1 %, con el motor IFC conservado en carga diferida.

La corrida Vitest definitiva, posterior al último parche de `App.tsx` y a la optimización de `AppFlow.test.tsx`, terminó con 109/109 suites y 244/244 tests aprobados, sin fallos ni pendientes. El caso antes sensible al timeout aprobó focalmente en 215256,5408 ms y dentro del full en 278035,3453 ms. TypeScript, build Vite, ESLint y Prettier se repitieron después de esa optimización y cerraron con exit 0; ESLint conserva 0 errores y 9 warnings heredados del visor IFC, dentro del presupuesto de 10. Los gates del alcance están cerrados.

## Consecuencias

### Positivas

- La separación ADMIN/USER es declarativa, auditable y verificable.
- La navegación y los deep links ya no dependen de listas estratégicas heredadas duplicadas por pantalla.
- `App.tsx` reduce responsabilidad de renderizado estratégico.
- El outlet central y las guardas de ruta ADMIN tienen pruebas unitarias dedicadas.
- Los modelos históricos y alternativos permanecen accesibles sin reinterpretación.
- La matriz de compatibilidad permite detectar regresiones antes de retirar una ruta o endpoint.

### Costos y riesgos

- El registro de rutas debe mantenerse sincronizado con el `ControlFlowView` y el outlet.
- Las superficies que agrupan lectura y acción requieren pruebas de permisos a nivel de botón y endpoint, aunque su ruta sea `USER_TRANSACTION`.
- Las colecciones no estratégicas de `applicationNavigation.ts` siguen siendo extensas; cualquier reducción posterior debe respetar las capacidades de Project Control, Facility, Property y Project Workspace Governance que están fuera del alcance de este hardening.
- La validación estática no reemplaza los gates de TypeScript, lint, unitarios, PostgreSQL y browser E2E.
- Las ocho fallas backend heredadas —una de Enterprise Structure y siete Gate07K con `MANUAL_REFERENCE_NOT_ALLOWED`— permanecen como deuda explícita. El release de este hardening se evalúa por diferencial contra `9cb0969`; su eventual aprobación no debe interpretarse como suite backend global verde.
- El JUnit PostgreSQL 6/6 valida únicamente cuatro casos Gate07A-BA y los gates parciales de Permit/Risk; no representa los 22 casos `tests.postgres` omitidos en la corrida global SQLite.

## Criterio de cierre

El ADR queda completamente validado porque se satisfacen conjuntamente:

1. todas las filas de control tienen clasificación válida y no existe contaminación cruzada USER/ADMIN;
2. rutas ADMIN directas fallan sin `can_configure` y funcionan con el permiso;
3. permisos backend rechazan configuración para roles transaccionales y rechazan transacciones para roles solo configuradores cuando no tengan el permiso de dominio;
4. suites frontend posteriores al último parche, backend focal SQLite/PostgreSQL y browser E2E están verdes;
5. el diferencial contra `9cb0969` no introduce fallos globales nuevos atribuibles al hardening;
6. las métricas posteriores no muestran regresión material de navegación, carga o bundle;
7. no se modificaron datos históricos ni modelos de gobierno alternativos.

Se emiten `STRATEGIC_MACROPROCESS_ADMIN_USER_AND_CODE_HARDENING_VALIDATED`, `STRATEGIC_MACROPROCESS_CLEAN_SEPARATED_AND_OPTIMIZED` y, de forma separada para Gate07A, `GATE07A_BA_BUSINESS_ANALYSIS_RELEASE_VALIDATED`.

`NEXT = ENHANCE_GATE07M_BC_WITH_FIVE_CASE_MODEL`

La frontera siguiente no forma parte de esta decisión y no autoriza cambios Five Case dentro del hardening ya cerrado.
