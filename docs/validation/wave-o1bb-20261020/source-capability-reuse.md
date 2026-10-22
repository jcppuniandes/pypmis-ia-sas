# O1B-B: inventario de intercambio, reutilización y límites P6

Fecha de verificación: 21 de octubre de 2026. Dominio: Schedule Foundation. Este documento describe capacidad técnica y evidencia disponible; no acredita una importación realizada en Primavera.

## 1. Caracterización previa y decisiones de reutilización

| Componente existente | Hallazgo verificado | Decisión aplicada |
| --- | --- | --- |
| `backend/app/services/schedule_parser.py::ScheduleParseError` | Excepción pura, sin persistencia ni efectos de Cost. | Reutilización directa del contrato de error. |
| `schedule_parser.py::parse_xer` | Tokenizador de compatibilidad histórica `%FMT:/%ER/%TR`; no reconoce el XER nativo con `%T/%F/%R`. La prueba de caracterización demuestra ese límite. | Se reutiliza únicamente como adaptador de entradas históricas, seguido de validación canónica nueva. No se cambia su comportamiento. |
| `schedule_parser.py::parse_p6_xml` | Extrae un subconjunto mínimo de actividades y relaciones en un namespace fijo; no conserva WBS, calendarios, DataDate, restricciones ni toda la evidencia requerida. | Se conserva intacto para consumidores históricos. No se considera importador canónico completo. |
| `ParsedSchedule.dcma_validate` | Resumen histórico con umbral fijo e indicadores que no representan toda la política nueva. | No sustituye las políticas gobernadas de salud de Schedule Foundation. |
| `backend/app/services/schedule_ingestion.py::ingest` | Materializa estructura de control, CBS/Cost, versiones de baseline y período histórico. | No se invoca desde el nuevo intercambio puro: sus efectos ampliarían autoridad y acoplarían Schedule con Cost. |
| `schedule_ingestion.py::_xer_rows` | Decodificación histórica con descarte de errores y filas de ancho no estricto. | Se conserva sin cambios para compatibilidad; el parser nuevo exige filas completas y decodificación explícita sin pérdida. |
| `schedule_ingestion.py::_hours_to_days` y `_duration_to_days` | Contienen conversión histórica por ocho horas / día. | No se reutilizan: el subconjunto nuevo conserva horas y no calcula días sin calendario. |
| Modelos históricos `ScheduleImport`, `BaselineVersion`, `WBS`, `Activity`, `ScheduleActivityMap` | Acoplados al proyecto histórico, control accounts y valores por defecto que pueden confundir UNKNOWN con cero/no crítico. | Se mantienen como adaptador legado. No son autoridad sobre snapshots canónicos inmutables ni Common Control Period de O1A. |
| Rutas y pantalla histórica de Schedule | Consumidores existentes de ingestión y mapeo histórico. | No se eliminan ni se reescriben desde este trabajo. La integración canónica queda en el módulo nuevo. |
| Exportador P6 existente | No se encontró un exportador XML/XER compatible con el contrato requerido. | Exportador XML nuevo, acotado y explícito, sin denominar CSV/JSON como P6. |

Los archivos anteriores no se modificaron para desarrollar el parser nuevo. No se importan servicios con escrituras implícitas. La reutilización no significa equivalencia total entre el flujo legado y la nueva autoridad de Schedule.

## 2. Contrato puro y preservación

`backend/app/modules/schedule_foundation/exchange.py` expone cuatro funciones sin acceso a base de datos:

- `parse_schedule_source(content: bytes, filename: str) -> dict`: envelope con snapshot, validación, SHA-256 del archivo original, formato, subconjunto soportado y campos no soportados.
- `validate_snapshot(snapshot: dict) -> dict`: errores, advertencias, `can_accept` y `cpm_calculated=False`, sin mutar el snapshot.
- `diff_schedule(previous: dict | None, incoming: dict) -> dict`: altas, bajas, cambios por identidad, DataDate e impactos de mapeos WBS/actividad.
- `export_schedule_xml(snapshot: dict, *, baseline_reference=None) -> bytes`: XML `APIBusinessObjects`, no un archivo de texto renombrado. La referencia de baseline permanece en el manifiesto, no se fabrica un objeto nativo `BaselineProject`.

Las colecciones canónicas son `project`, `wbs`, `activities`, `calendars`, `relationships`, `constraints`, `codes`, `code_assignments` y `external_links`. Las referencias son strings `external_id`. `source_fields` conserva los valores fuente de cada objeto; el servicio conserva además bytes originales y hash. Los campos y objetos fuera del subconjunto se declaran y no se presentan como transportados por el exportador.

Duraciones, float y lags se conservan como HOUR; no existe cálculo CPM, nuevas fechas, ruta crítica ni conversión ocho horas/día. Float y criticidad ausentes permanecen `None`. Porcentaje y fechas reales importados son evidencia y no autoridad de Progress. Se retiene DataDate con la hora/offset informado; no se agrega una zona horaria por suposición. Las relaciones FS/SS/FF/SF mantienen lags positivos, cero o negativos y referencias externas explícitas.

## 3. Subconjuntos y exclusiones

