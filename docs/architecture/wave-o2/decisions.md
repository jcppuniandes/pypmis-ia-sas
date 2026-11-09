# Decisiones y riesgos de arquitectura Wave O2

La implementación de estas decisiones corresponde a las olas autorizadas. La
revisión actual valida el diseño, sus límites y los casos de referencia, no
certifica transacciones nuevas.

| ID | Riesgo o decisión | Resolución de diseño | Evidencia o verificación |
|---|---|---|---|
| D01 | Identidad y alcance ambiguos | Workspace canónico O1A y contexto activo. Legado únicamente por binding explícito. | Mapa O2-02 a O2-40 y chequeo V-03 |
| D02 | Entregable confundido con EWP | Engineering gobierna la revisión técnica; AWP conserva EWP y sus mappings. | Diseño Ingeniería y mapa O2-02 a O2-05, O2-29 |
| D03 | PWP confundido con ProcurementPackage | AWP organiza la ejecución. ProcurementPackage agrupa sourcing y enlaza PWP M:N. | Mapa O2-07 y O2-29 |
| D04 | PO duplicada y award automático | Procurement congela decisión y handoff; Contracts acepta por comando independiente. | ADR comercial, frontera de adjudicación y V-08 |
| D05 | Cost como escritor de obligación | Contracts escribe obligación y su revisión; Cost verifica origen y concilia por referencia. | CostCommitmentReference existente y mapa O2-25/O2-27 |
| D06 | Compromiso estratégico contado como compra | Funding, FID y condiciones autorizan o limitan; no crean obligación con un proveedor. | ADR comercial y mapa O2-39 |
| D07 | Doble suma de contrato, PO y SOV | ADDITIVE, INCLUDED, CALL_OFF y REFERENCE_ONLY antes de agregar. El SOV desglosa el mismo importe. | ADR comercial y V-01 a V-05 |
| D08 | Contract Line confundida con SOV Line | Separar obligación y desglose contractual. Mapping N:N con cobertura y asignación aprobadas. | Mapa O2-21/O2-24, ADR comercial y V-07 |
| D09 | Cambios que reescriben la SOV original | Sucesor efectivo e inmutable, con fecha de vigencia y de conocimiento. | ADR comercial y V-04 |
| D10 | Cost Sheet paralelo y detalle divergente | Una lectura Cost por período, moneda y dimensión; drill-down compartido en ambos sentidos. | Mapa O2-28, ADR comercial y V-07 |
| D11 | Certificación confundida con pago o avance | Bases separadas de medición contractual, certificación, invoice, Actual y settlement. | ADR comercial y V-06 |
| D12 | Maestro Vendor o material duplicado | Reutilizar identidad autorizada del tenant. Si no se demuestra maestro válido, aprobar una sola fuente antes de activar; sin alta paralela. | Inventario comercial, diseño O2B, mapa O2-14/O2-37 |
| D13 | Registro documental duplicado | CDE conserva archivo y revisión; referencias exactas con permisos de origen, sin copiar documento. | Diseño de CDE y mapa O2-38 |
| D14 | Readiness liberado por una lectura | Proveedor entrega evidencia; AWP valida clearance, evaluación y release explícitos. | Diseño O2D y V-09 |
| D15 | Restricciones y fechas homónimas | Separar condición contractual/de compra, constraint AWP y restricción de CPM de P6. | Mapa O2-31/O2-33 y diseño de integración |
| D16 | Nuevos escritores de Schedule Cost Progress Forecast | EPC aporta hechos candidatos. El dominio que posee la fuente decide su incorporación y protege versiones aprobadas. | Mapa O2-33 a O2-36 |
| D17 | Publicación de perfil confundida con autorización | ADMIN publica política versionada. USER opera con permiso y SoD por actor. Auditoría no registra mutaciones en GET. | Roadmap, secciones ADMIN, RBAC y auditoría |
| D18 | Activación anticipada o migración destructiva | O2 entrega diseño. Migraciones aditivas y gates PostgreSQL/Chromium por ola; sin backfill ni activación por defecto. | Roadmap, estrategia de migración y criterios de salida |
| D19 | Legado y obligación nueva activos simultáneamente | Habilitar adopción por origen aprobado, con mapa de identidades, fecha de corte y reconciliación de cobertura. | ADR comercial; falta implementación O2C |
| D20 | Ciclo entre Cost Sheet y Forecast | Forecast lee Cost reconocido y conciliación de menor nivel. Cost Sheet lee Forecast aprobado. | Mapa, decisiones de integración |

## Límites de aceptación

- No se identificaron S1 o S2 abiertos del diseño tras la revisión cruzada de
  dominios, decisiones y casos. Esto no certifica una UAT, un cambio de
  producción ni una aprobación de negocio.
- Confirmar el maestro de contrapartes y la identidad de catálogos antes de
  activar O2B/O2C. No migrar registros de compras o contratos por nombre ni
  agregar importes legados si no se pueden reconciliar.
- Las integraciones y pantallas descritas no están activadas. El único
  incremento recomendado después de este cierre es O2A Engineering Foundation.
