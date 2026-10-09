# Manual De Uso Detallado Modulo Por Modulo

Fecha base: 2026-05-07

Este manual explica como operar P&Pmis Ai SaaS durante el piloto. La plataforma debe usarse como una herramienta colaborativa en linea: cada usuario entra con su rol, trabaja solo en los proyectos donde tiene membresia y las acciones relevantes quedan trazadas en auditoria.

## 1. Acceso, Usuarios Y Roles

### Objetivo

Controlar quien entra, que proyecto puede ver y que acciones puede ejecutar.

### Roles base

| Rol | Uso principal | Permisos clave |
| --- | --- | --- |
| Control Manager | Gobierno del piloto, aprobaciones y decisiones. | Configurar, aprobar workflow, capturar avance/costo. |
| Planner | Cronograma, baseline, mapping y calidad de schedule. | Cargar cronograma y capturar avance. |
| Project Controls | Analisis EVM, tendencias, alertas y reportes. | Capturar avance/costo y analizar dashboard. |
| Cost Controller | Actas de pago, evidencia de costo, funding y cash flow. | Capturar incurrido y Cost Manager. |
| Contract Manager | RFQ, contratos, ordenes de compra, actas, entradas de almacen, comunicaciones, notices y claims. | Gestion contractual y procurement. |
| Field Engineer | Avance fisico, cantidades, horas y evidencia. | Capturar progreso. |
| Workface Planner | AWP, paquetes de trabajo y restricciones. | Gestionar readiness AWP. |
| Claims Analyst | Causalidad, impactos y paquete forense. | Gestionar claims. |
| Executive | Lectura ejecutiva. | Consulta sin transacciones. |

### Como usar

1. Abrir `http://localhost:5173`.
2. Seleccionar usuario demo o autenticar con token.
3. Seleccionar proyecto disponible.
4. Confirmar rol visible en la barra superior.
5. Validar que las acciones bloqueadas correspondan al rol.

### Validacion esperada

- Usuario sin token recibe `401`.
- Usuario autenticado sin membresia recibe `403`.
- Usuario con rol correcto puede ejecutar su flujo.

## 2. Modulo Projects / Users / Roles

### Objetivo

Crear proyectos, usuarios y membresias para operar el piloto multiusuario.

### Cuando usarlo

- Al iniciar un proyecto piloto.
- Al sumar un nuevo participante.
- Al cambiar responsabilidades por proyecto.

### Paso a paso

1. Ir a `Projects / Users / Roles`.
2. Crear o confirmar el proyecto piloto.
3. Crear usuarios si hacen falta.
4. Asignar cada usuario al proyecto con un rol.
5. Cambiar de usuario desde la barra superior para probar permisos.

### Datos minimos del proyecto

- Codigo.
- Nombre.
- Fase.
- Moneda.
- Fecha inicio.
- Fecha fin.

### Salida esperada

- Equipo del proyecto visible.
- Al menos cinco roles activos para piloto.
- Acceso segregado por proyecto.

## 3. Modulo Roadmap / Plan De Control / PEP

### Objetivo

Formalizar como se medira, controlara, reportara y gobernara el proyecto.

### Cuando usarlo

Antes de capturar datos reales del piloto. El Plan de Control es el acuerdo operacional del equipo.

### Campos principales

- Estrategia de ejecucion.
- Estrategia de control.
- Regla de medicion de progreso.
- Regla de medicion de costo.
- Gestion de cambios.
- Gestion de riesgos.
- Estrategia de adquisiciones.
- Control documental.
- Cadencia de reportes.
- Estado.

### Paso a paso

1. Ir a `Roadmap`.
2. Revisar el nivel de madurez por fase.
3. Abrir la seccion del Plan de Control / PEP.
4. Ajustar reglas al proyecto real.
5. Cambiar estado a `active` o `approved`.
6. Guardar.
7. Medir readiness nuevamente.

### Control colaborativo

El Plan usa `expected_version`. Si dos usuarios editan el mismo plan y uno guarda primero, el segundo debe refrescar antes de guardar.

### Salida esperada

- Plan activo.
- Reglas aceptadas por Planner, Cost Controller, Field Engineer y Contract Manager.
- Readiness Fase 2 en estado `ready`.

## 4. Modulo Business Processes

### Objetivo

Gestionar decisiones, revisiones, aprobaciones y ball-in-court con trazabilidad.

### Que contiene

- Registro BP.
- Proceso.
- Titulo.
- Paso actual.
- Responsable actual.
- Estado.
- Acciones de workflow.

