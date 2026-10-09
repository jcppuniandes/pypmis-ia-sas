# Informe técnico Wave 3B Owner Capability Readiness

P&Pmis Construction AI

**Estado actual:** OWNER_CAPABILITY_READINESS_RELEASE_VALIDATED

Periodo de trabajo local: 2026-10-07 a 2026-10-08. Fecha del informe: 2026-10-08, America Bogota.

## 1. Resumen ejecutivo

Implementamos y validamos Owner Capability Readiness, con política gobernada en ADMIN y evaluación por Project Workspace en USER. El dominio evalúa si el propietario dispone de gobierno, responsabilidad, mecanismos y capacidades suficientes para desarrollar y supervisar una inversión. PostgreSQL aprobó 74 casos, Chromium aprobó los dos flujos reales y las regresiones estratégicas aprobaron 140 casos. La misma imagen probada quedó desplegada en localhost, con migración aditiva 0066 y datos existentes preservados. El proveedor está disponible, pero cada proyecto necesita una evaluación COMPLETED READY actual para aportar evidencia elegible; no se publicaron requisitos Gate ni se fabricaron evaluaciones locales.

## 2. Baseline real del repositorio

La rama era main y el commit 9cb0969abb5d48cc25b0c6a935b11e6bd7afd16f. Había 76 archivos rastreados modificados, 7394 inserciones y 949 eliminaciones, además de archivos nuevos de incrementos previos. Se revisaron status, diff completo, diff stat, los últimos 15 commits y alembic heads. Se preservó el trabajo local. El repositorio y PostgreSQL estaban en 20261008_0065. Wave 2B constaba como RISK_GOVERNANCE_AND_BASIC_DATA_READINESS_RELEASE_VALIDATED y su proveedor Basic Data estaba disponible. No se recibió autorización para commit o push.

## 3. Decisión arquitectónica Wave 3B

La decisión registrada en docs/78-adr-wave3b-owner-capability-readiness.md reutiliza la configuración versionada, identidad Project, numeración, permisos y auditoría existentes. El agregado conserva ítems, brechas y mitigaciones estructurados, sin un motor de tareas. La historia COMPLETED se separa de la proyección actual de vigencia.

## 4. Posición en la arquitectura objetivo

La capacidad del propietario ocupa la fase estratégica existente de definición y caso de inversión, equivalente a Business Case and Investment Development del diseño. Enterprise Strategy Manager continúa siendo el macroproceso. La evidencia puede apoyar Management Case y un consumo futuro por Gate; el incremento no crea otra fase ni cambia decisiones.

## 5. Matriz de autoridad

| Dominio | Autoridad de escritura | Límite |
| --- | --- | --- |
| Owner Capability | Requisitos, evaluaciones, brechas y mitigaciones del propietario | No staffing ni capacidad numérica |
| Resource Planning | Demanda, capacidad y escenarios | Sólo contexto para Owner Capability |
| Commercial Strategy | Estrategia y versiones comerciales | No se duplica ni se modifica |
| FEL y PDRI | Etapa y madurez de definición | Consulta de identificadores y hashes |
| Risk y Basic Data | Riesgos y datos técnicos gobernados | No se reevaluán desde Owner Capability |
| Gate y FID | Paquetes y decisiones de inversión | Sin mutación automática |

## 6. Reutilización antes de creación

| Componente existente | Uso en Wave 3B | Decisión |
| --- | --- | --- |
| AdminConfiguration | Framework, reglas, herencia y revisión | Reutilizado |
| AdminNumberSequence | Identidad visible OCA | Reutilizado |
| EnterpriseWorkspace | Project y jerarquía | Sin identidad duplicada |
| ProjectDefinitionService | Clasificadores y FEL/PDRI | Sólo lectura |
| Commercial y Resource Planning | Referencias de contexto | Autoridad preservada |
| Risk Governance y Risk Readiness | Política y resumen actuales | Sólo lectura |
| Basic Data y Benefits | Evidencia y responsabilidades | Sin reevaluación ni registro nuevo |
| Investment Evidence registry | Contrato normalizado del proveedor | Sin segundo registro |
| RBAC y SecurityEvent | Permisos, alcance y trazabilidad | Reutilizados |
| ETag e idempotencia | Conflictos y reintentos | Patrones existentes |
| strategicNavigationBlueprint | Pantallas por modo | Sin ampliar App.tsx |

## 7. Definición de capacidad del propietario

Se evalúa la capacidad organizacional para patrocinar, gobernar, definir, contratar, controlar, supervisar y gestionar la transición de una inversión. La capacidad se expresa mediante requisitos, funciones responsables, madurez, evidencia y brechas. No se deduce solamente del número de personas disponibles.

## 8. Límite con planificación de recursos

