# Informe técnico Integración contextual de evidencia QRA

**Estado actual:** QRA_RESULT_EVIDENCE_POLICY_INTEGRATION_RELEASE_VALIDATED

## 1. Resumen ejecutivo

Integramos resultados QRA aceptados en la cadena de evidencia de inversión mediante las políticas y fuentes existentes. Costo y plazo se exigen por separado y por contexto. El paquete Gate conserva la evidencia utilizada; Business Case recibe referencias compactas en revisiones nuevas. QRA no decide FID, no aprueba contingencia y no modifica presupuestos ni cronogramas. La validación local reúne 582 pruebas backend aprobadas y un perfilador opcional omitido, 438 pruebas frontend aprobadas y cuatro escenarios Chromium aprobados. El flujo real PostgreSQL también aprobó sus cuatro casos. Los inventarios deduplicados y los reruns se distinguen de una única ejecución global; el alcance y las limitaciones se detallan en este informe.

## 2. Baseline real del repositorio

Inicio en main, commit 3cadbe0, working tree limpio. Los 42 archivos anteriores ya estaban guardados por el usuario. Revisamos status, diff, diff stat y los últimos 15 commits. Alembic operacional está en 20261011_0068. La base contiene cinco políticas Evidence publicadas, ninguna modificada por este incremento. El baseline técnico y sus lecturas quedan en la carpeta privada de validación.

## 3. ADR de integración

El ADR 84 registra un solo proveedor con calificadores, política contextual en JSON existente y consumo de fuentes por referencia. No existe un nuevo motor, subsistema Gate QRA, módulo superior o mecanismo paralelo de revisión. La integración se limita a evidencia; mantiene las autoridades y los snapshots históricos.

## 4. Matriz de autoridad

| Componente | Autoridad conservada | Acción de este incremento |
| --- | --- | --- |
| QRA Engine | Cálculo y aceptación independiente | Publica resumen analítico aceptado |
| Evidence Policy | Exigencia y criterios por contexto | Califica costo y plazo |
| Gate07J | Preparación y congelación | Captura evidencia y política |
| Business Case | Síntesis Five Case | Incorpora referencias en sucesores |
| Gate07K | Decisión de inversión | Consume paquete congelado |
| Gate07L | Elegibilidad posterior a FID | Mantiene reglas anteriores |
| Budget Funding FIN P6 | Dominios de origen | Sin actualización automática |

## 5. Reutilización antes de crear

Reutilizamos QraRunReview, currentness de QraModelDefinition, provider registry, clases A B C, lifecycle de AdminConfiguration, effective dating, criterios EVID2, paquetes Gate, Business Case refresh y Five Case. La navegación conserva strategicNavigationBlueprint. El código nuevo es un helper de calificadores y componentes pequeños de edición y resumen; App.tsx no recibe lógica adicional.

| Ubicación principal | Responsabilidad del cambio | Reutilización |
| --- | --- | --- |
| investment_evidence_policy/qra_evidence.py | Aplicabilidad capacidad y resumen calificado | Contexto y motor existentes |
| investment_evidence_policy/service.py | Clone preview publish y contexto de portafolio | AdminConfiguration y registry |
| investment_evidence_policy/decision_criteria.py | Valores QRA y comparabilidad | Evaluador EVID2 |
| qra_engine/service.py | Selector por análisis alcance y aceptación | Corridas y revisión inmutables |
| investment_gate_preparation/service.py | Filas freeze y currentness | Paquetes Gate07J |
| business_case/service.py | Fuentes por referencia y sucesor | Bundle refresh y Five Case |
| QraPolicyEditor y QraEvidenceSummary | Editor ADMIN y resumen USER | Rutas y permisos actuales |

Las primeras seis ubicaciones se encuentran bajo backend/app/modules; los componentes frontend bajo frontend/src/features/investment-evidence-policy. Las pruebas, el ADR y el generador de informe se añaden sin reemplazar funcionalidades previas.

## 6. Baseline del proveedor QRA

QRA_RESULT_PROVIDER ya estaba AVAILABLE para resultados aceptados y vigentes. Su disponibilidad indica contrato implementado, no existencia de resultado por proyecto. La extensión conserva evidence_type QRA_RESULT para consumidores anteriores y normaliza las filas calificadas a COST_QRA_RESULT o SCHEDULE_QRA_RESULT. No se crean proveedores separados.

## 7. Capacidades del motor vigente

| Capacidad | Estado | Límite relevante |
| --- | --- | --- |
| Cost QRA | Disponible | Moneda y base de costo explícitas |
| Schedule QRA | Disponible | Actividades no iniciadas y tiempo transcurrido |
| QRA integrado | No disponible | No puede exigirse como evidencia activa |
| Convergencia de media | Disponible | No certifica P90 P95 ni colas |
| Calendarios laborales P6 | No disponibles | Sin conversión silenciosa |
| Eventos Risk automáticos | No disponibles | Referencias no equivalen a eventos |

## 8. Modelo de aplicabilidad

Cada fila qra_policy declara análisis, exigencia, filtros, calidad, convergencia, alcance y antigüedad. Los resultados distinguen REQUIRED, NOT_REQUIRED, NOT_APPLICABLE y NOT_EVALUABLE. CONDITIONAL se resuelve con datos gobernados. Falta de contexto o moneda incompatible no convierte una regla obligatoria en no requerida.

## 9. Reglas por Gate Profile

PYP INV SELECT y PYP FFA conservan políticas independientes. El administrador puede mantener QRA no requerido en selección y exigirlo en autorización solo donde corresponda. No se añade Class A universal a FFA. La ausencia de perfil gobernado no se interpreta como FFA en Business Case.

## 10. Reglas por Governance Model