| Capacidad | Estado y límite |
| --- | --- |
| Import XML P6 | Un proyecto por archivo, namespace P6 API, WBS, actividades, calendarios, relaciones, códigos y restricciones declaradas. Objetos no soportados se informan; el original no se reescribe. |
| Import XER nativo | Tablas PROJECT/PROJWBS/TASK/TASKPRED/CALENDAR/ACTVTYPE/ACTVCODE/TASKACTV con encabezados y filas estrictos. El calendario `clndr_data` se retiene opaco: no se interpreta como calendario computable. |
| XER crítico / longest path | `driving_path_flag` significa Longest Path según Oracle y no se convierte en IsCritical. El subconjunto TASK no ofrece un IsCritical canónico: queda UNKNOWN incluso con float negativo. XML sí conserva IsCritical explícito de la fuente. |
| Calendarios XML | Semana/turnos y excepciones/feriados conservados como estructura fuente, junto con HoursPerDay explícito. No se ejecuta aritmética de calendario. |
| Export XML | Subconjunto plano `APIBusinessObjects` para proyecto, calendario, WBS, actividad, relación y códigos. Requiere IDs positivos nativos, HOUR y tipos conocidos. No transporta campos desconocidos, metadata de zona horaria propietaria ni baseline nativo. |
| Export XER | No implementado; `xer_export_supported=False`. |
| Baseline nativo XML | No implementado en este incremento; `native_baseline_transport_supported=False`. Manifiesto/referencia gobernada no equivale a baseline embebido importable por P6. |
| Calendario XER → XML | Se bloquea si el calendario sigue opaco, para no presentar como lossless una conversión que pierde turnos/excepciones. |
| Integración directa P6 / CPM | Fuera del alcance. Sin API P6, sync directo, CPM nativo, leveling ni autorización de Cost/Progress. |

Fixtures: `backend/tests/fixtures/schedule-foundation-p6.xml` y `schedule-foundation-p6.xer`. Son archivos estructurales sintéticos creados para pruebas, no exportaciones obtenidas de una instalación/licencia de Primavera. Incluyen dos WBS, cuatro actividades/hitos, calendarios de diez y seis horas, cuatro tipos de relaciones y una externa.

## 4. Seguridad y validación verificadas

Límites: archivo 20 MiB, registros 50.000, profundidad XML/WBS 50, tablas XER 128 y columnas por tabla 512. Se rechazan DTD/ENTITY, XML no UTF-8, bytes nulos, contenedores incorrectos, XML inválido, campos escalares duplicados, XER truncado, filas de ancho incorrecto y datos después del terminador. XER admite UTF-8 y fallback Windows-1252 explícito sin `errors=ignore`.

Se comprueban identidades/códigos duplicados de actividades y WBS, ciclos y padres WBS no resueltos, referencias de WBS y asignaciones de códigos, fechas inválidas, duraciones negativas, números no finitos, tipos de relación y porcentaje fuera de rango. Relaciones externas/no resueltas se preservan con advertencia; no se inventan actividades internas. Las políticas de salud y aceptación gobernada corresponden al servicio, no se confunden con validez sintáctica del archivo.

Evidencia ejecutable: `backend/tests/test_schedule_foundation_exchange.py`. Comando local: `python -m pytest backend/tests/test_schedule_foundation_exchange.py -q --no-cov -o addopts=`. La prueba de exportación confirma XML bien formado y relectura por el parser propio con igualdad del núcleo soportado; **no equivale a validación XSD ni round-trip en Primavera**.

`backend/tests/observe_schedule_exchange.py` mide siete muestras reales de parse XML, parse XER y diff sobre las fixtures indicadas, después de un warm-up no contado. Registra plataforma, versión Python, bytes y SHA-256 de parser/fuentes. Sus resultados son observaciones locales de fixtures pequeñas, no SLA ni prueba de throughput productivo.

## 5. Documentación primaria Oracle consultada

1. [XML Schema — P6 API](https://docs.oracle.com/cd/F25600_01/English/Integration/p6_and_p6_pro_api_programming/55397.htm): identifica `p6apibo.xsd` y su descarga desde el servidor API instalado. No hay esquema instalado en este entorno; no se afirma validación XSD.
2. [XMLExporter — P6 Integration API](https://docs.oracle.com/cd/E80666_01/English/Integration_Documentation/p6_eppm_api_reference/com/primavera/integration/client/xml/xmlexporter/XMLExporter.html): referencia de exportación de business objects en XML.
3. [TASK — XER import/export data map](https://docs.oracle.com/cd/G48897_01/English/Mapping_and_Schema/xer_import_export_data_map_project/97906.htm): campos de actividad, float en horas, duración, restricciones y significado Longest Path.
4. [TASKPRED — XER import/export data map](https://docs.oracle.com/cd/F74773_01/English/Mapping_and_Schema/xer_import_export_data_map_project/97914.htm): identificadores de predecesor/sucesor/proyecto, tipo y lag.
5. [TASKACTV — XER import/export data map](https://docs.oracle.com/cd/G48897_01/English/Mapping_and_Schema/xer_import_export_data_map_project/97907.htm): asignaciones actividad/tipo/valor de código.
6. [Calendar Fields — P6 web services](https://docs.oracle.com/cd/G48897_01/English/Integration_Documentation/p6_eppm_web_services_reference/42377.htm): HoursPerDay, semana, turnos y excepciones; sustenta no imponer una jornada fija.
7. [Calendar XML example](https://docs.oracle.com/cd/F25735_01/English/User_Guides/develop/10290393.htm): estructura XML de semana de trabajo y excepciones.
8. [Activity Fields — P6 web services](https://docs.oracle.com/cd/E75420_01/English/Integration_Documentation/p6_eppm_web_services_reference/42344.htm): campos y tipos de actividad/restricción.
9. [Field Summary — P6 Professional Integration API](https://docs.oracle.com/cd/F74771_01/English/Integration/p6_pro_api_reference/FieldSummary.html): referencia de Project/DataDate y campos de actividades.

Son consultas públicas de documentación, no llamadas a una API de P6. El namespace V19 elegido no implica certificación contra todas las versiones P6. Para acreditar compatibilidad real futura se requiere esquema de la versión objetivo y prueba import/export en una instalación Primavera autorizada.
