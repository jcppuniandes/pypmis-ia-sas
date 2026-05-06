# Paso A Paso Detallado Del Piloto Y Estado Para Produccion

Fecha base: 2026-05-06

## Resumen Ejecutivo

La plataforma esta lista para ejecutar un piloto controlado con el proyecto demo `CTRL-DEMO-001`.

Resultado actual validado:

- Readiness de piloto: 94.2%.
- Estado del proyecto piloto: ready.
- Smoke test: OK.
- API, frontend, worker, PostgreSQL y Redis: arriba.
- Cost Manager: OK.
- Document Control tipo Aconex: registro documental, revisiones, transmittals y project mail.
- Plataforma multiusuario colaborativa: funcional para piloto.

Lectura honesta para produccion:

- Preparacion para produccion empresarial: 58%.
- Preparacion para beta controlada en staging: 72%.
- Preparacion para piloto operativo: 94.2%.

La diferencia es intencional: una app puede estar lista para piloto y no estar lista para produccion empresarial. El piloto valida valor funcional, flujo, datos, roles y adopcion. Produccion exige seguridad, disponibilidad, backups, integraciones reales, observabilidad, pruebas amplias, hardening, soporte y gobierno operativo.

## Objetivo Del Piloto

Validar que P&Pmis Ai SaaS puede operar como plataforma colaborativa en linea de Project Controls para un equipo real o semi-real, usando un proyecto representativo, con cronograma, cuentas de control, avance, costos, funding, cash flow, EVM, AWP, contratos, claims, control documental tipo Aconex, workflows y auditoria.

El piloto debe responder estas preguntas:

1. El equipo puede operar el ciclo semanal sin depender de hojas sueltas.
2. El cronograma puede funcionar como entrada maestra.
3. Las cuentas de control integran schedule, costo y progreso.
4. Los roles y permisos soportan trabajo multiusuario.
5. El dashboard ayuda a decidir.
6. Cost Manager aporta visibilidad de costo, funding y cash flow.
7. AWP y claims aportan trazabilidad operativa y contractual.
8. Las brechas para produccion quedan claras y priorizadas.

## Alcance Del Piloto

### Alcance incluido

- Un proyecto piloto.
- Un cronograma fuente o dataset semilla validado.
- Un ciclo de control semanal.
- Roles de proyecto con permisos separados.
- Plan de Control / PEP activo.
- Schedule Intake y baseline.
- WBS/CBS/Activity mapping.
- Cuentas de control.
- Captura de avance.
- Captura de costos reales; el comprometido nace de contratos u ordenes de compra.
- Funding sources.
- Cash flow por periodo.
- Control Dashboard con EVM.
- AWP Workface Readiness.
- Cambios.
- Contratos, notices y claims.
- Registro documental controlado.
- Transmittals.
- Project mail / correspondencia.
- Revisiones documentales.
- Documentos/evidencia.
- Workflows y audit log.
- Prueba de concurrencia multiusuario.

### Alcance no incluido

- Produccion enterprise 24/7.
- SSO/OIDC corporativo.
- Alta disponibilidad.
- Backups productivos certificados.
- Integracion ERP real.
- Integracion Primavera P6 en vivo.
- Parser XER industrial completo.
- Observabilidad APM completa.
- Notificaciones realtime.
- Gobierno documental completo enterprise fuera del piloto, pero el MVP ya opera registro, revisiones, transmittals y project mail.

## Equipo Minimo Del Piloto

| Rol | Responsable recomendado | Actividad principal |
| --- | --- | --- |
| Sponsor | Gerente del area | Aprueba alcance, criterios de exito y decision final. |
| Control Manager | Lider Project Controls | Gobierna piloto, aprueba Plan de Control y baseline. |
| Planner | Planificador | Carga cronograma, revisa calidad y mapping. |
| Cost Controller | Control de costos | Carga actas de pago, evidencia de costo, funding y cash flow. |
| Field Engineer | Responsable campo | Captura avance fisico, cantidades, horas y evidencia. |
| Workface Planner | Planeacion AWP | Valida paquetes, restricciones y readiness. |
| Contract Manager | Administracion contractual y procurement | Gestiona contratos, ordenes de compra, comunicaciones, notices y claims. |
| Claims Analyst | Claims/forensic | Revisa causalidad, impactos y evidencia. |
| Executive | Usuario ejecutivo | Lee tablero y valida utilidad gerencial. |

