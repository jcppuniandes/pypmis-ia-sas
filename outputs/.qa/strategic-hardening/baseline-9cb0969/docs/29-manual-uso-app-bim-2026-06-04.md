# Manual de uso de la app y modulo BIM

Fecha de corte: 2026-06-04

Este manual explica como operar Pypmis AI SaaS en ambiente local y, con mayor detalle, como usar el modulo de Cantidades BIM. La app debe entenderse como una plataforma de Project Controls: el cronograma, la WBS, la CBS, la FBS, las cantidades BIM, los paquetes AWP y el avance se conectan para producir informacion de control, no listas sueltas.

## 1. Acceso rapido

| Paso | Pantalla | Accion / resultado |
|---|---|---|
| 1 | Navegador | Abrir http://localhost:5173. |
| 2 | Login | Ingresar con usuario local de demostracion. En el ambiente actual se usa admin / 1234. |
| 3 | Workspace | Seleccionar o crear un proyecto. Cada usuario solo debe ver los proyectos donde tiene membresia. |
| 4 | Menu lateral | Entrar al modulo requerido: Dashboard, Process Flow, Planning, Cantidades BIM, Costs, Decisions, Users & Roles. |
| 5 | Flujo guiado | Seguir el siguiente paso recomendado. El objetivo es reducir trabajo manual sin control. |

## 2. Logica general del flujo de informacion

| Orden | Modulo | Salida que alimenta el siguiente paso |
|---|---|---|
| 1 | Project Administration | Proyecto, usuarios, roles y membresias por proyecto. |
| 2 | Planning | Carga XER/XML, WBS, Activity Sheet, baseline, CPM y calidad del cronograma. |
| 3 | WBS / CBS / FBS mapping | Estructura de alcance, estructura de costos y fuentes de fondos alineadas. |
| 4 | Cantidades BIM | Modelo IFC, cantidades controladas, geometria real, tabla de cantidades y trazabilidad a WBS/CBS/FBS/paquetes. |
| 5 | AWP packages | Definicion de CWA/CWP/IWP con path of construction y restricciones. |
| 6 | Progress and EVM | Avance fisico aprobado, PV, EV, AC, SPI, CPI, BAC, EAC y variaciones. |
| 7 | Business processes | Aprobaciones, versiones, recost, conciliacion, decisiones y evidencias. |
| 8 | Closeout evidence | Documentos controlados, auditoria y soporte de cierre. |

La regla operativa es simple: primero se crea estructura, despues se cargan datos fuente, luego se aprueban cantidades o mediciones, y finalmente se usan para costos, avance, paquetes y decisiones. Si falta WBS, CBS, FBS o paquete, el dato existe pero no debe alimentar control definitivo.

## 3. Pantallas principales

| Pantalla | Para que sirve | Como se usa |
|---|---|---|
| Dashboard | Ver estado ejecutivo del proyecto. | Revisar indicadores EVM, curva S, alertas, presupuesto y estado general. Si no hay avance/costos reales, PV/EV/AC deben mantenerse en cero o como dato no disponible. |
| Process Flow | Entender el flujo de proceso. | Revisar que paso esta abierto, que bloquea el avance y que modulo debe operar el usuario. |
| Planning | Controlar cronograma y WBS. | Cargar XER/XML, validar WBS, Activity Sheet, CPM, baseline y calidad del cronograma. |
| Cantidades BIM | Controlar modelo IFC y cantidades fisicas. | Cargar modelo IFC, cargar takeoff, seleccionar elementos, aprobar cantidad geometrica y asignar WBS/CBS/FBS/paquete. |
| Costs | Revisar CBS, FBS, cuentas de control y costo. | Ver presupuesto, fondos, compromisos, costos reales y conciliacion. |
| AWP packages | Preparar paquetes CWA/CWP/IWP. | Revisar paquetes draft, path of construction, restricciones y readiness. |
| Users & Roles | Administrar acceso del proyecto. | Crear usuarios, asignar roles, remover acceso y verificar permisos. |

## 4. Creacion y seleccion de proyecto

