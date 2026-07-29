# Arquitectura Funcional TCM

## Sistema nervioso de control

La arquitectura funcional se organiza alrededor de un Control Core, no alrededor de modulos independientes. Sin embargo, el sistema no empieza en el Control Core: empieza en el cronograma fuente.

```text
Cronograma fuente XML/XER
  -> Schedule Intake
      -> Data Quality Gate
          -> Planeacion
```

El cronograma importado es la primera realidad estructurada del proyecto. Desde alli se derivan WBS, actividades, logica, baseline, ruta critica, recursos, cost loading y cuentas de control.
AWP se integra despues de la validacion del cronograma: el path of construction organiza CWA/CWP/EWP/PWP/IWP y el constraint log determina readiness antes de liberar trabajo al campo.

```text
Planeacion
  -> WBS, actividades, baseline, logica, ruta critica
  -> Cuentas de Control
      -> presupuesto, BAC, CBS, cost loading
      -> Ejecucion
          -> costos reales, progreso, recursos, documentos, eventos
          -> Control Core
              -> medir progreso
              -> medir costo real
              -> evaluar EVM
              -> validar workface readiness AWP
              -> gestionar cambios
              -> analizar reclamos
              -> Decision
                  -> alertas, recomendaciones, aprobaciones, acciones
                  -> Retroalimentacion
                      -> forecast, lookahead, rebaseline controlado, acciones de campo
```

## Control Core

El Control Core consolida cinco capacidades inseparables:

1. Medicion del progreso.
2. Medicion del costo real.
3. Evaluacion del desempeno mediante EVM.
4. Gestion de cambios.
5. Reclamos y analisis forense.

Cada corrida de control genera KPI, alertas y recomendaciones trazables.

## Procesos transversales

Data Quality:
- valida campos obligatorios, data date, calendarios, relaciones abiertas, actividades sin WBS, actividades sin cuenta de control, unidades, fechas, moneda, documentos soporte y consistencia entre avance/costo/schedule.

Quality Control:
- conecta inspecciones, evidencias y no conformidades con cantidades, avance fisico, eventos y reclamos.

Administracion contractual:
- conecta contratos, comunicaciones, obligaciones, eventos notificables, cambios y claims.

AWP:
- conecta path of construction, paquetes CWA/CWP/EWP/PWP/IWP, restricciones, liberacion de workface, avance fisico y evidencia.

## Early Warning

El sistema opera el ciclo:

```text
Identify -> Monitor -> Analyze -> Alert -> Act
```

Reglas iniciales:

- SPI < 0.9.
- CPI < 0.9.
- Productividad por debajo de umbral.
- Retrasos de materiales.
- Riesgos criticos activos.

## Decision loop

Las decisiones nacen de desviaciones verificadas y se ejecutan solo mediante acciones aprobadas. Toda accion debe retroalimentar forecast, lookahead, costo esperado, documentos y registro de auditoria.

## Evaluacion de conformidad TCM

La version anterior era parcialmente conforme: tenia Control Core, EVM, cuentas de control, alertas, cambios y claims. La brecha principal era que permitia operar desde datos semilla/manuales sin exigir cronograma fuente. La version corregida exige que XML/XER sea la entrada maestra, coloca un Data Quality Gate antes de Planeacion y mantiene el flujo TCM obligatorio despues de esa validacion.
