# Informe técnico Wave 2B — Risk Governance y Basic Data Readiness

**Fecha:** 7 de octubre de 2026.

**Estado actual:** RISK_GOVERNANCE_AND_BASIC_DATA_READINESS_RELEASE_VALIDATED

Este documento corresponde únicamente al incremento solicitado en PROMPT_WAVE2B_RISK_APPETITE_CAPACITY_THRESHOLDS_AND_BASIC_DATA_READINESS.md. Los nombres de estados y contratos se mantienen en inglés para facilitar la trazabilidad con el código. No certifica una ejecución remota de GitHub Actions ni autoriza el siguiente incremento.

## 1. Resumen ejecutivo

Se implementaron dos dominios independientes: Risk Governance para políticas empresariales de capacidad, apetito y umbrales, y Basic Data para requisitos, evidencia técnica y evaluaciones de suficiencia por Project Workspace. ADMIN configura políticas reutilizables; USER opera evidencia y evaluaciones, sin convertir una política de riesgo en una decisión de inversión. La resolución y los cálculos son responsabilidad del backend.

La implementación reutiliza AdminConfiguration, la identidad canónica de EnterpriseWorkspace, los clasificadores y el adaptador FEL existentes, RBAC, SecurityEvent, numeración administrativa y la navegación estratégica. Se añadieron solamente tres tablas para datos técnicos, evaluaciones y recibos idempotentes. QRA, Owner Capability y cambios automáticos de Gate/FID están excluidos.

La validación local aprobó las pruebas SQLite y PostgreSQL, las dos migraciones reversibles, 94 regresiones estratégicas, 38 pruebas frontend y los dos recorridos Chromium USER/ADMIN. El cierre adicional de seguridad impide mutaciones por la API administrativa legacy. Los servicios habituales quedaron disponibles en http://127.0.0.1:5173/app y API 8000. El provider Basic Data está AVAILABLE, sin cambiar requisitos Gate publicados.

## 2. Baseline real del repositorio

Repositorio local: C:/Users/Ricardo/Documents/GitHub/pypmis-ia-sas. Rama main; HEAD inicial 9cb0969abb5d48cc25b0c6a935b11e6bd7afd16f. El árbol ya contenía 75 archivos versionados modificados, 7.198 inserciones y 948 eliminaciones, además de archivos no versionados de incrementos anteriores. Se preservaron esos cambios y se registró el diff inicial en outputs/.qa/wave2b-risk-basic-data/baseline.diff.

El head Alembic verificado inicialmente fue 20261005_0064, único. Wave 3A, Wave 2A y Wave 1 estaban desarrollados. El nuevo sucesor es 20261008_0065; la fecha del identificador sigue la propuesta del prompt, no pretende indicar la fecha de ejecución. No se creó un commit ni se hizo push en esta solicitud.

## 3. ADR Wave 2B

La decisión queda en docs/76-adr-wave2b-risk-governance-basic-data.md: reutilizar AdminConfiguration para ambas políticas; no crear tablas de Risk Governance; mantener las autoridades de FEL, PDRI, Risk, Permit, Gate y FID independientes; congelar evaluaciones completadas y separar su historia de la lectura de actualidad. La configuración inicial Basic Data es un DRAFT vacío, no evidencia READY inventada.

Los resolutores usan jerarquía y contexto del backend. Las políticas son reemplazos completos en su ámbito, no mezclas implícitas de umbrales de diferentes versiones. El registro de un proveedor disponible no incorpora automáticamente un nuevo requisito a una política Gate publicada.

## 4. Posición en la arquitectura objetivo

Risk Governance aporta contexto empresarial a futuros consumidores. Basic Data aporta evidencia técnica gobernada del proyecto. FEL/PDRI aportan contexto de etapa y madurez, sin ser sustituidos por Basic Data. El proveedor nuevo permite una futura decisión explícita de consumo, pero no toma decisiones ni actualiza snapshots ajenos.

La arquitectura separa configuración reutilizable, transacciones del proyecto, evaluación backend, proyección de actualidad e historia inmutable. Los nuevos módulos backend son app/modules/risk_governance y app/modules/basic_data; las vistas se integran en StrategicViewOutlet sin aumentar App.tsx.

## 5. Matriz de autoridad

| Dominio | Autoridad de escritura | Límite |
| --- | --- | --- |
| Risk Governance | ADMIN con permisos de configuración/publicación | Solo políticas, nunca Risk Register ni FID |
| Basic Data Configuration | ADMIN con permisos específicos | Categorías, requisitos y reglas; no completar evaluaciones live |
| Project Basic Data | USER con permisos y alcance Project | Evidencia y validación técnica |
| Basic Data Assessment | Preparador y revisor independientes | Snapshot del propio dominio |
| FEL y PDRI | Servicios existentes | Wave 2B solo lee contexto y hashes |
| Gate07J y Gate07K/FID | Autoridades existentes | Ninguna actualización automática |

## 6. REUSE BEFORE CREATE

| Componente existente | Uso en Wave 2B | Decisión |
| --- | --- | --- |
| AdminConfiguration | Políticas versionadas, status, hash y scope | Reutilizado; sin tabla paralela de riesgo |
| Jerarquía de configuración | _workspace_path y selección efectiva | Reutilizada con resolución específica del dominio |
| EVID-2 | EVIDENCE_QUALITY_STATES y operadores controlados | Vocabulario y evaluador reutilizados |
| Risk Readiness | Contexto de autoridad y pruebas de independencia | Sin escritura ni recálculo histórico |
| Project Definition/FEL | Clasificadores y investment_gate_evidence | Adaptador existente de solo lectura |
| Definition Maturity/PDRI | Referencias ID, score, version y hash | Contexto, no nueva evaluación PDRI |
| EnterpriseWorkspace | Identidad Project y árbol empresarial | Sin Project duplicado |
| AdminNumberSequence | Numeración BDA | Contador existente |
| RBAC/SecurityEvent | Permisos, scopes y auditoría | Ampliación del catálogo existente |
| ETag/idempotencia | Helpers HTTP de Portfolio Review; recibos gobernados | Helpers reutilizados, ledger propio de Basic Data |
| Evidence provider registry | BASIC_DATA_READINESS_PROVIDER | Adaptador aditivo, sin cambiar requisitos Gate |
| Business Case | Contexto de future source y Five Case | Sin registro duplicado ni reescritura histórica |
| Navegación | strategicNavigationBlueprint | Fuente canónica única |
| Referencias de evidencia | evidence_refs, source_reference/version/hash | Metadatos; sin nuevo almacenamiento de documentos |

## 7. Modelo Risk Capacity

Las capacity_statements contienen código, dimensión, declaración y justificación, con aplicabilidad declarativa. Expresan límites empresariales de capacidad para absorber exposición; no calculan solvencia ni aceptan un riesgo específico. La política valida códigos únicos y dimensiones activas existentes.

La semilla neutral no introduce cifras financieras o límites de seguridad supuestos. Un administrador debe configurar límites reales, revisar la política y publicarla bajo separación de funciones.

## 8. Modelo Risk Appetite