## Ambiente Y Accesos

### URLs

- Frontend: `http://localhost:5173`
- API: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`

### Usuario recomendado

```text
ana.control@demo.local
demo123
```

### Usuarios demo utiles

```text
ana.control@demo.local / demo123
carlos.planner@demo.local / demo123
sofia.cost@demo.local / demo123
laura.contracts@demo.local / demo123
```

## Fase 0. Preparar Ambiente

### Responsable

Administrador tecnico o Control Manager con apoyo tecnico.

### Objetivo

Dejar la plataforma arriba, migrada y validada antes de invitar usuarios.

### Paso a paso

1. Abrir PowerShell.
2. Ir al repositorio.
3. Levantar servicios Docker.
4. Aplicar migraciones.
5. Ejecutar smoke check.
6. Ejecutar pilot check.
7. Confirmar URLs.

### Comandos

```powershell
cd "D:\Documentos\GitHub\pypmis ia sas"
docker compose up -d --build
docker compose exec api alembic upgrade head
powershell -ExecutionPolicy Bypass -File .\tools\smoke_check.ps1
powershell -ExecutionPolicy Bypass -File .\tools\pilot_check.ps1
docker compose ps api frontend worker db redis
```

### Resultado esperado

- API health: ok.
- Readiness: ready.
- Frontend HTTP 200.
- Proyecto `CTRL-DEMO-001` listo.
- Readiness del piloto mayor o igual a 75%.

### Evidencia a guardar

- Captura del smoke check.
- Captura del pilot check.
- Captura del dashboard inicial.

## Fase 1. Kickoff Del Piloto

### Responsable

Sponsor y Control Manager.

### Objetivo

Alinear alcance, usuarios, criterios de exito, duracion y reglas del piloto.

### Duracion sugerida

60 a 90 minutos.

### Paso a paso

1. Presentar objetivo del piloto.
2. Confirmar proyecto piloto.
3. Confirmar roles participantes.
4. Confirmar que el piloto no reemplaza aun sistemas productivos.
5. Definir fecha de inicio.
6. Definir fecha de cierre.
7. Definir ciclo de control a probar.
8. Definir criterios de exito.
9. Definir evidencias a recopilar.
10. Definir responsable de registrar brechas.

### Criterios de exito minimos

- Cinco o mas roles usan la plataforma.
- El Plan de Control queda activo.
- Se valida cronograma o dataset semilla.
- Se aprueba baseline de control o queda brecha clara.
- Se captura avance.
- Se registra incurrido desde acta de pago.
- Se registra comprometido desde contrato u orden de compra.
- Se carga funding.
- Se carga cash flow.
- Se genera dashboard EVM.
- Se registra al menos una decision por workflow.
- Se valida un paquete AWP.
- Se opera control documental tipo Aconex: documento, revision, transmittal, review y project mail.
- Se vincula evidencia documental.
- Readiness final mayor o igual a 75%.

### Salida esperada

- Acta corta de kickoff.
- Lista de usuarios.
- Criterios de exito aprobados.

## Fase 2. Configurar Equipo Y Permisos

### Responsable

Control Manager.

### Objetivo

Confirmar que cada usuario entra con su rol y solo ve sus proyectos.

### Paso a paso en la app

1. Abrir `http://localhost:5173`.
2. Entrar como `ana.control@demo.local`.
3. Ir a `Projects / Users / Roles`.
4. Revisar usuarios existentes.
5. Crear usuarios faltantes si aplica.
6. Asignar rol por proyecto.
7. Cambiar usuario desde la barra superior.
8. Confirmar que cada usuario ve el proyecto correcto.
9. Intentar una accion no permitida con un rol restringido.
10. Confirmar que la plataforma bloquea la accion.

### Pruebas de permisos

| Prueba | Resultado esperado |
| --- | --- |
| Entrar sin token | API responde 401. |
| Usuario sin membresia intenta ver proyecto | API responde 403. |
| Planner intenta gestionar contratos | Accion bloqueada. |
| Cost Controller captura costo | Accion permitida. |
| Field Engineer captura avance | Accion permitida. |
| Executive intenta modificar | Accion bloqueada. |

### Evidencia

