# Flujos de Procesos

## Flujo operativo obligatorio

```text
Cronograma fuente XML/XER -> Schedule Intake -> Data Quality Gate -> Planeacion
```

```text
Planeacion -> Cuentas de Control -> Ejecucion -> Control Core -> Decision -> Retroalimentacion
```

## Schedule Intake

```text
Recibir cronograma fuente XML/XER
  -> identificar fuente y version
  -> extraer WBS, actividades, fechas, logica, recursos y cost loading
  -> validar data date, baseline, relaciones abiertas, calendarios y actividades sin cuenta
  -> registrar score de calidad
  -> aprobar version para control
  -> alimentar Planeacion
```

## Control Core loop

```text
CAPTURAR
  -> costos, avance, recursos, documentos, eventos
VALIDAR
  -> data quality, soporte documental, consistencia de fechas/unidades
ANALIZAR
  -> EVM, productividad, riesgos, cambios, reclamos
ALERTAR
  -> SPI/CPI/productividad/materiales/riesgo
DECIDIR
  -> recomendacion, responsable, prioridad, aprobacion
ACTUAR
  -> accion correctiva, comunicacion, forecast, cambio
REPETIR
```

## Advanced Work Packaging

```text
Cronograma validado
  -> definir path of construction
  -> crear CWA / CWP / EWP / PWP / IWP
  -> vincular paquetes a cuentas de control
  -> registrar restricciones de ingenieria, materiales, acceso, permisos, seguridad y documentos
  -> calcular readiness
  -> liberar IWP/CWP al frente de trabajo
  -> capturar avance y costos
  -> retroalimentar Control Core, alertas, cambios y claims
```

## Change Management

```text
Desviacion detectada
  -> analisis tecnico/costo/plazo
  -> clasificacion contractual
  -> aprobacion o rechazo
  -> incorporacion a forecast/control account
  -> seguimiento y cierre
```

## Claims / Forensic

```text
Evento
  -> notificacion contractual
  -> causalidad
  -> impacto en plazo/costo/productividad
  -> matriz entitlement RP120R/RP130R
  -> quantum y segregacion de causas
  -> evidencia documental
  -> cuantificacion
  -> posicion contractual
```

## Early Warning

```text
Identify -> Monitor -> Analyze -> Alert -> Act
```

Cada alerta debe tener origen de datos, severidad, causa probable, recomendacion y estado.