Resource Planning conserva FTE, HOURS, CREW_EQUIVALENT, capacidad y demanda. Owner Capability registra si la estrategia de acceso a recursos y los mecanismos de supervisión satisfacen requisitos. Un escenario restringido aporta contexto; el dominio no nivela ni modifica recursos.

## 9. Límite con staffing

No se incorporan asignaciones nominales, hojas de vida, turnos, timesheets ni competencias individuales. Las referencias a roles, funciones y responsables de mitigación expresan rendición de cuentas y no una plantilla de personal.

## 10. Límite con contratistas y proveedores

La entidad evaluada es el propietario o patrocinador. Se puede evaluar su capacidad de administrar contratos y supervisar proveedores; no se califica EPC, contratistas, consultores ni desempeño de proveedores.

## 11. Límite con readiness operacional

La capacidad de gobernar la transición no equivale a preparación para operar el activo. No se implementan repuestos, mantenimiento, comisionamiento, SOP, formación de operadores ni aceptación operacional.

## 12. Límite con FEL y PDRI

La definición del proyecto y su puntuación PDRI permanecen bajo Project Definition. Owner Capability consume etapa, evaluación completada y referencias de versión y hash. Un cambio material puede volver obsoleta la evidencia de capacidad sin alterar el score ni la historia de definición.

## 13. Límite con riesgos

Las brechas pueden referenciar Risk IDs, sin crear riesgos automáticamente. Risk Register, Risk Readiness y Risk Governance mantienen su autoridad. La evidencia de capacidad no constituye QRA ni una conclusión probabilística.

## 14. Límite con estrategia comercial

Commercial Strategy conserva modelo, paquetes, contratación y asignación de riesgos. Owner Capability evalúa la capacidad del propietario para aplicar y supervisar esa estrategia. El contexto comercial se captura por referencia; sus cambios se controlan mediante vigencia.

## 15. Correspondencia con Five Case

Management Case es el consumidor principal futuro. Commercial Case puede utilizar la capacidad de gobierno contractual y Strategic Case el patrocinio. Una nueva revisión Business Case podrá referenciar el proveedor; no se copia el agregado completo ni se modifica una revisión completada.

## 16. Framework configurable

ADMIN define el framework mediante AdminConfiguration. Las políticas publicadas son inmutables y disponen de revisión y hash. El seed no publica requisitos reales ni fabrica evaluaciones; la configuración debe aprobarse explícitamente.

## 17. Dimensiones configurables

Las dimensiones pertenecen a la política y no a tablas o ramas por sector. Pueden incluir gobierno, patrocinio, gestión, controles, aseguramiento, contratación, interfaces, acceso a recursos y transición. El conjunto real lo define ADMIN.

## 18. Requisitos configurables

Cada requisito identifica código y dimensión, descripción, aplicabilidad, madurez y calidad mínimas, condición bloqueante, evidencia esperada y función responsable. Las reglas contextuales determinan mínimos por etapa o clasificación. No existe una lista fija de capacidades finales en el frontend.

## 19. Escala de madurez

La escala controla código, etiqueta, orden y descripción. Ejemplos como DEFINED e IMPLEMENTED son valores de política, no decisiones universales. Los requisitos se comparan con la escala vigente capturada por la evaluación.

## 20. Readiness y madurez

La madurez describe el estado de una capacidad; readiness expresa si todos los requisitos aplicables satisfacen la política. La misma madurez puede ser suficiente para FEL 2 y bloquear FEL 3. La interfaz muestra el resultado calculado por el backend.

## 21. Tailoring contextual

La política utiliza Governance Model, Project Type, industria, etapa FEL, perfil Gate, tamaño, complejidad, riesgo, incertidumbre y contexto comercial. El proyecto aporta clasificadores canónicos. Las diferencias sectoriales se expresan en configuración y no en lógica de Mining o Industrial.

## 22. Comportamiento por Governance Model

CAPITAL_OWNER es la aplicabilidad inicial. CONTRACTOR_DELIVERY y DIRECT_INTERNAL no reciben exigencias completas de capacidad del propietario por defecto. La política debe optar explícitamente por otros modelos; Project Type no sustituye Governance Model.

## 23. Progresión por etapa

La progresión de requisitos puede exigir gobierno y sponsor en FEL 1, controles y aseguramiento en FEL 2, y mecanismos de administración y supervisión en FEL 3. ADMIN controla las reglas concretas; el dominio no completa ni avanza etapas FEL.

## 24. Agregado de evaluación

Un Project Workspace tiene múltiples evaluaciones con identidad estable, versión y predecesor. El ciclo es DRAFT, IN_REVIEW y COMPLETED. Una evaluación completada congela el snapshot y la evidencia; la reevaluación genera un sucesor.

## 25. Modelo de ítems