| Paso | Accion | Resultado esperado |
|---|---|---|
| 1 | En la pantalla inicial usar New Project. | Se abre el formulario de proyecto sin tapar la tabla de proyectos. |
| 2 | Ingresar codigo, nombre, fase, moneda y fechas. | Se crea el proyecto y el creador queda como Control Manager. |
| 3 | Asignar usuarios y roles. | Cada usuario solo ve los proyectos a los que pertenece. |
| 4 | Completar configuracion operativa. | Quedan permisos, modulos, cost sheet, funding sheet y P6 mapping listos. |
| 5 | Cargar cronograma fuente. | Se crea Activity Sheet, WBS Sheet y baseline para control. |

## 5. Uso del modulo Planning

| Paso | Accion | Validacion |
|---|---|---|
| 1 | Entrar a Planning. | Debe mostrar WBS, Baseline Schedule, CPM, Progress Update, Lookahead, Delay, Recovery y Dashboard del modulo. |
| 2 | Cargar XER/XML. | La app extrae actividades, relaciones, WBS, fechas, duraciones, costos si existen y data date. |
| 3 | Revisar WBS Master Structure. | La jerarquia debe respetar padre/hijo, indentacion y rollup de actividades/costos. |
| 4 | Revisar Activity Sheet. | Cada actividad debe tener Activity ID, WBS, nombre, fechas, duracion, float y costo planeado si el archivo lo trae. |
| 5 | Validar baseline. | La baseline no debe aprobarse si falta moneda, costo cargado o estructura minima de control. |
| 6 | Revisar CPM. | Actividades criticas y float deben venir del cronograma o del calculo CPM basico. |

## 6. CBS, FBS y relacion con WBS

CBS y FBS no deben ser listas aisladas. Deben servir para controlar costo y fondos dentro de la WBS.

| Elemento | Definicion operativa | Relacion esperada |
|---|---|---|
| WBS | Estructura de alcance y trabajo. | Es la base de agrupacion: Ingenieria, Procura, Construccion, Pruebas, etc. |
| CBS | Estructura de costos. | Se relaciona con WBS y familias de costo. Ejemplo: CBS-{Proyecto}-{WBS}-{FamiliaCosto}. |
| FBS | Estructura de fondos. | Se relaciona con fuente de financiacion, autorizacion y control de disponibilidad. |
| Control Account | Punto de control costo/alcance/avance. | Conecta WBS, CBS, paquete AWP, presupuesto y medicion. |
| Quantity Takeoff Line | Cantidad fisica BIM/Excel/IFC. | Debe tener WBS, CBS, FBS y paquete antes de alimentar rollup de control. |

En la version actual las lineas BIM guardan codigos visibles y tambien IDs reales: wbs_id, cbs_id, fbs_id y work_package_id. Esto mejora trazabilidad y evita depender solo de texto.

## 7. Modulo Cantidades BIM: objetivo

El modulo Cantidades BIM sirve para convertir informacion de un modelo BIM/IFC o de un takeoff Excel/CSV en cantidades controladas para Project Controls. El modulo no debe usarse como visor 3D aislado; debe usarse para conectar geometria, cantidad, WBS, CBS, FBS y paquete AWP.

| Funcion | Resultado |
|---|---|
| Cargar modelo IFC | El visor muestra geometria real del edificio/modelo usando web-ifc en navegador. |
| Leer propiedades IFC | El usuario puede seleccionar elementos y ver clase IFC, GUID, nombre, nivel, tipo y propiedades disponibles. |
| Calcular geometria real | La app estima dimensiones y cantidades geometricas reales desde la malla seleccionada cuando es posible. |
| Cargar takeoff | La tabla de cantidades recibe datos desde IFC Quantity Sets, Excel o CSV. |
| Aprobar medicion | El usuario aprueba una cantidad controlada desde geometria o tabla. |
| Asignar codigos | Cada linea queda conectada a WBS, CBS, FBS y paquete. |
| Preparar control | Las cantidades quedan listas para costos, avance fisico, paquetes AWP y conciliacion. |

## 8. BIM: requisitos antes de cargar

