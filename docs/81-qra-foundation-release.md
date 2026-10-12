# Informe técnico QRA Foundation

P&Pmis Construction AI · Capital Portfolio and Investment Governance · 2026-10-11

**Estado actual:** QRA_SOURCE_READINESS_AND_METHODOLOGY_FOUNDATION_RELEASE_VALIDATED

## 1. Resumen ejecutivo

Se incorpora preparación gobernada para QRA: Cost Source Readiness, Schedule Source Readiness, metodología configurable y QraModelDefinition. La definición aprobada es una entrada preparada para un motor futuro; no constituye un análisis probabilístico realizado, contingencia aprobada ni simulación disponible.

La implementación reutiliza la plataforma existente y conserva sus autoridades. ADMIN configura metodología; USER prepara fuentes y modelos en proyectos autorizados. Se añaden historial inmutable, vigencia, revisión independiente, API protegida y navegación canónica. Los resultados de validación se detallan en las secciones de pruebas y cierre; no se confunde código escrito con release validado.

## 2. Baseline real del repositorio

Baseline de implementación observado el 9 de octubre: rama main, HEAD 9cb0969abb5d48cc25b0c6a935b11e6bd7afd16f y head Alembic 20261008_0066. Existían 76 archivos modificados rastreados, 7.604 inserciones y 949 eliminaciones, además de incrementos previos no rastreados. Este trabajo se preservó.

La reanudación del 11 de octubre parte de main d762d873fe2282a8dfe790bacc3b2450691abe83, con árbol rastreado limpio y los desarrollos anteriores ya enviados a origin. La cabeza única del código es 20261009_0067. La API operativa inicial todavía contiene 0066 y no tiene el módulo QRA; no se confunde esa imagen previa con el entorno de aceptación del nuevo código. Las correcciones de esta reanudación permanecen como cambios locales hasta un nuevo commit autorizado. No se ejecutan reset ni checkout destructivos.

El servicio local previo usaba la imagen validada de Wave 3B. El respaldo histórico del 9 de octubre se preserva. En esta reanudación se creó un respaldo PostgreSQL nuevo en formato custom de 1.979.037 bytes: pg_restore --list leyó 3.520 entradas y su SHA-256 es 4602B0FAB97707C11D80AD544CC3C7237298681210CC7363468910A5F7BA93A7. Se capturaron conteos y hashes de 35 categorías de datos y seguridad antes de la actualización. Un respaldo legible no equivale a una prueba completa de restauración.

## 3. ADR QRA Foundation

La ADR 80 establece una separación explícita entre definición de fuentes/modelo y futura ejecución. Se crea el módulo backend qra_foundation, con adaptadores de lectura y tres agregados versionados. AdminConfiguration, secuencias, SecurityEvent, permisos y navegación siguen siendo servicios comunes reutilizados.

La columna adicional ScheduleImport.source_metadata conserva evidencia cruda de nuevas importaciones. No se reconstruyen datos ausentes en historia. Los snapshots completados y aprobados no se sobrescriben; la vigencia se calcula como proyección. El motor probabilístico queda fuera del incremento.

## 4. Posición en la arquitectura objetivo

QRA Foundation está después de las fuentes y sus políticas de gobierno, y antes del motor QRA. Los consumidores leen evidencias gobernadas por proyecto. El punto de entrada USER está en Enterprise Strategy Manager, Business Case & Investment Development; ADMIN se integra en su configuración de definición e inversión.

El módulo no sustituye Project Definition, Risk Governance, Basic Data, Owner Capability, FIN ni Budget. Su salida derivada READY_FOR_QRA_ANALYSIS significa definición técnicamente preparada. Una eventual integración Gate utilizará un requisito configurado en otro incremento, no una nueva restricción automática.

## 5. Matriz de autoridad del dominio

| Dominio | Autoridad conservada | Uso en Foundation |
| --- | --- | --- |
| FEL y PDRI | Project Definition | Contexto y evidencia actual de definición |
| Risk y Risk Governance | Módulos de riesgos | Lectura de readiness y política publicada |
| Basic Data y Owner | Evaluaciones gobernadas existentes | Prerrequisitos configurables y hashes |
| FIN y Budget | Modelos financieros y escenarios | Contexto o fuente identificada sin recalcular |
| Cronograma | ScheduleImport y mapas canónicos | Fuente manual y metadatos crudos |
| Gate y FID | Investment Gate y Decision | Sin nuevas decisiones ni cambios históricos |
| QRA Foundation | Nuevo módulo acotado | Preparación de fuentes y definición de modelo |

## 6. Reutilizar antes de crear

Se reutilizan EnterpriseWorkspace PROJECT, el enlace explícito a Project operativo, AdminConfiguration, AdminNumberSequence, SecurityEvent, RBAC, infraestructura de ETag y contratos de configuración. ScheduleImport, ScheduleActivityMap, ActivityRelationship, Activity, WBS y BaselineVersion permanecen como autoridad de cronograma.

Se crean sólo qra_cost_source_assessments, qra_schedule_source_assessments, qra_model_definitions y qra_commands. No se crea una base paralela de cronograma, una tabla QraRun ni otra jerarquía de proyectos. En frontend se reutiliza GovernedPolicyEditor y el outlet estratégico; App.tsx no se amplía.

## 7. Matriz de prerrequisitos Wave 3B

| Prerrequisito | Fuente real | Uso y condición |
| --- | --- | --- |
| FEL PDRI | Assessment completado y etapa FEL | Hash y vigencia actuales |
| Riesgos | Risk Readiness | Evidencia gobernada disponible |
| Política de riesgos | Risk Governance | Perfil publicado aplicable |
| Datos básicos | Basic Data Readiness | Evaluación completada y actual |
| Capacidad del propietario | Owner Capability | Evaluación READY actual |
| FIN Budget Resources | Autoridades existentes | Sólo si el perfil los exige |

La fixture de integración prepara los cinco primeros mediante sus servicios reales, no mediante flags AVAILABLE fabricados. El bootstrap local crea únicamente una metodología neutral DRAFT; no genera evaluaciones QRA ni presume preparación de los proyectos existentes.

