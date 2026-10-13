# Informe técnico Wave 4 QRA Calculation Engine

**Estado actual:** QRA_CALCULATION_ENGINE_RELEASE_VALIDATED

Fecha de corte: 2026-10-12. Producto: P&Pmis Construction AI. Documento asociado: ADR 82.

## 1. Resumen ejecutivo

Se implementó un motor Monte Carlo gobernado para costo y cronograma, separado de QRA Foundation. Incorpora corrida inmutable, semilla reproducible, muestreo correlacionado, resultados estadísticos, ejecución Celery, revisión independiente y un provider de evidencia. Reutiliza las fuentes, modelos aprobados y metodología existentes. El soporte integrado costo-plazo permanece deshabilitado explícitamente.

La validación de costo y plazo está cerrada: READY_FOR_GOVERNED_QRA_RESULTS. El inventario backend consolidado contiene 284 casos PASS y un perfil opt-in, ejecutado aparte con éxito; el navegador final pasó tres escenarios del motor con PostgreSQL y Celery reales y dos regresiones de Foundation. La migración 0068 está aplicada en localhost y no cambió las fuentes operativas comparadas.

No se convierte automáticamente un percentil en presupuesto, contingencia aprobada, fecha contractual ni FID. La metodología histórica con configuración de ejecución vacía sigue siendo válida para Foundation, pero no autoriza nuevas simulaciones. El tenant local conserva su metodología DRAFT y no se publicó durante la instalación. La capacidad validada no equivale a tener un modelo operativo aprobado.

## 2. Baseline real del repositorio

Inicio en rama main, commit d762d873fe2282a8dfe790bacc3b2450691abe83, con head Alembic 20261009_0067. Existían doce archivos modificados y el Word del cierre Foundation. Esos cambios fueron preservados. No se autorizó commit, push, reescritura de historial Git ni publicación de metodología en esta solicitud.

Durante la continuación se encontraron commits del usuario 911a251 y 6a5192e, que ya conservaban parte del incremento; no se deshicieron ni reemplazaron. El backend existente usa FastAPI, SQLAlchemy, Alembic, PostgreSQL, Celery y Redis. El frontend usa React, TypeScript, Vite, Vitest y Playwright. La nueva integración mantiene el router estratégico y la navegación canónica, sin ampliar App.tsx con lógica QRA.

## 3. ADR Wave 4

docs/82-adr-qra-calculation-engine.md registra decisiones, límites, autoridad y referencias primarias. Las decisiones principales son separar QraRun del modelo, congelar un manifiesto reproducible, ejecutar por chunks en un worker real y aceptar resultados mediante un agregado distinto. La red de cronograma es analítica y no sustituye el CPM operativo de P6.

## 4. Arquitectura del motor

La secuencia es: modelo aprobado → preflight vigente → creación de corrida y snapshot congelado → intención durable de ejecución → cola control-core → worker → validación y cálculo → resultado inmutable → revisión y aceptación independiente. El kernel calculation.py no conoce ORM ni escribe dominios de negocio.

models.py define persistencia; policy.py valida configuración; schemas.py tipa comandos; service.py gobierna autoridad y estados; router.py expone contratos; tasks.py ejecuta y recupera intentos abandonados. NumPy y SciPy se fijaron como dependencias del backend.

## 5. Matriz de autoridad de dominio

| Dominio | Autoridad conservada | Límite del motor |
| --- | --- | --- |
| Foundation | Fuentes, metodología, aprobación del modelo | Revalidar y congelar; no reaprobar |
| QRA Engine | Corridas y evidencia analítica | Sin decisiones financieras u operativas |
| Budget, Funding, FIN | Presupuesto, fondos y modelo financiero | Lectura referenciada; ninguna escritura |
| P6 y Schedule | Cronograma operativo importado | Red analítica; sin write-back |
| Risk y Gate/FID | Riesgos, política y decisión gobernada | Sin creación de eventos o aprobación automática |

## 6. Reutilizar antes de crear

Se reutilizan workspace canónico, resolución de configuración, AdminNumberSequence, RBAC, SecurityEvent, ETag, receipts e idempotencia. Se conserva el editor ADMIN de metodología y las pantallas Foundation. No se crean un segundo Project, un nuevo manager ADMIN ni una política Gate paralela. Los nuevos agregados responden únicamente a la ausencia previa de ejecución y aceptación QRA.

## 7. Agregado QraRun

qra_runs conserva tenant, workspace, número, modelo y versión/hash, metodología y revisión/hash, análisis, motor y fórmulas, semilla, iteraciones, input congelado, estado, progreso, resultado, trazabilidad, warnings, actores, fechas, task_id y revisión optimista. La semilla se almacena como cadena decimal para mantener exactamente unsigned 64 bits, incluso al cruzar JavaScript.

## 8. Ciclo de vida de la corrida

QUEUED admite solicitar ejecución o cancelar. VALIDATING pertenece al worker que adquirió el claim. RUNNING publica checkpoints; COMPLETED conserva todas las iteraciones y hashes de resultado. FAILED y CANCELLED no ofrecen resultados parciales aceptables. No hay transición que reutilice una corrida completada como un nuevo intento.

## 9. Cardinalidad modelo y corridas

Una QraModelDefinition puede producir múltiples QraRun, cada una con identidad, número, manifiesto, semilla y resultado propios. Repetir la misma semilla permite verificar reproducción; cambiarla constituye otra realización. Comparar corridas no fusiona ni modifica modelos o resultados.

## 10. Validación previa

Solo pueden ejecutarse modelos APPROVED_FOR_ANALYSIS, vigentes, completos y compatibles. Se verifican hashes, fuentes, denominador, scope, inputs, correlaciones, metodología efectiva y contextos requeridos. Las validaciones se repiten al crear, solicitar ejecución, iniciar y finalizar. Un cambio entre cola y entrega bloquea el intento; no hay refresh oculto.