El filtro inicial es CAPITAL_OWNER. CONTRACTOR_DELIVERY, DIRECT_INTERNAL y LEGACY_UNCLASSIFIED quedan fuera de una regla que no los incluya. La configuración explícita puede cambiar el ámbito en una nueva revisión; no se reinterpreta retrospectivamente una política publicada.

## 11. Reglas por Project Type

Los filtros usan project_type existente y admiten selección explícita o todos. La jerarquía de la fila y el calificador deben ser coherentes. Se valida la fila combinada con sus overrides para impedir una exigencia integrada o fallback manual introducidos indirectamente. Las pruebas separan contexto capital y no capital.

## 12. Valor riesgo complejidad e incertidumbre

El rango de valor usa PROJECT_CREATION_ESTIMATED_BUDGET, estimated_budget y currency_code. Riesgo, complejidad e incertidumbre usan atributos existentes, sin puntuación nueva ni recálculo de Risk. Monedas diferentes o valores ausentes producen condición no evaluable. No usamos Portfolio Budget como prueba automática de suficiencia QRA.

## 13. Compatibilidad de capacidades

Aplicabilidad, capacidad del motor y calidad de la corrida son verificaciones distintas. El proveedor o el adaptador de política explican el contexto no soportado. SUPPORTED_WITH_LIMITATIONS permite mostrar Schedule con límites explícitos; no equivale a reproducción de calendarios laborales.

## 14. Limitaciones de Schedule QRA

Schedule exige NOT_STARTED, duración restante igual a duración fuente y NORMALIZED_ELAPSED_TIME_V1. El guard emplea la normalización del kernel y acepta variantes válidas como Not Started y TK NotStart sin ocultar avance real. Se inspeccionan atributos de ScheduleImport para reconocer remanentes incompatibles. HOURS y DAYS mantienen su semántica transcurrida; no se comparan con días laborales sin conversión gobernada.

## 15. Prohibición de QRA integrado

INTEGRATED_COST_SCHEDULE_QRA no puede publicarse como exigencia activa. La validación rechaza tipo no liberado o incongruencia entre evidence_type y analysis_type. Dos análisis separados de costo y plazo no se presentan como un cálculo integrado.

## 16. Clases de evidencia

A exige fuente gobernada y prohíbe fallback manual. B mantiene evidencia gobernada suficiente según reglas existentes. C es no requerida. La determinación contextual fuera de ámbito transforma la fila efectiva en no bloqueante, sin cambiar el documento publicado que originó la evaluación.

## 17. Ciclo de la política

La incorporación se configura mediante clonación de la política vigente, edición DRAFT, preview, validación y publicación autorizada de sucesor. No se edita una revisión PUBLISHED. Las operaciones se auditan con SecurityEvent y conservan los patrones previos de control de versión.

La prueba repetida de nuevas revisiones detectó que el nombre generado por clone podía superar los 180 caracteres de la columna PostgreSQL. El nombre de la nueva revisión se limita a esa capacidad conservando el sufijo de revisión; no se renombra la fuente publicada ni se amplía el esquema. La procedencia se conserva en la auditoría, independiente del texto abreviado de presentación.

## 18. Vigencia explícita

Cada revisión conserva published_at, effective_from, scope y content_hash. La política futura no desplaza una regla todavía vigente. El paquete captura los identificadores de la regla aplicada. El resolver usa ámbito y fecha, no una elección informal del último registro.

## 19. Nuevas rondas y reciclaje

Una nueva preparación o actualización explícita obtiene CURRENT_EFFECTIVE_POLICY_AT_NEW_OR_EXPLICIT_REFRESH_PREPARATION. La etapa FEL procede del registro gobernado y se captura con su referencia, no de metadata antigua. Una ronda histórica sigue ligada al paquete capturado. La decisión nueva consume esa preparación, no una política publicada después del freeze.

## 20. Evidencia QRA de costo

COST_QRA_RESULT resuelve únicamente COST_QRA. La política puede exigir proyecto completo o permitir alcance parcial. Se congelan moneda, base de costo, percentiles y probabilidades ya calculadas. El valor mostrado es analítico y no constituye presupuesto ni contingencia aprobada.

## 21. Evidencia QRA de plazo

SCHEDULE_QRA_RESULT resuelve únicamente SCHEDULE_QRA compatible. El resumen mantiene unidad, ancla temporal y método. La vista advierte que no se reproducen turnos ni festivos P6 y que el motor no admite progreso real ni remanentes distintos de la duración fuente.

## 22. Elegibilidad del proveedor

Se exige COMPLETED y review ACCEPTED, tenant y proyecto correctos, modelo y método vigentes, fuentes actuales y ausencia de supersession. COMPLETED por sí solo no habilita evidencia. Las fallas de calidad de una sucesora no habilitan regresar a una corrida obsoleta.

## 23. Correspondencia de análisis

El calificador se pasa al resolver del motor. Un resultado de costo no satisface plazo ni viceversa. Los identificadores y analysis_type se incluyen en el resumen y el paquete, de modo que la fila no oculta una sustitución incorrecta.

## 24. Correspondencia de alcance

WHOLE_PROJECT filtra ENTIRE_PROJECT en la consulta. Una corrida parcial no satisface ese requisito. La supersession se compara por alcance exacto y tipo; una corrida de otro alcance no invalida por sí sola el resultado de proyecto completo. PARTIAL_ALLOWED debe estar expresamente configurado.

## 25. Vigencia de resultados

Las fuentes, el modelo y la metodología se revalidan mediante Foundation. Cambios materiales retiran la evidencia vigente. Un paquete nuevo queda bloqueado cuando la fuente es stale, mientras el paquete congelado conserva los números y hashes originalmente capturados.

## 26. Preparación analítica

La regla distingue READY_ONLY y WARNINGS_ALLOWED. READY_WITH_WARNINGS no se convierte en READY. La advertencia de contingencia o asignaciones superpuestas permanece visible. La aceptación independiente no elimina automáticamente los límites de la calidad analítica.