Las appetite_statements expresan la exposición que la empresa está dispuesta a aceptar para perseguir sus objetivos. Se almacenan separadas de capacity_statements y thresholds, conservando dimensión, contexto y rationale. El ámbito puede ser tenant, Enterprise, Business Unit o Portfolio.

Un Project recibe un contexto aplicable de lectura, no permiso para editar esa política ni una aprobación implícita. Project Type y Governance Model siguen siendo dimensiones independientes.

## 9. Modelo Risk Threshold

Cada threshold identifica dimensión, tipo, operador, valor, unidad, moneda cuando aplica y referencia opcional de escalamiento. Se admiten valores numéricos, porcentajes, duración, moneda, categoría y booleanos con operadores compatibles. La validación rechaza operadores arbitrarios, dimensiones inexistentes, referencias de escalamiento inválidas y valores no finitos.

El evaluador determinístico devuelve WITHIN_APPETITE, AT_THRESHOLD, OUTSIDE_APPETITE o NOT_EVALUABLE. La moneda o unidad incompatible no se convierte silenciosamente; una fuente ausente tampoco equivale a cero.

## 10. Lifecycle de la política de riesgo

AdminConfiguration conserva draft, published y archived, revision, version y content_hash. Clone crea un DRAFT sucesor; update solo modifica DRAFT; preview valida sin persistir; publish requiere permiso y SoD; archive retira una versión publicada de la resolución activa. History conserva versiones y eventos.

Una publicación posterior no modifica el contenido de versiones anteriores ni archiva automáticamente todas las versiones históricas: las fechas efectivas siguen siendo relevantes. La semilla inicial published es neutral y advierte NO_RISK_BOUNDARIES_CONFIGURED.

## 11. Herencia de la política de riesgo

Se reutiliza la ruta de EnterpriseWorkspace. Entre políticas aplicables, el orden es ámbito ancestral más cercano, especificidad del contexto, effective_from más reciente, revision y finalmente ID como desempate determinístico. inherit_to_descendants controla si una política alcanza descendientes.

La política seleccionada reemplaza el conjunto anterior; no hay combinación implícita de límites ni precedence en el frontend. Se prueban overrides Enterprise, Business Unit y Portfolio, además de aislamiento respecto de un Portfolio hermano.

## 12. Semántica de fechas efectivas

effective_from es obligatorio y effective_to opcional. Ambos límites son inclusivos por fecha; un rango inverso es inválido. El request del resolver acepta effective_date y descarta versiones que todavía no son efectivas o dejaron de serlo. Las lecturas históricas usan versiones publicadas sin reinterpretarlas con los nuevos valores.

Archive cambia el status gobernado de la política, pero no reescribe la evidencia previamente capturada por otros dominios. Los consumidores que congelen evidencia deben conservar el ID, la revisión y el hash de la política empleada.

## 13. Operadores controlados

Se reutilizan los operadores declarativos de EVID-2: comparaciones, igualdad/desigualdad, pertenencia/exclusión y booleanos. Se añaden WITHIN_RANGE y OUTSIDE_RANGE con extremos numéricos inclusivos. No se admite eval, exec ni código de usuario.

AT_THRESHOLD comunica que la fuente está exactamente sobre un límite, no si una autoridad debe aprobarla. Las pruebas cubren operadores numéricos, categóricos y booleanos, ausencia de fuente, moneda/unidad incompatibles y entradas inválidas.

## 14. Risk Appetite frente a Risk Readiness

Risk Appetite es una política empresarial; Risk Readiness es evidencia del estado de gestión de riesgos del Project. Publicar un nuevo apetito no crea ProjectRisk, no altera tratamientos y no recalcula evaluaciones históricas RiskReadinessAssessment. Su consumo futuro necesita un contrato y una política expresamente aprobados.

## 15. Risk Appetite frente a QRA

Los umbrales proporcionan contexto gobernado, no distribuciones de probabilidad ni simulaciones. Wave 2B no calcula percentiles, contingencia, reserva, correlaciones ni exposición probabilística agregada. La existencia de appetite y Basic Data no prueba que las fuentes de costo y cronograma estén listas para QRA.

## 16. Risk Appetite frente a criterios Gate

OUTSIDE_APPETITE no mata un Project ni bloquea automáticamente FID. Los criterios de Gate07J-EVID-2 y la autoridad de Gate07K siguen en sus dominios. Un futuro criterio deberá referenciar una política efectiva y conservar la evidencia evaluada, mediante una nueva versión publicada y no mediante cambios retrospectivos.

## 17. Diseño ADMIN de riesgo

Risk Governance Configuration se ubica en la fase canónica Enterprise Foundation de ADMIN. La vista usa un editor compartido de políticas gobernadas con secciones de dimensiones, Capacity, Appetite, Thresholds, aplicabilidad, fechas, herencia y SoD. Los contenidos declarativos se editan como JSON por sección, con validación backend y mensajes de issues.

Incluye selección de versión, clone, guardar DRAFT, preview, publish, archive e historia. No ofrece operaciones del Risk Register. allowed_actions procede de permisos, estado, ámbito y SoD del backend; ocultar un botón no reemplaza la autorización de la API.

## 18. Consumo USER de riesgo

Basic Data muestra un Risk Governance Context de solo lectura para el Project seleccionado. El contrato devuelve política ID, code, revision, version, content_hash, scope, fechas, declaraciones y umbrales. La API effective valida tenant y alcance. USER no recibe controles de configuración ni publicación.

## 19. Definición de negocio Basic Data

Basic Data representa los insumos técnicos que una etapa necesita para sustentar su definición: estudios, levantamientos, datos de proceso, línea base ambiental, interfaces e información operativa existente, según la política. Su pregunta es si la evidencia requerida está disponible, validada, con calidad/confianza suficientes y vigente.

No sustituye el alcance del proyecto, el score de definición, el registro de riesgos, permisos ni el modelo financiero. La configuración inicial vacía obliga a definir y publicar requisitos reales antes de evaluar readiness.

## 20. Framework de categorías

Las categorías son valores de la configuración, no tablas o clases por industria. Cada requisito referencia una categoría declarada y código único. No se crea un catálogo universal obligatorio de minería ni una tabla por evidencia.

La prueba minera configura diez categorías: geology, geotechnical, hydrogeology, metallurgy, survey, environmental, interfaces, operations, utilities y design-criteria. La fixture de navegador reduce el caso a dos requisitos para verificar el recorrido de forma controlada.

## 21. Tailoring por industria y Project Type

La aplicabilidad combina Governance Model, Project Type, industry, FEL stage, Gate profile, location, risk, complexity y uncertainty. Se leen los clasificadores canónicos del Project y el contexto FEL efectivo. No se deduce CAPITAL_OWNER del tipo MINING.

La política por defecto opta por CAPITAL_OWNER; CONTRACTOR_DELIVERY y DIRECT_INTERNAL no reciben requisitos owner por inferencia. Una configuración futura puede optar explícitamente por esos modelos. stage_rules adapta exigencias de cada requisito sin rechazar PRELIMINARY de manera global.

## 22. Modelo Basic Data Requirement