Los ítems conservan código del requisito, madurez, calidad, confianza, fundamento, referencias, función responsable, referencias a roles y riesgos, fechas y notas de revisión. Las brechas son registros separados del mismo agregado vinculados por requisito. No se crean tablas por dimensión o nivel de madurez.

## 26. Modelo de brechas

Una brecha contiene código del requisito, descripción, severidad, condición bloqueante, estado, responsable, fecha objetivo y evidencia de cierre. Las acciones de fortalecimiento se registran como mitigaciones del mismo requisito. Una brecha abierta marcada como bloqueante impide READY; la etiqueta de severidad por sí sola no sustituye esa regla. La estructura está circunscrita a capacidad del propietario.

## 27. Modelo de mitigaciones

Las acciones de fortalecimiento se vinculan mediante requirement_code al requisito que agrupa la brecha y conservan enfoque, responsable, fecha, estado, evidencia y revisión. No existe una relación independiente por gap_id. La mera existencia de una acción no satisface el requisito. Su aceptación depende de reglas explícitas.

## 28. Capacidad interna y externa

La capacidad puede demostrarse mediante mecanismos internos, apoyo externo contratado o un modelo híbrido. La ausencia de capacidad interna no impone automáticamente un bloqueo si la política acepta apoyo externo gobernado. La aprobación y evidencia requerida siguen siendo obligatorias.

## 29. Referencias de evidencia

El dominio almacena referencias a charters, RACI, planes de controles, aseguramiento, interfaces, procedimientos y contratos de apoyo. Cada referencia debe identificar una fuente mediante source_reference o reference no vacío; un objeto vacío, sólo hash o sólo versión no acredita evidencia. La validación protege tanto los comandos actuales como la evaluación defensiva de agregados almacenados. Las versiones, hashes y fechas aportan trazabilidad y vigencia, sin constituir un repositorio documental ni verificar por sí mismos el contenido externo.

## 30. Calidad y confianza

El vocabulario legado EVIDENCE_QUALITY_STATES mezcla LOW_CONFIDENCE con calidad. La nueva escala de calidad distingue verificación y suficiencia de evidencia; confidence es otro campo. No se reescriben snapshots Basic Data ni paquetes Gate históricos.

## 31. Readiness por dimensión

El backend agrupa resultados de los requisitos aplicables por dimensión configurada. Cada resumen devuelve cantidades required y satisfied, junto con status. El detalle de pendientes, brechas y bloqueos permanece en requirements y en el resultado global. La conclusión global respeta las reglas de cobertura y los bloqueos explícitos.

## 32. Denominador exacto

La cobertura cuenta sólo los requisitos aplicables activos. El denominador queda capturado junto a los códigos que lo componen. Una cobertura alta no convierte requisitos excluidos en cumplidos ni reemplaza la evaluación de cada bloqueo.

## 33. Bloqueos críticos

Los mínimos de madurez, evidencia, sponsor, vigencia y brechas abiertas pueden bloquear la evaluación conforme a la política. Una conclusión BLOCKED conserva el detalle del requisito responsable; no se oculta en un promedio o score ponderado.

## 34. Vigencia de la evidencia

La proyección actual compara el contexto material y la política efectiva con la captura histórica. FEL, Gate Profile, Governance Model, estrategia comercial, recursos y evidencia pueden causar STALE. El hash de la evaluación completada no cambia.

## 35. Refresh Preview y Refresh Apply

La vista previa no persiste y presenta diferencias de contexto, requisitos y evidencia. Apply exige concurrencia, permiso e idempotencia y crea un DRAFT sucesor. Nunca modifica el snapshot COMPLETED que originó el refresh.

## 36. Contexto de recursos

La integración consulta escenarios y referencias existentes. Los identificadores, versiones, hashes y condición de restricción permiten evaluar acceso a recursos sin recalcular capacidad, nivelar recursos ni cambiar escenarios.

## 37. Contexto comercial

La evaluación captura la estrategia vigente, su versión y hash, junto con el contexto de contratación pertinente. La frescura se controla conforme a la política. Las fuentes comerciales permanecen intactas.

## 38. Contexto FEL y PDRI

Se reutiliza ProjectDefinitionService para clasificaciones y evidencias de definición, además de la referencia de la última evaluación completada. Stage, score, maturity y framework hash aportan contexto y no son editables aquí.

## 39. Contexto Risk Governance

Se consulta la política empresarial efectiva de capacidad, apetito y umbrales. Owner Capability no publica esa política ni cambia sus límites. Su referencia permite rastrear el contexto de gobierno utilizado.

## 40. Contexto Risk Readiness

