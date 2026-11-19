# O2B.CLOSE-2

Este corte se limita a cuatro controles S2. No introduce contratos ni compromisos, no cambia el catálogo de navegación productivo y no habilita despliegues.

| Control | Qué se corrigió o probó | Evidencia final |
| --- | --- | --- |
| CLOSE-PG-O1 | Gate06D usa rutas y permisos nativos. Los cambios previos `eb3fa4d`, `2ba53f1` y `cbd4c73` introdujeron los contratos vigentes. Se conservan las denegaciones y la comprobación de rutas obsoletas. | `pg-o1/o1/<intento>/junit.xml` |
| CLOSE-PROG-LINEAGE | Progress reconoce un IWP supersedido. El vínculo sucesor tiene versión y hash nuevos; el despacho conserva identidad, versión y fecha. El registro anterior se compara íntegro. | `progress-lineage/<intento>/progress-lineage.json` |
| CLOSE-FCST-SOURCES | Se usan `ProcurementVendorMilestone.forecast_date` y `ProcurementExpeditingEvent.forecast_date` de despacho. Los valores planificados y pronosticados se verifican por separado. | `forecast-sources/<intento>/*-forecast-evidence.json` |
| CLOSE-AUTH-WRITE | Un comprador con rol nativo positivo de Procurement recibe denegación en 10 comandos de las autoridades ajenas. Se comparan las huellas SQL de 20 tablas. | `auth-write/<intento>/authority-proof.json` |

## Validación reproducible

El directorio local ignorado `outputs/.qa/wave-o2b-close2-20261112/` retiene los JUnit, las huellas y el manifiesto de decisión. Las credenciales, trazas privadas y datos sintéticos no deben publicarse. No se deben mezclar las carpetas `diag-*` con un corte formal.

Usar `backend/.venv/Scripts/python.exe` desde la raíz. Los lanzadores rechazan bases que no coincidan con las identidades desechables esperadas. Las observaciones del Proyecto 14 usan el observador de solo lectura de O1.

```powershell
backend/.venv/Scripts/python.exe scripts/wave-o2b-close2/validate.py preservation final-a before
backend/.venv/Scripts/python.exe scripts/wave-o2b-close2/validate.py freeze final-a
backend/.venv/Scripts/python.exe scripts/wave-o2b-close2/validate.py pg final-a o1
backend/.venv/Scripts/python.exe scripts/wave-o2b-close2/validate.py pg final-a o2a
backend/.venv/Scripts/python.exe scripts/wave-o2b-close2/validate.py pg final-a o2b
```

Establecer `PYPMIS_CLOSE2_CONSUMER_URL` a la base desechable `o2b_close_consumers` en loopback 5558, nunca a la base normal. Ejecutar `consumers.py <carril> final-a` para `progress-lineage`, `forecast-sources`, `auth-write` y `postgres`. Para Chromium, `validate.py web final-a <fase> <o2a|o2b>` reutiliza el lanzador anterior. Para O2B, ejecutar además `validate.py web-consumers final-a prepare` y, con API y frontend sanos, `validate.py web-consumers final-a validate`. Cada ejecución usa un tenant sintético separado.

Tras los carriles, ejecutar `validate.py preservation final-a after`, `validate.py verify final-a`, `capture_profiles.py final-a` y `decision.py final-a`. La decisión rechaza hashes distintos y evidencia faltante. Las pruebas de navegador abren los módulos reales y leen el historial con una sesión autenticada; las decisiones se prueban por separado mediante HTTP y SQL.

El primer Chromium O2A quedó como diagnóstico de entrega local: el HTML respondió, pero falló la descarga de un recurso JavaScript de Vite. Se repitió todo el carril con un tenant sintético nuevo, sin modificar código o pruebas, y el resultado fue 2/2. El JUnit original se conserva. Para seleccionar únicamente la repetición verificada se usa `decision.py final-a --o2a-retry final-a-retry1`. El recolector exige que el manifiesto de fuente de la repetición sea byte por byte el del corte original.

## Decisión técnica

`WAVE_O2B_PROCUREMENT_MATERIALS_LOGISTICS_FOUNDATION_RELEASE_VALIDATED`

`READY_FOR_WAVE_O2C_CONTRACTS_COMMITMENTS_FOUNDATION`

Los cuatro controles S2 y las brechas O2B-G01 y O2B-G02 quedaron cerrados. O1 pasó 1.052/1.052, O2A 59/59, O2B 11/11 y la regresión de consumidores 7/7. Pasaron las cinco pruebas Chromium seleccionadas. Proyecto 14 mantuvo la huella del workspace canónico; se repitió la comprobación de los 70 conjuntos de referencias legadas sin modificar la base observada. No se autorizó un despliegue ni se inició O2C.