## 27. Política de convergencia

REQUIRED exige CONVERGED; WARNING_ALLOWED muestra NOT_CONVERGED y NOT_REQUIRED conserva el diagnóstico sin exigirlo. La selección de la política no recalcula ninguna estadística. Una regla más estricta puede bloquear una corrida previamente aceptada como evidencia analítica.

## 28. Convergencia de colas

El resumen fija tail_convergence_certified=false y explica MEAN_ONLY_NOT_P80_P90_P95_OR_TAIL_CERTIFICATION. Un P90 visible no se presenta como certificado por la estabilidad de la media. La exigencia de convergencia de cola no liberada se rechaza.

## 29. Contrato de resumen QRA

El contrato incluye proveedor y versión, tipo, proyecto, corrida, modelo, método, revisión de aceptación, hashes, readiness, convergencia, percentiles seleccionados, probabilidades, alcance, moneda o unidad y fecha. El whitelist excluye histogramas, CDF, sensibilidad, runtime detallado y muestras.

## 30. Filas de evidencia Gate

La matriz muestra filas separadas de Cost y Schedule, clase, razón contextual, accepted, current, readiness, convergencia, alcance y advertencias. View QRA usa la ruta existente y una referencia exacta cuando el visor recibe proyecto y corrida. No existe botón Simulate en Gate.

## 31. Contrato congelado

El paquete captura política y hash, determinación, clase, versión del proveedor, tipo, run hash, model hash, acceptance hash, metodología y resumen seleccionado. Los datos se incluyen en los JSON existentes. La identidad de la evidencia y de la exigencia quedan trazables por separado.

Para consistencia BC no QRA, project_source_reference de FEL conserva project_workspace_id, status_id, status_revision, definition_source_hash y definition_readiness_hash. project_source_references de Risk conserva por proyecto assessment_id, assessment_hash, risk_readiness_hash, source_current y readiness_status. Gate registra la base de comparación hash_basis, la identidad nativa y provider_evidence_hash. Una referencia confiable ausente o duplicada permanece SOURCE_MISSING o MISMATCH; no se busca otra fuente para evitar el bloqueo.

## 32. Cambios posteriores al freeze

El historial FROZEN no vuelve a consultar QRA para su representación. Una preparación activa detecta supersession y stale mediante lecturas. Aceptar una corrida B no reescribe el paquete que capturó A. La actualización explícita conserva el procedimiento normal de control de cambios.

## 33. Integración de criterios

Los criterios EVID2 consumen el resumen QRA y los operadores controlados existentes. Preview reutiliza el evaluador para mostrar el impacto de los criterios QRA obligatorios sin persistir ni simular. Una fila QRA no requerida deja su criterio contextual no aplicable; una condición no evaluable permanece bloqueante. El resultado formal sigue perteneciendo a Gate07K.

## 34. Criterios de probabilidad

Se consume probability_meeting_target_amount o probability_meeting_target_date existente. Deben coincidir objetivo capturado, moneda o base temporal y procedencia de la regla. No se interpolan probabilidades a partir de percentiles ni se ejecuta una simulación desde Gate.

## 35. Criterios de percentil

La política selecciona el percentil y un umbral con procedencia gobernada. Antes de publicar se comprueba el contrato de métodos publicados compatibles para todos los percentiles seleccionados, incluso sin criterio numérico. No hay P80 obligatorio universal. Para Schedule se compara completion_date bajo la unidad y el método compatibles.

## 36. Procedencia del objetivo

GATE_CRITERION identifica el umbral de la política publicada. Se congela valor y referencia junto con el resultado. Un target propio de la corrida no se etiqueta como fecha contractual o monto aprobado sin una autoridad de origen que lo respalde.

## 37. Monedas fechas y unidades

La moneda se verifica por igualdad y no se aplica FX. Schedule verifica HOURS o DAYS y NORMALIZED_ELAPSED_TIME_V1. Las fechas y los límites de rango se validan de forma controlada. La incompatibilidad produce NOT_EVALUABLE o bloqueo, nunca una comparación silenciosa. Las comparaciones QRA normalizan únicamente representaciones equivalentes: un número validado como texto conserva el mismo valor y las fechas con Z, +00:00 o un desplazamiento equivalente representan el mismo instante UTC. Esto no convierte días laborales, monedas o unidades, y conserva el valor original y la procedencia en el snapshot.

## 38. Integración Five Case

Cost QRA se incorpora en Economic Case y Financial Case; Schedule QRA en Management Case. Las filas son referencias analíticas compactas. FIN conserva sus métricas y reconciliación deterministas. La síntesis no se convierte en un tablero de simulación.

## 39. Bundle de Business Case

Las claves cost_qra_result y schedule_qra_result capturan las fuentes mediante la misma política y provider usados por Gate. El portafolio objetivo de la propuesta se verifica mediante la membresía N M vigente; no se altera el padre empresarial. _qra_evidence congela política, contexto de membresía y exigencias. Una ambigüedad material requiere contexto explícito; sin QRA aplicable se conserva el flujo previo.

Las claves FEL y Risk de BC siguen conservando sus registros y hashes nativos por proyecto. Se reutilizan para comparar las referencias capturadas del proveedor Gate en la misma capa. No se modifica el bundle de una revisión COMPLETED para corregir una discrepancia ni se toma una nueva lectura viva al comparar el paquete histórico.

## 40. Inmutabilidad de Business Case

Las filas QRA solo aparecen en revisiones que capturaron el marcador. Las revisiones antiguas no reciben filas vacías nuevas que alteren five_case_hash. Cuando QRA cambia después de COMPLETED, el refresh existente crea un sucesor DRAFT; no corrige el registro completado.