### Paso a paso

1. Ir a `Business Processes`.
2. Seleccionar un registro.
3. Revisar paso actual y ball-in-court.
4. Ejecutar accion disponible, por ejemplo enviar, aprobar o cerrar.
5. Confirmar que el audit log actualice la accion.

### Buenas practicas

- No usar el workflow como comentario informal.
- Registrar decisiones reales: aprobar baseline, responder alerta, gestionar cambio, cerrar restriccion.
- Verificar que el responsable sea un rol, no una persona aislada.

### Salida esperada

- Decision trazada.
- Estado actualizado.
- Audit log disponible.

## 5. Modulo BP Designer

### Objetivo

Configurar plantillas simples de procesos de negocio sin tocar codigo.

### Cuando usarlo

- Crear una plantilla piloto para cambios, alertas o aprobaciones internas.
- Probar un flujo de aprobacion por rol.
- Definir campos y pasos antes de automatizar mas.

### Paso a paso

1. Ir a `Projects / Users / Roles` o panel de configuracion BP.
2. Crear codigo de proceso.
3. Definir nombre, categoria y descripcion.
4. Definir campos del formulario.
5. Definir pasos con formato: `Paso | Rol | Descripcion`.
6. Definir transiciones con accion, paso origen, paso destino, rol destino y estado.
7. Guardar plantilla.

### Salida esperada

- Plantilla visible en el catalogo.
- Transiciones listas para ser usadas por la API.

### Limitacion actual

Es un MVP. Falta editor visual avanzado, reglas por campo, versionado formal de plantilla y migracion de instancias.

## 6. Modulo Schedule Intake

### Objetivo

Usar el cronograma fuente como entrada maestra del sistema.

### Cuando usarlo

Al iniciar el piloto o cuando se reciba una nueva version de cronograma.

### Paso a paso

1. Ir a `Schedule`.
2. Cargar archivo XML/XER o usar dataset semilla.
3. Revisar estado de importacion.
4. Revisar data date y baseline.
5. Revisar hallazgos de calidad.
6. Confirmar que se creo el workflow de baseline.

### Datos revisados

- Actividades.
- Relaciones logicas.
- Criticidad.
- Fechas.
- WBS.
- Data quality score.
- Findings tipo DCMA/AACE.

### Salida esperada

- Cronograma validado.
- Fase 1 readiness en `ready` o `watch` controlado.
- Errores criticos documentados o cerrados.

## 7. Modulo Control Accounts / Mapping

### Objetivo

Conectar cronograma, WBS, CBS, actividades, presupuesto y cuentas de control.

### Cuando usarlo

Despues de cargar el cronograma y antes de desbloquear captura operacional.

### Paso a paso

1. Ir a `Schedule`.
2. Revisar resumen de mapping.
3. Validar cuentas de control generadas.
4. Revisar WBS/CBS/Activity mapping.
5. Confirmar cost loading.
6. Aprobar baseline de control si mapping y cost loading cumplen criterio.

### Indicadores clave

- Mapping score.
- Cost loading score.
- Actividades mapeadas.
- Actividades sin cuenta.
- Baseline status.

### Salida esperada

- Baseline aprobado.
- Cuentas de control disponibles para avance, costo, AWP y cambios.
- Fase 3 readiness en `ready` o con accion clara.

## 8. Modulo Progress

### Objetivo

Capturar avance fisico real por cuenta de control.

### Rol principal

Field Engineer, Planner o Project Controls.

### Paso a paso

1. Ir a `BP Entry Forms`.
2. En `Progress`, seleccionar cuenta de control.
3. Registrar porcentaje fisico.
4. Registrar cantidad instalada.
5. Registrar horas.
6. Registrar fecha de reporte.
7. Vincular referencia de evidencia.
8. Guardar.
9. Revisar `Progress` y `Control Dashboard`.

### Validaciones

- El cronograma debe estar listo.
- Debe existir cuenta de control.
- El usuario necesita permiso `can_capture_progress`.

### Salida esperada

- Registro de avance creado.
- Control Core recalcula EVM.
- PV, EV, SPI y productividad actualizados.

## 9. Modulo Cost Manager

### Objetivo

Controlar costo, presupuesto, incurrido desde actas de pago y entradas de almacen, comprometido contractual, funding y cash flow del piloto.

### Submodulos

- Cost Sheet.
- Payment Certificates.
- Warehouse Receipts.
- Cost Evidence Records.
- Contract Commitments.
- Purchase Order Commitments.
- Funding Sources.
- Cash Flow.
- Cost Manager Summary.