El adaptador reutiliza RiskReadinessService.project_readiness, la proyección pública actual de sólo lectura. Conserva referencia de la evaluación, hash y valid_until; refleja source_current, warnings y blockers, incluido EXPIRED. La prueba de vencimiento verificó cero DML y hash histórico intacto. Owner Capability no crea riesgos, modifica el register ni completa otra evaluación de riesgo.

## 41. Contexto Basic Data

Se consulta el snapshot de la última evaluación COMPLETED de Basic Data y su ID, versión y hash. El adaptador identifica explícitamente HISTORICAL_COMPLETED_SUMMARY_NO_REEVALUATION. No ejecuta una reevaluación, no actualiza ítems y no certifica por sí mismo la frescura viva de Basic Data. La referencia relaciona la capacidad organizacional con la evidencia técnica que ya fue completada.

## 42. Integración futura Portfolio Review

Wave 3A puede consumir en una revisión futura un resumen actual de Owner Capability. Este incremento no extiende ni reescribe snapshots históricos de review; el contrato futuro debe ser aditivo y de sólo lectura.

## 43. Referencias Benefits

Las responsabilidades de Benefit Owner y la capacidad de cambio pueden referenciar el plan existente. Benefits Plan y su register conservan la autoridad; no se duplica un registro de beneficios.

## 44. Arquitectura del proveedor

OWNER_CAPABILITY_READINESS_PROVIDER reutiliza Investment Evidence y devuelve proyecto, evaluación y versión, hash, configuración, readiness, dimensiones, cobertura, critical_gaps, mitigation_summary, warnings, blockers, fecha y referencias. No transmite todos los registros de brechas y mitigaciones: su contrato resume y referencia la evaluación propietaria. La evidencia gobernada exige COMPLETED READY actual y compatible.

## 45. Estado del registro del proveedor

La disponibilidad del adaptador significa que existe un contrato implementado; no que todos los proyectos posean evidencia READY. DRAFT, IN_REVIEW, BLOCKED, STALE, otro tenant, otro proyecto o una evaluación histórica superseded no deben aportar evidencia elegible.

## 46. Consumo futuro por Gate

El consumo se documenta, no se publica. Conceptualmente PYP INV SELECT en FEL 2 podría requerir clase B o A por complejidad y PYP FFA en FEL 3 clase A para CAPITAL_OWNER. Debe configurarse en un incremento explícito; las políticas y paquetes actuales no se alteran.

## 47. Contrato futuro Management Case

Una revisión Business Case nueva podrá guardar una referencia al proveedor y su hash. La historia de casos completados permanece inmutable. El esquema de referencia evita duplicar evaluaciones, brechas o conclusiones.

## 48. Diseño ADMIN

ADMIN dispone de configuración del framework, dimensiones, requisitos, escalas, tailoring, reglas bloqueantes, cobertura, aceptación de mitigaciones, frescura, numeración, herencia y SoD. Permite preview sin persistencia, clone, publicación independiente, archivo e historia. No completa evaluaciones de proyectos.

## 49. Flujo USER

USER selecciona Project Workspace, consulta requisitos, crea DRAFT, registra madurez y evidencia, identifica brechas y mitigaciones, somete a revisión y completa con autoridad independiente. Las vistas muestran contexto, dimensiones, readiness e historia.

## 50. Matriz de modos

| Acción | ADMIN Configuration | USER operativo |
| --- | --- | --- |
| Framework y reglas | Configura DRAFT | Consulta política efectiva |
| Publicación y archivo | Autoridad independiente | No disponible |
| Evaluación y mitigación | No es flujo ADMIN | Prepara con permisos |
| Revisión y cierre | No es flujo ADMIN | Revisor independiente |
| Gate y FID | Sin actualización automática | Sin actualización automática |

## 51. Identidad canónica Project

EnterpriseWorkspace con workspace_type_code project sigue siendo la identidad única. Las referencias del agregado se vinculan al tenant y proyecto existentes. No se incorpora una segunda tabla de Project ni se infiere identidad desde una pantalla.

## 52. Herencia y versionado

Se reutiliza la jerarquía Tenant, Enterprise, Business Unit y Portfolio. El backend resuelve la política publicada aplicable; la evaluación captura ID, revisión, versión de concurrencia, hash, resolution_hash y lineage. La referencia versionada se incorpora mediante un override de Owner Capability sin cambiar Basic Data ni sus snapshots. Una política más específica no modifica silenciosamente la historia de otra evaluación.

## 53. Snapshot completado

snapshot_json captura contexto, política, requisitos aplicables, mínimos y valores registrados, referencias de evidencia, dimensiones y conclusión global, junto con critical_gaps, mitigation_summary e identificadores de mitigaciones aceptadas por requisito. Los registros completos de ítems, brechas y mitigaciones permanecen en aggregate_json, también inmutable al completar. assessment_hash incluye agregado y snapshot, de modo que la lectura histórica corresponde al cierre y no a datos vivos.