## 8. Definición Cost Source Readiness

Evalúa si una fuente de costo identificada tiene base suficiente para definir incertidumbre. Considera referencia, versión, hash, moneda, fecha base, BoE, estructura, cantidades, tasas, supuestos, exclusiones y alcance. Tener un importe o una línea de presupuesto no basta para declarar preparación.

Los adaptadores distinguen FIN_CAPEX, Business Case, Portfolio Budget, Control Accounts, Schedule Cost y referencia externa. La granularidad real se conserva. Business Case sin población de estimación no se convierte artificialmente en una fuente detallada; Control Accounts informa su carácter de contexto de control.

## 9. Requisitos y dimensiones de costo

Las dimensiones, requisitos, criticidad, evidencia mínima y calidad se configuran en el perfil publicado. El ejemplo minero exige diez campos: identidad, cobertura, moneda, fecha, estimate basis, contingency basis, quantity basis, rate basis, assumptions y exclusions. Es un ejemplo de pruebas, no una regla universal publicada para todos los tenants.

La evaluación cuenta requisitos satisfechos, parciales y faltantes; los bloqueos explícitos no se ocultan mediante una media. Se rechazan moneda desconocida o heterogénea, importes no finitos y fechas inválidas. Los resultados conservan explicación, referencias y snapshot de las reglas usadas.

## 10. Reconciliación y tratamiento de contingencia

La reconciliación compara fuentes actuales compatibles y una tolerancia configurada. Sus estados son MATCHED, WITHIN_TOLERANCE, OUT_OF_TOLERANCE y NOT_COMPARABLE. No hay conversión FX, sustitución de presupuesto ni recálculo del modelo financiero.

La base debe indicar BASE_COST, COST_WITH_ESTIMATE_ALLOWANCE u otra base permitida, incluyendo COST_WITH_CONTINGENCY si se autoriza. Una base desconocida bloquea. Documentar contingencia existente no implica calcular una nueva ni management reserve. Si faltan moneda, referencia comparable o información suficiente, se informa NOT_COMPARABLE.

## 11. Agregado de evaluación de costo

CostSourceReadinessAssessment contiene tenant, proyecto canónico, número, versión, predecesor, configuración y hash de metodología, aggregate_json, snapshot_json, hash, actores y fechas de gobierno. El ciclo DRAFT → IN_REVIEW → COMPLETED requiere comandos autorizados y revisión registrada.

COMPLETED congela el resultado aun cuando éste documente bloqueos; el proveedor no lo presenta como READY si no satisface la metodología. Una nueva fuente o revisión de política puede invalidar la proyección actual sin reescribir la evaluación histórica.

## 12. Definición Schedule Source Readiness

Evalúa un cronograma manual importado con identidad, Data Date, calendario, duraciones, estados, lógica, restricciones, alcance y referencias. No comprueba por simulación si una fecha final será alcanzable ni calcula ruta crítica.

La preparación exige campos reales según política. La ausencia de metadatos antiguos es una carencia explícita, no una oportunidad para deducir calendario o duración. Los negativos de fuente se resuelven mediante una importación corregida y un nuevo assessment.

## 13. Reutilización de la autoridad de cronograma

Se leen ScheduleImport, ScheduleActivityMap, ActivityRelationship, Activity, WBS y BaselineVersion del Project operativo enlazado explícitamente al EnterpriseWorkspace PROJECT. Coincidencias de ID o código no se usan como vínculo implícito.

La consulta de opciones y relaciones trabaja por lote. El snapshot identifica la importación seleccionada y su población; una importación posterior hace que la evaluación anterior deje de representar la fuente corriente. Foundation no modifica actividades ni relaciones durante su evaluación.

## 14. Límite P6 XML

Se mantiene importación manual P6 XML/XER. La ampliación captura campos fuente, no integra REST, P6 API ni OPC. MustFinishByDate se elimina como fallback de Data Date: una fecha límite no es fecha de corte.

Se preservan PlannedDuration, RemainingDuration, calendarios, estado, tipo, restricciones, fechas reales y lags crudos. Las unidades XML sólo se consideran conocidas si la fuente las declara. XER conserva campos explícitos en horas. No se infiere jornada de ocho horas ni se expande un calendario para ejecutar CPM. Referencia técnica: documentación oficial Oracle Primavera P6 REST Activity, utilizada únicamente para revisar semántica de campos.

## 15. Identidad y snapshot del cronograma

source_metadata incluye schema_version, imported_source, SHA-256 del archivo, actividades, calendarios y relaciones originales. El hash QRA además recoge material canónico y metadatos usados por las reglas. Cambiar restricciones o unidades altera la identidad material.

Las importaciones previas reciben un objeto vacío en la migración, sin backfill de evidencia. El snapshot conserva source reference, versión, hash, Data Date, alcance y configuración exacta, permitiendo demostrar qué se revisó aunque la fuente activa haya cambiado.

## 16. Dimensiones de preparación de cronograma

Las dimensiones son configurables: identidad y currentness, cobertura de alcance, fecha de corte, calendarios, duración, status, relaciones y base de incertidumbre. El ejemplo exige identidad, scope, Data Date, calendarios y schedule type.

Se registra la cobertura exacta de actividades incluidas y excluidas. Datos faltantes producen bloqueos cuando el perfil los exige; el usuario no puede completar campos fuente desde el formulario para ocultar su ausencia en la importación.

## 17. Controles de calidad del cronograma

La política puede exigir Data Date, calendarios, duración y metadatos, limitar open ends, restricciones, lags negativos y máximos, y controlar hallazgos de status. Las excepciones de inicio y fin deben tener referencias explícitas.

Se validan tipos de relación y lags originales; un tipo desconocido no se acepta porque el normalizador histórico lo haya convertido a FS, ni un lag inválido se acepta como cero. Las comparaciones de lag usan unidades declaradas; unidades ausentes o incompatibles no se convierten silenciosamente.

## 18. Alcance y preparación de inputs de cronograma