## 11. Versionado de motor y fórmulas

Motor wave4-qra-v1; distribuciones distribution-inverse-cdf-v1; red normalized-generalized-precedence-dag-v1; percentiles numpy-linear-hyndman-fan-7-v1; sensibilidad streaming-centered-pearson-v1. El manifiesto registra NumPy 2.5.1, SciPy 1.18.0 y PCG64. Una incompatibilidad del entorno no se presenta como una ejecución del mismo motor.

## 12. Gobierno de PRNG y semilla

Se usa un generador PCG64 local por corrida, nunca el estado aleatorio global. USER_SPECIFIED, SYSTEM_GENERATED_AND_PERSISTED y FIXED_FOR_REPRODUCIBILITY son políticas explícitas. Se congelan orden canónico, semilla y chunk. La reproducción depende también del manifiesto y versiones: la misma semilla por sí sola no demuestra equivalencia de modelos.

Referencia primaria: https://numpy.org/doc/stable/reference/random/bit_generators/pcg64.html

## 13. Precisión numérica

Muestreo, cópula y agregación emplean float64. No se redondean partidas durante la simulación. La presentación puede formatear decimales sin cambiar el snapshot. Se rechazan valores no finitos y dominios incompatibles. Las tolerancias aprobadas de PSD y probabilidad son acotadas y quedan congeladas, no se escogen después de observar un fallo.

## 14. Motor de distribuciones

El sampler transforma probabilidades uniformes o correlacionadas por inversas de distribuciones explícitas. Se soportan TRIANGULAR, PERT, BETA_PERT, UNIFORM, NORMAL, LOGNORMAL y DISCRETE, además de componentes deterministas aprobados. Parámetros y base fuente deben ser coherentes; no hay elección automática de distribución por tipo de objeto.

## 15. Triangular

Para mínimo a, modo m y máximo b se exige a ≤ m ≤ b. La inversa usa el punto de separación (m−a)/(b−a) y las dos ramas cuadráticas. El caso a=b es determinista. Se valida soporte y media teórica (a+m+b)/3, además de reproducción exacta con el mismo manifiesto.

## 16. PERT y Beta PERT

Con peso λ explícito, α=1+λ(m−a)/(b−a) y β=1+λ(b−m)/(b−a). Se aplica betaincinv a la probabilidad y se escala a [a,b]. La media es (a+λm+b)/(λ+2). Un intervalo degenerado produce una constante. No se introduce un λ oculto ni una beta distinta de la metodología.

Referencia primaria: https://docs.scipy.org/doc/scipy/reference/generated/scipy.special.betaincinv.html

## 17. Uniforme

La inversa a+(b−a)u preserva límites y permite caso constante. Las pruebas contrastan media (a+b)/2, desviación teórica y percentiles. Una amplitud negativa o parámetros no finitos impiden cálculo; no se intercambian límites silenciosamente.

## 18. Normal

Se exige media y desviación estándar válidas. Una normal no firmada necesita TRUNCATE_AT_ZERO explícitamente aprobado: se usa distribución normal condicionada a no negatividad, no recorte a cero de valores negativos. Las pruebas distinguen ambas operaciones y comprueban su media condicional y reproducción.

Referencia primaria: https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.truncnorm.html

## 19. Lognormal

La parametrización μ y σ en espacio logarítmico es explícita y se valida antes de muestrear. El resultado debe mantenerse positivo y finito. Las pruebas comparan momentos teóricos, soporte y percentiles; parámetros extremos que desborden el cálculo no se convierten en resultados válidos.

## 20. Discreta

Valores y probabilidades se normalizan solo bajo la tolerancia aprobada y la suma debe representar una distribución válida. La inversa usa la probabilidad acumulada. Se rechazan probabilidades negativas, inconsistencias de tamaño y dominios no soportados. Una distribución discreta no genera automáticamente un evento del Risk Register.

## 21. Métodos no soportados

CUSTOM_CONFIGURED, análisis integrado y métodos de correlación o calendario no implementados producen bloqueos explícitos. No se ejecuta eval ni código suministrado en parámetros. La UI y preflight exponen los motivos; una opción declarada no equivale a un método habilitado.

## 22. Construcción de matrices de correlación

Se respeta el orden canónico de inputs, referencias, pares y bloques declarados por el modelo. NO_CORRELATION utiliza independencia. Los componentes conectados permiten matrices acotadas al bloque, evitando una matriz global densa para miles de inputs independientes. Duplicados incompatibles y referencias fuera del scope se rechazan.

## 23. Validación PSD

Se comprueban dimensión, cobertura, coeficientes en [−1,1], simetría, diagonal unitaria y autovalores. Un autovalor materialmente negativo bloquea el cálculo. No se aplica nearest-PSD. Solo el error de redondeo dentro de tolerancia metodológica aprobada puede tratarse en la factorización, con diagnóstico de mínimo autovalor y conteo, manteniendo la matriz fuente sin cambios.

## 24. Muestreo correlacionado

La cópula gaussiana aplica una factorización por autovalores a normales latentes y transforma sus CDF a las marginales. Los coeficientes gobiernan correlación Pearson latente; no se afirma calibración exacta de Pearson marginal para distribuciones no normales. Las probabilidades extremas se acotan a precisión de máquina para evitar inversas infinitas y el método queda versionado.

## 25. QRA de costo

El resultado es la suma, por iteración, de partidas incluidas y componentes deterministas dentro del scope congelado. Deben existir moneda y base fuente compatibles. Un modelo parcial conserva su denominador y exclusiones: no se extrapola a todo el proyecto sin una regla aprobada.

## 26. Base de costo y límite de contingencia