## 41. Consistencia entre Business Case y Gate

bc_consistency_required permite exigir que el hash QRA de BC coincida con el resumen Gate. La comparación usa CROSS_SOURCE_MISMATCH existente. Una regla sin esa exigencia no inventa una obligación adicional. La consistencia es por tipo y hash de la evidencia aceptada.

La prueba de navegador con criterio numérico obligatorio detectó además una comparación previa entre capas distintas: BC conserva el hash nativo FEL por proyecto y el hash Risk por proyecto, mientras Gate conservaba el hash envolvente Definition Readiness y el agregado Risk PROJECT_SET. El contrato se amplió de forma aditiva para capturar proyecto, registro y hash nativos desde la misma lectura del proveedor. La comparación usa esas referencias solo para filas persistidas GOVERNED_SOURCE, retiene los hashes envolventes para auditoría y no vuelve a consultar ni recalcular fuentes. Los controles de identidad, proyecto, duplicados y origen impiden que un payload manual simule procedencia. La ruta legacy sin contrato nativo conserva su comparación previa.

## 42. Límite FIN y Business Case

No se convierte FIN en probabilístico ni se sustituyen NPV IRR o funding reconciliation. La actualización QRA solo cambia las referencias en un nuevo Business Case. Los cambios materiales de las fuentes FIN o de costo continúan activando currentness normal del motor.

## 43. Consumo por Gate07K

Gate07K conserva el paquete Gate congelado como fuente de decisión. No reejecuta QRA, no consulta simulaciones brutas y no aplica reglas nuevas a un paquete anterior. La disponibilidad de evidencia autoriza continuar el proceso, no determina el resultado de inversión.

## 44. Compatibilidad del FID histórico

El baseline operacional no contiene decisiones FID ni paquetes congelados históricos. Por ello la conservación del historial debe comprobarse en fixtures aislados con registros reales del flujo anterior. La ausencia de filas operacionales no se presenta como una prueba histórica positiva.

## 45. Regresión Gate07L

No se añade una autoridad post FID ni una obligación retroactiva. La elegibilidad capturada mantiene su hash y filas originales en los ensayos históricos. El acceso a ejecución sigue regido por el proceso existente de inicialización y activación.

## 46. Diseño ADMIN

La edición QRA se integra en Evidence Policy. Solo una revisión DRAFT permite cambiar análisis, ámbito, clase, convergencia, readiness, alcance, vigencia y criterios. History muestra revisión, fechas y hash; Preview distingue exigencia, capacidad y disponibilidad. No se crean controles de ejecución.

## 47. Diseño USER Gate

La preparación incorpora un componente compacto común. Las fuentes se abren desde View QRA y el enlace respeta las autorizaciones del visor. Se conserva la actualización y el freeze del módulo. La interfaz no permite modificar política ni sustituir manualmente Class A.

## 48. Diseño USER Business Case

Business Case muestra resumen de Cost y Schedule desde su bundle congelado. El refresh normal conserva su autoridad y genera un sucesor. El componente usa valores devueltos por backend; no obtiene histogramas ni calcula resultados en el navegador.

La tabla de las nuevas filas QRA proyecta número de corrida, versión de modelo, hash congelado, readiness, currentness y fecha a partir de los campos reales de la matriz y su resumen. Evita mostrar NOT_AVAILABLE por una diferencia de alias. La corrección está acotada a QRA; el contrato visual genérico de las demás fuentes legacy se conserva.

Las capturas BC nuevas conservan además la clasificación de la exigencia y la aplicabilidad con compatibilidad de motor devuelta por el proveedor resuelto. No sustituyen esa compatibilidad por el estado NOT_EVALUATED de la regla previa a resolver. El marcador mantiene separada la política configurada; una revisión COMPLETED anterior conserva exactamente sus metadatos, aunque no haya capturado estos campos.

## 49. Roles y permisos

Se reutilizan permisos de Evidence Policy, Gate y Business Case. No se añaden roles globales. Las lecturas se limitan a tenant y proyecto. El acceso directo al motor sigue requiriendo los permisos existentes de QRA; disponer de un enlace no otorga permiso.

## 50. Separación de funciones

Se respeta author_must_differ_from_publisher cuando se configura en la política. El ejecutor QRA no adquiere autoridad para cambiar la regla Gate. El preparador no puede eludir Class A y la aceptación de resultados conserva independencia respecto de creador y ejecutor.

## 51. Control de versión

Los DRAFT conservan ETag e If Match y responden 412 cuando la versión no coincide. Las políticas publicadas permanecen inmutables. La interfaz utiliza los contratos existentes y no escribe directamente sobre un snapshot.

## 52. Idempotencia

Clone admite una clave Idempotency Key, ligada al actor, fuente y versión. El replay conserva la revisión creada. Publish mantiene su operación versionada e idempotencia previa; Gate refresh y freeze conservan sus receipts. Una clave no se reutiliza para una petición distinta.

## 53. Auditoría

SecurityEvent registra clonación, edición y publicación con procedencia. Los ensayos verifican preview sin persistencia y sin eventos añadidos. Un cálculo QRA no aparece como efecto de resolver evidencia. La información de auditoría no sustituye el hash de los snapshots.

## 54. Decisión de persistencia

No hay migración nueva. Los campos JSON existentes representan configuración, calificadores, snapshots y fuentes. El Alembic head operacional permanece en 0068. La base del navegador aislado también confirmó 20261011_0068 y los dos triggers existentes de QraRun y QraRunReview. La ampliación es aditiva en los contratos y no agrega columnas ni modifica esos triggers. Las pruebas puras y SQLite no se presentan como verificación de dichos triggers PostgreSQL.