El alcance puede ser proyecto completo, WBS seleccionados o referencias seleccionadas. Un alcance parcial requiere IDs explícitos y conocidos. Se calculan población incluida y exclusiones; referencias inexistentes, vacías o duplicadas generan problemas de identidad o cobertura.

Los hitos pueden ser deterministas sólo bajo política y justificación. El modelo debe definir cada miembro del denominador real, sin eliminar actividades difíciles para mejorar la cobertura. No se produce fecha probabilística ni reserve de cronograma.

## 19. Agregado de evaluación de cronograma

ScheduleSourceReadinessAssessment comparte trazabilidad y gobierno con la evaluación de costo, pero congela población y evidencia del cronograma. Revisión y complete son diferentes comandos; ambos son auditables y exigen revisión vigente.

Su historial es inmutable. Refresh Preview compara snapshot histórico y fuente actual sin persistir; Refresh Apply crea un nuevo DRAFT enlazado al predecesor. Las evaluaciones antiguas continúan disponibles en History.

## 20. Uncertainty Range Policy

ADMIN define representaciones permitidas, mínimos de calidad, evidencia y rationale, signo, piso cero, porcentajes máximos y compatibilidad con distribuciones. La validación es determinista: comprueba coherencia de la definición, no comportamiento aleatorio.

Valores booleanos, strings numéricos, NaN e infinito no son importes válidos. Una representación no habilitada en la política bloquea. Las comprobaciones se hacen en backend y no dependen de esconder botones del frontend.

## 21. Representaciones y origen de rangos

El catálogo contempla MIN_MOST_LIKELY_MAX, LOW_BASE_HIGH, PERCENT_MINUS_PLUS, ABSOLUTE_RANGE, DISCRETE_SCENARIO y OTHER_CONFIGURED_RANGE. Sólo se usan representaciones habilitadas, con parámetros y fuente declarada.

La evidencia puede provenir de juicio experto, históricos u otra referencia documentada. Se conserva rango, unidad, source item, calidad, confidence, rationale y referencia. El código no inventa rangos a partir de un importe presupuestal ni estima parámetros.

## 22. Distribution Policy y familias

Las familias disponibles para configuración incluyen TRIANGULAR, PERT, BETA_PERT, UNIFORM, NORMAL, LOGNORMAL, DISCRETE y CUSTOM_CONFIGURED. Habilitar una familia exige sus reglas, representaciones compatibles y parámetros válidos; el catálogo no equivale a un motor implementado.

Se comprueban ordering, cotas, positividad cuando corresponda, desviaciones y probabilidades de escenarios. Las familias no habilitadas o parámetros extra desconocidos no se aceptan. No existe muestreo, ajuste estadístico ni generación de resultados.

## 23. Límite PERT

PERT/BETA_PERT conservan tres puntos y lambda/configuración requerida según perfil. El ejemplo usa lambda positiva dentro de límites explícitos. Se valida como parámetro de definición, sin generar una beta, calcular percentiles ni simular.

La ausencia de lambda, valor no finito o fuera de límites bloquea. No se presupone lambda universal ni se interpreta una definición PERT aprobada como estimación probabilística ya calculada. En DISCRETE_SCENARIO se validan por separado los valores de cada escenario y sus probabilidades: un valor negativo o fuera de los límites del rango no se acepta porque sus probabilidades sumen uno.

## 24. Correlation Policy y gobierno

Los métodos configurables son NO_CORRELATION, PAIRWISE_CORRELATION, GROUP_CORRELATION, MATRIX_CORRELATION y OTHER_CONFIGURED_METHOD. Coeficientes, referencias, membership y rationale forman parte del modelo versionado.

Se rechaza contenido que no corresponda al método elegido; no se ignoran grupos o matrices extra. La gobernanza permite documentar dependencias y revisarlas antes de un futuro engine, sin producir muestras correlacionadas.

## 25. Validación estructural de correlación

Se comprueban referencias existentes, ausencia de duplicados inválidos, coeficientes finitos dentro de cotas, dimensiones de matriz, simetría y diagonal. Los grupos necesitan membresía válida y los pares no pueden apuntar a inputs ajenos al modelo.

Límite explícito: no se garantiza semidefinición positiva, ni transformación Cholesky, ni muestreo correlacionado. El resultado declara NOT_IMPLEMENTED_STRUCTURAL_VALIDATION_ONLY para esa capacidad matemática. Un engine futuro deberá validar su factibilidad antes de ejecutar.

## 26. QRA Methodology Profile

El perfil usa AdminConfiguration kind qra_methodology_configuration. Integra scope, applicability, analysis types, requisitos de fuentes, controles de cronograma, rangos, distribuciones, correlaciones, model governance, SoD, freshness y numbering.

El bootstrap crea una configuración neutral DRAFT sin requisitos operativos ni evidencias. La publicación independiente debe pasar validación; guardar un borrador no lo convierte en autoridad. Los settings reservados del futuro engine son declarativos y no ejecutables.

Las reglas efectivas de distribución se configuran en distribution_families; las de aplicabilidad en applicability y requirement.stage_rules; las de revisión en model_governance y separation_of_duties. Los bloques globales distribution_rules, review_approval y los cinco aliases superiores de tailoring no tienen evaluador propio: contenido no vacío se rechaza explícitamente como UNSUPPORTED_CONFIGURATION_SECTION. No se publica una regla ignorada por el evaluador. Tipos JSON anidados incorrectos reciben rechazo de validación en vez de excepciones de servidor.

El override por etapa se aplica antes de filtrar active y applicability del requisito. Desactivar todos los requisitos no produce cobertura READY de 0/0: el resultado es BLOCKED con SOURCE_REQUIREMENTS_NOT_CONFIGURED y provider UNAVAILABLE. La navegación lateral conserva edición pendiente y distingue Cost, Schedule y Model incluso cuando no existen proyectos autorizados.

## 27. Tipos de análisis

Se soportan definiciones COST_QRA, SCHEDULE_QRA e INTEGRATED_COST_SCHEDULE_QRA. El tipo controla fuentes obligatorias y población requerida. La integración costo-cronograma es una definición conjunta, no simulación conjunta.