- Captura del equipo del proyecto.
- Captura de rol activo.
- Registro de una accion bloqueada.

## Fase 3. Activar Plan De Control / PEP

### Responsable

Control Manager.

### Objetivo

Formalizar como se controla el proyecto durante el piloto.

### Paso a paso

1. Ir a `Roadmap`.
2. Revisar score global.
3. Abrir Plan de Control / PEP.
4. Validar estrategia de ejecucion.
5. Validar estrategia de control.
6. Validar regla de avance.
7. Validar regla de costo.
8. Validar gestion de cambios.
9. Validar gestion de riesgos.
10. Validar adquisiciones.
11. Validar control documental.
12. Confirmar cadencia semanal.
13. Cambiar estado a `active` o `approved`.
14. Guardar.
15. Refrescar readiness.

### Campos que no deben quedar vacios

- Execution strategy.
- Control strategy.
- Progress measurement rule.
- Cost measurement rule.
- Change management rule.
- Risk management rule.
- Procurement strategy.
- Document control rule.
- Reporting cadence.

### Resultado esperado

- Fase 2 en readiness: ready.
- Plan activo.
- Audit log con actualizacion del plan.

## Fase 4. Validar Cronograma Y Data Quality

### Responsable

Planner.

### Objetivo

Confirmar que el cronograma funciona como entrada maestra del control.

### Paso a paso

1. Ir a `Schedule`.
2. Revisar schedule import existente o cargar archivo.
3. Confirmar fuente XML/XER.
4. Revisar data date.
5. Revisar baseline name.
6. Revisar cantidad de actividades.
7. Revisar relaciones logicas.
8. Revisar quality score.
9. Revisar findings.
10. Confirmar si hay errores bloqueantes.
11. Documentar warnings aceptados para piloto.

### Criterios de aceptacion

- Quality score mayor o igual a 70%.
- Sin errores criticos abiertos para el ciclo piloto.
- Actividades y relaciones visibles.
- Workflow de baseline creado.

### Evidencia

- Captura de Schedule.
- Lista de findings.
- Decision de aceptar o corregir cronograma.

## Fase 5. Aprobar Baseline Y Cuentas De Control

### Responsable

Control Manager con Planner y Project Controls.

### Objetivo

Dejar lista la estructura WBS/CBS/Activity para medir avance, costo y EVM.

### Paso a paso

1. Ir a `Schedule`.
2. Revisar `Control Account Mapping Summary`.
3. Revisar mapping score.
4. Revisar cost loading score.
5. Revisar cuentas de control.
6. Revisar actividades sin mapping.
7. Revisar CBS por cuenta.
8. Confirmar BAC por cuenta.
9. Aceptar brechas menores o corregirlas.
10. Aprobar baseline de control.

### Criterios de aceptacion

- Cuentas de control visibles.
- Mapping score suficiente para piloto.
- Cost loading suficiente para EVM.
- Baseline aprobado o brecha documentada.

### Resultado esperado

- Captura operacional desbloqueada.
- Cuentas listas para Progress, Cost Manager, AWP y Changes.

## Fase 6. Capturar Avance Del Ciclo

### Responsable

Field Engineer o Planner.

### Objetivo

Registrar avance fisico, cantidades y horas para alimentar EV y productividad.

### Paso a paso

1. Ir a `BP Entry Forms`.
2. Ubicar formulario `Progress`.
3. Seleccionar cuenta de control.
4. Registrar porcentaje fisico.
5. Registrar cantidad instalada.
6. Registrar horas.
7. Registrar fecha de reporte.
8. Agregar referencia de evidencia.
9. Guardar.
10. Revisar mensaje de recalculo.
11. Ir a `Progress`.
12. Confirmar registro.
13. Ir a `Control Dashboard`.
14. Revisar EV, SPI y productividad.

### Datos de ejemplo

```text
Control account: CA-MECH-100
Physical percent: 65
Quantity installed: 95000
Labor hours: 8200
Reported on: 2026-05-01
Evidence: FIELD-REPORT-2026-05-01
```

### Resultado esperado

- Registro de avance creado.
- Control Core recalculado.
- Dashboard actualizado.

## Fase 7. Capturar Costos, Funding Y Cash Flow

### Responsable

Cost Controller.

### Objetivo

