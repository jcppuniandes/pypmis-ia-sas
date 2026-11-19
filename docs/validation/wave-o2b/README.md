# Wave O2B Procurement Materials Logistics

Se implementó Procurement Manager dentro del contexto operacional. El resultado
es una validación técnica parcial, no una aprobación de despliegue ni una
recomendación para iniciar O2C. La base habitual no recibió 0077.

## Validación ejecutada

| Evidencia | Resultado | Archivo local de QA |
| --- | --- | --- |
| Caso crítico HTTP y SQL, 3 pruebas de disponibilidad y 7 de sourcing | 11 aprobadas | `pg-o2b-final.xml` |
| Migración y arranque sin DDL implícito | 2 aprobadas; 27 tablas y 28 triggers en PostgreSQL | `pg-migration.xml` |
| Regresión O2A y consumidores | 368 aprobadas | `pg-o2a-regression.xml` |
| Regresión operacional O1 y O1C | 1.020 aprobadas | `operational-regression.xml` |
| Chromium con API y PostgreSQL | 1 aprobada; material READY; IWP NOT_RELEASED | `browser-3.xml`, `chromium-3/browser-uat.json` |
| Latencia local | 8 consultas, 3 muestras por consulta | `local-performance.json` |
| Proyecto 14 | Comparación de solo lectura coincide | `preservation-before.json`, `preservation-after.json` |

Los resultados JUnit y capturas se guardaron bajo `outputs/.qa/wave-o2b`. Los
dos archivos de preservación están en este directorio. Algunas políticas se
ejecutan en memoria; no se cuentan como ciclos transaccionales separados. Las
suites de regresión tienen cobertura parcialmente superpuesta.

## Reproducción aislada

- `docker-compose.wave-o2b.yml` separa la base HTTP (5555), la de migración
  (5556) y la de Chromium (5557). El origen O2A se clona **solo como esquema**
  con `scripts/wave-o2b/clone_upstream_schema.py`.
- Alembic aplica `20261111_0077` sobre `20261109_0076`. La ida y vuelta
  se ejecuta únicamente con la base de migración vacía.
- `tests/provision_o2b_browser.py` prepara un proyecto sintético por los
  comandos de O1 y O2A. Genera un manifiesto privado; no debe publicarse.
- `frontend/e2e/procurement-foundation.spec.ts` exige API 8860, frontend 5520
  y un manifiesto del escenario. Las primeras dos corridas fallaron por un
  permiso de modo faltante en el fixture y por el literal de estado esperado.
  La tercera aprobó con un proyecto nuevo.
- La única consulta a la base habitual fue la observación de preservación
  ejecutada en transacción de solo lectura. No se utilizó el Proyecto 14
  para pruebas de escritura.

Se conserva el [mapa de autoridades reutilizadas](repository-reuse.md).
Queda pendiente repetir las migraciones y UAT históricas de O1 y acreditar
el consumo controlado desde Cost, Progress y Forecast. Se entregan el Word
de 39 secciones y la matriz Excel de 17 hojas en `outputs/wave-o2b`.