No se admiten tipos no configurados. El contrato conserva el tipo y vínculos a assessments exactos de costo y cronograma, de manera que una aprobación no pueda reinterpretarse con fuentes posteriores.

## 28. Ciclo e herencia de metodología

La metodología usa DRAFT, PUBLISHED y ARCHIVED mediante clones y versiones. El resolver considera scope Tenant → Enterprise → Business Unit → Portfolio, herencia a descendientes, fechas efectivas y contexto. La política más específica aplicable gobierna; cada perfil debe ser completo, no un parche ambiguo de otro.

Se registra la cadena de resolución y hash. Project Type, Governance Model, industria, FEL, Gate, complejidad, riesgo e incertidumbre pueden restringir o adaptar requisitos. Publicar una nueva revisión aplicable invalida la lectura corriente de los cierres basados en la anterior.

## 29. Agregado QraModelDefinition

El modelo contiene identidad estable model_number, record number, version, predecesor, analysis_type, propósito, vínculos de assessments, inputs, correlación, configuración y snapshots. Las condiciones de aprobación se evalúan en servidor contra fuentes actuales.

Un modelo no posee runs, iteraciones, seeds ni resultados probabilísticos. La columna snapshot guarda evidencia de la definición revisada. La relación con assessments evita copiar sus autoridades y permite reconstruir denominador y vigencia.

## 30. Identidad ciclo y versiones de modelo

El ciclo es DRAFT → IN_REVIEW → APPROVED_FOR_ANALYSIS. model_number es estable entre versiones; number identifica el registro de versión. Hay unicidad tenant/model_number/version y predecesor explícito. La revisión técnica del registro usa revision_version, distinta de la versión de negocio.

Un refresh de un modelo aprobado genera sucesor DRAFT, conserva model_number y la versión anterior. No reutiliza el mismo registro ni cambia su hash. El historial muestra estado, actores, fecha, predecesor y versión.

## 31. Separación de funciones del modelo

Permisos y política SoD son controles distintos. El preparador no puede aprobar donde la metodología lo impide. La aprobación exige review registrado; las restricciones adicionales pueden impedir al preparador de fuentes, publisher o decision maker actuar como aprobador único.

ADMIN configuration-only no obtiene permisos de aprobar modelos operativos. La autorización se aplica a rutas directas y servicio, además del frontend. Las respuestas de denegación permiten distinguir falta de permiso, proyecto fuera de alcance y conflicto de funciones.

## 32. Validez y staleness del modelo

Se comprueba metodología efectiva, currentness de fuentes, hash y versión de assessments, contexto requerido, vencimiento y materialidad de snapshots. La validez actual se separa del estado histórico aprobado.

Cambios de importación, costo, configuración o contexto pueden producir STALE. También se aplica freshness.maximum_model_age_days desde la fecha inmutable de aprobación, no desde la hora de la consulta. El máximo configurado es inclusivo en días calendario; superarlo produce MODEL_FRESHNESS_EXPIRED, bloquea la preparación y retira currentness sin cambiar snapshot ni hash históricos. History sigue mostrando el contenido exacto aprobado. Refresh Preview no altera registros; Refresh Apply prepara una nueva versión que debe pasar otra vez sus controles y ciclo de aprobación.

## 33. Readiness y hash del modelo

La proyección distingue preparación para review de aprobación gobernada. APPROVED_FOR_ANALYSIS sólo se emite tras los comandos de revisión/aprobación y condiciones satisfechas. El hash SHA-256 se calcula sobre material normalizado, snapshots, entradas y referencias, no sobre hora variable de consulta.

Se muestran bloqueos, warnings y coverage exacto. No se fabrica un hash de simulación ni un proveedor de QRA terminado. READY_FOR_GOVERNED_QRA_ANALYSIS es un estado de cierre del incremento, no preparación automática de todos los proyectos locales.

## 34. Modelo de definición de inputs

Cada input referencia source_kind y source_item_ref reales. Incluye mode, range_type, values, distribution_family y parámetros, unidad, rango fuente, evidencia, calidad, confidence y rationale. La población se resuelve por lote desde las fuentes seleccionadas.

La compatibilidad de rango, distribución y unidad se valida en backend. Referencias ajenas, duplicados y datos no finitos se rechazan. La representación persistida es definición de incertidumbre, sin multiplicar aleatoriamente importes o duraciones.

## 35. Exclusiones deterministas

DETERMINISTIC es una declaración explícita para un miembro de la población, no una eliminación silenciosa. La metodología debe permitirla y puede exigir justificación y evidencia. Hitos del ejemplo se tratan de este modo bajo reglas aprobadas.

Las exclusiones de alcance son diferentes de un input determinista: las primeras pertenecen al alcance fuente, los segundos siguen dentro del denominador del modelo. La interfaz y snapshot permiten distinguir ambas decisiones.

## 36. Completitud de inputs

El denominador incluye cada item de costo y/o actividad del alcance elegido. required, uncertain, deterministic, missing, invalid y percentage informan cobertura sin ocultar faltantes mediante promedios.

Un input faltante bloquea la aprobación aunque la mayoría esté completa. Los items desconocidos no amplían artificialmente la cobertura. Cambiar alcance exige reevaluación de fuentes y modelo, preservando el snapshot histórico previo.

## 37. Proveedores de fuentes

COST_SOURCE_READINESS_PROVIDER y SCHEDULE_SOURCE_READINESS_PROVIDER devuelven contrato gobernado, hash, as_of_date, source_current, quality, confidence, referencias, warnings y blockers. La evidencia de proyecto sólo está AVAILABLE desde un assessment COMPLETED, READY y corriente.

Un borrador o assessment completado con bloqueos no satisface el contrato. Al cambiar la fuente se retira disponibilidad corriente pero no la evaluación histórica. Los adaptadores de Investment Evidence consumen la misma verificación; no fabrican evidencia desde un registro del catálogo.

## 38. Decisión de registro de proveedores

Se registran los dos contratos con versión 1.0 y scopes de proyecto. AVAILABLE en registry significa implementación disponible; no equivale a evidencia disponible en todos los proyectos.