Definition Readiness y Risk Evidence exponen referencias nativas opcionales en sus DTO y capturas JSON existentes, sin nuevas tablas ni autoridad. FEL usa el ProjectFELStatus ya leído; Risk usa project_readiness del agregado ya construido. La extensión no recalcula Risk ni altera el hash histórico del envolvente.

Para preservar el contrato material anterior, Basic Data excluye solamente el nuevo campo de transporte project_source_reference de su proyección FEL v1 utilizada por Owner Capability y QRA Foundation. Identidad, revisión, readiness y hashes originales siguen presentes. El control de stale permanece activo frente a cambios reales y no invalida una fuente idéntica por una ampliación aditiva del DTO.

## 55. Reutilización del registry

El registry contiene un QRA_RESULT_PROVIDER con analysis_types y compatible_evidence_types. La versión de resumen expone el contrato ampliado sin registrar providers Cost o Schedule independientes. Se mantiene la compatibilidad del adaptador genérico anterior.

## 56. API

Se amplían los endpoints existentes de Evidence Policy para JSON DRAFT y clone, y los contratos de Gate para qra_summary y qra_applicability. Business Case emplea source bundle y refresh normales. No se crea endpoint simulate ni una mutación especial de BC QRA.

## 57. Navegación

Se conserva strategicNavigationBlueprint y qra run overview. Las referencias exactas permiten abrir una corrida ajena a la primera página sin elegir otra por fallback. El par proyecto corrida se verifica contra la respuesta autorizada. No se expande App.tsx.

La automatización CI incorpora dos jobs aislados, PostgreSQL y Chromium, con la misma pila docker-compose.qra-evidence.yml. El smoke general no ejecuta esos escenarios contra el puerto operacional; tampoco repite el escenario Wave4 ya separado. La comprobación del head existente se alinea con 0068. Se validaron localmente el YAML y la configuración Compose; no se ejecutó ni se acredita aquí una corrida remota de GitHub Actions.

## 58. Flujo PostgreSQL de costo

El flujo real aislado aprobó los cuatro casos de test_qra_evidence_stack. La última ejecución creó fuentes y corridas nuevas mediante el flujo real, sin reutilizar el proyecto de la prueba anterior, y aprobó los cuatro casos en 729,401 segundos según JUnit. En PostgreSQL qra_evidence, el proyecto 7 usa la política 57 revisión 7, Cost run 6 y Schedule run 7, calculados por el kernel y aceptados mediante revisión independiente. Clone, configuración contextual, preview, publish, Business Case sucesor y freeze completaron el proceso. El preview registró persisted=false y cero instrucciones DML; el número de corridas permaneció 7 antes y después de consumir evidencia.

La evidencia reproducible está en outputs/.qa/qra-evidence/actual-stack-fresh-release-20261013.xml y su JSON asociado. Los identificadores pertenecen exclusivamente a la base aislada, no a proyectos operacionales. La fixture reutiliza los procesos reales anteriores; su política Five Case se adapta, solo en esa base, a las fuentes efectivamente disponibles y no acredita toda la configuración empresarial predeterminada. La equivalencia numérica y UTC está cubierta adicionalmente por los 109 casos del suplemento UTC y las matrices posteriores de cierre.

Durante la preparación de las fixtures se inyecta el despacho del broker y se ejecutan el servicio worker_execute y el kernel real. Los resultados, fuentes, aceptación, permisos y persistencia son reales; la entrega asíncrona por Celery no se vuelve a validar en este incremento de consumo de evidencia. Gate y Business Case no llaman al worker ni crean corridas.

## 59. Flujo PostgreSQL de plazo

La misma prueba aprobada usa ScheduleImport no iniciado y tiempo transcurrido explícito. La corrida 7 proviene del kernel real y revisión independiente, no de JSON fabricado. El paquete capturó SCHEDULE_QRA con sus límites de calendario y semántica temporal. Ni la resolución ni el freeze ejecutaron un cálculo nuevo o actualizaron P6.

## 60. Selección de bajo riesgo

Los tests de aplicabilidad mantienen no requerida la evidencia fuera de la banda de valor o del contexto configurado. INV SELECT puede continuar sin QRA ausente cuando su clase efectiva es C. Se conserva la diferencia entre ausencia de obligación y provider no disponible.

## 61. Contexto Schedule no soportado

Los tests negativos reconocen avance, remanentes o calendarios incompatibles. La fila obligatoria nunca queda SATISFIED por un resultado de otro tipo ni por una conversión implícita. La salida muestra ENGINE_CAPABILITY_NOT_SUPPORTED y exige resolver la limitación por un incremento autorizado futuro.

## 62. Regla integrada negativa

La validación de política rechaza análisis integrado. La interfaz y la ruta directa se prueban con la misma restricción. No se utiliza un par de resultados separados como autoridad integrada.

## 63. Resultado no aceptado

La selección consulta QraRunReview ACCEPTED y QraRun COMPLETED. Una corrida sin aceptación no satisface la regla, aunque sus números estén completos. La prueba de proveedor mantiene explícito QRA_ACCEPTED_RESULT_REQUIRED.

## 64. Resultado obsoleto

La política consume source_current del proveedor. El resultado aceptado conserva identidad y aceptación para diagnóstico, pero SOURCE_STALE impide satisfacer Class A. La prueba comprueba que el snapshot histórico permanece ligado al hash previo.

## 65. Análisis equivocado

La regla de plazo pasa SCHEDULE_QRA al selector. La prueba no permite resolver Cost por una fila genérica. Una discrepancia de analysis_type provoca QRA_ANALYSIS_TYPE_MISMATCH o ausencia de evidencia calificada.

## 66. Alcance insuficiente

El selector WHOLE_PROJECT evita cargar como vigente una corrida parcial. QRA_SCOPE_MISMATCH distingue ese caso de inexistencia general de resultado. PARTIAL_ALLOWED es una autorización explícita y mantiene el alcance capturado.