Cada requisito tiene requirement_code, categoría, etiqueta, obligatoriedad, condición blocking, aplicabilidad, mínimos de disponibilidad/validación/calidad/confianza, exigencia de evidencia y política de vigencia. stage_rules permite overrides por contexto de etapa/Gate.

El requisito vive en la política versionada, no como una fila global mutable aplicada a la historia. La evaluación captura el conjunto efectivo exacto y la revisión/hash de configuración. Los requisitos opcionales no inflan el denominador obligatorio.

## 23. Project Basic Data Item

project_basic_data_items contiene tenant_id, project_workspace_id, requirement_code y category, cinco dimensiones de evaluación, metadatos de fuente, evidence_refs, limitaciones, supuestos, gaps, comentarios y actores/fechas de creación y validación. La combinación tenant/Project/requisito es única.

Crear o actualizar un dato no completa una evaluación. Cambiar el contenido reinicia la validación para impedir que un dato materialmente diferente conserve la certificación anterior. Se usa revision_version para concurrencia y filtros paginados para registro y cola de validación.

## 24. Modelo de disponibilidad

NOT_AVAILABLE, PARTIALLY_AVAILABLE y AVAILABLE indican existencia o cobertura del insumo. AVAILABLE no significa validado ni confiable. La política define el mínimo requerido y la evaluación conserva la dimensión de disponibilidad, sin derivar automáticamente otras dimensiones.

## 25. Modelo de validación

NOT_VALIDATED, UNDER_VALIDATION, VALIDATED y REJECTED reflejan el estado de revisión técnica. validate_item exige permiso basic_data.item.validate, If-Match e Idempotency-Key y registra actor y timestamp. Tener permiso de validación no autoriza completar una evaluación.

## 26. Modelo de calidad

Se reutiliza EVIDENCE_QUALITY_STATES de Gate07J-EVID-2. El orden de suficiencia es NOT_AVAILABLE/NOT_VALIDATED, LOW_CONFIDENCE, PRELIMINARY, PARTIALLY_VALIDATED y VALIDATED. Esta reutilización evita una taxonomía paralela, aunque el vocabulario legacy incluye LOW_CONFIDENCE entre las etiquetas de calidad.

La calidad se compara contra el mínimo efectivo del requisito. Una misma fuente PRELIMINARY puede satisfacer FEL-2 y resultar insuficiente para FEL-3, sin cambiar la fuente ni el score PDRI.

## 27. Modelo de confianza

PRELIMINARY, MODERATE y HIGH se almacenan como dimensión distinta de calidad. La evaluación captura mínimos y resultados por requisito; la confianza no se infiere del porcentaje de cobertura ni de la existencia de un documento. No representa un percentil probabilístico de QRA.

## 28. Modelo de actualidad

La política utiliza max_age_days y la evidencia incorpora source_date, expires_on y source_current. El cálculo considera la fecha de evaluación y el vencimiento de cada fuente. Fuente caducada, no actual o incompatible con la política causa un gap gobernado, no una revalidación silenciosa.

El snapshot conserva la actualidad observada cuando se completó. La lectura current-readiness comprueba condiciones actuales por separado y puede devolver STALE sin modificar aquella historia.

## 29. Basic Data Assessment

basic_data_readiness_assessments conserva número BDA, versión por Project, predecessor_id, configuración referenciada, estado, snapshot, hash y actores/fechas. Lifecycle: DRAFT, IN_REVIEW y COMPLETED. Preview no persiste; submit congela el material de revisión; complete exige revisión autorizada y SoD.

Una evaluación COMPLETED no admite update/delete mediante los servicios ni mediante eventos ORM ordinarios. Un refresh explícito crea una evaluación sucesora DRAFT. No se permite completar una evaluación cuyo material cambió desde la captura de revisión.

## 30. Dimensiones de readiness

Disponibilidad, validación, calidad, confianza y actualidad se evaluan por requisito. Overall readiness resume si se satisface la política; no es una media intercambiable con calidad/confianza. READY exige requisitos efectivos suficientes y ausencia de blockers críticos. Un dominio no configurado no entrega evidencia gobernada READY.

El resultado muestra required/satisfied/partial/missing, coverage, critical_gaps, warnings/blockers y las razones por requisito. El frontend presenta el contrato backend y no recalcula decisiones de suficiencia.

## 31. Cobertura exacta

El denominador es el número exacto de requisitos obligatorios aplicables. La cobertura se deriva de satisfied_count / required_count; partial y missing se informan por separado. Crear evidencia adicional no eleva la cobertura de requisitos que siguen sin satisfacer.

La configuración define minimum_percent. Diez requisitos con nueve satisfechos producen 90%, aunque el requisito faltante sea crítico. Ese valor numérico no puede ocultar un blocker ni convertirse en READY por una media ponderada.

## 32. Blockers críticos

Un requisito blocking no satisfecho genera un critical_gap y BLOCKED dentro del dominio Basic Data. La evaluación informa requisito y motivos concretos: ausencia, validación, calidad/confianza insuficientes o falta de vigencia.

El bloqueo no cambia FEL, Business Case, Gate07J ni FID. La consecuencia fuera de Basic Data requiere una política consumidora futura expresamente publicada.

## 33. Linaje de fuentes

Se conservan source_type, source_reference, source_version, source_hash, source_date, evidence_refs y source_current, junto con la revisión del item. El snapshot identifica las fuentes que sustentaron cada resultado. Son referencias gobernadas, no una afirmación de que el contenido de un archivo externo fue inspeccionado automáticamente.

No se creó un segundo gestor documental. Los cambios declarados en referencia, versión/hash o validación alimentan el hash de fuente y las comprobaciones de drift. Integraciones externas deberán actualizar estos metadatos mediante un flujo autorizado.

## 34. Staleness y refresh

Cambios de items, validación, fuentes vencidas, nueva configuración aplicable o contexto FEL/Gate material provocan STALE en la proyección actual. La historia conserva status, snapshot y assessment_hash originales. La detección GET no escribe eventos ni marca filas históricas; los comandos de refresh sí se auditan.

Refresh Preview devuelve persisted=false, diferencias de requisitos, cobertura, calidad/confianza, blockers y contexto. Refresh Apply genera un sucesor DRAFT con predecessor_id, nunca sobrescribe COMPLETED.

## 35. Basic Data frente a FEL

FEL gobierna la etapa de definición. Basic Data usa esa etapa para seleccionar requisitos técnicos y mínimos; no inicia, completa ni cambia una etapa. La prueba reutiliza un FEL-2 real y comprueba que las modificaciones de datos no alteran ProjectFELStatus ni la evaluación de definición.

## 36. Basic Data frente a PDRI

PDRI/Definition Maturity evalúa madurez de definición con su framework y score. Basic Data evalúa suficiencia y actualidad de los insumos técnicos. Un Project puede mantener el mismo PDRI histórico y pasar a Basic Data BLOCKED o STALE; no hay conversión entre porcentaje de cobertura y score PDRI.

## 37. Integración PDRI

El adaptador existente ProjectDefinitionService.investment_gate_evidence aporta contexto de etapa, resultado de definición, ID, revisión, score y hash. El snapshot Basic Data conserva las referencias disponibles y la pantalla las muestra como contexto de solo lectura.