## 54. Roles y permisos

Se agregan nueve permisos owner_capability al catálogo existente. Project Definition Manager prepara y revisa sujeto a SoD; assessor prepara; reviewer revisa y completa; viewer consulta. Configuration Admin sólo obtiene lectura y comandos de configuración. Organization Admin conserva el catálogo sin eludir SoD. El CLI explícito app.bootstrap_owner_capability requiere tenant y actor existentes con autoridad positiva; añade únicamente esos permisos y sus grants a roles ya existentes. No crea roles, asignaciones, memberships ni evaluaciones, y no ejecuta seed_demo. Un usuario activo de un tenant vacío no adquiere autoridad implícita.

## 55. Separación de funciones

La regla configurable impide que el preparador sea revisor final. La autoridad de publicación reconoce autores y editores de la configuración; no basta cambiar la regla en un DRAFT para publicarlo uno mismo. Las capacidades visibles de la interfaz proceden de allowed_actions.

## 56. Concurrencia mediante ETag

Cada agregado y configuración tiene versión de concurrencia. Las mutaciones exigen If Match; una versión desactualizada devuelve 412 ETAG_MISMATCH. La resolución de conflicto no sobrescribe automáticamente el trabajo de otro usuario.

## 57. Idempotencia

Las claves se vinculan a tenant, actor, comando y hash del payload. Un reintento compatible recupera la respuesta original; reutilizar una clave con otra operación o contenido produce conflicto. El ledger es independiente del historial de evaluación.

## 58. Auditoría SecurityEvent

Los comandos de configuración y evaluación conservan eventos con actor, tenant, entidad y referencias. Las consultas, previews y proyecciones de vigencia no deben fabricar evidencia ni escrituras de negocio. El informe de cierre distingue pruebas de interfaz de efectos persistidos.

## 59. Persistencia

La política permanece en AdminConfiguration. El agregado y el ledger pertenecen a owner_capability_assessments y owner_capability_commands. El agregado utiliza aggregate_json para ítems, brechas, mitigaciones y preparer_ids, y snapshot_json para el resultado capturado. Reviewed_by y reviewed_at registran revisión independiente; assessment_hash sólo se fija al completar. Los índices tenant_id, project_workspace_id e ix_owner_capability_history soportan consulta y versionado. No se agregan tablas de dimensiones, maturity, HR o tareas.

## 60. Migración aditiva

La revisión sucesora es 20261008_0066 desde 20261008_0065. SQLite verificó up down up con éxito en 51,99 segundos. La última ejecución PostgreSQL verificó el mismo ciclo en 35,58 segundos, conservando los marcadores de fuentes anteriores. Las pruebas aisladas construyen las dependencias mínimas de claves foráneas y verifican índices y constraints; no representan una repetición completa de las 65 revisiones históricas. Upgrade sólo crea las dos tablas nuevas. Downgrade elimina esas tablas y sus datos Owner, por lo que sólo se ejecutó en bases desechables. Antes del upgrade local se renovó y verificó un respaldo privado de PostgreSQL de 1963518 bytes mediante pg_restore --list y SHA256. No se restauró ni se entregó ese respaldo como informe.

## 61. API y contratos

El prefijo /api/v1/owner-capability conserva contratos separados por autoridad. Los comandos de escritura exigen Idempotency Key y, salvo creación inicial, If Match. Las lecturas y previews no escriben evidencia. No existe un endpoint independiente de ítems: PUT de evaluación actualiza el agregado estructurado.

| Grupo de API | Operaciones | Control |
| --- | --- | --- |
| /options | GET con search page page_size | owner_capability.read y alcance |
| /projects/{id}/requirements y /contexts | GET | Política efectiva y contexto readonly |
| /projects/{id}/assessments | GET paginado y POST | read o assessment.create |
| /assessments/{id} | GET y PUT | ETag e idempotencia para edit |
| /assessments/{id}/preview | POST | persisted false sin mutación |
| /submit /review /complete | POST por evaluación | Permiso específico y SoD |
| /mitigations | GET POST y PUT por acción | mitigation.edit y concurrencia |
| /refresh-preview y /refresh-apply | GET o POST preview y POST apply | Preview readonly y sucesor DRAFT |
| /current-readiness y /provider-evidence | GET por proyecto | Proyección actual y contrato gobernado |
| /admin/configurations | GET detalle historia PUT clone publish archive | Configuración y publicación independientes |
| /admin/preview y /admin/effective-preview | POST | Sin persistencia |

Las rutas genéricas de configuración rechazan el kind owner_capability_readiness_configuration con HTTP 409 GOVERNED_CONFIGURATION_API_REQUIRED. Cuatro pruebas de ese guard pasaron; cubren DRAFT, PUBLISHED y ARCHIVED, aliases normalizados, ausencia de DML y conservación de filas, hashes y auditoría.