Completar el componente financiero del ciclo: incurrido, comprometido contractual, funding y cash flow. En el piloto el incurrido/AC sale de actas de pago certificadas; el comprometido se calcula desde contratos activos y ordenes de compra emitidas, vinculadas a cuentas de control.

### 7.1 Registrar incurrido desde acta de pago

1. Ir a `BP Entry Forms`.
2. Ubicar formulario `Payment Certificates`.
3. Seleccionar cuenta de control.
4. Vincular contrato si aplica.
5. Vincular orden de compra si aplica.
6. Registrar numero de acta/certificado.
7. Registrar periodo.
8. Registrar monto certificado.
9. Registrar retencion si aplica.
10. Registrar fecha de certificacion.
11. Guardar.
12. Ir a `Cost Manager`.
13. Revisar que el valor aparezca como `Incurred`.

### 7.2 Capturar evidencia auxiliar de costo

1. Ir a `BP Entry Forms`.
2. Ubicar formulario `Cost Evidence`.
3. Seleccionar cuenta de control.
4. Seleccionar fuente de evidencia.
5. Registrar monto.
6. Registrar fecha.
7. Registrar descripcion.
8. Guardar.
9. Revisar `Cost Evidence Records`.

Fuentes disponibles:

- invoice.
- payroll.
- equipment.
- materials.

Regla del piloto: si el valor es incurrido, usar `Payment Certificates`. Si el valor es comprometido, usar `Contracts` o `Purchase Orders`. `Cost Evidence` queda como soporte auxiliar.

### 7.3 Registrar comprometido desde contrato

1. Ir a `BP Entry Forms`.
2. Ubicar formulario `Contracts`.
3. Seleccionar cuenta de control.
4. Registrar codigo de contrato.
5. Registrar tipo.
6. Registrar titulo.
7. Registrar contraparte.
8. Registrar valor contractual.
9. Dejar estado `active` o `approved`.
10. Guardar.
11. Ir a `Cost Manager`.
12. Revisar que el valor aparezca en columna `Contract` y sume a `Committed Cost`.

### 7.4 Registrar comprometido desde orden de compra

1. Ir a `BP Entry Forms`.
2. Ubicar formulario `Purchase Orders`.
3. Seleccionar cuenta de control.
4. Vincular contrato si aplica.
5. Registrar numero de orden de compra.
6. Registrar descripcion.
7. Registrar proveedor.
8. Registrar monto comprometido.
9. Registrar fecha de emision.
10. Dejar estado `issued` o `approved`.
11. Guardar.
12. Ir a `Cost Manager`.
13. Revisar que el valor aparezca en columna `PO` y sume a `Committed Cost`.

### 7.5 Registrar funding

1. Ir a `Cost Manager`.
2. En `Funding Sources`, registrar codigo.
3. Registrar nombre.
4. Registrar monto.
5. Seleccionar estado.
6. Guardar.
7. Revisar Funding Coverage.

Estados recomendados:

- approved.
- planned.
- on_hold.

### 7.6 Registrar cash flow

1. Ir a `Cost Manager`.
2. En `Cash Flow`, registrar periodo `YYYY-MM`.
3. Registrar planned inflow.
4. Registrar planned outflow.
5. Registrar actual inflow.
6. Registrar actual outflow.
7. Registrar forecast outflow.
8. Guardar.
9. Revisar Cash Flow Variance.

### Indicadores a revisar

- BAC.
- EV.
- Incurred / AC desde actas de pago.
- Contract Commitment.
- PO Commitment.
- Total Committed Cost.
- CPI.
- Cost Variance.
- Funding Coverage.
- Cash Flow Variance.
- Forecast Outflow.

### Resultado esperado

- Fase 4 readiness: ready.
- Cost Manager con actas de pago, contratos, ordenes de compra, funding y cash flow del ciclo.
- Dashboard financiero listo para reunion.

## Fase 8. Ejecutar Y Revisar Control Dashboard

### Responsable

Control Manager y Project Controls.

### Objetivo

Convertir datos capturados en informacion de decision.

### Paso a paso

1. Ir a `Control Dashboard`.
2. Revisar PV, EV y AC.
3. Revisar SPI.
4. Revisar CPI.
5. Revisar SV y CV.
6. Revisar EAC, ETC y VAC.
7. Revisar curva PV/EV/AC.
8. Revisar alertas rojas.
9. Revisar alertas amarillas.
10. Revisar AI brief.
11. Revisar escenarios de forecast.
12. Definir decisiones.