No se duplicó un servicio PDRI ni se escribió un nuevo resultado de definición. Los cambios materiales del contexto pueden volver obsoleta la evaluación actual de Basic Data, manteniendo ambos históricos intactos.

## 38. Basic Data frente a Risk

Los datos técnicos pueden ser insumos de una evaluación de riesgos futura, pero Wave 2B no crea Risk Register entries ni RiskReadinessAssessment. Risk Governance, Basic Data y Risk Readiness tienen vocabularios y autoridades diferentes. Los hashes de las autoridades ajenas se contrastan antes y después de comandos Wave 2B.

## 39. Basic Data frente a Permit

Una línea base ambiental o un estudio técnico no equivale a un permiso concedido. La autoridad Permit Readiness continúa en su módulo; Basic Data no cambia el estado de permisos ni interpreta permisos históricos. Las referencias técnicas pueden ser reutilizadas a través de contratos futuros explícitos.

## 40. Basic Data frente a FIN y Commercial

La calidad de una fuente técnica no recalcula el modelo económico-financiero ni la estrategia contractual. FIN y Commercial permanecen providers y lifecycles existentes. No se calculan costos nuevos, compromisos, procurement ni ejecución contractual en este incremento.

## 41. Contrato para QRA futuro

Un consumidor QRA futuro deberá pedir evidencia Basic Data COMPLETED/READY/current, con Project ID, etapa, configuración/hash, coverage exacta, quality/confidence por requisito, critical_gaps, refs/versiones/hashes y as_of. Deberá consumir también la política efectiva de riesgo con scope, dates y policy hash.

Ese contrato no es un resultado QRA. Faltan acuerdos de fuentes de costo/cronograma, incertidumbres, distribuciones, correlaciones, metodología aprobada, SoD y validez de modelos. Esos componentes no se implementaron aquí.

## 42. Arquitectura de proveedores

BasicDataService.provider_evidence solo publica la evaluación COMPLETED más reciente que resuelva READY y no STALE para el Project autorizado. DRAFT, IN_REVIEW, BLOCKED, no configurado o fuente obsoleta no se ofrecen como evidencia disponible.

InvestmentEvidencePolicyService normaliza el payload al contrato existente: source_module, evidence_type, source_record_id, evidence_hash, as_of_date, readiness_status, source_current, warnings, blockers y evidence_refs. La integración es aditiva y de lectura.

## 43. Estado del registro de proveedores

BASIC_DATA_READINESS_PROVIDER se registra AVAILABLE con BASIC_DATA_READINESS y contrato BasicDataReadinessEvidence.v1 para scopes EACH_PROJECT y SELECTED_PROJECTS_ONLY. AVAILABLE en el catálogo indica capacidad del adaptador, no que todos los proyectos ya tengan una evaluación válida.

La disponibilidad de evidencia de cada Project depende de la evaluación gobernada actual. El registro no añade BASIC_DATA_READINESS a los requisitos publicados por defecto de Gate07J.

## 44. Recomendación de consumo Gate07J

Un prompt futuro debe definir en qué Gate profiles, Project Types y Governance Models se exige Basic Data, cuáles gaps bloquean y cuál vigencia es admisible. El cambio debe crear una nueva revisión de política y operar sobre nuevas rondas, preservando paquetes y decisiones históricas.

Wave 2B solo deja el provider compatible. No se publicó una política Gate nueva ni se forzó un blocker universal para FID.

## 45. Integración Five Case

Basic Data constituye una fuente potencial del Management Case y, según el contexto, de soporte del Economic Case. La implementación existente de Business Case incluye un aviso de fuente Basic Data aún no integrada; Wave 2B no lo sustituye con evidencia ficticia ni modifica BusinessCaseVersion históricos.

El adaptador de Gate queda disponible. El registro/selección explícita de esta fuente en Business Case y el refresh gobernado de nuevas versiones son deuda futura, no un trabajo completado en este incremento. Se preserva el lifecycle Five Case vigente.

## 46. ADMIN Basic Data

Basic Data Readiness Configuration se integra en Project Definition & Investment Case Configuration. El editor compartido expone categorías, requisitos, tailoring, stage_rules, disponibilidad, calidad, confianza, vigencia, blockers, coverage, scope/herencia, SoD y numbering.

La edición es declarativa por secciones JSON, con preview persisted=false y errores del backend; clone, guardar, publicar, archivar e historia siguen el contrato gobernado. No hay botones de crear items, validar evidencia o completar evaluaciones live dentro de ADMIN.

## 47. USER Basic Data

Basic Data Readiness se ubica en la fase USER Project Definition & Investment Case del blueprint actual. Incluye selección/búsqueda paginada de Project, requisitos, registro paginado, formulario de datos/fuentes, validación, resumen de gaps/readiness, contexto FEL/PDRI, historia y lifecycle de evaluación según permisos.

También muestra Risk Governance Context read-only. Los permisos y estados del backend determinan allowed_actions por Project/entidad. No se editan políticas desde USER.

## 48. Matriz ADMIN/USER

| Acción | ADMIN Configuration | USER operativo |
| --- | --- | --- |
| Editar Capacity/Appetite/Thresholds | Con permiso específico, DRAFT | No |
| Editar requisitos Basic Data | Con permiso específico, DRAFT | No |
| Preview/publish/archive políticas | Permiso y SoD | No |
| Crear/editar/validar items | No por rol config-only | Según permisos Project |
| Crear/submit evaluación | No por rol config-only | Preparador autorizado |
| Complete evaluación | No por rol config-only | Revisor independiente autorizado |
| Leer contexto/historia | Según permisos y scope | Según permisos y scope |

Cambiar modo visual no cambia la identidad ni concede permisos. Un actor puede tener ambos conjuntos de permisos explícitamente; la API valida cada operación.

## 49. Reutilización de identidad Project

Toda evidencia usa EnterpriseWorkspace.id con workspace_type_code=project y tenant_id. El Project legacy del encabezado general sigue existiendo para su contexto operativo anterior; no se confunde con la identidad canónica usada por los nuevos dominios estratégicos.

Los selectores se limitan al ámbito autorizado y los resolutores usan el árbol empresarial existente. IDs externos de otros tenants o de Workspaces no Project son rechazados/ocultados según el contrato.

## 50. Roles y permisos

Se añadieron trece permisos: risk_governance.read/admin.configure/admin.publish; basic_data.read, item.create/edit/validate, assessment.create/submit/review/complete y admin.configure/publish. Se ampliaron roles existentes, sin crear un catálogo paralelo de usuarios o roles.

project_definition_manager prepara y revisa; definition_assessor prepara/valida pero no completa; definition_reviewer revisa/completa; project_definition_viewer lee. project_definition_configuration_admin y configuration_admin configuran sin derechos live implícitos. Los roles Risk Readiness reciben lectura de política; risk_configuration_admin recibe configuración de riesgo. organization_admin conserva administración integral, sujeta a SoD.

La consulta RBAC ahora exige SecurityRole activo del tenant incluso para permisos sin whitelist de roles. Los routers nuevos usan bootstrap=False: las lecturas no siembran permisos ni políticas. El bootstrap es una operación explícita.

