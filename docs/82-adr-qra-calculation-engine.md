# ADR Wave 4 QRA Calculation Engine

Estado: implementado en desarrollo local; cierre condicionado a la evidencia de validación del informe de release.

## Contexto y baseline

La rama inicial es main, commit d762d873fe2282a8dfe790bacc3b2450691abe83, con head Alembic 20261009_0067. Se preservan doce archivos modificados y el informe Word del cierre QRA Foundation de 2026-10-11. No se realiza commit, push ni publicación automática de metodología.

Foundation conserva la autoridad sobre evaluaciones de fuentes, configuración publicada y QraModelDefinition aprobado. El nuevo motor solo puede consumir una definición aprobada y vigente, cuyo hash, ámbito, fuentes, metodología y contextos requeridos se vuelven a comprobar al crear, solicitar, iniciar y completar una corrida.

## Decisión de dominio

Crear QraRun separado, con número QRR generado por AdminNumberSequence, input congelado, semilla unsigned de 64 bits, versiones y hashes de input, resultado y trazabilidad. QraRunReview conserva revisión y aceptación independientes del resultado inmutable. Una definición admite varias corridas; toda repetición constituye una nueva identidad.

La aceptación significa evidencia analítica revisada, no FID, presupuesto, contingencia aprobada ni nueva fecha contractual. El provider QRA_RESULT_PROVIDER únicamente ofrece evidencia aceptada, vigente y no supersedida. Su presencia en el catálogo no modifica políticas publicadas de Gate07J.

## Ejecución y atomicidad

Reutilizar Celery, Redis y la cola control-core. El comando de ejecución registra primero una intención durable y realiza el envío después del commit. Reintentos de envío conservan task_id e idempotencia. El worker adquiere la corrida mediante compare and swap de estado e identificador, valida permisos actuales del actor y revalida el modelo.

Los checkpoints confirman progreso y heartbeat por chunk. Cancelación y fallo no publican resultados parciales. La comprobación final exige mantener el claim RUNNING y la identidad del worker; la expiración de lease conserva un intento FAILED y requiere una nueva corrida. Un recuperador periódico atiende workers abandonados sin repetir silenciosamente simulaciones.

## Matemática y reproducción

NumPy 2.5.1 y SciPy 1.18.0 quedan fijados. PCG64 utiliza una instancia explícita por corrida; se congela el orden canónico de inputs y el tamaño de chunk. Se registra el manifiesto con versiones de librerías, PRNG, distribuciones, percentiles, red y sensibilidad. Si el entorno cambia, una corrida pendiente no se ejecuta como si correspondiera al mismo motor.

El muestreo y agregación emplean float64 sin redondeo monetario durante la simulación. Los percentiles usan interpolación lineal Hyndman Fan tipo 7. La sensibilidad usa Pearson centrado acumulado por chunks. La convergencia compara el error estándar relativo de la media y el mínimo metodológico de iteraciones; no certifica convergencia de colas.

Triangular, PERT y Beta PERT, uniforme, normal, lognormal y discreta tienen fórmulas y parámetros explícitos. La normal no firmada necesita autorización de truncación condicional en cero, nunca recorte silencioso de muestras. CUSTOM_CONFIGURED y métodos desconocidos se bloquean.

## Correlación

Validar referencias, cobertura, simetría, diagonal, coeficientes y semidefinitud positiva. Los bloques conectados permiten matrices locales acotadas; no se crea una matriz densa global para 10000 inputs independientes. La cópula gaussiana utiliza coeficientes de correlación latente, no una calibración de correlaciones marginales.

No hay nearest PSD. Solo se tolera error numérico aprobado en autovalores cercanos a cero; su magnitud y tratamiento de factorización quedan declarados. Una matriz materialmente indefinida se rechaza sin modificar el modelo.

## Costo

Sumar incertidumbre y componentes deterministas dentro del ámbito aprobado, conservando moneda y base de costo. Exponer media, dispersión, percentiles, histograma, CDF y probabilidades respecto de referencias explícitas. Un indicador de diferencia entre percentil y referencia es exclusivamente analítico. No existe FX implícito ni escritura en Budget, Funding o FIN.

## Cronograma

Primera versión deliberadamente limitada a NORMALIZED_ELAPSED_TIME_V1 aprobado: horas de 3600 segundos o días transcurridos de 86400 segundos, ancla explícita y resultados UTC. Los calendarios importados permanecen congelados y trazables, pero esta versión no reproduce calendarios laborales, feriados ni turnos de P6. No se presume jornada de ocho horas ni semana de cinco días.

La red analítica es un DAG de precedencias generalizadas FS, SS, FF y SF con lags de unidad coincidente. Se rechazan ciclos, referencias fuera del ámbito, restricciones no implementadas y avance real sin un modelo de duración remanente. No se reutilizan flags de criticidad ni float operativo como métricas probabilísticas.

## Alcances no implementados

INTEGRATED_COST_SCHEDULE_QRA se bloquea. Tampoco se implementan eventos automáticos del Risk Register, calibración marginal de correlaciones, criticidad de caminos, contingencia aprobada, probabilistic FIN ni sincronización con P6. Son límites visibles, no resultados simulados ni PASS ficticios.

## Memoria y persistencia

El motor procesa inputs por chunks y conserva las series de resultados globales y de hasta 25 hitos, no todas las muestras input por iteración. Las sensibilidades se acumulan con momentos centrados. Complejidad de memoria: inputs por chunk, bloques de correlación acotados y resultados por iteración e hito seleccionado.

No se persisten muestras crudas. Los manifiestos congelados, versiones y semilla permiten reproducción. Los read models de lista y estado difieren JSON grandes; Foundation incorpora proyección JSON y paginación de arrays en SQL, picker de identidades sin materializar todas las fuentes y edición incremental de inputs.

## Migración y seguridad

La migración aditiva y reversible 20261011_0068 sucede a 0067 sin modificarla. Crea qra_runs y qra_run_reviews, constraints, índices y protección de historial en PostgreSQL y SQLite. Los triggers impiden cambios del input congelado, modificación de corridas completas y eliminación de historial; los reviews aceptados también quedan protegidos.

Se reutilizan workspace canónico, RBAC, asignaciones existentes, ETag, receipts y SecurityEvent. Se añaden permisos qra_run read, create, execute, cancel, review y accept a responsabilidades existentes, sin crear un módulo ADMIN paralelo.

## UX y operación

USER navega por QRA dentro de Business Case and Investment Development, selecciona modelos, valida, crea y ejecuta corridas, consulta progreso, resultados, convergencia, evidencia, comparación e historial. ADMIN configura la sección de ejecución dentro de QRA Methodology vigente. Una configuración histórica con reserved_engine_settings vacío mantiene validez Foundation, pero no habilita ejecución.

## Referencias primarias

- NumPy PCG64: https://numpy.org/doc/stable/reference/random/bit_generators/pcg64.html
- NumPy percentiles: https://numpy.org/doc/stable/reference/generated/numpy.percentile.html
- SciPy inversa beta regularizada: https://docs.scipy.org/doc/scipy/reference/generated/scipy.special.betaincinv.html
- SciPy normal truncada: https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.truncnorm.html
- NIST función beta: https://dlmf.nist.gov/8.17