La base, fecha, valor de referencia y target se conservan como información fuente. La diferencia entre un percentil seleccionado y la referencia es un indicador analítico, no una contingencia aprobada. No se usa BAC, presupuesto o funding como referencia intercambiable sin declaración. No se aplica FX implícito.

## 27. Salidas de costo

Media, desviación, mínimo, máximo, coeficiente de variación, percentiles, histograma, CDF empírica, probabilidad de exceder referencia y cumplir target cuando existen. Los drivers y el indicador analítico permanecen vinculados al input y snapshot. El API pagina detalles y no entrega una matriz cruda de simulaciones.

## 28. QRA de cronograma

Se congela una red analítica de actividades, duraciones fuente, relaciones, lags, unidades y ancla de fecha. Cada iteración recalcula precedencias con las duraciones muestreadas. El primer release admite solo actividades explícitamente no iniciadas; avance real y duraciones restantes distintas requieren otro modelo y se bloquean.

## 29. CPM operativo y red probabilística

P6 sigue siendo la autoridad del cronograma operativo. El kernel no publica fechas, float ni criticidad en el import ni en tareas de ejecución. La equivalencia determinista se verifica contra una red de referencia bajo el método analítico aprobado; no se afirma reproducción completa de todos los calendarios y restricciones de P6.

## 30. Relaciones y lags

Se admiten FS, SS, FF y SF en un DAG. Las restricciones para ES del sucesor son respectivamente ES_i+d_i+lag, ES_i+lag, ES_i+d_i+lag−d_j y ES_i+lag−d_j. Se aplica máximo con cero y predecesores; EF=ES+d. Se rechazan ciclos, referencias ajenas, tipos desconocidos y unidades de lag no coincidentes.

## 31. Calendarios

NORMALIZED_ELAPSED_TIME_V1 debe estar aprobado y declara HOURS=3600 o DAYS=86400 segundos. Los calendarios importados permanecen trazables, pero no se evalúan turnos, festivos ni jornadas laborales. No se presume día de ocho horas ni semana laboral. Las fechas resultantes se expresan en UTC con ancla explícita.

## 32. Salidas de cronograma

Duración total, percentiles y fechas, distribución, media, dispersión, probabilidades respecto de referencias y targets declarados, sensibilidad por actividad y hasta 25 hitos seleccionados. Se conserva la unidad de duración y base temporal. Los resultados no se escriben de vuelta al cronograma operativo.

## 33. Criticidad y caminos

No se publican índices de criticidad, frecuencia de caminos dominantes ni métricas CPM probabilísticas en esta versión. La sensibilidad Pearson mide asociación con la duración global; no se renombra como criticidad. Esta limitación es visible y no se marca como una funcionalidad completada.

## 34. Estado del QRA integrado

INTEGRATED_COST_SCHEDULE_QRA queda bloqueado. El release se limita a COST_QRA y SCHEDULE_QRA. Las pruebas verifican que no se produzca un resultado integrado por combinar pantallas o ejecutar dos modelos independientes.

## 35. Acoplamiento integrado

No existe acoplamiento gobernado de escalación por plazo, financiación, recursos ni costos dependientes de actividad. Por ello no se declara soporte integrado. Una extensión futura debe congelar contratos y validar dimensionalmente el vínculo; no basta con compartir semilla o correlaciones.

## 36. Iteraciones

La metodología establece mínimo, default, máximo y autorización de override, con tope técnico de 1.000.000. Cada corrida congela el valor solicitado y registra completadas. Una cancelación o fallo conserva el progreso alcanzado sin convertirlo en resultado completo. El chunk queda aprobado y congelado entre 16 y 1024.

## 37. Convergencia

Estados CONVERGED, NOT_CONVERGED y NOT_EVALUATED se distinguen de COMPLETED. La prueba compara el error estándar de la media s/√N relativo al valor absoluto de la media y exige mínimo metodológico. Si la media es cero, el error relativo es cero únicamente cuando la dispersión también lo es; con dispersión positiva no se declara convergencia relativa. No certifica convergencia de P90/P95 ni de colas extremas.

## 38. Método de percentiles

Interpolación lineal Hyndman–Fan tipo 7, h=(N−1)p/100. Se registran el método y versión; los percentiles son únicos y acotados a 25. Las pruebas usan series conocidas para verificar interpolación y extremos. No se intercambian resultados con otra definición de percentil sin indicar incompatibilidad.

Referencia primaria: https://numpy.org/doc/stable/reference/generated/numpy.percentile.html

## 39. Almacenamiento de resultados

Se persisten resumen, percentiles, bins, CDF, sensibilidad, hitos, diagnóstico de convergencia, provenance y hashes. El JSON de resultado se difiere en consultas de lista/estado; runtime_metadata conserva un resumen pequeño. El resultado solo se guarda de forma atómica tras comprobar estado RUNNING y claim vigente.

## 40. Decisión sobre muestras crudas

No se guardan matrices input×iteración ni muestras crudas en PostgreSQL. Se conserva información suficiente para una nueva reproducción bajo las versiones congeladas. El engine mantiene series globales e hitos durante cálculo para percentiles exactos; esa memoria temporal no constituye almacenamiento persistente ni aprobación de evidencia.

## 41. Sensibilidad

Pearson centrado acumulado por chunks relaciona cada input con el resultado global. Los drivers tienen identidad fuente y método streaming-centered-pearson-v1. Si un input o resultado tiene varianza cero, la correlación no está definida y se reporta como tal, no como un coeficiente fabricado.

## 42. Eventos de riesgo discreto

La distribución discreta se soporta, pero el motor no importa probabilidades e impactos desde Risk Register ni crea eventos de riesgo. El flujo gobernado de este release trata los inputs como incertidumbre y no conserva un mapping individual Risk→input. Los riesgos pueden aportar contexto fuente; eso no constituye un evento probabilístico ni un vínculo causal validado.