## 67. Advertencia de convergencia

WARNING_ALLOWED conserva NOT_CONVERGED y READY_WITH_WARNINGS en el resumen. La prueba verifica calidad separada de aceptación. Las limitaciones de colas permanecen visibles incluso si la media converge.

## 68. Convergencia exigida

REQUIRED bloquea NOT_CONVERGED con QRA_CONVERGENCE_REQUIRED. El sistema no busca una corrida antigua para sustituir una sucesora vigente. El criterio no simula ni altera iteraciones para satisfacer la regla.

## 69. Disposición sobre colas

Los tests comprueban tail_convergence_certified=false y rechazan tail_convergence_required. P90 puede mostrarse como estimación con la advertencia explícita, pero no se certifica como cola convergente.

## 70. Flujo Business Case

Las cinco pruebas enfocadas de integración BC y las nueve pruebas Five Case anteriores aprobaron. Verifican Cost en Economic y Financial y Schedule en Management mediante el mismo proveedor, así como el contexto de portafolio de la propuesta y la ausencia de filas nuevas en históricos. El flujo PostgreSQL completó el sucesor BC 13 usando el refresh existente y sus autoridades normales de revisión, mantuvo FIN determinista y comprobó los hashes capturados.

## 71. Inmutabilidad BC

La prueba de proyección compara dos lecturas de una revisión histórica sin realizar una consulta vigente. La incorporación nueva no cambia sus filas ni five_case_hash. Un resultado posterior debe capturarse en un nuevo DRAFT, nunca editar COMPLETED.

## 72. Desalineación BC

Cuando bc_consistency_required es true y BC referencia A mientras Gate resuelve B, CROSS_SOURCE_MISMATCH bloquea el paquete. Si la política no exige esa alineación, no se agrega una autoridad más estricta de forma implícita.

## 73. Inmutabilidad del freeze

El ensayo PostgreSQL aprobado captura la corrida A, acepta B y vuelve a leer el histórico. El paquete y el hash almacenados permanecieron iguales. Una preparación nueva resolvió B sin alterar A. El caso de cambio material bloqueó una preparación nueva y conservó el paquete anterior; no se corrigieron números ni resultados para obtener ese comportamiento.

## 74. FID futuro

Class A QRA condiciona readiness del paquete previo a decidir. La evidencia válida permitió el proceso normal; evidencia ausente u obsoleta lo bloqueó. La última ejecución aprobada congeló la preparación 8 y creó la decisión 6, is_fid=true, mediante el actor independiente autorizado y con authorized_amount y moneda explícitos. La decisión conserva su catálogo GO HOLD RECYCLE KILL y no es generada por QRA. Su hash y el hash del paquete están registrados en el JSON de la prueba.

## 75. Regresión de FID histórico

La fixture creó decisiones anteriores antes de publicar QRA y conservó hashes y filas completos. El baseline de la última ejecución aislada contiene cinco preparaciones congeladas, cuatro decisiones, tres elegibilidades Gate07L y once revisiones BC completadas, incluidas las de ensayos previos. Las comparaciones posteriores aprobaron sobre registros almacenados, no sobre readiness recalculada. El entorno operacional carece de estos registros y no se utiliza para afirmar una prueba histórica que no existe allí.

## 76. Contractor y Direct

Los filtros CAPITAL_OWNER dejan estos modelos fuera por defecto. Las pruebas verifican clase efectiva C y ausencia de bloqueo QRA. Optar explícitamente por una nueva política sigue requiriendo capacidad y evidencia compatible.

## 77. Proyecto canónico 14

Las lecturas operacionales de baseline, del 13 de octubre y la comprobación final del 14 de octubre conservan el MD5 de fila del workspace de proyecto 14, ef67b78a4d4902d2dc6db3efb017b80b. No se utiliza este proyecto como fixture ni se le publica una política. También permanecen iguales los hashes de las cinco políticas Evidence publicadas, la metodología 866 sigue DRAFT y existen cero corridas QRA operacionales. Se mantiene Alembic 20261011_0068 sin ejecutar una migración operacional. Las comprobaciones constan en local-preservation-readonly-20261013.json y release-closeout-manifest-20261014.json. Frontend responde HTTP 200 en localhost 5173 y la API responde HTTP 200 en su ruta /api/v1/health/ready; los seis servicios principales permanecen activos.

## 78. Moneda múltiple

Los tests negativos verifican moneda distinta en rango y criterio. La respuesta no aplica tipo de cambio ni considera comparable un objetivo USD con resultado de otra moneda. Si se necesita normalización futura, deberá provenir de autoridad gobernada adicional.

## 79. Unidades y fechas Schedule

La compatibilidad exige unidad y método explícitos. Las fechas de percentil se utilizan bajo el método transcurrido capturado. Los rangos de fechas invertidos son inválidos; los días laborales no se comparan silenciosamente con DAYS transcurridos.

## 80. Navegador ADMIN

El escenario ADMIN aprobó en 60,289 segundos sobre frontend 5533, API 8830 y PostgreSQL qra_evidence_browser aislados. La interfaz permitió clone, alternar clases A B C, alcance y convergencia, guardar y comprobar la política persistida, preview persisted=false y publicación de una revisión nueva. El criterio P90 obligatorio quedó SATISFIED en el preview. TARGET_PROBABILITY se editó de forma transitoria y se restauró P90 antes de guardar; este escenario no acredita un objetivo probabilístico gobernado persistido. Las validaciones backend cubren sus comparaciones. El rechazo de configuración integrada se comprobó por ruta directa en el escenario de seguridad, no como publicación integrada observada.