No se crea QRA_FOUNDATION_READINESS_PROVIDER porque duplicaría estado de preparación sin aportar autoridad separada. Tampoco existe un QRA-result provider. Los tests distinguen explícitamente contract availability y project evidence availability.

## 39. Compatibilidad futura Gate07J

El registry reconoce COST_SOURCE_READINESS y SCHEDULE_SOURCE_READINESS como tipos de evidencia futura. Las políticas Gate07J publicadas y sus defaults no adquieren requisitos QRA automáticos en este incremento.

Paquetes Gate, decisiones Gate07K/FID y post-FID permanecen bajo sus autoridades. Una política futura deberá definir aplicabilidad, freshness y criterio de decisión explícitos. La salida QRA Foundation no decide inversión ni activa proyecto.

## 40. Diseño ADMIN

QRA Methodology & Source Readiness reutiliza GovernedPolicyEditor y presenta 25 secciones para requisitos, reglas, rangos, distribución, correlación, gobernanza, SoD, vigencia, numeración y tailoring. Permite leer, clonar, editar DRAFT, preview no persistente, publicación independiente, archive e historial.

Las capacidades están dictadas por allowed_actions y permisos. Las rutas genéricas legacy se bloquean para este kind, incluyendo alias normalizados, evitando que otra pantalla publique sin controles dedicados. No hay formularios de fuentes/modelos vivos en ADMIN.

## 41. Diseño USER

QRA Foundation presenta Cost Source Readiness, Schedule Source Readiness, Model Definitions e History. Los formularios mantienen evidencia de fuentes, alcance, preview, submit, review, complete/approve y refresco gobernado. La pantalla distingue datos históricos de proyección corriente.

Las vistas de lectura usan summary y páginas de 25 items; cambios de página realizan una sola petición. El editor JSON completo se carga bajo demanda y tiene límites de dominio explícitos. No se ha integrado botón Run ni gráficos de percentiles.

## 42. Matriz ADMIN USER

| Acción | ADMIN configuration only | USER autorizado |
| --- | --- | --- |
| Editar metodología DRAFT | Sí con configure | No por permiso operativo |
| Publicar metodología | Sí con publish y SoD | No por read/create |
| Preparar fuentes | No por configure | Sí con permiso de fuente |
| Revisar y completar fuentes | No por configure | Sí con review y SoD |
| Preparar modelo | No por configure | Sí con model create/edit/submit |
| Aprobar modelo | No por configure | Sí con approve y SoD |
| Leer historial permitido | Según alcance read | Según alcance read |

Cambiar el modo visual no cambia los permisos del actor. Rutas directas, tenant y project scope se verifican nuevamente en backend.

## 43. Roles y permisos

Se añaden exactamente 16 permisos QRA: read; create/edit/submit/review para cost y schedule; create/edit/submit/review/approve para model; configure/publish para metodología. Se reutilizan roles Project Definition existentes, sin crear roles ni asignaciones en el bootstrap.

Project Definition Manager combina preparación y revisión conforme a SoD; Assessor prepara; Reviewer revisa/aprueba; Viewer lee; Configuration Admin sólo administra metodología y lectura. Los permisos organizacionales existentes se amplían sólo con el catálogo QRA aplicable, sin borrar grants anteriores.

## 44. ETag

Las mutaciones requieren la revisión esperada mediante If-Match/ETag. Un actor con una vista desactualizada recibe 412 en lugar de sobrescribir el registro. La revisión de negocio y la de concurrencia se presentan separadamente.

Submit, review, complete/approve, refresh y comandos de configuración controlan concurrencia. El cliente mantiene el ETag de la última lectura y refresca después de cada acción. Un botón deshabilitado no sustituye este control del servidor.

## 45. Idempotencia

qra_commands guarda tenant, idempotency_key, command_type, request_hash, result_json, actor y fecha. Reintentar el mismo comando con el mismo actor y payload devuelve resultado consistente; una clave reutilizada con otro payload o actor produce conflicto.

Las llaves están limitadas en tamaño y son únicas por tenant. Las respuestas idempotentes no omiten autorización actual; el acceso al proyecto se comprueba antes de consumir la operación. Los tests verifican conteos de recibos y eventos, no sólo códigos HTTP.

## 46. SecurityEvent

Se registran las mutaciones gobernadas de creación/edición, submit, review, complete/approve, publicación y refresco. El registro incluye actor, tenant, objetivo y metadatos acotados, sin secretos ni tokens. Los errores de autorización, ETag e idempotencia se rechazan; los controles heredados no garantizan persistencia de un SecurityEvent para cada solicitud denegada o transacción revertida. Esa cobertura no se declara validada.

El publisher real de metodología se resuelve desde el evento de publicación, no se adivina desde created_by. Esto permite aplicar SoD a una revisión clonada/editada sin confundir autor, preparador, reviewer y publisher.

## 47. Persistencia

Las tres tablas de agregados contienen JSON de definición y snapshot, configuración referenciada, actores, timestamps, versión y revision_version. Restricciones SQL limitan estados y exigen hash, completed_at, approved_by y reviewed_by para cierres.

Hay índices por tenant, proyecto, status/history y referencias de assessment. qra_commands concentra recibos. Los hooks ORM impiden modificar historia completada/aprobada; la protección no se presenta como privilegio contra acceso directo de un DBA con capacidad de modificar SQL.

## 48. Migración

20261009_0067 sigue 20261008_0066; añade cuatro tablas y una sola columna JSON source_metadata a schedule_imports. No renombra ni borra tablas existentes durante upgrade. La revisión 0066 conserva SHA-256 6D59E013EA9B44CBEFAE21AC464EBF5BFFC47680B96CFF355016DB43C71CB5E4.

El downgrade elimina exclusivamente esos objetos nuevos, en orden dependiente. Se prueba upgrade/downgrade/upgrade en bases desechables SQLite y PostgreSQL. No se ejecuta downgrade en la base local del usuario: perdería evidencia QRA creada después de la migración.

## 49. API

El prefijo es /api/v1/qra-foundation. Options, requirements y contexts resuelven proyecto y política; source-options entrega fuentes reales; cost/schedule-assessments y models exponen listas paginadas, lectura, update, preview y acciones gobernadas.