## 43. Doble contabilización

Las referencias duplicadas, cobertura y scope se validan. Una base distinta de BASE_COST genera POTENTIAL_OVERLAP_EXISTING_ALLOWANCE_OR_CONTINGENCY_REVIEW_REQUIRED. Este aviso exige revisar posibles allowances o contingencias ya incluidas, pero no detecta automáticamente todo doble conteo ni compensa fuentes. La compatibilidad con eventos individuales del Risk Register no se implementó.

## 44. Readiness analítico

Preflight distingue elegibilidad técnica y actual de la aceptación posterior. COMPLETED indica cálculo íntegro; el estado de convergencia agrega un diagnóstico metodológico distinto. READY_FOR_GOVERNED_QRA_RESULTS es el estado de cierre del incremento, no una aprobación universal de inversiones o fuentes.

## 45. Provenance

Manifiesto de input y resultado conserva modelo, fuentes y hashes, configuración, contexto, scope, referencias, moneda/unidad/base, semilla, iteraciones, PRNG, versiones, fórmulas y timestamps. Los hashes permiten detectar diferencias y confirmar reproducción. La UI de evidencia consulta provenance acotado sin descargar matrices de muestras.

## 46. Inmutabilidad

ORM y triggers protegen identidad y input congelado, incluidos parámetros de lease. Una corrida COMPLETED no admite modificación ni eliminación, tampoco vía SQL directo. La revisión vive en otra tabla; aceptar no altera resultado. Las protecciones se prueban en la migración real, no solo con flags del frontend.

## 47. Cancelación y fallo

Cancelar no publica parcial ni activa provider. La cancelación es cooperativa en checkpoints o finalización; no mata inmediatamente el proceso. El recuperador periódico marca FAILED los intentos con heartbeat vencido. El worker comprueba estado y task_id y no puede resucitar un intento ya marcado FAILED. Fallos registran motivo y progreso, con resultado vacío. Un nuevo cálculo requiere otra corrida.

## 48. Jobs y worker

Se reutilizan Celery, Redis y control-core. execute_qra_run reclama un único intento; la identidad de tarea evita dobles entregas. recover_qra_workers se agenda cada minuto para detectar heartbeat vencido bajo lease congelado. Se verifican permisos del actor al inicio y antes de persistir; revocarlos no se ignora por haber creado la corrida antes.

## 49. Progreso

Cada chunk actualiza iteraciones completadas, heartbeat y versión. El API de estado y polling abortable exponen progreso sin cargar snapshots grandes. El progreso no significa aceptación. Las pruebas distinguen una corrida en cola, cálculo activo, terminal y ausencia de resultados parciales tras fallo.

## 50. Reintento e idempotencia

Los comandos usan Idempotency-Key y ETag. Primero se confirma la intención en la base y después se despacha; un fallo del broker deja estado durable y motivo. El reintento explícito conserva task_id y payload. La misma clave no crea otra corrida y una clave reutilizada con contenido distinto se rechaza.

## 51. Separación de funciones

Seis permisos: qra_run.read, create, execute, cancel, review y accept. Se integran en responsabilidades existentes sin nuevas identidades de rol. El executor no puede aceptar su resultado. Además se conservan SoD de preparación, revisión, aprobación del modelo y publicación de metodología. Los permisos de pantalla no reemplazan controles del servidor.

## 52. Revisión y aceptación

El bootstrap de ejecución reutiliza la autorización Foundation, pero solo añade los seis permisos QRA y grants a roles existentes; no cambia metodología ni asignaciones. Diecisiete pruebas SQLite de bootstrap Foundation y Engine pasaron, incluidos escenarios sin autoridad e idempotencia.

QraRunReview registra IN_REVIEW y ACCEPTED con actores, comentarios, fechas, versión y hash de aceptación. Se exige corrida completa vigente y autoridad independiente. La aceptación significa evidencia analítica revisada, no conformidad contractual, financiación ni aprobación FID. El review aceptado queda inmutable.

## 53. Decisión sobre QRA Result Provider

Se integra QRA_RESULT_PROVIDER con contrato QraResultEvidence.v1. AVAILABLE exige corrida aceptada, íntegra, vigente y no supersedida; de lo contrario se devuelve indisponibilidad con razones. Puede conservar warnings o NOT_CONVERGED: no certifica convergencia ni cobertura universal. El consumidor debe validar tipo de análisis y alcance; la adopción y applicability Gate quedan para Evidence Policy futura, no resueltas por instalar el catálogo.

## 54. Vigencia del provider

Se vuelven a comprobar modelo, metodología, fuentes y contexto. Un cambio de fuente después de aceptación vuelve la evidencia no disponible sin modificar historial. Se conservan referencias y hashes acotados. No se usa el último resultado numérico sin revisar para sustituir una evidencia aceptada.

## 55. Límite Gate07J

No se publica ni modifica automáticamente una política de evidencia Gate07J. El registro ofrece una capacidad futura opcional. Su obligatoriedad debería depender de tipo de proyecto, valor, complejidad, riesgo, incertidumbre, Gate Profile y FEL Stage. Los paquetes históricos y decisiones no se reevalúan ni reescriben por instalar el motor.

## 56. Budget, Funding y FIN

No existen llamadas de escritura a los agregados financieros. Referencias usadas como fuente mantienen identidad y hashes. Ni un percentil ni el indicador de contingencia crean BudgetScenario, compromiso de fondos o actualización de modelo económico. Las pruebas de independencia comparan snapshots de tablas antes y después de ejecutar.

## 57. Schedule y Risk