## 62. Navegación canónica

strategicNavigationBlueprint.ts define los view IDs y su modo; StrategicViewOutlet.tsx renderiza las pantallas. applicationNavigation conserva los tipos. App.tsx no incorpora el dominio nuevo ni otra fuente de reglas de navegación.

## 63. Happy path PostgreSQL

La imagen final congelada completó 74 pruebas PostgreSQL en 121,63 segundos con salida cero: 66 del dominio, tres de integración del proveedor, cuatro del guard legado y una del esquema. El flujo publicó una política con autoridad independiente y completó una evaluación CAPITAL_OWNER con FEL 3, evidencia y revisión. El proveedor normalizado quedó AVAILABLE y READY para ese proyecto, con el hash de la evaluación. Los contextos reales incluyeron Commercial COMPLETED, Basic Data COMPLETED READY y un escenario Resource DRAFT; este último se mantuvo explícitamente como borrador y no se convirtió en evidencia de capacidad lista. Los datos se crearon exclusivamente en bases desechables.

## 64. Casos negativos del proveedor

La suite específica SQLite cerró 66 casos con éxito en 116,36 segundos, sin advertencias. Incluye elegibilidad negativa DRAFT, IN_REVIEW, BLOCKED y STALE, aislamiento por proyecto y tenant, política inaplicable y superseded. También rechaza referencias no identificables por API y evalúa defensivamente evidencia vacía ya almacenada. El contrato normalizado y la independencia de fuentes se comprueban adicionalmente en PostgreSQL; no se considera AVAILABLE un proyecto por la sola existencia del adaptador.

## 65. Prueba de bloqueo con alta cobertura

La prueba de diez requisitos confirmó nueve satisfechos, cobertura de 90 por ciento y OVERALL BLOCKED cuando Project Controls está bajo el mínimo. Un porcentaje alto no oculta el bloqueo. La suite específica conserva el código del requisito y las brechas responsables de la conclusión.

## 66. Prueba de madurez por etapa

La prueba confirmó DEFINED suficiente bajo reglas FEL 2 y BLOCKED ante IMPLEMENTED requerido en FEL 3. El resultado deriva del tailoring de política; no modifica etapa FEL, score PDRI ni Governance Model.

## 67. Prueba de mitigación externa

La prueba confirmó que una mitigación externa aceptada por la política puede satisfacer el mínimo de madurez después de revisión independiente. Una acción propuesta o sin aprobación no satisface el requisito. La aceptación no elimina condiciones de calidad, evidencia actual, accountability ni brechas bloqueantes explícitas.

## 68. Prueba de sponsor ausente

La prueba confirmó ACCOUNTABILITY_MISSING y BLOCKED cuando un requisito obligatorio de sponsor no identifica función responsable. El diagnóstico aparece una sola vez y no se crea sponsor automáticamente. Durante el cierre se corrigió una condición de diagnóstico omitida; el resultado aquí corresponde a la ejecución final posterior a esa corrección.

## 69. Prueba de vigencia e historia

Las pruebas confirmaron STALE ante cambios materiales de contexto o política y ante evidencia vencida. El snapshot y el hash COMPLETED permanecen intactos; refresh produce un DRAFT sucesor. Otra prueba confirmó que pasar al día siguiente sin vencimiento ni cambios materiales mantiene READY, evitando falsa obsolescencia por fecha de consulta.

## 70. Regresiones de independencia

La integración PostgreSQL comparó conteos y hashes de fuentes Resource, Commercial, FEL, PDRI, Risk, Basic Data, Gate, FID y políticas ajenas antes y después del ciclo Owner. Las 13 categorías del snapshot de autoridad permanecieron iguales. Otras pruebas registraron cero DML en lecturas y previews y conservaron hashes históricos de riesgo vencido. Esto prueba independencia de esas fuentes durante el flujo ensayado, no cobertura completa de todos los comandos de los otros dominios.

## 71. Regresión por Governance Model

Se validaron CAPITAL_OWNER, CONTRACTOR_DELIVERY y DIRECT_INTERNAL. Los dos últimos permanecen no aplicables por defecto. Las pruebas publicaron después un opt in explícito para cada uno y completaron una evaluación READY bajo la nueva política. No se infiere Governance Model desde Project Type.

## 72. Tailoring por Project Type

Los casos Mining, Infrastructure e Industrial bajo el mismo Governance Model demostraron diferencias de cantidad y madurez mínima gobernadas por política. No se incorporó lógica fija por industria. El denominador del preview ADMIN de una política inaplicable se verificó como cero, igual que los requisitos de USER, incluida herencia desactivada y fechas futuras o vencidas.