| Requisito | Recomendacion |
|---|---|
| Proyecto creado | Trabajar dentro del proyecto correcto. No cargar modelos en proyectos de prueba si se usaran para control. |
| WBS activa | La WBS debe existir y representar el alcance real del proyecto. |
| CBS / FBS | Deben existir codigos de costo y fondos para poder mapear cantidades. |
| Paquetes AWP | Deben existir CWA/CWP/IWP si se quiere conectar la cantidad al paquete. |
| Archivo IFC | Usar IFC coordinado. Para modelos muy pesados, preferir modelo optimizado o exportacion de cantidades. |
| Excel/CSV takeoff | Usar plantilla controlada con columnas de elemento, clase IFC, cantidad, unidad, WBS/CBS/FBS/paquete si ya existen. |

## 9. BIM: cargar un modelo IFC

| Paso | Accion | Resultado esperado |
|---|---|---|
| 1 | Ir a Cantidades BIM. | Aparece el modulo BIM, el visor IFC y la tabla de cantidades controladas. |
| 2 | Usar el boton para cargar modelo. | Seleccionar archivo .ifc. |
| 3 | Esperar lectura. | El backend registra el modelo y el frontend intenta abrir la geometria real. |
| 4 | Verificar visor. | Debe verse el modelo real, no una nube de bloques simbolicos. |
| 5 | Revisar metadatos. | Debe mostrarse archivo, esquema IFC, unidades, niveles, proyecto, edificio y georreferenciacion si existe. |
| 6 | Si se carga otro modelo | Usar limpiar modelo cargado y despues cargar el nuevo IFC. |

Notas importantes:

- El visor actual es el visor IFC real, no el inventario simbolico anterior.
- En modelos grandes, la carga puede consumir memoria o tardar. Si el navegador se vuelve lento, usar un IFC optimizado para coordinacion y un takeoff Excel/CSV para cantidades.
- La cantidad no queda automaticamente aprobada por ver el modelo. El usuario debe aprobar o mapear la medicion.

## 10. BIM: seleccionar elementos en el 3D

| Paso | Accion | Resultado esperado |
|---|---|---|
| 1 | Hacer click sobre un elemento del modelo. | El elemento queda resaltado visualmente. |
| 2 | Revisar panel de propiedades. | Debe mostrar elemento seleccionado, clase IFC, GUID, nombre, tipo, nivel y trazas BIM. |
| 3 | Revisar dimensiones geometricas. | Se muestran dimensiones de la caja geometrica y unidad detectada. |
| 4 | Revisar cantidad geometrica real. | Se muestra area, volumen o longitud estimada si la geometria permite calcularla. |
| 5 | Comparar con tabla de cantidades. | Si existe una linea de takeoff vinculada al GUID, el panel muestra cantidad controlada y regla. |

Si al hacer click no aparece seleccion, revisar:

| Caso | Que hacer |
|---|---|
| Modelo no renderizo | Esperar lectura completa o recargar. |
| Click en zona vacia | Usar zoom/orbita y seleccionar una cara visible. |
| Elemento sin propiedades | Revisar si el IFC exporto GUID y datos de producto. |
| Modelo muy pesado | Usar version optimizada del IFC. |

## 11. BIM: entender que es el tipo de elemento

En IFC el tipo constructivo puede venir de la clase IFC y de la definicion de tipo. La app debe mostrar primero el nombre constructivo comprensible y despues la clase tecnica IFC.

| Dato | Ejemplo | Uso |
|---|---|---|
| Elemento constructivo | Muro arquitectonico, columna, viga, losa, puerta. | Lo entiende el usuario final. |
| Clase IFC | IfcWallStandardCase, IfcColumn, IfcBeam, IfcSlab. | Lo usa el motor IFC. |
| Familia / tipo | Basic Wall / Exterior 200mm. | Ayuda a diferenciar dimensiones y materiales. |
| Instancia | Wall 10, Column A-01. | Identifica el objeto exacto. |
| GUID | 2IRu... | Traza unica del elemento BIM. |

Si el modelo no trae IFC Quantity Sets, la app puede generar ElementCount o estimar geometria. Esa cantidad debe revisarse antes de usarla para costos o avance.

## 12. BIM: cargar cantidades desde IFC, Excel o CSV

