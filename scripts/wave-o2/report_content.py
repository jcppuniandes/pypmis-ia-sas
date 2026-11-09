"""Spanish report sections for the validated architecture increment."""


def chapters(data):
    preservation = data["baseline"]
    return [
        (
            "Resumen ejecutivo",
            "Validamos el diseño de O2 para integrar Ingeniería, Compras, Materiales, Logística y Contratos con los controles existentes. Contratos será el único escritor de la obligación legal y del Schedule of Values, o SOV. Cost consolidará esos hechos por referencia en el Project Cost Sheet. Se verificaron 57 criterios de diseño y nueve casos sintéticos. No se desplegaron módulos ni se modificaron datos de proyecto.",
        ),
        (
            "Base O1 validada",
            f"Verificamos los siete manifiestos de O1A a O1C y los {preservation['o1c_manifest_files_matched']} hashes del manifiesto O1C. Se reutilizan el Project y período común O1A, Scope y Plan, Schedule/P6, AWP y 4D, Cost, Progress/EVM y Forecast. Las 949 pruebas PostgreSQL y 13 comprobaciones Chromium corresponden al cierre anterior de O1C, no a transacciones O2.",
        ),
        (
            "Hallazgos del repositorio",
            "El repositorio ya contiene RFQ y ofertas, Contract, PurchaseOrder, ScheduleOfValueLine, PaymentCertificate, WarehouseReceipt y una hoja de costos legada. Los registros legados usan el Project anterior y no prueban un SOV revisado con aprobación y moneda. La hoja antigua suma contratos y órdenes y toma certificados o recibos como fuentes de costo. Conservamos esas funciones detrás de adaptadores y reutilizamos la conciliación canónica de Cost.",
        ),
        (
            "Mapa de dominios O2",
            "El mapa identifica 40 objetos con clave, ámbito, ciclo, dueño, entradas, lectores y reglas de mutación. Project es la identidad canónica de Enterprise Workspace, no el ID de la tabla legada de proyectos. Toda referencia atraviesa un vínculo autorizado o una identidad tipada del mismo tenant y Project. El detalle está en el mapa de dominios y en la segunda hoja de la matriz.",
        ),
        (
            "Autoridad de Ingeniería",
            "Engineering gobierna entregables, revisiones, disciplina, paquete de diseño, revisión, aprobación y liberación IFC. La revisión conserva fechas planificada, prevista y real, responsable y referencia documental con hash. Subir un archivo no libera el entregable. Las correcciones después de aprobación o liberación se registran como sucesores.",
        ),
        (
            "Relación con EWP",
            "EWP es un paquete de ejecución de AWP; un entregable es un resultado técnico de Ingeniería. Una revisión puede vincularse a varios EWP, CWA, Scope Items, Plan Items, CWP/IWP y actividades. Ingeniería posee sus referencias EPC; AWP conserva su PackageMapping.",
        ),
        (
            "Autoridad de Compras",
            "Procurement gobierna requisiciones, lotes de sourcing, RFQ/RFP, invitaciones, ofertas, aclaraciones, evaluaciones técnicas y comerciales, recomendaciones y la decisión de adjudicación. Conserva revisiones de la oferta, criterios vigentes y trazabilidad por línea. Las secuencias de ingeniería y compra se configuran según el caso; no hay una dependencia lineal obligatoria.",
        ),
        (
            "Relación con PWP",
            "PWP agrupa trabajo de ejecución de AWP. ProcurementPackage agrupa un expediente de sourcing. Una requisición o lote puede vincularse a varios PWP y entregables. La identidad del expediente no es la de una requisición, una orden ni un contrato.",
        ),
        (
            "Autoridad de Materiales",
            "Materials posee requisitos, reservas, recepciones, inspecciones, disponibilidad y salidas a frente. Un requisito conserva el origen en Scope, Plan, BOM/MTO, revisión técnica o paquete. Las cantidades BIM no crean demanda sin mapeo aprobado. La disponibilidad requiere cantidad, unidad, lote, inspección, ubicación y fecha compatibles; ORDERED no acredita disponibilidad.",
        ),
        (
            "Autoridad de Logística",
            "Logistics gobierna el plan, envío, tramo, salida, llegada, aduana y entrega. El paquete logístico operativo no sustituye al Work Package LOGISTICS de AWP. Arribo, entrega en el destino, recepción e inspección son hechos distintos. Una ETA aporta evidencia para Forecast sin cambiar las fechas de P6.",
        ),
        (
            "Autoridad de Contratos",
            "Contracts será el único dueño de Contract, PO, Subcontract, Service Agreement, líneas, cambios autorizados, SOV y compromiso legal. Separará aprobación de términos y activación de obligación. Una condición contractual no se registra como restricción de P6 o de ejecución.",
        ),
        (
            "Autoridad de Compromisos",
            "Un compromiso legal tiene identidad económica estable, revisión, alcance, moneda, vigencia y modo de inclusión. Se deriva de una obligación autorizada y de cambios efectivos; no se vuelve a capturar como importe manual. Cost consume una vista neta por corte y explica cobertura, conflictos o monedas no conciliadas.",
        ),
        (
            "Límite de compromisos estratégicos",
            "FID, fondos, estrategia comercial y condiciones de activación acreditan contexto, techo o autorización según el modelo del Project. Ninguno crea una obligación con un proveedor. Un proyecto del propietario, un contrato de entrega y una iniciativa interna validan la fuente que les corresponde; no se exige un FID inexistente.",
        ),
        (
            "Límite de Cost Commitment",
            "CostCommitmentReference y el reconciliador vigente son el punto de extensión. El adaptador futuro debe verificar el ID, revisión y hash del instrumento O2C, sin usar una referencia externa como bypass. El corte de adopción sustituye solo el origen legado conciliado; las divergencias no se suman ni se ocultan.",
        ),
        (
            "Semántica de contrato orden y subcontrato",
            "Un marco puede ser informativo o vinculante. ADDITIVE aporta una obligación independiente; INCLUDED y CALL_OFF consumen cobertura ya contada cuando aplica; REFERENCE_ONLY conserva el rastro sin sumar. Si el marco no era vinculante, se registra una orden emitida como origen aditivo con referencia al techo. Venta, compra y referencias no se mezclan.",
        ),
        (
            "Arquitectura SOV y modelo de línea",
            "Cada instrumento que lo requiera tiene una SOV actual y revisiones inmutables. SOVLine no es Contract Line: pueden mapearse N:N por ID y con asignaciones conciliadas. LUMP_SUM declara el importe; UNIT_RATE multiplica cantidad contractual aprobada por tarifa compatible. Un cambio efectivo origina un sucesor. Las certificaciones anteriores, del período, acumuladas y la retención se conservan separadas del avance físico.",
        ),
        (
            "Integración del Project Cost Sheet",
            "Cost consolida presupuesto original, cambios y vigente; compromisos originales, cambios, vigentes y pendientes; Actual, accruals y Forecast. El SOV distribuye el mismo compromiso entre CBS, código y cuenta de control. Ambas rutas de detalle vuelven al instrumento y a la línea exacta. El saldo sin asignar se muestra y las monedas no se suman sin FX autorizado. Forecast lee Cost conciliado, no esta vista que ya consume Forecast.",
        ),
        (
            "Separación de Procurement y Contracts",
            "Compras decide el proceso de adquisición y deja el expediente. Contratos es el único dominio que crea y activa una PO o instrumento legal. Se retienen los RFQ existentes como evidencia de sourcing; la puntuación de una oferta no firma un contrato ni reemplaza adjudicación.",
        ),
        (
            "Entrega de adjudicación",
            "La decisión autorizada fija proveedor, alcance, valores por línea, moneda, fuente, versión, hash y vigencia. El comando de Contratos revalida permisos, condiciones, límites por línea e idempotencia antes de crear un borrador. Leer el handoff o aprobar una recomendación no crea el contrato.",
        ),
        (
            "Integración AWP",
            "Los enlaces EPC identifican origen, versión, destino y estado. AWP conserva EWP, PWP, CWP, IWP, TWP, SUPPORT y LOGISTICS, junto con sus dependencias y 4D. Un vínculo técnico contextual no es una asignación monetaria; evita que una línea se sume una vez por paquete.",
        ),
        (
            "Integración Readiness",
            "Los seis proveedores propuestos cubren Ingeniería, Compras, Materiales, Logística, Contratos y Vendor con versión, vigencia, hash, cobertura y reglas de perfil. AWP mantiene el clearance, la evaluación y el release como comandos separados. READY no equivale a RELEASED. Una evidencia sustituida o vencida invalida la vista actual sin editar el snapshot histórico.",
        ),
        (
            "Integración Schedule",
            "El enlace a actividad fija Schedule Version e identidad aceptada. Hitos de ingeniería, compra, envío y contrato son hechos de su dominio. No escriben fechas, lógica CPM ni restricciones P6. Si desaparece una actividad, el enlace requiere revisión en vez de remapearse por nombre.",
        ),
        (
            "Integración Cost",
            "Cost conserva CBS, códigos, cuentas, presupuesto, línea base y Actual reconocido. Estimaciones y recibos operativos son evidencias candidatas, no reconocimiento de costo. Un pendiente no se incorpora a Current Commitment y un accrual reconocido no vuelve a sumarse cuando se sustituye por Actual.",
        ),
        (
            "Integración Progress",
            "Los eventos EPC pueden aportar evidencia a reglas de crédito y mediciones. Progress valida y aprueba el avance. La medición contractual por tarifa, la certificación, la factura y el pago conservan numeradores, fechas y fuentes propios.",
        ),
        (
            "Integración Forecast",
            "Forecast puede incorporar fechas de ingeniería, lead time, entrega de proveedor, disponibilidad, ETA y award por comando y revisión gobernados. El corte distingue fecha efectiva y momento de conocimiento. Ninguna lectura ni evento EPC reescribe una proyección aprobada.",
        ),
        (
            "Límite Vendor y Partner",
            "Se identificaron nombres de proveedor y contraparte en registros legados y entradas de navegación. No quedó demostrado un maestro canónico activo para toda la cadena. Antes de O2B/O2C se debe homologar una sola identidad de tenant con roles y vigencia, o gobernar una fuente compartida si falta. No se crea un maestro por módulo.",
        ),
        (
            "Límite documental y CDE",
            "Document, Attachment, Transmittal y Review existentes conservan archivos y decisiones documentales. El adaptador O1A exige vínculo de legado y autorización de lectura, o una fuente canónica verificable. El dominio EPC conserva documento, revisión y hash. Una referencia no concede descarga ni equivale a aprobación técnica.",
        ),
        (
            "ADMIN y USER",
            "ADMIN configura tipos, disciplinas, criterios, estados, aprobación, inclusión económica, aplicabilidad por paquete, vigencia y evidencias. Publicar una política no activa transacciones ni asigna usuarios. USER actúa en el Project autorizado con la versión exacta del perfil.",
        ),
        (
            "Seguridad y separación de funciones",
            "El diseño exige permisos por acción y alcance, sin provisión automática. Se separan solicitante, comprador, evaluadores, aprobador de award, preparador y aprobador contractual, receptor e inspector. Un usuario con varios roles no evade el control por actor. El mismo aislamiento aplica al drill-down y a datos sensibles de ofertas.",
        ),
        (
            "Auditoría",
            "Cada comando registra actor, alcance, motivo, instante y fecha de negocio, antes y después, revisión, correlación y hash de evidencia. Las denegaciones se registran en seguridad sin exponer datos sensibles. Un GET no crea hechos, no escribe historial de negocio ni materializa decisiones.",
        ),
        (
            "Arquitectura API",
            "Se especifican siete grupos de endpoints: Engineering, Procurement, Materials, Logistics, Contracts y extensiones de Cost y AWP/Readiness. Las mutaciones futuras exigen If-Match donde aplica e Idempotency-Key con comprobación de actor, alcance y contenido. Los DTO declaran ausencia, frescura, versión y causa; no sustituyen desconocido por cero.",
        ),
        (
            "Arquitectura de interfaz",
            "Se reutilizan Workspace Navigator, cabecera compacta y perfiles gobernados ADMIN. USER tendrá vistas paginadas con historial y acción autorizada. Cost Manager mostrará Project Cost Sheet y sus fuentes; Contracts Manager mostrará contratos, órdenes, subcontratos, SOV, cambios y compromisos. No se expone una pantalla simulada de pagos.",
        ),
        (
            "Estrategia de migración",
            "No hay migración O2 en este cierre. La primera ola confirmará el head real, con 0075 como base local O1C, y usará DDL aditivo congelado. El legado se incorpora solo por conciliación autorizada y dry-run. Se requieren PostgreSQL aislado, guardas SQL, arranque sin creación implícita y Chromium antes de activar.",
        ),
        (
            "Riesgos de duplicación y resoluciones",
            "Se registraron 20 decisiones: una sola obligación, un maestro de contraparte, un CDE, separación de PWP y expediente, y separación de restricciones. La revisión identificó como mayor riesgo económico sumar el legado a O2C o multiplicar importes mediante un join de asignaciones. El corte de adopción y el grano financiero los separan.",
        ),
        (
            "Escala e índices",
            "Los registros de entregables, requisitos, RFQ/Bid, PO/Contract/SOV, envíos, documentos y mappings usarán índices compuestos por tenant, Project, padre, estado, vigencia e ID según la consulta. Listados por cursor, límite inicial de 50 y máximo de 200 propuestos. Los planes y tiempos se medirán en fixtures de volumen antes de establecer capacidad; no se ofrece SLA.",
        ),
        (
            "Hoja de ruta O2A a O2D",
            "O2A establece revisiones técnicas y liberación IFC. O2B implementa sourcing, materiales y logística sin órdenes legales. O2C establece instrumentos, SOV y conciliación Cost Sheet. O2D conecta evidencias con AWP y Readiness. Cada ola tiene alcance, configuración, UI, migración, dependencias, pruebas y criterios de salida; ninguna arranca automáticamente.",
        ),
        (
            "Brechas restantes",
            "Falta confirmar el maestro empresarial de contrapartes y el origen de catálogo antes de O2B/O2C, y aprobar el corte de adopción por obligación. La validación transaccional, el volumen productivo y la aceptación de negocio quedan para las olas correspondientes. No se implementaron pagos, tesorería, contabilidad, Claims, Field ni Commissioning.",
        ),
        (
            "Decisión de arquitectura",
            f"La revisión no dejó S1/S2 abiertos de arquitectura. Project 14 y sus referencias observadas permanecen iguales; {preservation['application_files_unchanged']:,} archivos de aplicación se compararon antes y después. Estado: {data['release_state']}. Resultado: {data['final_output']}. No se aplicó DDL ni se desplegaron transacciones O2.",
        ),
        (
            "Único siguiente incremento recomendado",
            "WAVE O2A — ENGINEERING FOUNDATION. El inicio requiere autorización explícita.",
        ),
    ]
