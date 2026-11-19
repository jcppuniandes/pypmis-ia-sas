# O2B.CLOSE — validación y adopción de Procurement

El cierre agrega tres rutas de consumidor y una bitácora de solo anexado. Procurement resuelve fuentes, versiones y hashes; no escribe presupuestos, compromisos, avances instalados ni pronósticos aprobados. La revisión `20261111_0078` es aditiva. No se aplicó a la base habitual.

| Consumidor | Contexto de la decisión | Límite de autoridad |
| --- | --- | --- |
| Cost | Orden o fuente de compras con mapeos CBS, código de costo y cuenta de control | La orden no crea un compromiso |
| Progress | Evidencia con fecha y período abierto | Recibido o aceptado no significa instalado |
| Forecast | Señal específica, período y versión de borrador | No recalcula ni edita una versión aprobada |

Las rutas comparten el patrón `/api/v1/{cost|progress|forecast}/projects/{workspace_id}/procurement-adoptions`. El sufijo `/lookup` resuelve una referencia antes de decidir. Un comando explícito fija el identificador, la versión y el hash del origen, el perfil publicado y el actor del consumidor. Usa `If-Match` (0 en la primera decisión) e idempotencia; la segunda decisión no sobrescribe la primera.

## Validación y evidencia

- La migración histórica parte de PostgreSQL físicamente vacío y reproduce el DDL original previo a Alembic; después aplica las 78 revisiones reales, sin sellado manual. Se verifica el catálogo tras volver de 0078 a 0075 y reaplicar.
- Los [lanzadores aislados](../../../scripts/wave-o2b-close/G01_VALIDATION.md) ejecutan O1, O2A y O2B en PostgreSQL y los recorridos O2A/O2B en Chromium. La prueba de contexto usa proyectos sintéticos. No se reutilizaron pruebas o perfiles de otros cortes para declarar el resultado.
- Los JUnit y manifiestos de `final-a` se guardan bajo `outputs/.qa/wave-o2b-close-20261111/`. Los JUnit separados por consumidor y política son extractos del mismo JUnit combinado, no corridas adicionales.
- `release/freeze-final-a.json` identifica el Git base y las huellas del árbol local; `release/decision-final-a.json` registra la decisión técnica, la evidencia y la acción requerida para cada bloqueo.
- Proyecto 14 se observa antes y después en transacciones de solo lectura. Seis lecturas locales se miden tres veces cada una; no representan un SLA.

El informe Word y la matriz Excel existentes en `outputs/wave-o2b/` contienen el resultado y los controles de cierre. El cierre técnico no es autorización de despliegue ni de inicio de O2C.

## Decisión final-a

`WAVE_O2B_RELEASE_BLOCKED`. O2B-G01 y O2B-G02 quedan abiertos.

- **CLOSE-PG-O1 · S2.** PostgreSQL ejecutó 1.052 casos: 1.049 aprobados y tres fallidos en Gate06D. Los tres fallos se reprodujeron en el Git base `e5747a6` exportado y ejecutado sobre SQLite aislado. Esa comparación identifica el origen previo, pero no sustituye O1 en PostgreSQL. Conciliar etiquetas y rutas operacionales vigentes y repetir O1 sin exclusiones.
- **CLOSE-PROG-LINEAGE · S2.** La suite aprobó la adopción física y preservó las medidas. Falta una prueba de reemplazo de referencia gobernada que conserve los hechos históricos.
- **CLOSE-FCST-SOURCES · S2.** No se sustituyeron fechas pronosticadas de adjudicación y orden por fechas planificadas. Falta identificar las fuentes de esas dos señales y probar por HTTP cambio de señal, revisión de PO sucesora e inactivación.
- **CLOSE-AUTH-WRITE · S2.** Las huellas demuestran que la adopción no generó escrituras indirectas. Falta un intento directo de escritura contra cada autoridad nativa con un actor exclusivo de Procurement.

Pasaron la migración histórica (4/4), PostgreSQL O2A (59/59) y O2B (11/11), Chromium O2A y O2B (2/2 cada uno) y las pruebas de adopción y política disponibles (7/7). Proyecto 14 conservó su identidad canónica y sus referencias observadas.
