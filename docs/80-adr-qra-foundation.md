# ADR QRA Foundation

Fecha: 2026-10-09. Decisión: preparación gobernada antes de cualquier motor probabilístico.

## Contexto

El baseline real es main 9cb0969 con trabajo previo no confirmado, migración 20261008_0066 y Owner Capability de Wave 3B existente. Cost Control, FIN, Budget, FEL/PDRI, Risk, Basic Data y Owner mantienen sus autoridades. Los importadores manuales P6 XML/XER y sus mapas ya son la autoridad de cronograma; no se sustituye ese dominio.

## Decisión

Implementar un módulo acotado `qra_foundation` que consume fuentes de sólo lectura, completa evaluaciones de preparación y gobierna definiciones del modelo. Reutilizar AdminConfiguration para metodología independiente, EnterpriseWorkspace PROJECT para identidad, SecurityEvent, roles, secuencias, ETag e idempotencia. Crear solamente tres agregados versionados y una tabla de recibos de comandos.

Conservar metadatos originales de nuevos ScheduleImport en una columna JSON aditiva. Las importaciones antiguas conservan metadatos vacíos: no se inventan calendarios, unidades, restricciones ni Data Date. Una fecha límite MustFinishByDate no es Data Date. Los controles QRA usan campos crudos y unidades explícitas, no deducen horas por día ni ejecutan CPM.

Evaluaciones COMPLETED y modelos APPROVED_FOR_ANALYSIS congelan snapshot y hash. Las proyecciones actuales pueden pasar a STALE sin modificar esa historia. Refresh Preview es no persistente; Refresh Apply crea un sucesor DRAFT, conservando identidad estable y predecesor.

## Autoridad

ADMIN publica metodología, no evidencia viva. USER prepara fuentes y modelos dentro de su proyecto autorizado. Los proveedores de costo y cronograma entregan evidencia solamente desde evaluaciones COMPLETED, READY y actuales. Registrar un contrato AVAILABLE no declara que todos los proyectos tengan evidencia disponible.

No se crea proveedor de resultados QRA ni requisito en las políticas Gate07J publicadas. No se alteran paquetes Gate históricos, FID, FEL/PDRI ni fuentes financieras. La base de Cost Source Readiness no es aprobación del presupuesto ni sustitución de Cost Control.

## Alternativas descartadas

Duplicar tablas de cronograma, integrar P6 API/OPC o normalizar duraciones mediante supuestos universales ocultaría la autoridad existente. Añadir simulación ahora mezclaría preparación de evidencia con ejecución probabilística. Una única política global publicada automáticamente ignoraría la configuración organizacional y la separación de funciones.

## Consecuencias

La preparación es auditable y reversible. La granularidad de los adaptadores limita el análisis: una línea FIN o de presupuesto no se presenta como detalle de estimación inexistente. Las referencias externas son declaradas y no verificadas criptográficamente contra contenido remoto. Las correlaciones se validan estructuralmente, sin garantía de semidefinición positiva ni muestreo. El editor JSON completo conserva un límite explícito de tamaño; las vistas de consulta sí utilizan resúmenes y páginas de 25 elementos sin N+1.

## Contrato futuro y límite

Un futuro motor sólo podrá recibir un QraModelDefinition APPROVED_FOR_ANALYSIS, actual y válido. QraRun, seed, iteraciones, percentiles, sensibilidad, contingencia y fechas probabilísticas pertenecen a ese incremento futuro. Ninguno se crea con esta ADR.