## 51. Separación de funciones

La política Basic Data por defecto requiere author_cannot_publish y preparer_cannot_complete; Risk usa preparer_cannot_publish. La publicación comprueba autor original y todos los editores del DRAFT; la obligación heredada de la política fuente queda capturada en SecurityEvent. Un editor no puede desactivar SoD y autopublicar ese mismo DRAFT.

Para evaluaciones, completar requiere permiso propio y actor independiente de preparación/submisión según la política capturada. Los cambios de la fuente/configuración invalidan la continuidad del material revisado. El modo visual ADMIN no otorga una excepción a estas reglas.

## 52. ETag y concurrencia

Se reutilizan los parsers If-Match y writer ETag del router Portfolio Review. Las entidades mutables exponen version o revision_version. Una versión anterior provoca 412 ETAG_MISMATCH y no persiste cambios; omitir el header obligatorio también se rechaza.

Las tablas live usan version_id_col con incremento explícito. Las políticas published son inmutables por contenido y se modifican mediante clone/sucesor, no mediante update de la misma versión.

## 53. Idempotencia

BasicDataCommand conserva tenant/key, command_type, request_hash, result_json y actor. El mismo comando y payload repiten el resultado sin duplicar items, evaluaciones o publicaciones; una key reutilizada con payload diferente genera conflicto. Los recibos son inmutables.

Risk Governance reutiliza SecurityEvent como recibo, con bloqueo de Tenant y metadata del request/result. Clone/publish/archive conservan resultados originales incluso si la entidad cambió después. Cada retry vuelve a pasar la autorización actual; el recibo no constituye un bypass de permisos.

## 54. SecurityEvent

Se auditan clone/update/publish/archive de ambas configuraciones, además del seed explícito Basic Data; creación, actualización y validación de items; creación, submit, complete y refresh de evaluaciones. El bootstrap neutral Risk no emite un evento seed propio. Los eventos conservan actor, tenant, target y metadata con referencias/hashes. La detección de staleness en GET es deliberadamente no persistente; los cambios y refresh que la producen sí dejan auditoría.

No se agregaron writes ocultos a GET/preview/effective. Las pruebas HTTP capturan INSERT/UPDATE/DELETE para comprobar esa frontera.

## 55. Diseño de persistencia

Risk Governance usa AdminConfiguration y SecurityEvent existentes. Basic Data añade project_basic_data_items, basic_data_readiness_assessments y basic_data_commands. Los índices cubren tenant/Project/category/validation/status/history; los constraints aseguran estados válidos, requisitos únicos, numeración y hashes al completar.

Los snapshots y evidence_refs usan JSON, evitando tablas por categoría/industria. La protección ORM y API no equivale a un trigger contra un administrador SQL: impedir escrituras directas privilegiadas requiere controles de infraestructura adicionales.

## 56. Contenido del snapshot

El snapshot congela configuración ID/revision/hash, Project, contexto FEL/PDRI, requisitos efectivos, estado de cada item, source references/version/hash, coverage, dimensiones de suficiencia, critical_gaps, warnings/blockers, readiness y as_of. assessment_hash identifica el paquete completo.

La respuesta histórica usa ese snapshot, no los items live para reinterpretar su resultado. allowed_actions puede variar según el actor actual; esa metadata de UI no forma parte del resultado técnico histórico ni altera el hash.

## 57. Migración

20261008_0065 depende de 20261005_0064 y añade exclusivamente las tres tablas Basic Data. No reescribe 0064, no renombra tablas anteriores ni crea Risk Governance persistence adicional. Downgrade elimina solo las tablas nuevas, por lo que no debe ejecutarse sobre datos reales sin respaldo.

Las pruebas up/down/up aprobaron en SQLite y PostgreSQL sobre una superficie mínima de claves foráneas, con marcadores de autoridades históricas intactos. Esta comprobación aísla el nuevo DDL y no pretende ejecutar desde cero todas las 64 migraciones previas. La base local habitual se respaldó en formato PostgreSQL custom antes de aplicar 0065; se verificaron 3.433 entradas del catálogo del respaldo. La migración local aprobó y dejó una cabeza única 20261008_0065, una política Risk neutral published y una Basic Data draft, sin items ni evaluaciones de prueba en ese ambiente.

## 58. API

Prefijo general /api/v1. Risk: /risk-governance/admin/configurations, detalle/history, clone, update, publish, archive, effective-preview, operators, effective y threshold-evaluation. Basic: /basic-data/options, projects/{id}/requirements/items/assessments/current-readiness, items/{id} y validate, assessments/{id} y preview/submit/complete/refresh-preview/refresh-apply, además de configuración ADMIN.

Los comandos autorizan permission+scope, tenant, tipo de Workspace, estado, If-Match e idempotencia cuando corresponde. Las listas live y opciones Project usan page/page_size con límites del servidor. OpenAPI constituye la referencia exacta de verbos y payloads.

## 59. Navegación

strategicNavigationBlueprint.ts sigue siendo la única fuente de fases, módulos y vistas. Se agregan risk-governance-configuration y basic-data-configuration en ADMIN, y basic-data-readiness en USER. StrategicViewOutlet resuelve las tres vistas; applicationNavigation.ts solo amplía tipos compatibles.

Se conservan las fases existentes más cercanas del repositorio, sin crear una segunda jerarquía por el nombre conceptual del prompt. App.tsx no se amplió ni contiene condiciones específicas de los nuevos dominios.

## 60. Happy path PostgreSQL Basic Data

La suite reutiliza el mismo escenario de aceptación en una base PostgreSQL wave2b desechable: Enterprise/Project CAPITAL_OWNER/MINING, política publicada por actor independiente, FEL-2 real, requisitos efectivos, creación y validación de evidencia, evaluación/submisión/completion, coverage exacta y provider READY/current. No se usan mocks de base de datos.

PostgreSQL: 37 escenarios aprobados en 476,14 s, más dos pruebas independientes de provider/escala aprobadas en 190,17 s. La prueba de migración PostgreSQL up/down/up aprobó en 37,19 s. Evidencias: postgres-first.log y provider-scale-postgres.log, dentro de outputs/.qa/wave2b-risk-basic-data. La base aislada evita poblar el ambiente habitual con datos de pruebas.

## 61. Ejemplo minero

El escenario de diez categorías configura el conjunto en JSON. La política FEL-2 acepta PRELIMINARY con evidencia y validación; FEL-3 exige VALIDATED/HIGH. Geotechnical es obligatorio y blocking. La fixture no transforma esas categorías en reglas universales del producto.

El código de producción no incluye un listado minero obligatorio ni infiere Governance Model de la industria. Los casos adicionales cambian Project Type/Governance Model para comprobar el tailoring independiente.

## 62. Prueba de requisito crítico faltante

test_basic_data_90_percent_cannot_hide_critical_missing_geotechnical configura diez requisitos y aporta nueve. Se comprueba required_count=10, satisfied_count=9, coverage=90 y critical_gap geotechnical, con overall BLOCKED. La prueba de partial/missing comprueba que esos conteos no se oculten en un promedio.