No se modifica import, tareas, relaciones, calendarios, riesgos ni readiness. La red analítica copia información aprobada en el snapshot de input. No se renombra criticidad importada como probabilidad ni se convierten risk ratings en distribuciones. Los límites se aplican al contrato y al kernel, no solo al texto del informe.

## 58. Consumidores futuros

Portfolio y Business Case pueden consumir evidencia versionada mediante contrato, sin asumir que un resultado sustituye sus decisiones. Una futura adopción necesita política, scope compatible y reglas de vigencia explícitas. No se implementan aquí sincronizaciones automáticas ni optimización de portafolio basada en simulaciones.

## 59. Diseño ADMIN

El editor existente QRA Methodology & Source Readiness incorpora ExecutionPolicy dentro de reserved_engine_settings. Se configuran versiones soportadas, percentiles, histogramas, chunks, iteraciones, seed, convergencia, correlación, revisión y calendario analítico. Una configuración vacía conserva compatibilidad Foundation y bloquea ejecución; no se publica una metodología de demostración en tenants reales.

## 60. Diseño USER

El usuario selecciona workspace y modelo aprobado, valida preflight, crea corrida y solicita ejecución. Consulta estado, resultados, percentiles, sensibilidad, convergencia y evidencia; puede comparar corridas compatibles, cancelar, revisar y aceptar según autoridad. Los botones provienen de allowed_actions del servidor. Un usuario read-only no recibe controles de mutación.

## 61. Navegación

El grupo QRA conserva las vistas Foundation y añade Approved Models, Runs, Run Overview, Cost Results, Schedule Results, Percentiles, Sensitivity, Convergence, Evidence & Traceability, Comparison e History. Se reutilizan blueprint, registry y StrategicViewOutlet. Cambios de workspace o ruta abortan solicitudes y descartan callbacks antiguos.

## 62. Gráficas y read models

El frontend muestra datos calculados por backend: histograma y CDF, percentiles y drivers paginados. No ejecuta Monte Carlo en el navegador. Requests seriales y abortables evitan polling superpuesto y resultados del workspace anterior. Los historiales y estados no descargan snapshots ni inputs completos.

## 63. Comparación

La comparación exige moneda, scope, unidades y base temporal compatibles. Las diferencias de percentiles y dispersión no cambian los originales. Referencias o targets distintos hacen que sus probabilidades se declaren NOT_COMPARABLE; no se resta una probabilidad definida sobre otro umbral como si fuera el mismo indicador.

## 64. Moneda y unidades

No se mezclan monedas ni se aplica conversión tácita. Costo conserva moneda/base; plazo conserva HOURS o DAYS, segundos por unidad y ancla UTC. Lags incompatibles y calendario no soportado bloquean la corrida. Diferencias de unidad o scope bloquean comparación aunque los números tengan magnitudes parecidas.

## 65. Respuesta a deuda de performance

Foundation incorpora proyección JSON en SQL, arrays paginados en PostgreSQL/SQLite, metadata-only picker de costo y PATCH incremental de hasta 200 inputs. Los summaries omiten matrices y listas grandes; las correlaciones se solicitan explícitamente para editar. Preparers se conserva internamente para SoD, aunque no se publica en resumen.

La reevaluación completa y generación del manifiesto aún materializan fuentes/modelo una vez: no se afirma coste constante ni normalización relacional de todos los inputs. El perfil de 10k actividades midió evaluación con JSON en 22,628 s y 71.843.617 bytes trazados. Leer 25 inputs demandó 0,106 s y 36.460 bytes; el summary 0,127 s y 133.970 bytes. No hubo escrituras y las consultas se mantuvieron constantes entre 5k y 10k. El tiempo de evaluación creció 2,092 veces y la memoria 1,994 veces; esta red sintética no demuestra complejidad universal.

## 66. Modelo de memoria

El cálculo procesa chunks de input y acumula momentos de sensibilidad. Mantiene resultados globales e hitos por iteración, no todas las muestras. La correlación ocupa matrices de bloques acotados. El benchmark publica memoria medida; no se fija un SLA usando una sola máquina y una carga concurrente de desarrollo.

## 67. Persistencia

qra_runs y qra_run_reviews añaden historial y aceptación. Índices sobre tenant, workspace, modelo, estado y history, unicidad de número por tenant y task_id, constraints de estado/progreso y resultado completo. JSON de input/resultado es deferred por defecto para lecturas frecuentes. Los SecurityEvent pertenecen a auditoría y no son mutaciones upstream.

## 68. Migración

20261011_0068 depende de 20261009_0067 y crea exclusivamente tablas y protecciones del motor. No reescribe Foundation ni fuentes. Up/down/up se probó en SQLite y PostgreSQL desechables con marcadores de preservación. El downgrade elimina únicamente el incremento; no constituye una orden de borrar datos operativos.

Localhost se actualizó después de respaldo pg_dump de 2.017.490 bytes, SHA256 BBBF5B07C1B223238A8C0287980E3C4D50877E11F99F02F4AB527ADD9C574A11 y comprobación del catálogo de restore. Se detuvieron API, worker y beat sin tareas activas; se aplicó Alembic antes de arrancar la API nueva. El bootstrap del tenant 1 y administrador 1 añadió seis permisos y veinte grants a roles existentes, sin roles, asignaciones, configuraciones ni corridas nuevas. El head local es 0068 y las dos tablas cuentan con triggers reales.

API ready confirmó database y Redis; frontend /app devolvió HTTP 200. Worker registró ejecución y recuperación QRA y beat publicó la recuperación periódica. Un timeout inicial del frontend y healthcheck transitorio durante arranque frío se resolvieron al completar la carga; la comprobación posterior fue correcta. En workspace canónico 14, options devolvió cero modelos aprobados y política vacía, coherente con la única metodología local aún DRAFT. No se publicó ni cargó una fixture operativa para aparentar disponibilidad de datos.

