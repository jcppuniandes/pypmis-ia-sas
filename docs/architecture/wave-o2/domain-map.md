# Mapa de dominios Wave O2

Este mapa especifica el diseño objetivo, no tablas desplegadas. Cada fila tiene un
solo dueño de escritura. Los IDs de diseño son lógicos: deberán seguir las
convenciones del repositorio al materializarse. **P** = mismo tenant y Project
Workspace canónico activo; **T** = identidad de tenant validada para uso en P;
**B** = legado accesible solo por vínculo O1A explícito. El contexto P no es
`projects.id`; ningún join cruza por nombre, código suelto ni igualdad de IDs.

| ID | Objeto | Dominio dueño | Clave primaria lógica | Contexto | Ciclo propuesto o vigente | Fuente de verdad | Entrada autorizada | Consumidor | Mutabilidad y enlaces |
|---|---|---|---|---|---|---|---|---|---|
| O2-01 | Disciplina y tipo de entregable | ADMIN | profile_id + revision | T/P | DRAFT → PUBLISHED → sucesor | Perfil ADMIN | Catálogo y reglas del tenant | Engineering | Publicado inmutable; perfil fijado en la revisión |
| O2-02 | Engineering Deliverable | Engineering | deliverable_id | P | DRAFT → IN_DEVELOPMENT → FOR_REVIEW → REVIEWED → APPROVED → IFC_RELEASED | Engineering Register | Scope, Plan y CDE | AWP, Procurement, Progress, Forecast | Identidad estable; revisión liberada inmutable. M:N EWP, CWA, CWP/IWP, Scope, Plan y Activity |
| O2-03 | Revisión de entregable | Engineering | deliverable_revision_id | P | DRAFT → APPROVED → IFC_RELEASED → sucesor o retiro | Engineering | Archivo/revisión exacta del CDE, revisor, motivo | Readiness, Progress | Hash, versión y fechas congelados al liberar; carga no libera |
| O2-04 | Design Package | Engineering | design_package_id + revisión | P | DRAFT → REVIEWED → ISSUED/CANCELLED | Engineering | Revisiones de entregables | EWP y Procurement | No es EWP. M:N entre paquete de diseño, revisiones y EWP |
| O2-05 | Revisión y consulta técnica | Engineering | engineering_event_id | P | OPEN → REVIEWED → CLOSED | Engineering | Revisión, responsable y evidencia CDE | Ingeniería, Procurement | Evento append-only; reabrir por sucesor; no es aprobación de oferta |
| O2-06 | Requisición y línea | Procurement | requisition_id / requisition_line_id | P | DRAFT → SUBMITTED → APPROVED → SOURCING | Procurement | Necesidad identificada y criterios técnicos | ProcurementPackage, Materials | Borrador editable; línea aprobada versionada; M:N PWP, requisitos y entregables |
| O2-07 | ProcurementPackage | Procurement | procurement_package_id | P | DRAFT → READY_TO_SOURCE → SOURCING → RECOMMENDED → HANDED_OFF/CANCELLED | Procurement | Líneas requisición y estrategia | RFQ/RFP, Award | Paquete de sourcing independiente del PWP; M:N PWP y EWP |
| O2-08 | RFQ/RFP e invitación | Procurement | solicitation_revision_id / invitation_id | P | DRAFT → ISSUED → CLOSED | Procurement | Paquete, Partner, perfil evaluación | Oferta y evaluación | Emisión congela criterios, líneas e invitaciones; enmienda por revisión |
| O2-09 | Oferta y línea | Procurement | bid_revision_id / bid_line_id | P | RECEIVED → QUALIFIED/REJECTED → SUPERSEDED | Procurement | Partner, invitación y evidencia recibida | Evaluación técnica y comercial | Presentación original inmutable; aclaración por evento/revisión; visibilidad limitada |
| O2-10 | Evaluación y aclaración | Procurement | evaluation_id / clarification_id | P | DRAFT → COMPLETED → sucesor | Procurement | Oferta y perfil publicado | Recomendación | Técnica y comercial separadas; puntuación no adjudica |
| O2-11 | Recomendación de adjudicación | Procurement | award_recommendation_id | P | DRAFT → SUBMITTED → ACCEPTED/REJECTED | Procurement | Evaluaciones congeladas y elegibilidad | Decisión autorizada | Registro aprobado inmutable, sin compromiso ni PO |
| O2-12 | Decisión de adjudicación | Procurement | award_decision_id | P | AUTHORIZED/REJECTED → supersesión | Procurement | Recomendación y aprobación independiente | Comando de handoff O2C | Identidad y hash fijados por lote; el contrato exige comando independiente |
| O2-13 | Requisito de material | Materials | material_requirement_id | P | REQUIRED → SOURCED → SATISFIED/CANCELLED | Materials | BOM/MTO, revisión, Scope, Plan o paquete | Requisición, reserva y Readiness | Aprobación explícita y traza M:N; IFC o cantidad por sí solos no crean demanda |
| O2-14 | Identidad de ítem de material | Materials | material_item_id o referencia canónica | T/P | ACTIVE → RETIRED | Catálogo Materials o fuente ERP autorizada | Tenant, unidad, código fuente | Requisito, recepción y reserva | Un código por fuente/tenant; sin duplicar catálogo ERP ni APU |
| O2-15 | Reserva y ubicación física | Materials | reservation_id | P | RESERVED → ISSUED/RELEASED | Materials | Ítem/lote y Warehouse Workspace | Workfront, Readiness | Ubicación del dominio físico; cantidad reservada no es disponible para otros |
| O2-16 | Recepción e inspección | Materials | receipt_line_id / inspection_id | P | RECEIVED → INSPECTED → ACCEPTED/REJECTED | Materials | Envío, orden referenciada, lote y cantidad | Disponibilidad y Cost como evidencia | Inspección independiente; eventos no son Actual ni pago |
| O2-17 | Disponibilidad y emisión | Materials | material_event_id | P | AVAILABLE → ISSUED → CONSUMED o reversión | Materials | Lote aceptado, ubicación, reserva, fecha | IWP/CWP y Readiness | Estado derivado por cantidad/corte; corrección por reversión. ORDERED no acredita disponibilidad |
| O2-18 | Paquete de logística operativa | Logistics | logistics_plan_id | P | DRAFT → PLANNED → CLOSED | Logistics | Material, destinos y requerimiento en sitio | Shipment, AWP | M:N LOGISTICS Work Package, PWP, CWP, IWP; identidad separada |
| O2-19 | Envío, tramo y entrega | Logistics | shipment_id / transport_leg_id / delivery_id | P | PLANNED → DEPARTED → ARRIVED → DELIVERED | Logistics | Material/lote, origen, destino y Partner | Materials, Readiness, Forecast | Eventos fechados, evidencia de recepción y condiciones aduaneras; no actualiza P6 |
| O2-20 | Instrumento contractual | Contracts | instrument_id | P | DRAFT → IN_REVIEW → APPROVED → ACTIVE → CLOSED/TERMINATED | Contracts | Award autorizado o autorización alternativa publicada | Cost y Readiness | Tipos Contract, PO, Subcontract, Service Agreement, Call-Off; revisión activa inmutable |
| O2-21 | Línea contractual | Contracts | contract_line_id + revisión | P | DRAFT → EFFECTIVE → sucesor | Contracts | Instrumento y cantidades/términos aprobados | SOV y Cost | Identidad de obligación, M:N Scope, Plan, paquetes, CBS, WBS/actividad |
| O2-22 | Cambio contractual | Contracts | contract_change_id | P | PROPOSED → REVIEW → APPROVED/EFFECTIVE | Contracts | Instrumento, evidencia y efecto incremental | SOV y legal commitment | Aprobado inmutable. Cambio Budget/Scope/Schedule es un comando separado |
| O2-23 | Schedule of Values | Contracts | sov_id / sov_revision_id | P | DRAFT → APPROVED → EFFECTIVE → sucesor | Contracts | Instrumento y cambios aprobados | Compromiso y certificación futura | Una revisión actual por instrumento; original preservado; moneda y fecha fijadas |
| O2-24 | Línea de SOV | Contracts | sov_line_id / sov_line_revision_id | P | DRAFT → EFFECTIVE → sucesor | Contracts | Una o varias líneas contractuales | Cost Sheet y futura certificación | Base LUMP_SUM/UNIT_RATE; asignaciones balanceadas. M:N todas las dimensiones aplicables, ninguna por nombre |
| O2-25 | Compromiso legal | Contracts | economic_origin_id / obligation_revision_id | P | ACTIVE → AMENDED/CLOSED | Contracts | Instrumento/línea, cambio, regla de inclusión | Cost Commitment View | Identidad económica estable; original + delta aprobado. SOV desglosa, no adiciona |
| O2-26 | Certificación o factura futura | Autoridad futura | external_certificate_id / invoice_line_id | P | No implementado en O2 | Proveedor futuro autorizado | Versión de SOV y documento aprobado | Cost solo tras reconocimiento | Referencia al estado original; pago, certificación, factura y avance físico son distintos |
| O2-27 | Vista de compromiso neto | Cost | source_obligation_key + corte | P | Lectura por corte o snapshot | Cost Commitment View | Proyección contractual y conciliación | Cost Sheet y Forecast | No crea obligación; cobertura y conflictos explicados; moneda no mezclada |
| O2-28 | Project Cost Sheet | Cost | project + basis + period + dimension | P | LIVE / snapshot publicado si se autoriza | Cost Manager | Budget, compromiso legal, Actual, accrual y Forecast | Control de proyecto y reportes | Read model; drill-down bidireccional, no edición del SOV ni duplicación de importes |
| O2-29 | EWP, PWP, CWP, IWP, TWP, SUPPORT y LOGISTICS | AWP | work_package_id | P | Ciclo AWP vigente | AWP WorkPackage | Scope, Plan, CWA y perfiles | Dominios EPC y 4D | Mapping gobernado; tipos EPC no crean paquetes |
| O2-30 | Mapping entre dominios | Dueño del origen | mapping_revision_id | P | DRAFT → ACTIVE → REMOVED/sucesor | Registro de mapping del dueño | Identidades verificadas y versión destino | Readiness, navegación, 4D, Cost | FK o validación tipada por tenant/P; revisiones de enlaces preservadas |
| O2-31 | Restricción de ejecución | AWP | execution_constraint_id | P | OPEN → CLEARED/WAIVED → reabierta por comando | AWP ExecutionConstraint | Evidencia EPC y reglas del Project | Readiness | Clearance explícito; no es restricción P6, condición de oferta ni condición contractual |
| O2-32 | Evaluación y liberación | AWP | readiness_assessment_id / release_event_id | P | EVALUATED → elegible → RELEASED por autorización | AWP Readiness | Evidencia vigente y constraints | Ejecución, Forecast, 4D | Snapshot y hash inmutables; evidencia obsoleta bloquea, READY no libera |
| O2-33 | Schedule y CPM | Schedule/P6 | schedule_version_id / activity_id | P | Importado → Accepted Current / Baseline aprobada | Schedule y cálculo externo P6 | XER/XML aprobado | AWP, O2, Forecast | Actividad y versión por ID; milestone EPC no sustituye fecha, lógica o restricción P6 |
| O2-34 | Budget, Baseline, Actual y accrual | Cost | ID nativo de Cost | P | Ciclos Cost vigentes | Cost | Dimensiones CBS/Código/Cuenta y fuentes reconocidas | Cost Sheet, EVM, Forecast | Enlace a fuente inmutable cuando aprobada; aprobación contractual no cambia Budget |
| O2-35 | Medición de avance | Progress | measurement_id / evm_snapshot_id | P | Ciclo de medición y período vigente | Progress | Evidencia, regla de crédito y aprobación | EVM, Reporting, Forecast | Hechos EPC son candidatos; no se convierten en avance físico por GET |
| O2-36 | Versión Forecast | Forecast | forecast_version_id | P | DRAFT → UNDER_REVIEW → APPROVED/REJECTED | Forecast O1C | Fuentes verificadas y supuestos gobernados | Cost Sheet, dashboards y reportes | Aprobado inmutable; fecha/lead time EPC es input por referencia |
| O2-37 | Vendor o Partner | Enterprise/Partner | partner_id o identidad homologada | T/P/B | Activo, suspendido o retirado según autoridad | Maestro existente vía adaptador | Verificación de elegibilidad | Requisición, oferta, contrato, transporte | Roles contextuales; sin alta paralela, deduplicación por identidad autorizada |
| O2-38 | Documento o archivo | CDE | document_id + revision / attachment_id | T/P/B | Ciclo CDE vigente | Registro documental y almacenamiento existentes | Carga, revisión y transmittal | Engineering, Procurement y Contracts | Enlace a versión/hash y autorización. Documentar aprobación técnica por separado |
| O2-39 | Autorización estratégica | Capital Portfolio | ID de autorización/commitment estratégico | T/P | Decisión publicada según ciclo vigente | Gobierno estratégico | FID, presupuesto autorizado y financiación | Contexto operativo | Contexto/techo, no obligación de proveedor; excluir del roll-up legal |
| O2-40 | Necesidad de sourcing | Procurement | requirement_id | P | PROPOSED → VALIDATED → SOURCED/CANCELLED | Procurement | Scope, Plan, PWP o Material Requirement | Requisición | Enlace con linaje; no crea demanda material paralela ni obligación |

## Decisiones de integración

- La ruta de costo sigue un solo hecho económico: instrumento y cambio
  aprobados → desglose SOV → compromiso legal → asignaciones por CBS, código y
  cuenta → vista Cost. Los recorridos de detalle conservan identidad y versión
  del instrumento, SOV y línea en ambos sentidos.
- Cost Sheet queda aguas abajo de Forecast. Forecast consume reconocimientos y
  conciliaciones de Cost, no los totales del Cost Sheet que ya incluyen Forecast;
  así no hay un circuito de cálculo circular.
- La ruta de preparación conserva responsabilidades separadas: proveedor EPC
  → evidencia tipada y vigente → validación de restricciones → evaluación AWP
  → liberación autorizada. El mapa no permite que un lector cambie un estado.
- La entrega de O2 cierra arquitectura y prueba los invariantes en casos
  sintéticos aislados. O2A–O2D deberán implementar y comprobar los contratos
  en PostgreSQL y navegador; no se activan al aprobar este diseño.