## 63. Prueba de fuente vencida

test_basic_data_expired_source_marks_current_stale_not_historical_snapshot completa READY y desplaza la fecha de evaluación más allá de la vigencia. La proyección actual devuelve STALE; el snapshot y el hash COMPLETED permanecen iguales. No se altera la fecha histórica para simular una nueva evaluación.

## 64. Prueba de calidad por etapa

test_basic_data_stage_preliminary_acceptable_fel2_blocked_fel3_pdri_unchanged contrasta la misma evidencia PRELIMINARY contra reglas FEL-2 y FEL-3. La segunda falla por su política más exigente, sin rechazo global de PRELIMINARY ni modificación de la evaluación PDRI existente.

## 65. Prueba de independencia PDRI

Los escenarios construyen un FEL real con ProjectDefinitionAssessment completada y comparan IDs, scores, hashes y ProjectFELStatus antes/después. Cambiar un Basic Data Item o su readiness no reescribe la evaluación de definición ni avanza la etapa.

El E2E USER también conserva el contexto de definición al crear, validar y completar evidencia técnica. La comparación del snapshot excluye únicamente metadata de permisos del actor, no campos de evidencia.

## 66. Prueba de independencia Risk

test_wave2b_risk_policy_publication_preserves_real_completed_risk_readiness_evidence reutiliza el fixture Risk existente para crear ProjectRisk y evaluación COMPLETED antes de publicar una nueva política. Se comparan todas sus columnas canónicas y hashes después, no solo conteos vacíos.

Las demás pruebas snapshot comparan autoridades Risk, Definition, Gate y decisiones antes/después de los comandos de política. No se reinterpretan resultados anteriores con el nuevo apetito.

## 67. Prueba de independencia Gate

Las pruebas capturan hashes de las políticas Gate publicadas, InvestmentGatePreparation, evidencia/paquetes y InvestmentDecision antes/después. El provider Basic Data se consulta por contrato aditivo sin cambiar requirements por defecto. Los snapshots históricos de FID quedan bajo las regresiones Gate07K/07L existentes.

Registrar un provider no implica que una política publicada lo exija. El guardrail estático comprueba esa distinción además de las pruebas comportamentales.

## 68. Prueba de herencia de riesgo

La suite verifica política Enterprise, override Business Unit y override Portfolio, incluyendo fechas efectivas, versiones futuras, contexto más específico, strategic_theme, investment_category y filtros de cada statement. Un actor scoped no puede retarget una política heredada ni acceder a un hermano.

## 69. Prueba de umbrales

Los casos parametrizados verifican comparaciones y rangos, operadores categóricos y booleanos, AT_THRESHOLD, NOT_EVALUABLE, unidades/monedas y payloads inválidos. La respuesta contiene contexto, no decisiones de Project. Se preservan las autoridades ajenas y no se ejecutan expresiones configurables.

## 70. Regresión Governance Model

CAPITAL_OWNER opta por el contexto owner cuando la política aplica. CONTRACTOR_DELIVERY y DIRECT_INTERNAL se prueban como clasificaciones diferentes, conservando compatibilidad legacy. No se introdujo una obligatoriedad universal de capital governance en proyectos de entrega o internos.

## 71. Regresión Project Type

Los clasificadores reutilizados leen metadata canónica y la fuente de creación existente. Las pruebas varían MINING y otros tipos con el mismo Governance Model, y el modelo con el mismo Project Type. MINING no se equipara a CAPITAL_OWNER.

## 72. E2E USER real

Chromium utiliza frontend 5517 y API 8814 sobre PostgreSQL wave2b_browser, con VITE_FRONTEND_VALIDATION_MODE=false. No hay interceptores de API ni fake success. Dos actores realizan registro, fuentes, validación, preview, submit y completion, con historia, gaps, contexto FEL/PDRI y aislamiento de ADMIN.

Resultado final: aprobado dentro de los dos recorridos Chromium completos, ambos PASS en 2,3 minutos después del cierre de seguridad legacy. Evidencia en outputs/.qa/wave2b-risk-basic-data/browser-security-closeout.log y browser-security-closeout-results. La ejecución anterior de 2,7 minutos también aprobó y se conserva. Las identidades y la contraseña demo pertenecen únicamente a la base desechable.

## 73. E2E ADMIN Basic Data real

El recorrido navega a la configuración canónica, inspecciona categorías/requisitos/tailoring/quality/confidence/freshness/blocking/coverage/herencia/SoD, modifica una política, preview persisted=false, clone/save y publicación por una segunda autoridad, seguido de archive. No se ofrecen operaciones live de evaluación en la vista ADMIN.

Resultado final: aprobado en el recorrido ADMIN combinado, dentro de la ejecución final de dos tests PASS en 2,3 minutos. Incluye tres llamadas legacy denegadas contra su DRAFT antes de publicar mediante la autoridad dedicada. Los intentos previos y sus traces se conservaron; se corrigieron un error de tipado en una prueba UI y la dependencia Redis del stack aislado, sin debilitar permisos ni sustituir el backend.

## 74. E2E ADMIN Risk Governance real

El recorrido modifica dimensiones, Capacity, Appetite y Thresholds reales, verifica aplicabilidad/operadores/overrides/fechas/herencia/SoD, preview, clone, save, publish independiente y archive. No se opera Risk Register. Se prueban también los intentos USER por ruta y API directa.

Resultado final: aprobado en el mismo recorrido ADMIN combinado, incluyendo tres llamadas legacy denegadas y publicación posterior por una segunda autoridad. La UI usa allowed_actions del backend para no ofrecer publicación al autor ni comandos a un lector; la clonación sin destino explícito conserva el scope de la política original.

## 75. Seguridad por ruta directa

Las pruebas verifican USER 403 al mutar ambas configuraciones, config-only sin completion live, validador sin permiso de review/completion, Project hermano y tenant ajeno, roles inactivos, If-Match obsoleto, claves idempotentes mal reutilizadas y ausencia de writes en lecturas. Un menú oculto no se considera prueba de seguridad.

Los routers siempre hacen autorización actual antes del servicio. La metadata allowed_actions ayuda a la UI, pero la denegación backend continúa siendo autoritativa.

Se cerró además un acceso transversal de la API antigua /admin-configuration: create, PATCH, clone y publish rechazan los dos kinds gobernados con HTTP 409 GOVERNED_CONFIGURATION_API_REQUIRED y remiten a su API específica. Un tenant configurator ya no puede eludir SoD, scope, ETag o idempotencia por esa ruta. Ocho pruebas SQLite aprobaron en 74,99 s y los mismos ocho casos PostgreSQL aprobaron en 95,41 s, verificando las tres situaciones draft/published/archived, aliases normalizados, cero escrituras y preservación de filas/hashes; el lifecycle de catálogos y la lectura overview permanecen compatibles. Chromium añade seis intentos legacy ADMIN al recorrido de publicación independiente.

## 76. Regresión Wave 3A

Se ejecuta la suite Periodic Portfolio Review completa: sesiones, snapshots, acciones request-only, SoD, scopes, staleness, refresh, historia e independencia de fuentes. Wave 2B no modifica el contrato de snapshot de Portfolio Review ni añade semántica de decisiones a sus acciones.