| Grupo | Operaciones | Control |
| --- | --- | --- |
| Fuentes | create update submit review complete | Proyecto permisos ETag idempotencia |
| Modelos | create update submit review approve | Fuentes actuales cobertura SoD |
| Historia | record items refresh-preview refresh-apply | Inmutabilidad sucesor DRAFT |
| Readiness y evidence | Proyección actual y proveedor | Sólo COMPLETED READY actual |
| Configuración | clone update preview publish archive history | ADMIN y publicación independiente |

summary=true limita vistas de consulta; /items?page&page_size=25 pagina poblaciones e inputs. No existen rutas /run o /simulate.

## 50. Navegación canónica

El blueprint estratégico y StrategicViewOutlet son la fuente única de navegación. USER conserva el identificador de fase 6 pero usa Business Case & Investment Development. ADMIN aloja la configuración QRA en su ubicación respectiva.

Los selectores de seis pruebas previas se actualizan sólo por el nuevo label USER, manteniendo los labels ADMIN y sus assertions. App.tsx conserva sus modificaciones previas, sin añadir rutas ni lógica QRA en este incremento.

## 51. Happy path PostgreSQL de costo

La aceptación usa PostgreSQL 16 desechable, proyecto canónico, enlace operativo explícito y fuente real Control Account de la importación manual. El perfil independiente exige BoE, moneda, fecha, base de contingencia y evidencia; create/save/submit/review/complete deben producir COMPLETED READY.

Se comprueba el proveedor AVAILABLE con hash exacto del cierre y no_simulation=true. El fixture minero es evidencia de pruebas aislada, no una configuración comercial aplicada automáticamente a la base local. Resultado final de ejecución se consolida en la sección 70.

## 52. Happy path PostgreSQL de cronograma

La importación XML real registra Data Date, calendario, unidades declaradas, hitos y relaciones. Se completan las reglas de identidad, scope y calidad bajo el perfil publicado. El assessment congela la población de actividades y obtiene proveedor de source readiness, no de completion risk.

Se usa el mismo camino canónico de ingestión que la aplicación, no una tabla paralela. Los lags se revisan por unidad explícita y no se recalculan duraciones, float o critical path. El resultado de PostgreSQL se registra junto al resto de aceptación.

## 53. Negativos de cronograma

Se cubren Data Date ausente, calendario faltante, unidad/duración incompleta, relación fuente desconocida, open ends no autorizados, alcance desconocido, restricciones y lag excesivo/negativo. Las pruebas del importador verifican además que MustFinishByDate no se transforme en Data Date y que un tipo raw inválido se conserve.

Las evaluaciones bloqueadas no habilitan el proveedor. Corregir sólo una proyección visual no completa evidencia; se requiere nueva fuente/definición y revisión. Las regresiones de importación manual permanecen dentro de la validación.

## 54. Negativos de costo

Se comprueban contingency basis desconocida, reconciliación fuera de tolerancia, moneda incompatible o ausente, base date inválida, referencias no encontradas y población vacía. El adaptador no convierte monedas ni confunde partidas agregadas con un estimate completo.

Cambiar el budget de una cuenta de control retira currentness y proveedor sin reescribir snapshot/hash históricos. Las referencias externas siguen marcadas como declaraciones no autenticadas contra contenido remoto.

## 55. Negativos de metodología

El hardening independiente cubre reglas malformadas, códigos duplicados, calidad fuera del catálogo, rangos no finitos, bool/string numéricos, lambda PERT inválida, parámetros extra y contenido de correlación incompatible.

Publicación por el autor, fechas no aplicables y scopes/tipos incorrectos se rechazan o quedan no aplicables. Las rutas legacy create/clone/patch/publish se prueban con estados y alias normalizados, sin permitir modificar políticas gobernadas desde una API genérica.

## 56. Happy path del modelo

El ejemplo combina fuente de costo y cronograma completadas, propósito, inputs de tres puntos y hitos deterministas justificados. Se verifica denominador exacto, submit, review independiente y approve. El resultado es APPROVED_FOR_ANALYSIS con hash estable y simulation_results nulo.

La integración adicional consume cinco prerrequisitos reales FEL/PDRI, Risk Readiness, Risk Governance, Basic Data y Owner. La aprobación y refresco deben preservar los hashes de tablas upstream. No se simulan FIN/Budget inexistentes en el fixture.

## 57. Staleness del modelo

Una importación posterior o publicación de metodología nueva produce STALE en la proyección corriente y retira evidencia disponible si corresponde. Los snapshots anteriores siguen inmutables. Se verifica comparación entre histórico y current preview.

Refresh Apply crea sucesor y mantiene model_number, incrementando la versión de negocio. No declara automáticamente READY al sucesor: se debe editar/revisar/aprobar con referencias corrientes y evidencia completa.

## 58. Pruebas SoD

Los tests intentan completar/aprobar con el mismo preparador y publicar metodología por su autor. La política y API deben denegar incluso cuando el actor tenga permisos funcionales suficientes.

Se prueba actor configuration-only contra operaciones vivas y USER operativo contra publicación ADMIN. Las denegaciones no crean cierres falsos ni alteran evidencia. El navegador usa actores diferenciados para preparación, revisión y administración. La revisión independiente del modelo es obligatoria; require_review=false se rechaza explícitamente en metodología. La persistencia de eventos para todas las denegaciones no está demostrada y se distingue de la auditoría de mutaciones exitosas.

## 59. Regresiones de independencia

La integración captura huellas de fuentes y autoridades antes y después de fuentes/modelo QRA y refresh. Se incluyen proyectos, FEL, PDRI, riesgos, datos básicos, Owner, Commercial, Business Case, FIN, Budget, Resources, Funding, Benefits, Gate, FID, post-FID, cronograma y seguridad.

En la base local se compararon 35 categorías antes/después de migración y bootstrap: cero cambios en sus conteos o hashes. Se excluyen únicamente nuevos permisos/grants/configuración QRA y la nueva columna metadata de la comparación legacy; no se excluyen cambios en contenido financiero ni decisiones históricas. Se preservaron 31 workspaces, 138 roles, 32 membresías y las fuentes operacionales existentes.