| Fuente | Cuando usarla | Resultado |
|---|---|---|
| IFC Quantity Sets | Cuando el modelo trae cantidades publicadas confiables. | Se importan medidas como NetSideArea, NetVolume, GrossArea, etc. |
| Excel/CSV takeoff | Cuando el modelo es pesado o el takeoff ya fue preparado por disciplina. | Se cargan cantidades controladas con columnas auditables. |
| Geometria real del visor | Cuando se necesita validar una medicion desde el elemento seleccionado. | Se calcula una cantidad geometrica y el usuario puede aprobarla. |

Columnas recomendadas para Excel/CSV:

| Campo | Ejemplo | Comentario |
|---|---|---|
| element_guid | 2IRuU8... | Mantiene trazabilidad con el modelo. |
| ifc_class | IfcWallStandardCase | Clase tecnica IFC. |
| category / family / type | Muros / Basic Wall / Exterior 200mm | Nombre constructivo para usuario. |
| storey | Ground floor | Nivel o piso. |
| quantity / unit | 14.25 / m2 | Cantidad y unidad. |
| measurement_rule | NetSideArea | Regla de medicion. |
| wbs_code | 01-04-01 | Alcance. |
| cbs_code | CBS-PRJ-01-04-01-CONC | Costo. |
| fbs_code | FBS-AFE-001 | Fondo. |
| package_code | IWP-01-04-01-CIV-01 | Paquete AWP. |

## 13. BIM: aprobar cantidad geometrica

| Paso | Accion | Resultado esperado |
|---|---|---|
| 1 | Seleccionar un elemento en el visor IFC. | Aparece el panel de propiedades con cantidad geometrica real si puede calcularse. |
| 2 | Revisar dimensiones y unidad. | Validar que metros, milimetros u otra unidad se interpreten correctamente. |
| 3 | Comparar con cantidad publicada o tabla. | Identificar diferencias entre Quantity Set, Excel y geometria. |
| 4 | Click en Usar cantidad geometrica. | La linea queda con medicion controlada aprobada. |
| 5 | Revisar la tabla. | Debe verse Medicion: Aprobada vN y la regla geometrica usada. |

La aprobacion no significa que el modelo sea perfecto. Significa que un usuario responsable acepto esa cantidad como base controlada para una linea o grupo de lineas.

## 14. BIM: asignar WBS, CBS, FBS y paquete

| Paso | Accion | Resultado esperado |
|---|---|---|
| 1 | En la tabla de cantidades, buscar la linea o grupo. | Ver elemento constructivo, cantidad, regla y trazabilidad BIM. |
| 2 | Seleccionar WBS. | La cantidad queda ubicada en el alcance correcto. |
| 3 | Seleccionar CBS. | La cantidad queda asociada a familia/codigo de costo. |
| 4 | Seleccionar FBS. | La cantidad queda asociada a fuente de fondos. |
| 5 | Seleccionar paquete. | La cantidad queda asociada a CWA/CWP/IWP. |
| 6 | Guardar codigos. | La app valida que los codigos existan y guarda codigos mas IDs reales. |

Resultado tecnico esperado:

| Campo | Uso |
|---|---|
| wbs_code / wbs_id | Trazabilidad a estructura de alcance. |
| cbs_code / cbs_id | Trazabilidad a estructura de costo. |
| fbs_code / fbs_id | Trazabilidad a fuente de fondos. |
| package_code / work_package_id | Trazabilidad a paquete AWP. |
| mapping_status | mapped si la cantidad esta lista; needs_mapping si falta algo. |
| raw_data.control_code_assignment | Auditoria de quien asigno, cuando y con que nota. |

## 15. BIM: interpretar la tabla de cantidades controladas

| Columna | Significado |
|---|---|
| Elemento constructivo | Nombre legible: muro, losa, viga, columna, puerta, sistema, familia y tipo. |
| Regla de cantidad | NetVolume, NetSideArea, ElementCount, GeometryMeshArea, GeometryMeshVolume, etc. |
| Cantidad | Valor numerico y unidad aprobada o cargada. |
| BIM Trace | GUID, elemento IFC y referencia de origen. |
| WBS / CBS / FBS / Package | Mapeo de control para usar la cantidad en costos, fondos y paquetes. |
| Estado | mapped, needs_mapping o review segun calidad y completitud. |