### Semaforo recomendado

| Indicador | Verde | Amarillo | Rojo |
| --- | --- | --- | --- |
| SPI | Mayor o igual a 1.00 | 0.90 a 0.99 | Menor a 0.90 |
| CPI | Mayor o igual a 1.00 | 0.90 a 0.99 | Menor a 0.90 |
| VAC | Positivo o cero | Negativo controlado | Negativo critico |
| Funding Coverage | Mayor o igual a 100% | 90% a 99% | Menor a 90% |

### Resultado esperado

- Riesgos priorizados.
- Decision semanal preparada.
- Acciones listas para workflow.

## Fase 9. Probar Business Processes Y Workflow

### Responsable

Control Manager.

### Objetivo

Validar que las decisiones quedan trazadas, con responsable y estado.

### Paso a paso

1. Ir a `Business Processes`.
2. Seleccionar registro.
3. Revisar record number.
4. Revisar proceso.
5. Revisar paso actual.
6. Revisar ball-in-court.
7. Ejecutar accion disponible.
8. Confirmar cambio de estado.
9. Revisar audit log.

### Pruebas sugeridas

- Aprobar baseline.
- Cerrar accion.
- Registrar cambio.
- Registrar claim impact.
- Cerrar restriccion AWP.

### Resultado esperado

- Decision trazada.
- Audit log actualizado.
- Ball-in-court claro.

## Fase 10. Probar Colaboracion Multiusuario

### Responsable

Control Manager con dos usuarios.

### Objetivo

Validar que dos usuarios concurrentes no se pisan datos sin control.

### Prueba A. Project Control Plan

1. Usuario A abre Plan de Control.
2. Usuario B abre el mismo Plan.
3. Usuario A cambia cadencia o estado.
4. Usuario A guarda.
5. Usuario B intenta guardar version anterior.
6. Confirmar error `409`.
7. Usuario B refresca.
8. Usuario B guarda nuevamente con version actual.

### Prueba B. Funding Source

1. Usuario A abre Cost Manager.
2. Usuario B abre Cost Manager.
3. Usuario A actualiza una fuente de funding.
4. Usuario B intenta actualizar el mismo registro con version anterior.
5. Confirmar conflicto.

### Prueba C. Cash Flow

1. Usuario A actualiza un periodo.
2. Usuario B intenta actualizar el mismo periodo sin refrescar.
3. Confirmar conflicto.

### Resultado esperado

- Conflictos concurrentes devuelven `409`.
- Usuario debe refrescar antes de reintentar.
- No hay sobreescritura silenciosa.

## Fase 11. Probar AWP Workface

### Responsable

Workface Planner.

### Objetivo

Validar paquetes de trabajo, restricciones y readiness.

### Paso a paso

1. Ir a `AWP Workface`.
2. Revisar paquetes existentes.
3. Confirmar CWA/CWP/EWP/PWP/IWP.
4. Revisar path of construction.
5. Revisar restricciones.
6. Identificar bloqueantes.
7. Cerrar una restriccion resuelta.
8. Confirmar recalculo de readiness.

### Crear paquete nuevo

1. Ir a `BP Entry Forms`.
2. Ubicar formulario AWP.
3. Elegir tipo de paquete.
4. Asociar cuenta de control.
5. Registrar codigo.
6. Registrar titulo.
7. Registrar disciplina.
8. Registrar secuencia.
9. Registrar path of construction.
10. Guardar.

### Resultado esperado

- Paquete listo o bloqueo claro.
- Restriccion con responsable.
- Readiness AWP visible.

## Fase 12. Probar Contracts, Notices Y Claims

### Responsable

Contract Manager y Claims Analyst.

### Objetivo

Validar trazabilidad contractual y soporte forense.

### Paso a paso contratos

1. Ir a `BP Entry Forms`.
2. Crear contrato.
3. Seleccionar cuenta de control.
4. Registrar codigo.
5. Registrar titulo.
6. Registrar contraparte.
7. Registrar tipo.
8. Registrar valor.
9. Guardar.
10. Confirmar que el valor contractual sume al comprometido del Cost Manager.

### Paso a paso ordenes de compra