### 9.1 Cost Sheet

Uso:

1. Ir a `Cost Manager`.
2. Revisar cada cuenta de control.
3. Comparar BAC, EV, incurrido por actas de pago, entradas de almacen, contratos y ordenes de compra comprometidas.
4. Identificar CPI menor a 1.0.
5. Revisar variacion negativa.

Campos:

- Control Account.
- CBS.
- BAC.
- EV.
- Incurred / AC desde actas de pago y entradas de almacen.
- Contract Commitment.
- PO Commitment.
- Total Committed Cost.
- CPI.

Salida esperada:

- Cuentas con sobrecosto identificadas.
- Base financiera lista para reunion semanal.

### 9.2 Payment Certificates / Actas de Pago

Uso:

1. Ir a `BP Entry Forms`.
2. En `Payment Certificates`, seleccionar cuenta de control.
3. Vincular contrato y orden de compra si aplica.
4. Registrar numero de acta/certificado.
5. Registrar periodo.
6. Registrar monto certificado.
7. Registrar retencion si aplica.
8. Registrar fecha de certificacion.
9. Guardar.

Validacion:

- El usuario necesita permiso `can_capture_cost` o `can_manage_contract`.
- El monto certificado debe ser mayor a cero.

Salida esperada:

- Incurrido / AC actualizado.
- Control Core recalcula CPI, CV, EAC y VAC.

### 9.3 Warehouse Receipts / Entradas De Almacen

Uso:

1. Ir a `BP Entry Forms`.
2. En `Warehouse Receipts`, seleccionar cuenta de control.
3. Vincular contrato y orden de compra si aplica.
4. Registrar numero de entrada de almacen.
5. Registrar descripcion.
6. Registrar cantidad recibida.
7. Registrar costo unitario.
8. Registrar valor recibido si aplica.
9. Registrar fecha de recepcion.
10. Guardar.

Validacion:

- El usuario necesita permiso `can_capture_cost` o `can_manage_contract`.
- El valor recibido debe ser mayor a cero o debe poder calcularse como cantidad por costo unitario.
- Estados `draft`, `rejected`, `void` o `cancelled` no suman al incurrido.

Salida esperada:

- Incurrido / AC actualizado desde almacen o recibo de bienes/servicios.
- Cost Sheet muestra columna `Almacen`.

### 9.4 Cost Evidence Records

Uso:

1. Ir a `BP Entry Forms`.
2. En `Cost Evidence`, seleccionar cuenta de control.
3. Seleccionar fuente: invoice, payroll, equipment o materials.
4. Registrar monto.
5. Registrar fecha.
6. Agregar descripcion.
7. Guardar.

Regla:

- Este registro es evidencia auxiliar.
- El incurrido financiero se calcula desde actas de pago y entradas de almacen, no desde este formulario.

### 9.5 Comprometido Contractual

Uso:

1. Ir a `BP Entry Forms`.
2. En `Contracts`, seleccionar cuenta de control.
3. Registrar contrato, contraparte, tipo, valor y estado.
4. Guardar.
5. En `Purchase Orders`, seleccionar cuenta de control.
6. Vincular contrato si aplica.
7. Registrar orden de compra, proveedor y monto comprometido.
8. Guardar.
9. Volver a `Cost Manager`.

Regla:

- El comprometido no se registra como costo real.
- El comprometido se calcula desde contratos activos/aprobados y ordenes de compra emitidas/aprobadas.

Salida esperada:

- `Contract Commitment`, `PO Commitment` y `Total Committed Cost` visibles por cuenta de control.

### 9.6 Funding Sources

Uso:

1. Ir a `Cost Manager`.
2. En `Funding Sources`, agregar codigo.
3. Registrar nombre del fondo.
4. Registrar monto.
5. Definir estado: approved, planned u on_hold.
6. Guardar.

Salida esperada:

- Total funding actualizado.
- Funding Coverage visible.
- Brecha funding vs BAC identificada.

Control colaborativo:

- `PATCH` usa `expected_version`.
- Si otro usuario edita antes, el sistema devuelve conflicto `409`.

### 9.7 Cash Flow

Uso:

1. Ir a `Cost Manager`.
2. Agregar periodo en formato recomendado `YYYY-MM`.
3. Registrar planned inflow.
4. Registrar planned outflow.
5. Registrar actual inflow.
6. Registrar actual outflow.
7. Registrar forecast outflow.
8. Guardar.

Salida esperada:

- Cash Flow Variance calculado.
- Forecast Outflow visible.
- Periodos listos para analisis de caja.

### Indicadores del Cost Manager

- Cost Variance: EV menos AC.
- Funding Coverage: Funding total sobre BAC.
- Cash Flow Variance: neto actual contra neto planeado.
- Forecast Outflow: salidas proyectadas acumuladas.
- Incurred Cost: actas de pago certificadas por cuenta de control.
- Committed Cost: contratos mas ordenes de compra vigentes por cuenta de control.

## 10. Modulo Control Dashboard

### Objetivo

Revisar salud integral del proyecto despues del ciclo de control.

### Indicadores principales

- PV: Planned Value.
- EV: Earned Value.
- AC: Actual Cost.
- SPI: Schedule Performance Index.
- CPI: Cost Performance Index.
- SV: Schedule Variance.
- CV: Cost Variance.
- BAC: Budget at Completion.
- EAC: Estimate at Completion.
- ETC: Estimate to Complete.
- VAC: Variance at Completion.

### Paso a paso

1. Ir a `Control Dashboard`.
2. Revisar SPI y CPI.
3. Revisar curva historica PV/EV/AC.
4. Revisar alertas.
5. Revisar escenarios forecast.
6. Pasar decisiones al workflow.

### Semaforo practico

- SPI/CPI mayor o igual a 1.0: estable.
- SPI/CPI entre 0.9 y 1.0: vigilancia.
- SPI/CPI menor a 0.9: accion requerida.

### Salida esperada

- Riesgos priorizados.
- Decision semanal preparada.
- Acciones para siguiente ciclo.

## 11. Modulo AWP Workface

### Objetivo

Gestionar paquetes de trabajo y restricciones para liberar trabajo en campo.

### Elementos

- CWA.
- CWP.
- EWP.
- PWP.
- IWP.
- Path of construction.
- Constraint log.
- Readiness status.

### Paso a paso

1. Ir a `AWP Workface`.
2. Revisar paquetes por secuencia.
3. Confirmar path of construction.
4. Revisar restricciones abiertas.
5. Cerrar restriccion cuando se resuelva.
6. Confirmar recalculo de readiness.

### Captura de nuevo paquete

1. Ir a `BP Entry Forms`.
2. En AWP, seleccionar tipo de paquete.
3. Asociar cuenta de control si aplica.
4. Registrar codigo, titulo, disciplina y secuencia.
5. Registrar fechas planeadas.
6. Guardar.

### Salida esperada

- Paquete liberable o bloqueo claro.
- Restricciones con responsable.
- Workface readiness visible.

## 12. Modulo Changes

### Objetivo

Registrar desviaciones, impactos y decisiones de cambio.

### Paso a paso

1. Ir a `BP Entry Forms`.
2. Crear change request.
3. Asociar cuenta de control si aplica.
4. Registrar titulo.
5. Describir desviacion.
6. Registrar impacto de costo.
7. Registrar impacto en dias.
8. Guardar y revisar workflow.

### Salida esperada

- Cambio creado como registro trazable.
- Impacto listo para decision.
- Auditoria actualizada.

## 13. Modulo Licitaciones / RFQ

### Objetivo

Gestionar paquetes de licitacion/RFQ, recibir ofertas, evaluar bidders y dejar recomendacion para contrato u orden de compra.

### Elementos

- RFQ Packages.
- RFQ Bid.
- Bid Leveling.
- Weighted score.
- Recommended bidder.

### Crear paquete RFQ

1. Ir a `BP Entry Forms`.
2. Ubicar formulario `RFQ Packages`.
3. Seleccionar cuenta de control.
4. Registrar package no.
5. Registrar titulo.
6. Registrar alcance.
7. Registrar presupuesto.
8. Registrar fecha de emision.
9. Registrar fecha limite.
10. Guardar.

### Registrar oferta

1. Ir a `BP Entry Forms`.
2. Ubicar formulario `RFQ Bid`.
3. Seleccionar paquete RFQ.
4. Registrar bidder.
5. Registrar monto ofertado.
6. Registrar score tecnico.
7. Registrar score comercial.
8. Registrar score de cronograma.
9. Registrar score de riesgo.
10. Registrar notas.
11. Guardar.

### Revisar evaluacion

1. Ir a `RFQ / Bids`.
2. Revisar total de paquetes.
3. Revisar ofertas recibidas.
4. Revisar average weighted score.
5. Revisar recommended bidder.
6. Convertir adjudicacion en contrato u orden de compra si procede.