Una linea sin WBS/CBS/FBS/paquete puede servir para revision tecnica, pero no deberia usarse para rollup de control de costos o avance.

## 16. BIM: como saber si la cantidad es confiable

| Senal | Interpretacion |
|---|---|
| Fuente IFC Quantity Set publicado | Alta confianza si el modelo fue bien exportado. |
| Fuente Excel/CSV controlado | Confianza media/alta si el archivo tiene responsable y plantilla auditada. |
| Fuente geometria real del visor | Util para validar, pero requiere aprobacion humana. |
| ElementCount | Solo conteo; no reemplaza area, volumen o longitud. |
| Sin GUID | Baja trazabilidad con el modelo. |
| Sin WBS/CBS/FBS/paquete | No esta listo para control integrado. |
| Unidad desconocida | Revisar antes de aprobar medicion. |

## 17. BIM: limpiar modelo y cargar otro

| Paso | Accion | Resultado |
|---|---|---|
| 1 | Entrar a Cantidades BIM. | Ver modelo cargado actual. |
| 2 | Click en limpiar modelo cargado. | Se elimina el registro del modelo seleccionado. |
| 3 | Confirmar que el visor queda vacio o en estado pendiente. | El proyecto queda listo para otro modelo. |
| 4 | Cargar nuevo IFC. | Se registra nuevo modelo y se intenta renderizar geometria real. |
| 5 | Revisar cantidades existentes. | Las cantidades de takeoff pueden pertenecer a otro modelo; verificar GUID y fuente antes de mezclar. |

Buenas practicas:

- No mezclar cantidades de un IFC viejo con un modelo nuevo sin validar GUIDs.
- Si el modelo cambia de revision, documentar la revision del IFC.
- Si se usa Excel/CSV, incluir nombre de archivo, fecha y responsable.

## 18. AWP y BIM

El modulo BIM alimenta AWP cuando las cantidades se asignan a paquetes. La paquetizacion debe respetar una jerarquia clara.

| Nivel AWP | Funcion | Relacion BIM |
|---|---|---|
| CWA | Area de construccion. | Agrupa zonas, niveles o frentes principales. |
| CWP | Paquete de trabajo de construccion. | Agrupa alcance por disciplina, WBS y secuencia. |
| IWP | Paquete instalable de frente. | Debe tener cantidades, restricciones cerradas y readiness para campo. |

El path of construction no es solo un texto. Debe representar la secuencia logica de ejecucion y debe estar soportado por WBS, actividades, paquetes y cantidades fisicas.

## 19. Dashboard y EVM

| Indicador | Formula base | Uso correcto |
|---|---|---|
| BAC | Presupuesto aprobado al completar. | Viene de baseline/cost loading aprobado. |
| PV | Valor planeado a fecha de corte. | Solo se calcula si hay curva planificada por tiempo. |
| EV | Valor ganado por avance fisico aprobado. | Solo se calcula cuando hay avance aprobado. |
| AC | Costo real certificado o incurrido. | Solo se calcula cuando hay costos reales. |
| SPI | EV / PV. | No debe interpretarse si PV es cero o no hay datos. |
| CPI | EV / AC. | No debe interpretarse si AC es cero o no hay costos reales. |
| EAC | Estimado al completar. | Debe calcularse con una regla definida, no como copia automatica si faltan datos. |

Si solo existe baseline y no hay avance ni costos reales, PV, EV y AC no deben inventarse. La curva S debe tener tiempo en el eje X y dinero acumulado en el eje Y.

## 20. Errores frecuentes y solucion