1. Ir a `BP Entry Forms`.
2. Ubicar formulario `Purchase Orders`.
3. Seleccionar cuenta de control.
4. Vincular contrato si la orden depende de un contrato marco.
5. Registrar numero de orden de compra.
6. Registrar proveedor.
7. Registrar descripcion.
8. Registrar monto comprometido.
9. Guardar.
10. Confirmar que la orden sume al comprometido del Cost Manager.

### Paso a paso comunicaciones

1. Seleccionar contrato.
2. Registrar tipo de comunicacion.
3. Registrar asunto.
4. Registrar referencia.
5. Registrar fecha.
6. Guardar.

### Paso a paso claims

1. Ir a `Claims`.
2. Revisar claim existente o crear flujo relacionado.
3. Revisar entitlement matrix.
4. Revisar notices.
5. Crear impact analysis.
6. Registrar causa.
7. Registrar efecto.
8. Registrar dias.
9. Registrar costo.
10. Registrar evidencia.
11. Guardar.

### Resultado esperado

- Forensic readiness calculado.
- Comprometido contractual visible desde contratos y ordenes de compra.
- Gaps de evidencia visibles.
- Impactos cuantificados.

## Fase 13. Operar Control Documental Tipo Aconex

### Responsable

Document Controller con apoyo de Control Manager, Planner, Contract Manager y Project Controls.

### Objetivo

Operar un flujo de control documental mas cercano a produccion: registro documental, revision, transmittal, project mail, trazabilidad de revision y evidencia vinculada.

### 13.1 Registrar documento controlado

1. Ir a `BP Entry Forms`.
2. Ubicar formulario `Document Register`.
3. Registrar Document No. o permitir autonumeracion.
4. Registrar revision.
5. Vincular entidad: ControlAccount, WorkPackage, ChangeRequest, Claim, ContractNotice o Contract.
6. Registrar titulo.
7. Seleccionar tipo documental.
8. Registrar disciplina.
9. Registrar organizacion emisora.
10. Registrar estado: current, issued, superseded o void.
11. Registrar review status.
12. Registrar file name.
13. Registrar URI o referencia EDMS.
14. Guardar.

### 13.2 Emitir transmittal

1. Ir a `BP Entry Forms`.
2. Ubicar formulario `Document Transmittal`.
3. Seleccionar documento y revision.
4. Registrar Transmittal No. o permitir autonumeracion.
5. Seleccionar proposito: for_review, for_approval, for_information o for_construction.
6. Registrar asunto.
7. Registrar organizacion receptora.
8. Registrar fecha limite de respuesta.
9. Emitir transmittal.
10. Confirmar que aparece en `Document Control`.

### 13.3 Crear project mail

1. Ir a `BP Entry Forms`.
2. Ubicar formulario `Project Mail`.
3. Registrar Mail No. o permitir autonumeracion.
4. Seleccionar tipo: document_review, RFI, letter o site_instruction.
5. Registrar asunto.
6. Definir rol destinatario.
7. Definir fecha limite.
8. Vincular documento.
9. Escribir cuerpo.
10. Enviar project mail.

### 13.4 Crear revision documental

1. Ir a `BP Entry Forms`.
2. Ubicar formulario `Document Review`.
3. Seleccionar documento.
4. Definir rol revisor.
5. Definir estado: outstanding, in_review, approved o revise_and_resubmit.
6. Definir fecha limite.
7. Registrar comentarios.
8. Crear paso de revision.

### 13.5 Revisar modulo Document Control

1. Ir a `Document Control`.
2. Revisar Controlled Score.
3. Revisar documentos current vs total.
4. Revisar reviews outstanding y overdue.
5. Revisar transmittals emitidos.
6. Revisar project mail abierto.
7. Revisar Document Register.
8. Revisar transmittals.
9. Revisar project mail.
10. Revisar review steps.

### Entidades recomendadas

- ControlAccount.
- WorkPackage.
- ChangeRequest.
- Claim.
- ContractNotice.
- Contract.

### Resultado esperado

- Documento controlado con numero y revision.
- Transmittal emitido.
- Project mail trazado.
- Revision documental creada.
- Evidence package vinculado a decisiones, claims o contratos.
- Document Control Score mayor a 80%.

## Fase 14. Reunion Semanal Del Piloto

### Responsable