### Salida esperada

- Oferta comparable por score.
- Recomendacion visible.
- Trazabilidad desde RFQ hacia contrato/OC.

### Comparacion Contra Oracle Preconstruction

Oracle Preconstruction cubre marketplace, directorio de subcontratistas, invitaciones, documentacion, mensajeria, RFIs y adjudicacion de bids/tenders. Este piloto cubre el nucleo interno: paquete RFQ, bids, score ponderado y recomendacion. Para igualar Oracle faltan portal externo para proveedores, invitaciones por correo, directorio de subcontratistas, RFI/addenda de licitacion, permisos por organizacion y bid leveling avanzado.

## 14. Modulo Contracts

### Objetivo

Gestionar contratos, comunicaciones y soporte contractual del piloto.

### Contratos

1. Ir a `BP Entry Forms`.
2. Crear contrato.
3. Registrar codigo, titulo, contraparte, tipo, valor y estado.
4. Guardar.

### Ordenes de compra

1. Ir a `BP Entry Forms`.
2. Crear orden de compra.
3. Vincular contrato si aplica.
4. Registrar numero, descripcion, proveedor, monto comprometido y fecha.
5. Guardar.

### Actas de pago

1. Ir a `BP Entry Forms`.
2. Crear Payment Certificate.
3. Vincular contrato y orden de compra si aplica.
4. Registrar monto certificado y retencion.
5. Guardar.

### Entradas de almacen

1. Ir a `BP Entry Forms`.
2. Crear Warehouse Receipt.
3. Vincular contrato y orden de compra si aplica.
4. Registrar cantidad, costo unitario o valor recibido.
5. Guardar.

### Comunicaciones

1. Seleccionar contrato.
2. Registrar tipo de comunicacion.
3. Registrar asunto.
4. Registrar referencia.
5. Registrar fecha de envio.
6. Guardar.

### Salida esperada

- Contrato visible.
- Comunicaciones trazadas.
- Base contractual disponible para notices y claims.
- Comprometido desde contratos y OC.
- Incurrido desde actas y entradas de almacen.

## 15. Modulo Claims / Forensic Entitlement

### Objetivo

Evaluar reclamos con enfoque forense: notice, causalidad, impacto, quantum y evidencia.

### Elementos

- Claims.
- Notices.
- Entitlement items.
- Impact analyses.
- Forensic readiness score.
- Evidence gaps.

### Paso a paso

1. Ir a `Claims`.
2. Revisar claims existentes.
3. Revisar cumplimiento de notices.
4. Revisar entitlement matrix.
5. Crear o actualizar analisis de impacto.
6. Vincular evidencia.
7. Revisar forensic readiness.

### Analisis de impacto

1. Ir a `BP Entry Forms`.
2. Seleccionar claim.
3. Elegir metodo.
4. Registrar actividad impactada.
5. Describir causa y efecto.
6. Registrar dias de impacto.
7. Registrar costo reclamado.
8. Registrar perdida de productividad.
9. Agregar evidencia.
10. Guardar.

### Salida esperada

- Claim cuantificado.
- Evidencia visible.
- Brechas de entitlement identificadas.

## 16. Modulo Documents / Document Control Files

### Objetivo

Vincular evidencia documental a entidades de control y almacenar archivos reales del piloto con trazabilidad, hash y descarga protegida.

### Entidades soportadas

- ControlAccount.
- WorkPackage.
- ChangeRequest.
- Claim.
- ContractNotice.
- Contract.

### Paso a paso

1. Ir a `BP Entry Forms`.
2. En Documents, seleccionar tipo de entidad.
3. Seleccionar id/registro.
4. Registrar titulo.
5. Definir tipo documental.
6. Registrar URI o referencia si existe.
7. Guardar.
8. En `Document File Upload`, seleccionar el documento creado.
9. Seleccionar archivo PDF, DOCX, XLSX, XML, XER, imagen, TXT, CSV o ZIP.
10. Presionar `Upload File`.
11. Revisar `Stored Files` en `Documents`.
12. Descargar el archivo para confirmar acceso autenticado.

### Carga ZIP

1. Preparar un ZIP con archivos permitidos.
2. Evitar carpetas con rutas relativas inseguras como `../`.
3. No incluir ZIP dentro de ZIP.
4. No incluir ejecutables o scripts.
5. Cargar el ZIP desde `Document File Upload`.
6. Confirmar que cada archivo interno queda registrado como adjunto independiente.

### Tipos y limites del piloto