Wave 3A aprobó sus 33 casos dentro de la ejecución estratégica integrada de 94 casos, todos aprobados en 979,76 s. Evidencia: strategic-regressions.log. Los avisos de escritura de pytest_cache son del entorno Windows y no representan fallos funcionales.

## 77. Regresión Wave 2A

La suite de Capital Allocation comprueba lifecycle, planes, Buckets, clasificaciones y contexto de Portfolio. Wave 2B no escribe Allocation Plans ni clasificación de capital. Sus siete casos aprobaron dentro de la ejecución integrada de 94 casos.

## 78. Regresión Wave 1

Se ejecutaron Capital Planning y sus pruebas RBAC HTTP: seis casos aprobados dentro de la regresión integrada. Se preservan Capital Demand, ciclos, relaciones de origen y SoD; no se añade contexto obligatorio de Basic Data a Demand.

## 79. Regresión Gate/FID

Se incluyen Gate07J-FEL, Gate07J-RISK, Gate07J-PERMIT, Gate07J-EVID-2, Evidence Policy, Gate07K y Gate07L: 48 casos aprobados dentro de la regresión integrada. La ampliación del catálogo/provider se prueba sin modificar requisitos ni decisiones históricas.

## 80. Observación de performance

Items, assessments y Project options tienen paginación server-side con page_size máximo 200. Los selectores scoped resuelven descendientes con una lectura batched de jerarquía; el registro evalúa requisitos e items en lote, sin query por fila. Se prueban conteos de consultas y se indexan Project/category/validation/status/history.

Los nuevos resolutores no inventan una caché global mutable. Se usa caché de permisos por request cuando corresponde; cualquier caché de política futura deberá incluir tenant, scope, contexto, fechas y hash. La prueba de escala creó 400 requisitos/items y 1.000 Projects: evaluar cobertura, pedir una página de 100 items y una página de 100 Projects requirió 23 consultas; 1,371 s en SQLite y 2,525 s en PostgreSQL. En el localhost habitual, una consulta durante validaciones concurrentes tardó 50,66 s y superó el timeout del cliente; su repetición posterior autenticada aprobó en 1,435 s. Es una observación funcional controlada, no un benchmark concurrente ni un SLA de producción.

## 81. Deuda técnica y límites

El editor ADMIN declarativo es utilizable pero puede evolucionar a formularios tipados por dominio. Las fuentes externas no se verifican automáticamente; su actualidad depende del metadata gobernado. La inmutabilidad está protegida en servicio/ORM, no por un trigger contra acceso SQL privilegiado. No se ejecutó un load test ni un pipeline remoto.

Business Case requiere consumo futuro explícito y refresh de nuevas versiones; Gate necesita una política nueva si decide exigir Basic Data. El esquema completo de 64 migraciones previas no se reconstruyó desde cero como parte de la prueba aislada del DDL 0065. El lint frontend aprobó con nueve warnings preexistentes en BimIfcModelViewer; no se modificó ese módulo. Ruff requirió formato mecánico de 25 archivos app/tests, sin cambios de lógica, para coincidir con la versión 0.16.3 fijada en CI. No se deben confundir esas limitaciones con funcionalidades terminadas.

## 82. Evaluación de preparación para QRA

| Prerrequisito | Estado arquitectónico | Brecha para QRA |
| --- | --- | --- |
| Risk Register y Risk Readiness | Existentes, autoridades preservadas | Definir inputs probabilísticos aceptados |
| Risk Appetite y Thresholds | Nuevos, versionados y efectivos | Política de consumo/consecuencia QRA |
| Basic Data Readiness | Nuevo dominio de evidencia gobernada | Providers técnicos específicos y calidad de entradas |
| FEL Stage | Existente, contextual | Gate de validez para el modelo |
| PDRI/Definition Maturity | Existente, contextual | Relación metodológica, sin convertir score en percentil |
| FIN context | Existente | Versionado económico del escenario QRA |
| Costo/cronograma | Fuentes operativas existentes | Readiness específica, distribuciones, incertidumbres y correlaciones |

No están demostrados todos los prerrequisitos de QRA. Wave 3B Owner Capability aborda la capacidad del owner para gobernar y ejecutar la inversión; Wave 4 QRA aborda incertidumbre probabilística y requiere metodología/fuentes adicionales. La existencia de Wave 2B no hace de QRA la siguiente etapa automática.

## 83. Estado final del release y matriz de aceptación

Estado exclusivo: RISK_GOVERNANCE_AND_BASIC_DATA_READINESS_RELEASE_VALIDATED. final_output = READY_FOR_GOVERNED_RISK_APPETITE_AND_BASIC_DATA_EVIDENCE. BASIC_DATA_READINESS_PROVIDER = AVAILABLE. Estos estados corresponden al incremento y su validación local observada; no certifican producción ni una ejecución remota de CI. No se realizó commit/push ni se ejecutó GitHub Actions remoto.

El frontend habitual responde HTTP 200 en http://127.0.0.1:5173/app; el API 8000 responde health/ready y lectura autenticada de la configuración Basic Data con HTTP 200 después del despliegue del guard. API, worker y beat fueron reconstruidos; PostgreSQL y Redis permanecen saludables. La base local no recibió las fixtures de evidencia de los escenarios aislados. El respaldo previo, los traces y la QA del documento quedan locales e ignorados por Git para evitar publicar datos del ambiente.

| Validación | Resultado | Evidencia |
| --- | --- | --- |
| SQLite Basic Data | 18 PASS / 251,09 s | basic-data-sqlite-final.log |
| SQLite Risk Governance | 18 PASS / 265,81 s | outputs/.qa/wave2b-risk-sqlite-final.log |
| SQLite provider y escala | 2 PASS / 100,73 s | provider-scale-sqlite.log |
| SQLite guard legacy | 8 PASS / 74,99 s | legacy-configuration-guard-sqlite.log |
| SQLite migración reversible | 1 PASS / 39,93 s | sqlite-migration.log |
| PostgreSQL aceptación y esquema | 37 PASS / 476,14 s | postgres-first.log |
| PostgreSQL provider y escala | 2 PASS / 190,17 s | provider-scale-postgres.log |
| PostgreSQL guard legacy | 8 PASS / 95,41 s | legacy-configuration-guard-postgres.log |
| PostgreSQL migración reversible | 1 PASS / 37,19 s | postgres-first.log |
| Regresiones estratégicas | 94 PASS / 979,76 s | strategic-regressions.log |
| Frontend Vitest focalizado | 38 PASS / 44,58 s | frontend-vitest-closeout.log |
| Chromium USER y ADMIN | 2 PASS / 2,3 min | browser-security-closeout.log y traces |
| TypeScript y build Vite | PASS / build final 36,30 s | browser-frontend-build-closeout.log |
| Ruff check y format CI | PASS / 386 archivos | backend-lint-closeout.log |
| ESLint y Prettier src | PASS / 9 warnings previos | frontend-eslint-release.log y frontend-prettier-release.log |
| Guardrails arquitectónicos | PASS | validate_wave2b_release_guardrails.py |