Control Manager.

### Duracion sugerida

60 minutos.

### Agenda detallada

1. Confirmar objetivo de la reunion.
2. Revisar readiness global.
3. Revisar Schedule Intake y data quality.
4. Revisar baseline y mapping.
5. Revisar PV, EV, AC.
6. Revisar SPI.
7. Revisar CPI.
8. Revisar EAC y VAC.
9. Revisar Cost Sheet.
10. Revisar Funding Coverage.
11. Revisar Cash Flow Variance.
12. Revisar alertas rojas.
13. Revisar alertas amarillas.
14. Revisar AWP readiness.
15. Revisar restricciones abiertas.
16. Revisar cambios.
17. Revisar contratos/notices.
18. Revisar claims e impactos.
19. Revisar documentos/evidencia.
20. Registrar decisiones.
21. Asignar responsables.
22. Definir acciones del siguiente ciclo.

### Salida esperada

- Decisiones registradas en workflow.
- Acciones con responsable.
- Brechas documentadas.
- Readiness actualizado.

## Fase 15. Cierre Del Piloto

### Responsable

Sponsor y Control Manager.

### Objetivo

Decidir si el producto pasa a siguiente ola, beta controlada o ajustes previos.

### Paso a paso

1. Ejecutar smoke check final.
2. Ejecutar pilot check final.
3. Exportar capturas del dashboard.
4. Revisar criterios de exito.
5. Documentar que funciono.
6. Documentar que fallo.
7. Documentar datos faltantes.
8. Documentar roles que realmente usaron la app.
9. Documentar integraciones necesarias.
10. Documentar riesgos de produccion.
11. Priorizar backlog.
12. Tomar decision.

### Decisiones posibles

- Continuar a piloto con proyecto real.
- Continuar a beta controlada.
- Preparar staging.
- Pausar y cerrar brechas criticas.
- Descartar alcance no viable.

## Checklist Maestro Del Piloto

### Preparacion

- Stack levantado.
- Migraciones aplicadas.
- Smoke check OK.
- Pilot check OK.
- Usuarios definidos.
- Roles asignados.
- Proyecto seleccionado.
- Criterios de exito aprobados.

### Operacion

- Plan de Control activo.
- Cronograma validado.
- Baseline revisado.
- Cuentas de control listas.
- Avance capturado.
- Costo capturado.
- Funding cargado.
- Cash flow cargado.
- Dashboard revisado.
- AWP revisado.
- Contracts/claims revisados.
- Document Control operado: register, transmittal, mail y reviews.
- Documentos/evidencia vinculados.
- Workflows usados.
- Audit log revisado.

### Cierre

- Readiness final medido.
- Evidencias guardadas.
- Brechas priorizadas.
- Decision del sponsor.
- Backlog de produccion definido.

## Porcentaje Actual Para Produccion

### Resultado sintetico

| Nivel | Porcentaje | Interpretacion |
| --- | --- | --- |
| Piloto operativo cercano a pre-produccion | 94.2% | Listo para ejecutar piloto con flujo multiusuario, Cost Manager y Document Control tipo Aconex. |
| Beta controlada en staging | 72% | Viable con usuarios reales limitados, soporte cercano, backups basicos y ambiente staging. |
| Produccion empresarial | 58% | Mas cerca de produccion, pero aun faltan hardening, SSO, observabilidad, CI/CD, HA e integraciones reales. |

### Por que produccion es 58%

La plataforma ya tiene mucho valor funcional, pero produccion empresarial requiere capacidades no funcionales y de gobierno que todavia estan incompletas.

| Dimension | Score | Estado |
| --- | --- | --- |
| Producto Project Controls funcional | 76% | MVP avanzado con Schedule, EVM, Cost Manager, AWP, claims y Document Control. |
| Multiusuario, roles y auditoria | 70% | Funcional, falta realtime y permisos mas finos. |
| Seguridad e identidad | 42% | JWT local; faltan SSO/OIDC, MFA, rotacion de secretos y politicas enterprise. |
| Datos, migraciones y modelo | 65% | Alembic, Postgres y modelo mas completo; falta estrategia completa de backups, retencion y gobierno de datos. |
| Operacion DevOps | 45% | Docker local listo; falta CI/CD productivo, ambientes, rollback y despliegue controlado. |
| Observabilidad y soporte | 35% | Health/readiness y logs basicos; falta APM, alertas, trazas, SLO y runbooks de incidente. |
| Integraciones | 32% | API-first; falta ERP, P6, SSO, documental corporativo y correo/notificaciones reales. |
| Calidad y pruebas | 45% | Smoke y tests base; falta cobertura amplia, pruebas E2E, carga, seguridad y regresion. |
| Escalabilidad y disponibilidad | 30% | Arquitectura preparada; falta HA, balanceo, backups restaurables y pruebas de carga. |
| Compliance y gestion documental | 70% | Registro documental, revisiones, transmittals y project mail implementados; faltan retencion legal, permisos finos y repositorio corporativo. |