## 69. API

Prefijo /api/v1/qra-engine: options por workspace, preflight por modelo, creación, historial, status, ejecución, cancelación, lectura paginada de resultados, provenance, comparación, revisión, aceptación y provider. Foundation conserva rutas existentes y agrega PATCH metadata/inputs y GET correlations explícito. Los comandos requieren RBAC, scope, ETag e idempotencia según corresponda.

## 70. Happy path de costo en PostgreSQL

PASS en los tests de servicio de PostgreSQL aislado: fuentes y modelo realmente aprobados, corrida creada, cálculo completo, resultado y revisión independiente. El despacho al broker se inyecta en esos tests, no el cálculo. El E2E separado usa PostgreSQL y Celery reales, sin interceptar rutas ni insertar resultados completados. Evidencia backend-postgres-final.xml, módulo test_qra_engine, y browser final.

## 71. Happy path de plazo en PostgreSQL

PASS en PostgreSQL aislado. La fixture declara autoridad P6 XML, unidades de lag y fuentes antes de aprobar evaluaciones. El caso calcula fechas y duraciones desde el snapshot y verifica no write-back. La regresión del parser tiene once pruebas, incluida XML de múltiples actividades con HOURS, DAYS y milestone. Las fixtures están restringidas a bases desechables; no se ejecutan en el tenant operativo.

## 72. Validación del análisis integrado

No liberado. Configuración, preflight y kernel bloquean soporte integrado; se valida rechazo. Esta exclusión no es un happy path integrado ni se registra como PASS del cálculo integrado.

## 73. Reproducibilidad

PASS. Se comparan múltiples corridas del mismo modelo, semilla, iteraciones y manifiesto: coinciden resultados y hash. En el navegador con worker real, repetir semilla 2026 produjo el mismo hash, mientras 2027 generó otro resultado. El hash numérico no incluye identidad ni timestamps de la nueva corrida; hashes de input y trazabilidad se distinguen de los del resultado.

## 74. Cambio de semilla

Otra semilla produce una realización distinta manteniendo distribución y significado. El cambio no convierte en inválidos los estadísticos por variación aleatoria. Las pruebas verifican diferencia de resultados junto a reproducción exacta de la misma semilla, sin depender de una expectativa de igualdad entre semillas diferentes.

## 75. Pruebas de distribuciones

La suite numérica final ejecutó 91 pruebas en 14,66 segundos: las 87 existentes y cuatro casos independientes añadidos durante el cierre. Incluye soporte, momentos, límites, parámetros inválidos, normal truncada, discreta, cuantiles lognormales contrastados con referencia analítica y percentiles tipo 7 de una serie no constante conocida. Evidencia calculation-final-20261012.xml; no se suman reruns para inflar cobertura.

## 76. Pruebas PSD

Se incluyen matrices válidas, singulares, coeficientes extremos, estructura inválida y matrices no PSD. El caso no PSD debe fallar sin modificar la correlación original. Las pruebas distinguen tolerancia de redondeo aprobada y reparación material prohibida. La cópula se contrasta con correlación latente y reproducibilidad.

## 77. Validación estadística

Se contrastan media, desviación, percentiles, CDF y frecuencias discretas con fórmulas o referencias conocidas y tolerancias explícitas. El sampler no se valida por apariencia de una gráfica. El benchmark mide capacidad; no reemplaza las pruebas de exactitud. La auditoría independiente añade casos adversariales del kernel y service.

## 78. Equivalencia determinista de cronograma

Con duraciones constantes la red debe producir el mismo resultado en todas las iteraciones. Se verifican seriales y ramas paralelas bajo elapsed-time. Estado de actividad ausente, iniciada/completada, restricciones no soportadas y remaining diferente de duración fuente bloquean. No se afirma equivalencia completa con P6 operativo.

## 79. Contraste independiente de red

La referencia de pruebas aplica directamente restricciones generalizadas FS/SS/FF/SF y lags, independiente de la función de producción. Ciclos, referencias externas y unidades incorrectas fallan. La revisión del kernel cerró un caso en que una actividad con avance podía parecer no iniciada por falta de fechas reales.

## 80. Validación de convergencia

Casos deterministas, mínimo insuficiente, tolerancia estricta y evaluación deshabilitada verifican estados distintos. El estado COMPLETED no garantiza CONVERGED. La regla de error estándar de media se valida; la convergencia de colas no fue implementada y permanece deuda explícita.

## 81. Validación de sensibilidad

PASS. Además de drivers conocidos y casos constantes, dos pruebas nuevas contrastan el acumulador por chunks con numpy.corrcoef sobre las mismas muestras, con bases cero y 1e12 y chunks de 128 o 257. Un resultado constante no genera un coeficiente ficticio. La referencia independiente detecta errores de centrado que una segunda llamada al mismo acumulador no demostraría.

## 82. Modelo stale

PASS. Las pruebas cambian una fuente después de aprobación y entre encolado e inicio. Preflight o worker bloquean, conservan motivo y no publican resultado. El provider aceptado también se vuelve no disponible por cambios de fuente sin reescribir el historial. Casos verificados en service, hardening, auditoría de aceptación y provider integration.

## 83. Método no soportado

Se verifica bloqueo de CUSTOM_CONFIGURED, Integrated, policy inválida, calendario y relaciones desconocidas. No se sustituyen por defaults. La configuración histórica vacía pasa Foundation pero no autoriza engine. Parámetros anidados malformados producen errores controlados, no excepciones internas por tipos inesperados.

## 84. Cancelación y atomicidad

Se prueban cancelación en cola y checkpoint, fallo tras progreso, broker no disponible, tarea duplicada y recuperación por lease. El claim final protege contra un worker tardío que intente completar una corrida FAILED. El resultado de una corrida fallida o cancelada debe permanecer vacío y no elegible para provider.

