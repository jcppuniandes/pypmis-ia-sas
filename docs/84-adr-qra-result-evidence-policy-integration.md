# Integración contextual de resultados QRA en evidencia de inversión

## Decisión arquitectónica

Reutilizamos QRA_RESULT_PROVIDER, la política de evidencia Gate07J EVID, los criterios Gate07J EVID2, el paquete congelado de preparación y las fuentes Five Case. COST_QRA_RESULT y SCHEDULE_QRA_RESULT son calificadores del mismo proveedor. La incorporación de capacidades no publica políticas ni convierte QRA en obligación universal.

Los requisitos se expresan en qra_policy dentro de la fila existente de evidence policy. El motor queda limitado a COST_QRA y SCHEDULE_QRA. Una regla integrada activa es inválida. Para Schedule Class A se exige declarar NOT_STARTED, SOURCE_DURATION y NORMALIZED_ELAPSED_TIME_V1; un proyecto incompatible permanece bloqueado con ENGINE_CAPABILITY_NOT_SUPPORTED, sin excepción ni autoridad externa inventada.

## Aplicabilidad y autoridad

Se usan atributos gobernados del proyecto y la etapa vigente de ProjectFELStatus. El valor usa estimated_budget y currency_code de creación, sin conversión FX. Una condición no evaluable no desactiva una exigencia configurada. CAPITAL_OWNER es el filtro inicial; CONTRACTOR_DELIVERY y DIRECT_INTERNAL solo participan si una revisión publicada los incluye. Sin gate_profile gobernado o explícito no se infiere PYP FFA para Business Case.

La clasificación A exige proveedor gobernado y prohíbe sustitución manual. B y C mantienen su semántica. La política selecciona readiness, convergencia, alcance, vigencia y percentiles. CONVERGED es estabilidad de la media; nunca certificación de colas. Los criterios consumen números calculados, con operadores controlados, moneda, unidad, base temporal y procedencia del umbral.

Gate07J no simula. Gate07K decide exclusivamente sobre el paquete congelado; no consulta un nuevo QRA ni una nueva política para reinterpretar la decisión histórica. Gate07L conserva su autoridad. No se escribe Budget, Funding, FIN, P6, contingencia o reserva.

Las comparaciones numéricas y de fechas calificadas QRA normalizan representaciones equivalentes de valores validados e instantes UTC, conservando el target original y su procedencia. La normalización no introduce FX, conversiones de unidades o reproducción de calendarios laborales ni cambia los criterios legacy no QRA.

## Selección y conservación

La selección existente de mayor identificador aceptado se conserva dentro del tipo de análisis y alcance compatibles. Un resultado nuevo en alcance distinto no sustituye el resultado de proyecto completo. No se busca una corrida antigua para eludir que su sucesora sea obsoleta o no convergente. Se conserva el vínculo de aceptación, modelo, método, fuente y motor, y se valida currentness. El guard Schedule utiliza la misma normalización de estado que el kernel; las variantes válidas de Not Started no se clasifican como incapacidad.

PortfolioProjectMembership representa una relación N M distinta de la jerarquía Enterprise. Business Case pasa el portafolio objetivo de su propuesta; el resolver verifica tenant, proyecto, membresía y vigencia. Sin contexto explícito se admite una membresía activa única. Una ambigüedad material de reglas QRA exige aclarar el contexto, no seleccionar la política más reciente. Si ninguna regla QRA es aplicable se conserva el flujo legacy no requerido. El snapshot registra el contexto de membresía y la etapa FEL gobernada utilizados.

El paquete captura política y determinación contextual, resumen QRA, hashes, aceptación, percentiles elegidos, probabilidades, advertencias y fecha. Excluye histogramas, CDF, sensibilidad y muestras. El historial FROZEN no vuelve a resolver fuentes. Una preparación no congelada detecta cambios mediante el proveedor vigente.

Business Case captura cost_qra_result para Economic y Financial Case y schedule_qra_result para Management Case. Un marcador explícito _qra_evidence activa estas filas únicamente en revisiones nuevas; no se añade una fila vacía a todos los registros históricos. La comparación vigente y la actualización emplean el procedimiento existente de sucesor DRAFT. FIN sigue siendo determinista.

Cuando EVID2 comprueba la consistencia de fuentes BC, no compara un hash nativo de ProjectFELStatus con el hash envolvente de Definition Readiness, ni un hash Risk por proyecto con el hash agregado PROJECT_SET. Los proveedores capturan referencias nativas compactas desde la misma lectura gobernada; Gate compara proyecto, identidad del registro y hash en esa capa, conservando también el hash del proveedor para auditoría. Solo admite este contrato si evidence_origin de la fila persistida es GOVERNED_SOURCE; un payload manual no puede declararse autorizado. Referencias ausentes, duplicadas, de otro proyecto o de identidad diferente no eluden la discrepancia. Los paquetes legacy conservan la comparación anterior y los históricos no consultan fuentes vivas.

El nuevo enriquecimiento project_source_reference se excluye únicamente de la proyección material FEL v1 que Basic Data ya transmite a Owner Capability y QRA Foundation. No se excluyen identificadores, readiness, revisiones ni hashes existentes. Así, añadir procedencia de transporte no convierte una fuente materialmente idéntica en stale; los cambios reales conservan sus controles de vigencia.

## Persistencia y seguridad

No se requiere migración: AdminConfiguration.content_json, BusinessCaseRevision.source_references_json, source_hashes_json y los snapshots Gate ya representan los calificadores y su procedencia. Alembic permanece en 20261011_0068. No se crean proveedores, roles globales, tablas de política o un gestor paralelo.

Se conservan los permisos de administración de Evidence Policy, el alcance por tenant y proyecto, If Match, clasificación A, auditoría SecurityEvent y separación autor publicador cuando está configurada. Clone admite replay por clave con identidad de petición. Los permisos del visor QRA siguen verificándose al abrir la fuente. La publicación comprueba los percentiles seleccionados contra métodos publicados compatibles incluso si no hay criterio numérico. Se validan también los valores combinados de overrides para impedir eludir los controles de análisis, capacidad o clase.

Clone normal y EVID2 acotan el nombre de presentación a los 180 caracteres del esquema vigente, conservando el sufijo completo de la nueva revisión. La auditoría conserva el identificador, revisión, hash y nombre completo de la fuente. No se renombra una política publicada, se cambia su contenido ni se modifica el marcador histórico utilizado por el replay EVID2.

## Límites

No se incluye QRA integrado, avance real, duraciones restantes, calendarios laborales P6, convergencia de percentiles extremos, modelado automático de eventos Risk, aprobación de contingencia ni decisión FID automática. La validación aislada debe separar políticas adaptadas de la cobertura de toda la configuración predeterminada. El estado de release solo se declara tras resultados reproducibles de PostgreSQL, navegador y regresión.