Promedio ponderado de produccion empresarial: 58%.

### Lectura ejecutiva

- Para piloto: proceder.
- Para beta controlada: preparar staging, accesos limitados y soporte cercano.
- Para produccion: cerrar brechas criticas antes de usarlo como sistema oficial.

## Brechas Criticas Antes De Produccion

### Seguridad

- Implementar OIDC/SSO.
- MFA si aplica.
- Gestion segura de secretos.
- Politicas de contrasena y sesiones.
- Auditoria de seguridad.
- Rate limiting.
- Hardening CORS y headers.

### Operacion

- Ambientes dev, staging y production.
- CI/CD.
- Backups automaticos.
- Pruebas de restauracion.
- Monitoreo.
- Alertas operativas.
- Runbook de incidentes.
- Rollback de despliegues.

### Integraciones

- ERP para costos reales, contratos y ordenes de compra.
- Primavera P6 o MS Project industrial.
- Sincronizacion con sistema documental corporativo si el cliente ya usa Aconex, SharePoint u otro EDMS.
- Correo/notificaciones.
- Directorio corporativo.

### Calidad

- Tests E2E.
- Tests de permisos por rol.
- Tests de concurrencia.
- Tests de carga.
- Tests de seguridad.
- Cobertura de API.
- Pruebas de migraciones.

### Producto

- Parser XER/XML robusto.
- Versionado de forecasts.
- Versionado de cash flow.
- Document Manager avanzado: paquetes masivos, distribucion, retencion legal, permisos por carpeta y adjuntos reales.
- Notificaciones realtime.
- Mejoras de BP Designer.
- Reportes ejecutivos exportables.

## Roadmap Recomendado Para Llegar A Produccion

### Ola 1. Beta controlada

Duracion sugerida: 2 a 4 semanas.

Objetivo: operar con usuarios reales en entorno controlado, sin criticidad productiva.

Entregables:

- Staging.
- Usuarios reales limitados.
- Backups basicos.
- Logs centralizados.
- Pruebas E2E minimas.
- Correcciones de usabilidad.

Meta: subir de 58% a 72%-78%.

### Ola 2. Hardening productivo

Duracion sugerida: 4 a 8 semanas.

Objetivo: cerrar seguridad, observabilidad, CI/CD y gobierno.

Entregables:

- OIDC/SSO.
- Gestion de secretos.
- CI/CD.
- Backups y restore test.
- Monitoreo y alertas.
- Pruebas de carga.
- Politicas de seguridad.

Meta: subir a 75%-82%.

### Ola 3. Integraciones enterprise

Duracion sugerida: 8 a 12 semanas.

Objetivo: conectar sistemas oficiales.

Entregables:

- ERP costos.
- P6/MS Project.
- Sistema documental.
- Notificaciones.
- Reportes ejecutivos.

Meta: subir a 85%-90%.

### Ola 4. Produccion critica

Duracion sugerida: depende del cliente y compliance.

Objetivo: operar como sistema oficial.

Entregables:

- Alta disponibilidad.
- DRP.
- Auditoria completa.
- SLA/SLO.
- Soporte.
- Gobierno de cambios.

Meta: 90% o mas.

## Decision Recomendada Hoy

La decision recomendada es proceder con piloto controlado.

No se recomienda declararla productiva empresarial todavia. Si el piloto confirma valor, el siguiente paso correcto es preparar beta controlada en staging, con usuarios reales limitados y backlog de hardening.

Estado actual:

- Piloto: si, proceder.
- Beta controlada: si, despues de cerrar ambiente staging y soporte.
- Produccion empresarial: aun no.
