"""Spanish technical closeout for Wave O2B; evidence stays separate from claims."""


def chapters(e):
    return [
        (
            "Resumen ejecutivo",
            (
                "Wave O2B incorpora un flujo operativo de compras, materiales y logística dentro del contexto de proyecto. "
                "La prueba crítica en PostgreSQL recorrió la cadena desde la demanda hasta material disponible para un IWP y verificó que el paquete siguió sin liberar. "
                f"Decisión de este corte: {e['decision']} No se desplegó a producción."
            ),
        ),
        (
            "Línea base reutilizada",
            (
                "La implementación parte de e5747a6 y de la revisión Alembic 20261109_0076. Reutiliza el contexto operacional O1A, "
                "Scope y Plan, Schedule/P6, los paquetes AWP, las autoridades de Cost, Progress y Forecast y el módulo Engineering O2A."
            ),
        ),
        (
            "Hallazgos del repositorio",
            (
                "Los pedidos y las entradas de almacén legados ya alimentan procesos financieros. La nueva orden operativa y la recepción física "
                "se guardan en tablas propias y no se registran de nuevo como pedido, entrada de almacén, compromiso o costo legado. "
                "Los adjuntos permanecen en CDE. El catálogo de proveedores nuevo se acota al tenant; los ítems, al proyecto."
            ),
        ),
        (
            "Autoridad de Procurement",
            (
                "Procurement gobierna el requerimiento de compra, la competencia, la adjudicación, la orden operativa, el seguimiento del proveedor "
                "y los hechos físicos desde expedición hasta asignación. Cada vínculo a una autoridad externa conserva su identidad y versión de origen."
            ),
        ),
        (
            "Procurement Packages",
            (
                "El paquete de compra agrupa necesidades, método de abastecimiento, disciplina, categoría y fechas planificadas. Su identidad no "
                "es un PWP. Los vínculos tipados permiten relacionarlos sin crear ni editar paquetes AWP."
            ),
        ),
        (
            "Requirements",
            (
                "El requerimiento pertenece a un paquete y expresa descripción, cantidad, unidad, necesidad en sitio y prioridad. "
                "Las referencias de alcance, planificación, ingeniería y cronograma se conservan como enlaces revisables."
            ),
        ),
        (
            "Requisitions",
            (
                "La requisición interna contiene líneas respaldadas por requerimientos del paquete. Someter, aprobar y rechazar son acciones "
                "distintas; el actor que preparó la requisición no puede aprobarla. La requisición aprobada habilita el proceso de oferta, no lo sustituye."
            ),
        ),
        (
            "RFQ",
            (
                "Una RFQ parte de una requisición aprobada. Invita a proveedores activos y aplica el mínimo del perfil antes de emitir. "
                "Cerrar la RFQ permite evaluar ofertas. Las invitaciones registran el vínculo entre proveedor y solicitud."
            ),
        ),
        (
            "Bids",
            (
                "La oferta se registra para un proveedor invitado con líneas, cantidad, precio, moneda y evidencia cuando la política la exige. "
                "La oferta es una propuesta del proveedor; no concede autorización para comprar."
            ),
        ),
        (
            "Evaluations",
            (
                "Las evaluaciones técnica y comercial se guardan por separado y se ligan a una oferta. El perfil gobierna cuáles se requieren. "
                "El recorrido crítico verificó que omitir la evaluación requerida impide adjudicar."
            ),
        ),
        (
            "Award",
            (
                "La adjudicación referencia la oferta, el proveedor y la RFQ. Su aprobación independiente establece la selección; no crea automáticamente "
                "una orden, contrato ni compromiso. Un aprobador no puede reemplazar el registro aprobado."
            ),
        ),
        (
            "Purchase Orders",
            (
                "La orden operativa conserva la adjudicación cuando el perfil la exige. Se aprueba y emite mediante acciones separadas. "
                "La aprobación inicial crea una versión y una modificación posterior se tramita como revisión sucesora con hash y aprobación propia."
            ),
        ),
        (
            "Materials",
            (
                "El catálogo de ítems del proyecto identifica material, unidad y trazabilidad. Un requerimiento de material deriva de la demanda "
                "de compra y conserva sus cantidades y referencias; una asignación reserva material aceptado para un paquete elegible."
            ),
        ),
        (
            "Expediting",
            (
                "Los hitos del proveedor relacionan una línea de PO con fechas planificadas y pronosticadas. Los eventos guardan su historial "
                "y alimentan el seguimiento. Un hito o un reporte de fabricación no sustituye una inspección."
            ),
        ),
        (
            "Inspections",
            (
                "La inspección registra una decisión de calidad separada del despacho y referencia evidencia CDE. Cuando el perfil la exige, "
                "un embarque no puede avanzar con una inspección pendiente o no aceptable."
            ),
        ),
        (
            "Logistics",
            (
                "El embarque contiene líneas vinculadas a una orden emitida y registra transiciones de despacho, tránsito y llegada. "
                "La llegada queda como hecho logístico; ninguna transición crea una recepción física."
            ),
        ),
        (
            "Material Receipt",
            (
                "La recepción verifica el sitio, la unidad y el saldo de las líneas embarcadas. La aceptación posterior asigna toda la cantidad "
                "entre aceptado, rechazado y cuarentena. Solo la fracción aceptada puede reservarse."
            ),
        ),
        (
            "Material Availability",
            (
                "El proveedor calcula cobertura por requerimiento y paquete a una fecha de corte. Valida los enlaces, las cantidades aceptadas, "
                "las reservas activas y su vigencia. La liberación de una reserva queda como evento, no como borrado del registro."
            ),
        ),
        (
            "Integración AWP",
            (
                "El adaptador MATERIAL solo interviene donde existe una relación gobernada. El hash del proveedor se incorpora a la evaluación AWP. "
                "La aceptación de materiales no puede cambiar el estado de liberación del IWP; AWP conserva esa decisión."
            ),
        ),
        (
            "Integración Engineering",
            (
                "Se reutiliza la verificación de revisiones, entregables e IFC de O2A. Una huella discrepante, una revisión sustituida o una "
                "liberación ya no efectiva dejan la referencia sin validez. Procurement no libera ni corrige entregables."
            ),
        ),
        (
            "Integración Scope y Plan",
            (
                "Los enlaces aceptan objetos canónicos del proyecto con su estado y huella. La necesidad de compra puede derivarse de ellos "
                "sin copiar su ciclo de vida ni alterar cantidades aprobadas."
            ),
        ),
        (
            "Integración Schedule",
            (
                "WBS, actividades e hitos de P6 se seleccionan por identificador externo y versión aceptada. Procurement no modifica la versión "
                "ni busca reemplazos por nombre. Un identificador ausente o una versión no vigente exige revisión."
            ),
        ),
        (
            "Límite con Cost",
            (
                "Los hechos de adjudicación y orden emitida son candidatos de origen consultables. Los enlaces CBS, código de costo y cuenta de "
                "control no convierten la orden en compromiso ni alteran el presupuesto, costos reales o estimado al completar."
            ),
        ),
        (
            "Límite con Progress",
            (
                "La consulta de hechos físicos distingue inspección, llegada, recepción y aceptación. No registra porcentaje de avance ni "
                "material instalado. Cualquier consumo posterior requiere la decisión del dominio de Progress."
            ),
        ),
        (
            "Límite con Forecast",
            (
                "Los hitos y proyecciones logísticas ofrecen señales de fecha y trazabilidad. No publican pronósticos ni cambian el forecast aprobado. "
                "La integración entregada es de lectura; no equivale a una adopción gobernada por el consumidor."
            ),
        ),
        (
            "Modos ADMIN y USER",
            (
                "ADMIN gobierna perfiles y publicación independiente. USER opera sobre un proyecto activo, con perfil vigente y permisos por función. "
                "El navegador operacional ofrece Procurement Manager en el contexto habilitado."
            ),
        ),
        (
            "Seguridad",
            (
                "Las consultas se acotan por tenant y proyecto. Los comandos validan permisos, perfil, contexto operativo y pertenencia de cada identidad. "
                "La búsqueda documental conserva las comprobaciones del CDE y oculta referencias que el actor no puede leer."
            ),
        ),
        (
            "Segregación de funciones",
            (
                "El perfil puede reforzar la separación entre preparación, aprobación, emisión, evaluación y aceptación. La prueba crítica ejecutó "
                "decisiones con actores independientes y verificó rechazos cuando un actor intentó asumir una decisión incompatible."
            ),
        ),
        (
            "Auditoría",
            (
                "Cada comando relevante registra actor, motivo, estado y versión. Los enlaces y hechos terminales se protegen contra sobrescritura. "
                "Los triggers de PostgreSQL complementan las reglas del servicio para conservar referencias, cantidades e historia."
            ),
        ),
        (
            "API",
            (
                "Las rutas se montan en /api/v1/procurement y separan configuración del tenant, catálogo y operaciones por proyecto. "
                "If-Match protege la concurrencia. Idempotency-Key permite repetir el mismo comando sin duplicarlo y rechaza el mismo identificador con otro contenido. "
                "El inventario por método y ruta está en la matriz."
            ),
        ),
        (
            "Interfaz web",
            (
                "Las vistas de registro, detalle, compras, materiales, seguimiento y trazabilidad se montan en el shell operacional existente. "
                "La configuración administrativa utiliza el centro de configuración; no se creó otra aplicación ni se modificó App.tsx."
            ),
        ),
        (
            "Migración",
            (
                f"20261111_0077 desciende de 20261109_0076 y añade 27 tablas con integridad SQL. El arranque no crea estas tablas. "
                f"Prueba de upgrade, downgrade y upgrade: {e['migration_text']} La base habitual no recibió esta migración."
            ),
        ),
        (
            "Validación PostgreSQL",
            (
                f"{e['pg_text']} El caso crítico usa HTTP y SQL sobre PostgreSQL aislado. Las pruebas deterministas no se cuentan como ciclos completos. "
                f"{e['regression_text']}"
            ),
        ),
        ("Validación Chromium", e["browser_text"]),
        ("Preservación del Proyecto 14", e["preservation_text"]),
        (
            "Rendimiento",
            "Las mediciones, cuando están disponibles, corresponden al proyecto sintético y al entorno local. "
            "La mediana y el tamaño de la respuesta describen esa muestra y no constituyen un SLA de producción. "
            + e["performance_text"],
        ),
        ("Brechas", " ".join(e["gaps"])),
        (
            "Decisión de liberación",
            f"{e['decision']} El resultado técnico no constituye aceptación de negocio, aprobación de despliegue ni autorización para iniciar O2C.",
        ),
        (
            "Siguiente incremento recomendado",
            (
                "Cerrar los controles pendientes de O2B y repetir las validaciones sobre una fuente congelada. "
                "Solo después corresponde decidir si O2C puede consumir la orden operacional como origen sin equipararla a un contrato o compromiso."
            ),
        ),
    ]