La ejecución completa del 14 de octubre aprobó cuatro escenarios Chromium, cero fallas, errores u omisiones: 306,418 segundos de suite y 324,891 segundos totales del ejecutor. JUnit, cinco capturas y cuatro traces están en browser-release-closeout-20261014. La fixture produjo Cost run 1 y Schedule run 2 mediante kernel y servicio worker reales, con despacho del broker omitido durante setup. No hay interceptación de respuestas QRA por page route ni simulación desde los consumidores.

## 81. Navegador USER Gate

El escenario USER Gate aprobó en 72,926 segundos. Verificó filas Cost y Schedule separadas, Class A, aceptación, vigencia, alcance, capacidad, percentiles y advertencias capturadas. Ambos enlaces View QRA abrieron pestañas reales del proyecto y corrida exactos. La ruta manual Class A devolvió 409 MANUAL_REFERENCE_NOT_ALLOWED; el botón Simulate no existe en el consumidor. El autor ejecutó Ready for review y un revisor independiente ejecutó Freeze package por interfaz. La respuesta del servicio fue FROZEN y las lecturas posteriores conservaron su hash; el paquete excluye histogramas, CDF y sensibilidad. La captura inmediata conserva transitoriamente READY_FOR_REVIEW por el refresco asíncrono. Una verificación suplementaria de solo lectura confirmó visualmente FROZEN, versión 11 y Freeze deshabilitado, con el mismo hash de la preparación 2 antes y después. No repitió mutaciones; su prueba está en browser-frozen-readonly-proof-20261014.json.

La preparación de referencias Class B se hizo con las API normales de autor y revisor antes de entrar al escenario Gate. No se forzó READY ni FROZEN, no se modificaron permisos y se conservaron los plazos originales de prueba. Gate solo resuelve evidencia de corridas previamente calculadas.

## 82. Navegador USER Business Case

El escenario Business Case aprobó en 157,969 segundos, incluida la preparación autorizada del siguiente escenario. Preview y refresh normales crearon un sucesor DRAFT. Cost quedó referenciado en Economic y Financial y Schedule en Management; las tres referencias muestran Class A, capacidad y aceptación vigente. La tabla Sources and Evidence usa los identificadores y hashes reales capturados. Los dos tipos de enlace View QRA se abrieron y verificaron en pestañas reales. Submit y la revisión independiente completaron el sucesor sin alterar los hashes de revisiones anteriores. No se recalcula FIN ni QRA y no se reescribe una revisión COMPLETED.

## 83. Seguridad por ruta directa

El escenario de seguridad aprobó en 15,234 segundos. USER sin edición ADMIN recibió 403 y no vio la región administrativa; un proyecto incorrecto recibió 403 o 404 mientras el proyecto autorizado devolvió AVAILABLE. El PUT de un DRAFT con análisis integrado devolvió 422. La publicación por el mismo autor, con separación de funciones exigida, devolvió 403 POLICY_AUTHOR_PUBLISHER_SOD_VIOLATION y conservó versión, estado DRAFT y hash. Las preparaciones histórica y recién congelada conservaron sus hashes al volver a leerlas.

Estas son las comprobaciones efectivamente ejecutadas en navegador. El aislamiento entre tenants y otras matrices negativas se validaron en backend, no se atribuyen a Chromium. El rechazo de Integrated observado es validación de DRAFT; no se afirma que el navegador haya intentado publicar esa configuración inválida. El visor QRA verifica además su propia autorización al abrir el enlace exacto.

## 84. Observación de rendimiento

La resolución no llama calculate ni worker_execute. La última ejecución PostgreSQL midió 8540,695 ms para el preview contextual del caso integrado y registró cero DML; la anterior, con fixture reutilizada, midió 8461,629 ms. Son observaciones en una máquina compartida y fixtures concretas, no un benchmark ni un SLA. El contador antes y después del consumo de evidencia, 7 a 7, prueba que ese consumo no simula de nuevo; el caso posterior de supersession sí crea deliberadamente una corrida sucesora.

El resumen excluye histogramas, CDF, sensibilidad, runtime detallado y muestras. El selector y supersession proyectan el pequeño análisis de alcance en lugar de cargar todos los manifiestos sucesores. El chequeo de integridad de la corrida seleccionada conserva lectura completa de su resultado; no se afirma eliminación de todo costo de currentness ni escalabilidad ya validada para modelos grandes.

Los reintentos de Chromium sobre una base con múltiples preparaciones activas mostraron lecturas de overview de decenas de segundos. Es una observación del entorno local compartido, no un SLA ni una medición aislada de QRA. El harnés conserva los límites de 300 y 180 segundos: prepara Class B mediante API autorizada al terminar BC y verifica View QRA en pestañas reales sin recargar el overview de origen. No fuerza readiness ni omite la revisión independiente. Queda pendiente perfilar el overview y su crecimiento con más preparaciones; el perfilador opt in de 5000 y 10000 fuentes no se ejecutó.

## 85. Regresión estratégica

La matriz backend incluye Engine, Foundation, EVID, EVID2, Gate07K, Gate07L, BC Five Case, FIN, Budget, Funding, Risk, Basic Data, Owner Capability, Portfolio Review y Capital Allocation. La ejecución amplia registró 535 casos; dos fallas se corrigieron y se verificaron en un suplemento de 100 casos, todos aprobados. Uno era un stub EVID2 sin published_at; el otro requería conservar la procedencia de portafolio en una salida contextual no obligatoria. La revisión de comparables numéricos y UTC añadió nueve casos; el suplemento UTC de 109 casos también aprobó, en 238,557 segundos.

Los suplementos de cierre aprobaron 154 casos de procedencia en 1270,458 segundos, 204 casos de compatibilidad material en 519,741 segundos y 14 casos BC y Five Case sobre la captura final de metadatos en 31,083 segundos. La matriz incluye identidades y proyectos distintos, referencias duplicadas, origen manual falso y conservación del contrato material v1, así como controles reales de stale, permisos, historial y cero escrituras de preview.