| Problema | Causa probable | Accion |
|---|---|---|
| No carga el modelo | IFC muy pesado, navegador saturado o archivo no compatible. | Usar IFC optimizado, recargar pagina o cargar takeoff Excel/CSV para cantidades. |
| El visor muestra geometria lenta | Modelo grande o muchas mallas. | Cerrar otras pestanas, usar modelo federado reducido o esperar la carga. |
| Selecciono elemento y no veo cantidad | No hay Quantity Set ni linea de takeoff vinculada. | Revisar propiedades, usar cantidad geometrica o cargar Excel/CSV. |
| La cantidad aparece como ElementCount | El IFC no trae cantidades publicadas. | Tratar como revision, no como cantidad final. |
| No puedo guardar codigos | Falta WBS, CBS, FBS o paquete existente. | Crear los catalogos antes de asignar. |
| Sale token invalido | Sesion expirada. | Cerrar sesion e ingresar nuevamente. |
| El proyecto no aparece | Usuario sin membresia en ese proyecto. | Asignar usuario desde Users & Roles con rol correcto. |
| El dashboard muestra EVM raro | Faltan datos de avance/costo o baseline incompleta. | Revisar Activity Sheet, cost loading, progreso y costos reales. |

## 21. Checklist operativo del modulo BIM

| Control | OK esperado |
|---|---|
| Proyecto correcto seleccionado | El nombre/codigo coinciden con el proyecto real. |
| IFC cargado | El visor muestra geometria real. |
| Metadatos revisados | Esquema, unidades, niveles y georreferenciacion si existe. |
| Elementos seleccionables | Click en el 3D resalta elemento y muestra propiedades. |
| Cantidades cargadas | La tabla muestra lineas controladas. |
| Tipo constructivo claro | El usuario ve muro/losa/viga/columna antes de la clase IFC. |
| Medicion aprobada | La tabla muestra aprobacion y version. |
| WBS/CBS/FBS/paquete asignados | Estado mapped y sin bloqueos de mapping. |
| Trazabilidad guardada | Existen codigos e IDs reales para WBS, CBS, FBS y paquete. |
| Listo para control | La cantidad puede alimentar costos, avance o paquete AWP. |

## 22. Recomendacion de uso para piloto

| Dia / sesion | Objetivo | Resultado esperado |
|---|---|---|
| Sesion 1 | Crear proyecto, usuarios, WBS, CBS, FBS. | Proyecto gobernado y roles claros. |
| Sesion 2 | Cargar XER/XML y validar Planning. | Activity Sheet, WBS Sheet, baseline y CPM revisados. |
| Sesion 3 | Cargar IFC y takeoff. | Modelo visible, cantidades cargadas y propiedades revisadas. |
| Sesion 4 | Aprobar mediciones y mapear codigos. | Cantidades mapped con WBS/CBS/FBS/paquete. |
| Sesion 5 | Revisar AWP y EVM. | Paquetes, restricciones y dashboard coherentes. |
| Sesion 6 | Generar evidencia y decisiones. | Hallazgos, aprobaciones y acciones trazadas. |

## 23. Estado actual de la parte BIM

| Componente | Estado actual |
|---|---|
| Visor IFC real | Implementado con web-ifc en navegador. |
| Seleccion 3D | Implementada con resaltado visual del elemento. |
| Propiedades del elemento | Implementadas con clase IFC, GUID, nombre, nivel y propiedades relevantes. |
| Calculo de geometria real | Implementado para dimensiones y estimaciones por malla cuando aplica. |
| Aprobacion de cantidad geometrica | Implementada con versionado de medicion controlada. |
| Tabla unica de cantidades | Implementada como tabla principal de control. |
| Inventario simbolico anterior | Retirado como vista principal porque no representaba geometria real. |
| Asignacion WBS/CBS/FBS/paquete | Implementada y validada contra catalogos existentes. |
| Relaciones fuertes | Implementadas: wbs_id, cbs_id, fbs_id, work_package_id. |
| E2E navegador real | Verificado con Playwright para visor, seleccion, aprobacion y asignacion. |

## 24. Cierre

La parte BIM ya no debe evaluarse como un visor aislado. Su utilidad esta en convertir el modelo y las cantidades en datos controlables para WBS, CBS, FBS, AWP y EVM. El flujo correcto es cargar modelo, validar geometria, cargar o calcular cantidades, aprobar mediciones, asignar estructuras de control y usar esas cantidades solo cuando tengan trazabilidad completa.
