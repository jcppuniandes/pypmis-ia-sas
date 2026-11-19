# O3A Construction Field Operations

La implementación conserva la autoridad de cada dominio. Field Operations registra hechos; los adaptadores nativos de Progress, AWP y Cost requieren decisiones explícitas. Contracts y Schedule consumen consultas informativas. No se ejecutó despliegue de producción ni se escribió el proyecto 14.

## Evidencia y reproducción

La evidencia privada de este corte está en `outputs/.qa/wave-o3a-20261118`. No publicar el manifiesto de credenciales del navegador ni su almacenamiento documental.

1. `migration_validation.py` crea su propio contenedor literal en loopback 5566 y ejecuta la cadena Alembic real y el ciclo 0080 / 0079 / 0080. Nunca usar la base normal.
2. Las pruebas funcionales requieren exactamente `postgresql+psycopg://o3a:o3a@127.0.0.1:5564/o3a`, `PYPMIS_O3A_FIXTURE=disposable-only`, `AUTO_CREATE_SCHEMA=false`, `SEED_DEMO_DATA=false`. Utilizar un runtime documental de QA exclusivo y `pytest -o addopts= -p no:cacheprovider`.
3. Ejecutar `test_field_operations_core_policy.py`, `test_field_operations_core_release.py`, `test_field_operations_execution_release.py`, `test_field_operations_consumer_policy.py` y `test_field_operations_consumers_release.py`. Los tests de seguridad adicionales requieren los manifiestos de UAT y ejecución ya completados.
4. `browser_fixture.py` aprovisiona únicamente fuentes anteriores a Field. `frontend/e2e/field-operations.spec.ts` recorre el shell real, ADMIN, captura Field y consumidores. Los endpoints aislados del corte son API 8863 y Vite 5523.
5. `frontend_validation.py` registra lint, formato, TypeScript, siete pruebas y build, verificando que el código no cambie durante las comprobaciones.
6. `preservation.py before` y `after` son observadores de solo lectura del proyecto 14. El comparador exige igualdad exacta.
7. `contracts_performance.py` mide tres lecturas por consulta y comprueba que no haya escrituras; conserva las deudas O2C sin declarar SLA.
8. `closeout.py` exige las evidencias reales antes de preparar la decisión. `build_report.py` y `build_matrix.mjs` generan los artefactos con las dependencias oficiales del runtime. Renderizar y revisar todas las páginas Word y hojas antes de `closeout.py --artifacts-reviewed`.

## Habilitación posterior

La habilitación en otro entorno requiere autorización y migración Alembic, aprovisionamiento explícito del catálogo mediante `python -m app.modules.field_operations.provision --tenant-id ... --actor-id ... --reason ...`, asignación de roles, habilitación del módulo en el proyecto y publicación independiente del perfil. El catálogo no asigna usuarios ni crea hechos operacionales.

No se modificó `App.tsx`. No hay commit ni push automático de O3A.