Salvo la ruta completa indicada para Risk SQLite, los logs de la tabla están en outputs/.qa/wave2b-risk-basic-data. Los conteos son ejecuciones por superficie, con casos compartidos; no deben sumarse como funcionalidades o pruebas únicas. Las suites backend focalizadas se ejecutaron sin cobertura global: no se afirma haber medido un umbral global de cobertura.

Las referencias R corresponden a backend/tests/test_risk_governance_wave2b.py; B a test_basic_data_wave2b.py; PG a tests/postgres/test_wave2b_risk_basic_data_postgres.py; M a test_wave2b_migration y su variante PostgreSQL; UI a tests frontend; E2E a wave2b-risk-basic-data.spec.ts; G a la suite estratégica integrada; A a validate_wave2b_release_guardrails.py; L a test_wave2b_legacy_configuration_guard.py. La matriz siguiente relaciona los 73 criterios con las evidencias aprobadas, además de su verificación documental.

| ID | Criterio de aceptación | Evidencia verificada | Estado |
| --- | --- | --- | --- |
| 1 | Risk Capacity governance | R policy lifecycle/context | PASS |
| 2 | Risk Appetite governance | R policy lifecycle/context | PASS |
| 3 | Risk Threshold governance | R controlled operators | PASS |
| 4 | Policy versioned/effective-dated | R effective dates/successors | PASS |
| 5 | Risk policy inheritance | R Enterprise/BU/Portfolio | PASS |
| 6 | Controlled threshold operators | R numeric/category/boolean | PASS |
| 7 | Appetite distinto de Readiness | R real completed Risk history | PASS |
| 8 | Appetite distinto de QRA | A authority boundaries | PASS |
| 9 | No Risk Register mutation | R authority snapshots | PASS |
| 10 | No historical Risk reinterpretation | R completed Risk evidence | PASS |
| 11 | Basic Data domain | B lifecycle | PASS |
| 12 | Configurable categories | B mining policy | PASS |
| 13 | Project Type tailoring | B classifiers/tailoring | PASS |
| 14 | FEL Stage tailoring | B FEL2/FEL3 | PASS |
| 15 | Gate Profile tailoring | B profile applicability | PASS |
| 16 | Availability separated | B exact per-item results | PASS |
| 17 | Validation separated | B validation/refresh | PASS |
| 18 | Quality separated | B stage-aware quality | PASS |
| 19 | Confidence separated | B requirement minima | PASS |
| 20 | Readiness distinto de quality/confidence | B dimensions/critical gaps | PASS |
| 21 | Exact requirement coverage | B 10 required, 9 satisfied | PASS |
| 22 | Critical blocker semantics | B geotechnical BLOCKED | PASS |
| 23 | Freshness | B source expiry | PASS |
| 24 | Source lineage | B refs/hash/version | PASS |
| 25 | Completed immutable | B ORM/history | PASS |
| 26 | Assessment history | B successor/refresh | PASS |
| 27 | Staleness | B current vs frozen result | PASS |
| 28 | Basic Data distinto de FEL | B FEL context unchanged | PASS |
| 29 | Basic Data distinto de PDRI | B score/hash unchanged | PASS |
| 30 | Basic Data distinto de QRA | A no simulation | PASS |
| 31 | Basic Data distinto de Permit | A/G Permit authority | PASS |
| 32 | PDRI score/hash not mutated | B/E2E real Definition history | PASS |
| 33 | FEL Stage not auto-mutated | B ProjectFELStatus | PASS |
| 34 | Existing FEL provider reused | B investment_gate_evidence | PASS |
| 35 | BASIC_DATA_READINESS_PROVIDER AVAILABLE | PG provider registry/payload | PASS |
| 36 | Provider only current governed evidence | B READY, DRAFT/stale denied | PASS |
| 37 | Published Gate07J policy unchanged | B/R/A policy snapshots | PASS |
| 38 | Historical Gate07J packages unchanged | R/G Gate package snapshots | PASS |
| 39 | Historical Gate07K/FID unchanged | R/G decisions | PASS |
| 40 | Future Gate compatibility documented | Sections 42–44 | PASS |
| 41 | Future QRA contract defined | Sections 41/82 | PASS |
| 42 | ADMIN Risk config only | UI/E2E/R direct security | PASS |
| 43 | ADMIN Basic config only | UI/E2E/B config-only actor | PASS |
| 44 | USER live Basic Data only | UI/E2E/B permissions | PASS |
| 45 | Direct-route security | B/R HTTP 403; L/E2E legacy 409 | PASS |
| 46 | SoD | B/R editor downgrade; L no legacy bypass | PASS |
| 47 | ETag | B/R HTTP 412 | PASS |
| 48 | Idempotency | B/R replay and conflict | PASS |
| 49 | SecurityEvent | B/R event metadata | PASS |
| 50 | Migration reversible | M SQLite/PostgreSQL | PASS |
| 51 | Canonical Project Workspace identity | B/R workspace scopes | PASS |
| 52 | Navigation source of truth | UI/A blueprint | PASS |
| 53 | App.tsx not expanded | UI/A outlet | PASS |
| 54 | PostgreSQL happy path | PG real PostgreSQL | PASS |
| 55 | Mining configuration example | B ten configured categories | PASS |
| 56 | Missing critical data | B 90 percent BLOCKED | PASS |
| 57 | Stale source | B expiry/current projection | PASS |
| 58 | Stage-aware quality | B PRELIMINARY stage tailoring | PASS |
| 59 | PDRI independence regression | B/E2E immutable definition | PASS |
| 60 | Risk independence regression | R/G real Risk history | PASS |
| 61 | Gate independence regression | B/R/G unchanged policies | PASS |
| 62 | Governance Model regression | B/R/G independent classifier | PASS |
| 63 | Project Type regression | B/R independent classifier | PASS |
| 64 | Browser USER | E2E Chromium real backend | PASS |
| 65 | Browser ADMIN Basic Data | E2E Chromium real backend | PASS |
| 66 | Browser ADMIN Risk Governance | E2E Chromium real backend | PASS |
| 67 | Wave 3A regression | G portfolio review | PASS |
| 68 | Wave 2A regression | G capital allocation | PASS |
| 69 | Wave 1 regression | G capital planning/RBAC | PASS |
| 70 | Gate/FID regression | G FEL/RISK/PERMIT/EVID2/K/L | PASS |
| 71 | No QRA implementation | A excluded commands | PASS |
| 72 | No Owner Capability implementation | A module scope | PASS |
| 73 | No operational scope | A no foreign authority writes | PASS |

## 84. Única recomendación de siguiente incremento

Recomendar Wave 3B — Owner Capability Readiness. La capacidad organizacional del owner sigue siendo una brecha material de gobierno para FID y puede desarrollarse reutilizando roles, responsabilidades, políticas y evidencia gobernada. QRA requeriría además cerrar los acuerdos metodológicos y la readiness de fuentes de costo/cronograma señalados en la sección 82.

Esta es la única recomendación de siguiente incremento. No se implementó Owner Capability ni QRA, no se cambió la política Gate y se respeta el STOP boundary hasta una nueva solicitud explícita.