## 60. Regresión Governance Model

Applicability se resuelve desde el proyecto existente, no un selector arbitrario de QRA. CAPITAL_OWNER del ejemplo es aplicable al perfil configurado; otros modelos requieren política correspondiente. No se universaliza QRA a contratos EPC/EPCM u otros modos sin reglas explícitas.

La ausencia de metodología aplicable no da READY. El perfil restringe modelos de gobierno mediante applicability y reglas de requisitos, manteniendo la autoridad de Project Governance; el alias global governance_model_rules no vacío se rechaza porque no posee semántica implementada. Las comparaciones son de contexto y definición, sin crear un proyecto ni cambiar su governance model.

## 61. Tailoring Project Type

Project Type y demás contexto restringen applicability y reglas específicas. Se permite tailoring por tipo, FEL, Gate, complejidad, risk e incertidumbre, conservando el origen y hash de metodología.

Un requisito crítico no se elimina por un cambio visual de tipo; el contexto procede del proyecto y fuentes canónicas. Los snapshots muestran la política resuelta que fundamentó el cierre, y cambios posteriores exigen nueva revisión.

## 62. Ejemplo minero

El perfil MINING_QRA_FOUNDATION es un ejemplo de pruebas: CAPITAL_OWNER, FEL-3, fuente manual P6, Control Account USD, BoE con quantity/rate/assumptions/exclusions, tres puntos y hitos deterministas. Sus diez requisitos de costo y cinco de cronograma no son defaults universales.

Los cinco contextos de gobierno se preparan mediante sus flujos reales. La base local recibe sólo metodología neutral DRAFT y permisos QRA añadidos a roles existentes; no se implanta este ejemplo ni se generan proyectos de demostración durante el despliegue.

## 63. Browser USER E2E

El recorrido Playwright usa navegador Chromium real contra API PostgreSQL y frontend de producción aislados. Comprueba navegación, selección del proyecto, fuentes, campos, preview, submit/review/complete, inputs y model approve, history y refresh.

Se distinguen snapshots históricos de readiness corriente. Los resultados finales, duración y fallos corregidos se registran en el cierre. El entorno de pruebas usa puertos 5519/8816 y no sustituye la aplicación normal de 5173.

## 64. Browser ADMIN E2E

El segundo recorrido valida entrada ADMIN, 25 secciones de metodología, clon DRAFT, edición, preview no persistente, SoD y publicación independiente, archive e historial. Se verifican restricciones de configuration-only frente a modelos vivos.

Un modo visual no habilita acciones fuera de permiso. Se comprueba que las políticas publicadas quedan inmutables y que una nueva revisión cambia autoridad efectiva sin reescribir cierres previos. Los screenshots y trazas son evidencia privada de QA.

## 65. Seguridad de rutas directas

Se prueban tenant equivocado, proyecto ajeno, fuente perteneciente a otro proyecto, ETag stale y conflicto de clave idempotente. La API no depende de la navegación ni del modo de pantalla para defender autoridad.

Las rutas legacy están guardadas para el kind QRA. Los tests de bootstrap niegan tenant vacío, actor inactivo, vínculo ajeno, permisos sólo de workspace y ausencia de autoridad organizacional. El bootstrap no crea roles/asignaciones para autoautorizarse.

## 66. Observación de performance

Las listas de assessments/modelos paginan registros en SQL. Las páginas de items limitan la respuesta en servidor, pero decodifican el snapshot JSON completo antes de seleccionar los 25 items: no son paginación SQL interna del JSON. Summary también serializa el agregado antes de recortarlo. Los adaptadores resuelven mapas, relaciones y fuentes por lote. Las opciones de costo materializan fuentes antes de recortar en Python. Overview usa un número fijo de solicitudes, sin una petición por actividad.

Se ejecutó una observación sintética en SQLite exclusivamente en memoria, con 5.000 y 10.000 actividades y 4.999/9.999 relaciones FS. Población, readiness, página y total pasaron; las consultas permanecieron constantes entre ambos tamaños. No hubo acceso a bases compartidas ni cálculo probabilístico.

| Operación con 10.000 actividades | Consultas y tiempo instrumentado | Pico Python y payload |
| --- | --- | --- |
| Adaptador canónico | 7 / 15,326 s | 79,60 MB / 5,11 MB |
| Calidad de cronograma | 0 / 1,425 s | 2,23 MB / 90,5 KB |
| Evaluación de fuente | 7 / 23,928 s | 79,39 MB / 4,37 MB |
| Página de 25 items | 1 / 1,090 s | 18,47 MB / 8,29 KB |
| Summary de un assessment | 2 / 4,522 s | 32,14 MB / 1,12 KB |

Los tiempos incluyen tracemalloc y carga concurrente: no son SLA ni benchmark PostgreSQL/navegador. El pico mide asignaciones incrementales Python, no RSS. No se midieron 25 versiones masivas ni 20.000 inputs de modelo. El editor JSON completo y el detalle histórico se cargan a demanda, no equivalen a edición incremental masiva. La evidencia sustenta ausencia de N+1 a 10.000 actividades, no un PASS universal de performance.

## 67. Deuda técnica

Los imports antiguos sin metadata requieren nueva importación para satisfacer reglas que exigen campos fuente. Una referencia externa con hash declarado no verifica autenticidad del contenido remoto. Granularidad FIN/Budget agregada no sustituye estimate detallado.

La validación de correlación es estructural, no matemática PSD. El editor JSON completo de modelos grandes necesita evolución a edición incremental por item; lectura paginada ya está implementada. Las opciones de costo y el detalle histórico todavía requieren materialización completa por lote. La auditoría persistente de cada denegación requiere un mecanismo de seguridad independiente de la transacción revertida. Los aliases globales sin semántica operativa se rechazan y no constituyen funciones de configuración implementadas. El acceso DBA directo no está cubierto por hooks ORM. La disponibilidad de perfiles operativos debe configurarse y publicarse por actores autorizados: el bootstrap no fabrica readiness.

## 68. Contrato futuro QRA Engine