## 73. Ejemplo de minería

El ejemplo de validación puede configurar sponsor, controls, technical assurance, integración de mina y proceso, commercial, interfaces, permisos, riesgo, owner's engineer y transición. Es un ejemplo de política aislada y no configuración productiva obligatoria.

## 74. Browser USER

Chromium real aprobó el flujo USER contra la API y PostgreSQL desechables, sin mocks ni interceptar respuestas. Verificó navegación canónica, contextos FEL 3 y fuentes existentes, registro de madurez y evidencia, brecha bloqueante y su cierre, mitigación propuesta, submit, revisión independiente, COMPLETED, proveedor actual AVAILABLE READY, refresh preview e historia con snapshot y hash intactos. USER no mostró controles ADMIN. Los dos escenarios de navegador finalizaron con éxito en 1,7 minutos; el log de cierre conserva el detalle de cada uno.

## 75. Browser ADMIN

Chromium aprobó ADMIN con edición efectiva del framework, dimensiones, escalas separadas de madurez y calidad, requisitos, tailoring FEL y complejidad, bloqueo, cobertura, aceptación de mitigaciones, herencia y SoD. Las 24 secciones estaban visibles; frescura y numeración se comprobaron como secciones disponibles, pero sus valores no se editaron en este escenario. Verificó clone, guardado de contenido, preview persisted false, herencia desactivada con denominador cero, herencia activada, publicación independiente, resolución por ID versión y lineage, archivo y proyección STALE sin cambiar el histórico. ADMIN no mostró comandos operativos de evaluación. La prueba rechazó USER directo con HTTP 403 y la ruta genérica legada con HTTP 409.

## 76. Seguridad de rutas directas

Las pruebas finales del dominio comprobaron rechazos de rutas directas para USER sin autoridad ADMIN, config only sin autoridad operativa, autor que intenta revisarse, alcance de proyecto y tenant incorrectos. Los comandos verificaron ETag desactualizado y claves idempotentes incompatibles. El guard legado rechazó mutaciones genéricas sin DML. Las diez pruebas SQLite del aprovisionamiento estrecho pasaron en 10,72 segundos, sin advertencias, e incluyeron tenant vacío sin autoridad, permiso sólo de workspace, actor inválido, rollback e idempotencia. Ocultar botones no sustituye estas comprobaciones del backend.

## 77. Rendimiento representativo

La muestra PostgreSQL final evaluó 400 requisitos y buscó entre 1000 Project Workspaces con paginación de servidor y resolución por lotes. Registró 28 consultas y 1,175 segundos en la ejecución observada. No se registró una consulta por proyecto o requisito. La medición es una muestra funcional local sin concurrencia representativa; no constituye un SLA ni una prueba de carga.

## 78. Regresiones Wave

La ejecución SQLite aislada completó 140 casos con éxito en 1419,89 segundos. Incluye Wave 3A, Basic Data y Risk Governance de Wave 2B, contratos y protecciones legacy, Wave 2A, Wave 1 y las suites Gate detalladas en la siguiente sección. El log strategic-regressions-sqlite.log conserva resultados por caso. Hubo dos advertencias de permisos de la caché pytest, sin fallo de prueba. La ejecución usó --no-cov y no acredita cobertura global del repositorio ni GitHub Actions remoto.

## 79. Regresiones Gate y FID

Las suites FEL, Risk, Permit, EVID 2, Investment Evidence Policy, Investment Decision 07K y Post FID 07L pasaron dentro de la ejecución aislada de 140 casos. Se verifican contratos, staleness, política efectiva, decisiones y snapshots históricos. Las pruebas de independencia Owner complementan este resultado comparando fuentes de contexto antes y después del flujo. No se ejecutó CI remoto ni se reinterpretaron decisiones históricas.

## 80. Deuda técnica

Los editores ADMIN reutilizados permiten edición estructurada JSON; no son un constructor nuevo de formularios por dimensión. USER dispone de formularios para evidencia, madurez, brechas y mitigaciones, pero presenta algunos contextos y resúmenes como JSON legible. El selector de proyectos utiliza búsqueda y paginación de servidor de 100 filas; historia usa 25 filas por página. Ítems, brechas y mitigaciones usan páginas locales de 25 filas dentro del agregado acotado a 2000 registros, y una edición transmite el agregado completo. La carga de proyecto usa cuatro consultas API fijas en paralelo, no una petición por ítem. El service hereda utilidades canónicas de BasicDataService y separa sus métodos de autoridad; extraer esas utilidades a un componente neutral sería una mejora de mantenibilidad posterior. No se afirma rendimiento productivo por una muestra local.

## 81. Matriz de prerrequisitos QRA