## 85. Regresiones de independencia

PASS en auditoría y regresiones seleccionadas: fuentes, configuración publicada, Foundation, Budget, Funding, FIN, Risk, Schedule, Gate y FID se comparan antes/después de ejecutar. No hubo escrituras upstream. En la instalación local también permanecieron iguales 35 categorías operativas y siete controles adicionales de Foundation, metodología, usuarios y cronograma completo. Las fixtures crean datos antes del snapshot solo en bases desechables; no se afirma ejecución de todo el catálogo histórico del repositorio.

## 86. Browser USER E2E

PASS en Chromium real → React → API → PostgreSQL → Redis/Celery, sobre el frontend reconstruido con los ajustes finales. Tres escenarios abarcan read-only, ADMIN y ciclo de ejecución: creación/preflight, costo y plazo, progreso, semillas, comparación, convergencia, evidencia y aceptación independiente. La cancelación del navegador corresponde a una corrida QUEUED antes de solicitar ejecución; la interrupción cooperativa de un worker activo se valida en backend. XML browser-final-20261012.xml, duración aproximada tres minutos, con trazas y capturas completas y focalizadas.

La corrida aceptada final QRR-000006 quedó COMPLETED, ACCEPTED, READY_WITH_WARNINGS y CONVERGED, con motor wave4-qra-v1 y semilla 2026. Esa identidad pertenece solo al tenant de prueba. No hubo page.route, respuesta simulada, resultados insertados ni cálculo Monte Carlo en browser. Se corrigió además un race de polling que abortaba la lectura de detalle al recibir COMPLETED; su regresión espera un detalle tardío y verifica historial y comparación actualizados.

## 87. Browser ADMIN E2E

PASS. El caso prueba ExecutionPolicy en el editor existente, clona y guarda DRAFT y confirma que la metodología publicada no cambia. Verifica ausencia de manager paralelo y de controles USER de ejecución en ADMIN. Una captura intermedia intentó leer el editor ya cerrado tras guardar; se corrigió el harness para reabrir el DRAFT y verificar su JSON antes de capturarlo. No fue un cambio funcional ni un resultado válido de E2E: el intento fallido quedó preservado y el rerun final de tres pruebas pasó. La publicación del método ocurre solo en fixture desechable anterior al E2E.

La regresión original de Foundation también pasó sus dos escenarios USER y ADMIN en 222,20 s. Valida ciclo de fuentes y modelos, autoridad independiente, historial congelado, tailoring, SoD, preview no persistido, publicación, archivo y staleness. Usó la fixture aislada del workspace 4 y configuración 21, sin tocar el tenant operativo. Su modelo INTEGRATED es solo una definición Foundation y no demuestra ejecución integrada del motor. Evidencia foundation-browser-final-20261012.xml, con trazas completas.

## 88. Seguridad de rutas directas

Permisos y scope se validan en servidor además de ocultar botones. Se incluyen actor sin autoridad, otro tenant/workspace, ETag stale y aceptación por executor. La navegación directa ADMIN con usuario read-only no expone el editor. El worker revalida permisos actuales del actor de ejecución, no una copia antigua de autorización.

## 89. Benchmark

Medición final de kernel con tracemalloc, Windows y carga concurrente, sin persistencia. No es SLA. Archivo benchmark-kernel-final-20261012.json. Se reportan MB decimales; RSS es un máximo acumulativo de proceso, no memoria exclusiva de cada operación.

| Caso | Wall s | CPU s | Memoria trazada MB | RSS máxima MB | Payload bytes |
| --- | --- | --- | --- | --- | --- |
| Costo 1.000 inputs × 10.000 iteraciones | 3,195 | 3,000 | 12,72 | 104,48 | 169.521 |
| Plazo 1.000 actividades × 10.000 iteraciones | 17,144 | 16,469 | 17,05 | 110,76 | 181.331 |
| Plazo 10.000 actividades × 2.000 iteraciones | 43,931 | 41,984 | 168,46 | 272,42 | 1.748.741 |

El último caso demuestra factibilidad de 10k actividades, no el costo de 10k×10k. Escrituras DB del kernel: cero. La limitación de espacio en C motivó reutilizar imágenes y no duplicar artefactos grandes.

El perfil separado ejecutó worker_execute real con 1.000 inputs triangulares independientes, 10.000 iteraciones y chunks de 128 en SQLite en memoria. Midió 23,925 s wall, 18,391 s CPU, 10.227.701 bytes trazados y RSS acumulativo de 393.502.720 bytes. Registró 416 SELECT, 85 escrituras DML —83 UPDATE qra_runs y dos INSERT de auditoría— y 80 checkpoints, incluido el inicial. El payload fue de 196.715 bytes, sin muestras crudas. Hashes de fuentes y momentos numéricos permanecieron correctos; la prueba pasó en 197,49 s.

El setup se midió aparte: schema 8,478 s, identidad 5,134 s, fixture aprobada 77,546 s y creación más solicitud 16,536 s. El dispatcher se omitió en este perfil, pero no se sustituyó el cálculo ni el service. No mide broker, HTTP, disco ni PostgreSQL; el E2E separado sí recorre PostgreSQL y Celery reales. Sus distribuciones y chunk difieren del benchmark kernel, por lo que no es una medida comparable de overhead puro ni un SLA. Evidencia worker-profile-final-20261012.json y XML.

## 90. Deuda técnica

Perfil Foundation final, 10.000 actividades en SQLite aislado, incluyendo serialización JSON. Todas las operaciones tuvieron cero escrituras.