El cierre de clone aprobó otros 133 casos en 194,951 segundos, incluidos cuatro casos nuevos que verifican 80 clones y 80 replays entre SQLite y PostgreSQL: nombres Unicode de 180 caracteres, veinte sucesores por caso y auditoría completa de fuente. Se conserva name, content, hash y revisión de la fuente; la publicación del sucesor puede cambiar legítimamente su status a SUPERSEDED e incrementar su versión. La primera ejecución conservada tiene cuatro fallas por una assertion de prueba que ignoraba esa transición; se corrigió la expectativa, no el lifecycle ni la inmutabilidad del contenido, y la última ejecución aprobó sin fallas.

Al deduplicar siete artefactos por clase y nombre parametrizado, con precedencia de la ejecución final, quedan 583 casos únicos: 582 PASS, cero FAIL, cero ERROR y un SKIP correspondiente al perfilador Foundation de 5000 y 10000 filas, opcional por opt in. El JSON backend-deduplicated-release-20261013.json conserva fuentes, SHA256, conteos y motivo. El inventario añade 30 aprobaciones frente al cierre UTC previo de 552 PASS y un SKIP; no suma reruns como casos nuevos. Las pruebas combinan PostgreSQL, pruebas puras y SQLite en memoria; no se describen todas como pruebas de persistencia PostgreSQL. Los cuatro casos de flujo real se informan por separado. Su fixture exige la base PostgreSQL desechable explícita; el smoke SQLite general no ejecuta ese flujo especializado.

La ejecución frontend amplia registró 437 casos en 78 archivos, con 435 PASS y dos fallas. La etiqueta histórica de un breadcrumb se alineó con el blueprint vigente. La otra prueba, AppFlow de navegación, excedía 420 segundos por calcular repetidamente nombres accesibles de todos los botones del árbol lateral. Se acotaron únicamente sus búsquedas positivas a la rama pertinente, conservando getByRole, el nombre, la visibilidad predeterminada, las comprobaciones negativas y el mismo timeout; no se cambió App.tsx. La prueba exacta de la versión final aprobó en 147,156 segundos.

Las nueve suites frontend enfocadas aprobaron sus 58 casos. El inventario con precedencia final registra 438 casos ejecutados únicos, todos PASS, sin fallas pendientes; no se afirma una única ejecución global limpia posterior. Los skipped de reruns filtrados no se cuentan como casos nuevos ni como cobertura omitida. frontend-case-inventory-final-20261013.json registra las fuentes y la reconciliación.

Ruff check aprobó y Ruff format verificó 441 archivos backend. TypeScript global aprobó sobre la versión final, incluidas las proyecciones QRA de BC. ESLint final terminó con cero errores y nueve advertencias BIM preexistentes, dentro del límite CI de diez; no hay advertencias nuevas en QRA o BC. Prettier aprobó todo src y la prueba AppFlow modificada; el spec de navegador también está formateado. frontend-static-validation-final-20261013.json conserva comandos, códigos de salida y hashes de fuentes. Los logs de pruebas conservan advertencias previas de React act y React Router; PASS no significa ejecución sin advertencias.

No se presenta ejecución local como CI remoto aprobado. El resultado de Chromium se informa en las secciones de navegador, separado de la regresión de componentes.

## 86. Deuda técnica

Permanece el análisis integrado, progreso real, remanentes, calendarios P6, convergencia de colas, criticality, eventos Risk automáticos y escalabilidad de modelos grandes. La fixture FFA heredada requiere adaptar su política Five Case a fuentes reales disponibles; esa adaptación no acredita toda la configuración predeterminada actual.

## 87. Brechas estratégicas finales

La implementación cierra el vínculo de evidencia contextual, pero el cierre estratégico requiere UAT con personas autorizadas y configuración empresarial representativa. No se automatiza ese juicio. Los límites avanzados QRA están identificados y separados de la autoridad de decisión existente.

## 88. Estado de release

QRA_RESULT_EVIDENCE_POLICY_INTEGRATION_RELEASE_VALIDATED. La integración queda validada localmente dentro del alcance descrito: 582 PASS backend y un perfilador opcional SKIP, 438 PASS frontend por inventario reconciliado, cuatro PASS de flujo PostgreSQL y cuatro PASS Chromium en una ejecución completa del 14 de octubre. Se verificaron formato, tipos, lint y preservación operacional. El informe Word se entrega después de renderizar y revisar todas sus páginas y auditar accesibilidad. No se atribuye a este cierre un CI remoto aprobado ni aceptación empresarial UAT.

La salida técnica es READY_FOR_CONTEXTUAL_QRA_EVIDENCE_IN_INVESTMENT_DECISIONS. El código está guardado localmente y disponible en localhost; no se han publicado políticas QRA operacionales ni ejecutado commit o push del agente. QRA sigue siendo evidencia de entrada, sin decisión FID automática, aprobación de contingencia, actualización presupuestal o cambio de cronograma. La pila QA temporal se detiene después de conservar sus evidencias; los servicios principales permanecen activos.

## 89. Recomendación del siguiente incremento

| Alternativa | Objetivo | Límite del incremento |
| --- | --- | --- |
| A Strategic Final UAT | Aceptación empresarial del flujo estratégico | Roles reglas datos y cierre de release |
| B Advanced QRA | Ampliar capacidad analítica y rendimiento | Integrado avance calendarios colas y eventos |

Recomendamos exactamente A Strategic Macroprocess Final UAT and Release Closeout. El vínculo de evidencia queda implementado y validado localmente, pero su adopción requiere verificar el flujo empresarial completo con personas autorizadas, políticas y datos representativos. B amplía matemática y rendimiento, pero no sustituye esa aceptación de gobernanza. No iniciamos ninguna de las dos alternativas automáticamente ni los procesos operacionales excluidos.