- Tipos permitidos: `.pdf`, `.doc`, `.docx`, `.xls`, `.xlsx`, `.ppt`, `.pptx`, `.zip`, `.jpg`, `.jpeg`, `.png`, `.csv`, `.txt`, `.xml`, `.xer`.
- Tamano maximo por archivo: 50 MB.
- ZIP maximo: 200 archivos y 250 MB descomprimidos.
- Tipos bloqueados: ejecutables y scripts como `.exe`, `.dll`, `.ps1`, `.sh`, `.js`, `.bat`, `.cmd`, `.vbs`.

### Salida esperada

- Evidencia vinculada al registro correcto.
- Trazabilidad para decision, claim o auditoria.
- Hash SHA-256 por archivo.
- Origen identificado como `upload` o `zip`.
- Descarga protegida por autenticacion y membresia de proyecto.

### Limitacion actual

El modulo ya cubre register, reviews, transmittals, project mail y adjuntos binarios para piloto. Faltan antivirus integrado, versionado documental formal avanzado, permisos por carpeta, retencion legal, distribucion masiva e integracion con repositorio corporativo.

## 17. Modulo Pilot Readiness

### Objetivo

Medir si el proyecto esta listo para piloto y que brechas debe cerrar.

### Como usar desde frontend

1. Ir a `Roadmap`.
2. Revisar score global.
3. Revisar cada fase.
4. Ejecutar acciones sugeridas.

### Como usar desde consola

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\pilot_check.ps1
```

### Fases evaluadas

- Fase 1: Schedule Intake / Data Quality.
- Fase 2: Business Process Engine / Plan de Control.
- Fase 3: Control Accounts / Mapping.
- Fase 4: EVM / Forecast / Cost Manager.
- Fase 5: Contracts / Claims / Evidence.
- Fase 6: SaaS colaborativo / Operacion.

### Salida esperada

- `ready`: listo para piloto.
- `pilot_candidate`: puede pilotear con brechas controladas.
- `needs_preparation`: debe prepararse antes de pilotear.

## 18. Modulo Audit Log

### Objetivo

Mantener trazabilidad de acciones relevantes.

### Que revisar

- Actor.
- Accion.
- Entidad.
- Id.
- Fecha.
- Payload.

### Uso en piloto

1. Revisar despues de cambios importantes.
2. Confirmar quien aprobo, creo o actualizo registros.
3. Usar como evidencia de colaboracion y gobierno.

## 18. Operacion Semanal Recomendada

### Antes de la reunion

1. Planner valida cronograma y mapping.
2. Field Engineer captura avance.
3. Cost Controller captura costo, funding y cash flow.
4. Contract Manager actualiza notices/comunicaciones.
5. Workface Planner actualiza restricciones.
6. Control Manager revisa dashboard.

### Durante la reunion

1. Revisar readiness.
2. Revisar SPI/CPI/VAC.
3. Revisar Cost Manager.
4. Revisar alertas.
5. Revisar AWP.
6. Revisar cambios y claims.
7. Registrar decisiones en workflow.

### Despues de la reunion

1. Ejecutar acciones asignadas.
2. Actualizar evidencia.
3. Cerrar restricciones resueltas.
4. Medir readiness nuevamente.

## 19. Comandos De Verificacion

Levantar stack:

```powershell
docker compose up -d --build
```

Aplicar migraciones:

```powershell
docker compose exec api alembic upgrade head
```

Pruebas backend:

```powershell
docker compose exec api pytest
```

Build frontend:

```powershell
docker compose exec frontend npm run build
```

Smoke:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\smoke_check.ps1
```

Readiness:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\pilot_check.ps1
```

## 20. Criterios De Uso Correcto

La app se esta usando correctamente si:

- Todo proyecto tiene cronograma fuente o dataset semilla validado.
- El Plan de Control esta activo.
- Cada usuario opera con su rol.
- El baseline de control esta aprobado o con brecha clara.
- Se capturan avance, costos, funding y cash flow.
- Las decisiones se registran en workflows.
- Las evidencias se vinculan a documentos.
- Readiness final supera 75%.

## 21. Brechas Para Despues Del Piloto

- SSO/OIDC.
- Realtime para ball-in-court y notificaciones.
- Integracion ERP para costos reales, contratos y ordenes de compra.
- Integracion industrial Primavera P6 / MS Project.
- Versionado formal de cash flow y forecasts.
- Document Manager avanzado.
- Reportes ejecutivos exportables.
- Backups, monitoreo y hardening productivo.