| Prerrequisito | Estado arquitectónico | Brecha para QRA |
| --- | --- | --- |
| Risk Register y Risk Readiness | AVAILABLE | Adaptar fuentes para modelo cuantitativo |
| Risk Appetite y Thresholds | AVAILABLE | Aprobación de metodología QRA distinta |
| Basic Data Readiness | AVAILABLE | No valida distribuciones ni correlación |
| Owner Capability | AVAILABLE | Evidencia del propietario por proyecto |
| FEL Stage y PDRI | AVAILABLE | Definición no equivale a modelo de riesgo |
| FIN context | AVAILABLE | Modelo económico determinista |
| Cost source readiness | PARTIALLY_AVAILABLE | REQUIRES_ADAPTER para ROM y estimaciones |
| Schedule source readiness | NOT_AVAILABLE | REQUIRES_NEW_DOMAIN de fuentes QRA |
| Uncertainty ranges | REQUIRES_POLICY | Escala y autorización de rangos |
| Distribution rules | REQUIRES_POLICY | Familias, límites y calibración |
| Correlation rules | REQUIRES_POLICY | Matriz y aprobación |
| Methodology approval | REQUIRES_POLICY | Gobierno cuantitativo específico |
| QRA model governance y SoD | REQUIRES_NEW_DOMAIN | Patrones disponibles no son modelo QRA |
| Model validity y staleness | REQUIRES_NEW_DOMAIN | Captura y revisión cuantitativa |

## 82. Evaluación de brechas de fuentes QRA

Portfolio Budget conserva fuentes ROM con referencias y cobertura; no gobierna la calidad de una fuente probabilística de costo. El modelo FIN calcula cashflows, NPV y BCR deterministas. No se encontró un contrato gobernado de readiness de cronograma, distribuciones o correlaciones. La existencia de ETag, SoD y snapshots permite reutilizar patrones, pero no autoriza afirmar que QRA ya está disponible.

## 83. Estado final del release

Estado: OWNER_CAPABILITY_READINESS_RELEASE_VALIDATED. final_output = READY_FOR_GOVERNED_OWNER_CAPABILITY_EVIDENCE. OWNER_CAPABILITY_READINESS_PROVIDER = AVAILABLE. Estas señales corresponden al release local validado, no a una ejecución de GitHub Actions ni a evidencia READY automática de todos los proyectos.

| Validación | Resultado | Evidencia |
| --- | --- | --- |
| Dominio SQLite | PASS | 66 casos en 116,36 s |
| PostgreSQL binario final | PASS | 74 casos en 121,63 s |
| Migración SQLite | PASS | Up down up en 51,99 s |
| Migración PostgreSQL | PASS | Up down up en 35,58 s |
| Aprovisionamiento limitado | PASS | 10 casos SQLite en 10,72 s |
| Regresiones estratégicas | PASS | 140 casos en 1419,89 s |
| Frontend focalizado | PASS | 42 casos en seis archivos, 215,34 s |
| Chromium real USER ADMIN | PASS | Dos escenarios en 1,7 min |
| Build de producción | PASS | TypeScript y Vite, 2476 módulos |
| Ruff app y tests | PASS | Check y formato, 400 archivos |
| ESLint y Prettier | PASS | Cero errores, nueve avisos BIM preexistentes |
| Guardas arquitectónicas | PASS | Autoridad, migración y 84 secciones |
| Integridad local | PASS | 20 categorías con conteos y hashes iguales |
| HTTP local | PASS | Frontend y API readiness con HTTP 200 |

API, worker y beat utilizan la misma imagen final aprobada en PostgreSQL y Chromium. La base normal quedó en 20261008_0066. Se añadieron nueve entradas del catálogo y 31 grants a roles existentes; no se crearon roles, asignaciones ni memberships. La base conserva una configuración Owner neutral DRAFT y cero evaluaciones Owner. El autor del borrador no puede publicarlo por sí mismo. El arranque automático de datos demo se desactivó en la configuración local para evitar escrituras sobre fuentes existentes.

http://localhost:5173/app y los endpoints readiness directo y vía proxy respondieron HTTP 200. El smoke autenticado consultó opciones, configuración y proveedor. El stack desechable pypmis-wave3b se detuvo sin borrar volúmenes; los servicios normales permanecieron activos. Las advertencias observadas no fallaron las pruebas: dos de caché pytest en regresiones, nueve de lint BIM existentes y avisos de color del runner Chromium. No se ejecutó commit ni push.

## 84. Único siguiente incremento recomendado

QRA SOURCE READINESS & METHODOLOGY FOUNDATION. Primero debe gobernar fuentes de costo y cronograma, incertidumbre, distribuciones, correlaciones, aprobación metodológica y vigencia del modelo. No se implementa ese incremento ni simulación Monte Carlo en este trabajo.