| Lectura | Wall s | CPU s | Pico trazado bytes | Consultas | Payload bytes |
| --- | --- | --- | --- | --- | --- |
| Adapter | 17,279 | 16,656 | 71.570.578 | 7 | 5.509.809 |
| Evaluación fuente | 22,628 | 21,844 | 71.843.617 | 8 | 4.674.634 |
| Registro completo | 7,377 | 6,906 | 36.449.085 | 7 | 5.171.110 |
| Página de 25 inputs | 0,106 | 0,109 | 36.460 | 4 | 4.415 |
| Resumen | 0,127 | 0,125 | 133.970 | 7 | 1.054 |

RSS acumulativo máximo 566.595.584 bytes, incluidos imports, setup y casos anteriores. El picker de 1.000 fuentes paginó 25 identidades en 0,283 s y cinco consultas. Las primeras ejecuciones del profiler fallaron por una colisión UNIQUE de control_snapshots en el seed amplio y una clave incorrecta de fixture; se corrigió únicamente el setup desechable con un bootstrap mínimo, sin cambiar el seed productivo. La ejecución final pasó en 121,70 s y conserva los fallos previos como evidencia, no como resultados válidos.

QRA integrado, calendarios laborales P6, avance real/remanentes, criticidad probabilística, calibración marginal, convergencia de colas y eventos Risk automáticos no están implementados. Foundation aún materializa el modelo para reevaluación e input congelado y tiene costo significativo al guardar modelos grandes. No se prometen SLA ni compatibilidad numérica indefinida entre versiones.

ESLint global pasó con nueve warnings del visor BIM existente, sin errores y dentro del límite CI de diez; no se modificó ese componente durante el cierre QRA. PostgreSQL produjo un aviso de deprecación Starlette y otro de serialización Pydantic en un caso negativo intencional. La etiqueta commit de health conserva el valor local configurado bb234f2, por lo que no acredita el HEAD Git ni un push. Los nuevos jobs CI están preparados, pero GitHub no se ejecutó ni se actualizó automáticamente en esta solicitud.

## 91. Estado del registry

QRA_RESULT_PROVIDER se añadió como capacidad opcional gobernada. Las pruebas de aceptación, currentness y supersession validan su contrato; COST_SOURCE_READINESS_PROVIDER y SCHEDULE_SOURCE_READINESS_PROVIDER mantienen los existentes. Las políticas publicadas no reciben un requisito QRA automáticamente. Catálogo disponible no significa resultado AVAILABLE para cualquier proyecto ni decisión de inversión aprobada.

## 92. Estado final de release

QRA_CALCULATION_ENGINE_RELEASE_VALIDATED. final_output = READY_FOR_GOVERNED_QRA_RESULTS. QRA_RESULT_PROVIDER = AVAILABLE como capacidad demostrada para el caso aceptado y vigente en prueba; no como disponibilidad universal del tenant local ni aprobación Gate.

| Comprobación | Resultado | Alcance de evidencia |
| --- | --- | --- |
| Backend consolidado | 284 PASS y un opt-in | 285 casos únicos, sin fallos pendientes |
| PostgreSQL amplio | 270 PASS, dos fallos posteriormente resueltos, un opt-in | 273 casos, 26 min 5,79 s |
| Suplemento final | 30 PASS | Bootstrap, parser y migración 0068; 5 min 7,29 s |
| Numérica final | 91 PASS | Cuatro contrastes independientes nuevos; 14,66 s |
| Frontend focalizado | 72 PASS en siete archivos | QRA, Foundation, política y navegación; 39,85 s |
| Chromium final | Tres PASS | Bundle reconstruido; PostgreSQL y Celery reales; 182,51 s |
| Chromium Foundation | Dos PASS | Regresión USER y ADMIN original; fixture aislada; 222,20 s |
| TypeScript y build | PASS | tsc global y Vite producción sobre código final |
| Ruff y formato backend | PASS | 434 archivos, Ruff 0.16.3 |
| ESLint y Prettier frontend | PASS | src completo; cero errores, nueve warnings BIM existentes |
| Guardrails y YAML | PASS | Suplemento estático, CI y Compose parseados, diff limpio |
| Perfiles opt-in | PASS por separado | Foundation 1 PASS y worker 1 PASS; tres casos kernel con sanity PASS |
| Migración y operación | PASS | Up/down/up desechable y upgrade local real, API ready y HTTP 200 |
| Integridad operativa | PASS | 35 categorías más siete controles, hashes sin cambios |
| Integrado y write-back | No liberados | Bloqueo explícito; sin Gate, FID, presupuesto o cronograma automático |

La consolidación por (classname, name) conserva el último resultado, sin sumar reruns. Los dos fallos iniciales del bootstrap —22 permisos frente a 16 esperados— se resolvieron en el suplemento con el filtro correcto. El perfil Foundation opt-in pasó aparte. Algunas pruebas del contenedor usan SQLite propio; no se afirma una única corrida de 285 tests PostgreSQL ni cero warnings.

Evidencias finales, inventario deduplicado y trazas: outputs/.qa/qra-engine. Los nuevos logs y dumps se excluyen de Git. El informe conserva 93 secciones. No hubo commit/push del agente ni ejecución GitHub CI; los jobs quedan listos para publicación autorizada.

## 93. Única recomendación del siguiente incremento

Recomiendo A QRA Result Evidence Policy Integration, con adopción opcional y applicability gobernada por riesgo, incertidumbre, valor y etapa. El motor de costo y plazo y el provider están validados; falta decidir su uso en Gate/FID. Frente a B QRA Advanced Analytics and Hardening, conviene validar primero ese consumo, manteniendo explícitos los límites de calendario, convergencia de media y ausencia de integración. Los benchmarks no son SLA y persiste deuda Foundation para modelos grandes. No se impone QRA universal ni se publica una política automáticamente.