Entrada futura: QraModelDefinition APPROVED_FOR_ANALYSIS, actual, válido, con fuentes y metodología congeladas y hash. Salida futura: QraRun separado. La ejecución deberá volver a verificar validez/currentness y mantener el lineage de la definición.

El futuro run podrá poseer engine version, seed, iterations, resultados, percentiles, sensibilidad, recomendación de contingencia y fechas ajustadas por riesgo. Ninguno existe en esta entrega. No se añade fórmula probabilística, servicio de simulación, gráfico P50/P80/P90 ni integración automática Gate/FID.

## 69. Matriz de preparación del futuro engine

| Componente | Implementación Foundation | Validación de release |
| --- | --- | --- |
| Cost Source Provider | Cierre READY actual y hash | PASS lifecycle y provider |
| Schedule Source Provider | Import canónico y cierre actual | PASS metadata y provider |
| Methodology Profile | Versionada publicada heredada | PASS backend y browser ADMIN |
| Uncertainty Inputs | Cobertura y evidencia por item | PASS inputs y negativos |
| Distribution Rules | Definición y validación sin sampling | PASS hardening de parámetros |
| Correlation Rules | Validación estructural sin sampling | PASS; no garantía PSD |
| Model Definition | Identidad y snapshots versionados | PASS backend y browser USER |
| Model SoD | Review y approve independientes | PASS actores diferenciados |
| Model Validity | Fuentes política contexto y caducidad | PASS vigencia y edad límite |
| Model Staleness | Proyección y refresh sucesor | PASS STALE visible e historia |

No se interpreta esta matriz como QRA completado. Los límites PSD y editor masivo deben ser atendidos en el diseño del motor, sin eliminar la preparación gobernada ya existente.

## 70. Estado final del release

Estado exclusivo: QRA_SOURCE_READINESS_AND_METHODOLOGY_FOUNDATION_RELEASE_VALIDATED.

Salida: final_output=READY_FOR_GOVERNED_QRA_ANALYSIS. Significa Foundation preparada; no significa simulación ejecutada ni que todos los proyectos locales tengan evidencia disponible.

| Comprobación ejecutada | Resultado | Alcance y evidencia |
| --- | --- | --- |
| QRA completa SQLite | 120 PASS / 1 omitida | Omisión PostgreSQL ejecutada por separado |
| QRA completa PostgreSQL | 121 PASS | Incluye migraciones SQLite y PostgreSQL up/down/up |
| Foundation y hardening finales SQLite | 94 PASS / 0 omitidas | Código final tras ajuste de stage_rules; 327,932 s |
| Foundation y hardening finales PostgreSQL | 94 PASS / 0 omitidas | Código final; 380,938 s |
| Regresiones previas focalizadas | 156 PASS / 12 módulos | 844,249 s; Basic Data Risk Owner FEL y políticas Gate |
| Frontend QRA y navegación | 40 PASS | API ADMIN USER y blueprint |
| Editor compartido y outlet | 22 PASS | Rutas ADMIN protegidas y reutilización |
| Workspace final | 19 PASS | Incluye ruta vacía editor pendiente y StrictMode |
| Chromium real final | 2 PASS / 0 omitidas | USER y ADMIN; 3,2 min; PostgreSQL aislado |
| Controles de código | PASS | Ruff formato TypeScript ESLint Prettier build diff y guardrails STOP |
| Integridad operacional | PASS / 35 categorías | Cero cambios legacy; respaldo custom legible |

Las suites completas iniciales precedieron sólo al último ajuste de tailoring por etapa, revalidado por las suites finales de 94 casos en ambas bases. Los conteos de ejecuciones se solapan: no se suman como tests únicos. Una advertencia preexistente de serialización Pydantic aparece en el test negativo de scope. Intentos Windows sin permiso de loopback y un arranque de navegador anterior a readiness no se cuentan como PASS. El primer ADMIN detectó un assert que esperaba texto NOT_APPLICABLE; se corrigió para comprobar applicable=false y requisitos vacíos, preservando la regla de herencia, y la repetición final pasó.

El despliegue operacional está en http://localhost:5173/app; API 8000 y frontend respondieron HTTP 200, API healthy y Alembic current/heads único 20261009_0067. Se reconstruyeron API worker beat y frontend sin eliminar volúmenes. La API expone 46 rutas QRA. El bootstrap autorizó al administrador existente del tenant 1: 16 permisos, 52 grants sobre roles existentes y metodología 866 DRAFT; cero roles, asignaciones, membresías, evaluaciones o modelos nuevos. El perfil minero de browser permanece exclusivamente en su base desechable. Para uso real un configurador y publisher independientes deben preparar y publicar una metodología aplicable.

El Word de fecha 2026-10-11 incorpora las 71 secciones y se verifica mediante exportación de lectura en Word y rasterización canónica a PNG, sin sustituir el informe histórico del 9 de octubre. La revisión de accesibilidad OOXML comprueba jerarquía, alt text y encabezados de tablas; no representa certificación WCAG integral. La evidencia QA permanece privada en outputs/.qa/qra-foundation.

La CI incorpora jobs PostgreSQL y browser QRA aislados, conserva artefactos de pruebas y verifica la nueva cabeza 0067. La configuración de CI no demuestra ejecución remota. Los commits anteriores se enviaron a origin por solicitud del usuario; esta reanudación no implica publicar automáticamente sus nuevas correcciones ni afirmar un resultado de GitHub Actions.

## 71. Única recomendación de próximo incremento

Única recomendación de próximo incremento: QRA CALCULATION ENGINE. La matriz Foundation está validada. Ese incremento deberá consumir una definición APPROVED_FOR_ANALYSIS actual, considerar validación matemática de correlaciones y mejorar el acceso a inputs masivos; las limitaciones instrumentadas de la sección 66 no se confunden con resultados probabilísticos ni SLA.

El siguiente incremento no se implementa automáticamente. Se respeta STOP: no Monte Carlo, QraRun, percentiles, contingencia, management reserve, fechas probabilísticas, probabilistic FIN, actualización Gate07J, bloqueo FID automático ni ejecución de procurement/delivery.
