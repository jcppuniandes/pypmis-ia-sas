/** Author the requested live-formula traceability XLSX using bundled Artifact Tool.
 * Run only after Root records the artifact-operation marker for this increment.
 * Source inspection is never promoted to executed PASS or human acceptance.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { SpreadsheetFile, Workbook } from '@oai/artifact-tool';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const dataDir = path.join(root, 'docs/validation/strategic-final-uat');
const outputDir = path.join(root, 'outputs/strategic-final-uat-20261014');
const qaDir = path.join(root, 'outputs/.qa/strategic-final-uat/workbook');
const resultPath = process.argv[2] || path.join(dataDir, 'release-results.json');
const outputName = 'P&Pmis_Strategic_Macroprocess_UAT_Traceability.xlsx';
const read = async (name) => JSON.parse((await fs.readFile(path.join(dataDir, name), 'utf8')).replace(/^\uFEFF/, ''));
const results = JSON.parse((await fs.readFile(resultPath, 'utf8')).replace(/^\uFEFF/, ''));
const register = await read('scenario-coverage-register.json');
const routes = await read('frontend_routes.json');
const apis = await read('backend-api-inventory.json');
const cleanupBackend = await read('backend-code-cleanup.json');
const cleanupFrontend = await read('frontend_cleanup_candidates.json');
const string = (v) => v == null ? '' : typeof v === 'object' ? Array.isArray(v) ? v.map(string).join('; ') : Object.entries(v).map(([k, value]) => `${k}: ${string(value)}`).join('; ') : String(v);
const entries = results.uat_results || results.cases || [];
const caseUpdates = Array.isArray(entries) ? Object.fromEntries(entries.map((v) => [v.uat_id || v.id, v])) : entries;
const cases = register.cases.map((v) => ({ ...v, ...(typeof caseUpdates[v.uat_id] === 'string' ? { status: caseUpdates[v.uat_id] } : caseUpdates[v.uat_id] || {}) }));
const wb = Workbook.create();
const names = ['01_Process_Matrix', '02_UAT_Cases', '03_Admin_User_Matrix', '04_Navigation_Matrix', '05_Business_Rules', '06_Defects', '07_Code_Cleanup', '08_Release_Criteria'];
const sheets = Object.fromEntries(names.map((name) => [name, wb.worksheets.add(name)]));
const col = (index) => { let out = ''; for (let n = index + 1; n > 0; n = Math.floor((n - 1) / 26)) out = String.fromCharCode(65 + (n - 1) % 26) + out; return out; };
const tableMeta = [];
const HEADER_ROW = 7;
const FIRST_ROW = HEADER_ROW + 1;

function sheetTable(name, title, headers, rows, widths, source) {
  const sheet = sheets[name];
  const lastCol = col(headers.length - 1);
  const lastRow = HEADER_ROW + Math.max(rows.length, 1);
  sheet.showGridLines = false;
  sheet.getRange(`A2:${lastCol}2`).format.rowHeight = 26;
  sheet.getRange('A2').values = [[title]];
  sheet.getRange('A2').format.font = { name: 'Arial', size: 14, bold: true, color: '#000000' };
  sheet.getRange(`A3:${lastCol}3`).format.borders = { bottom: { style: 'thin', color: '#D9D9D9' } };
  sheet.getRange('A4').values = [['Corte 14 octubre 2026']];
  sheet.getRange('D4').values = [['Fuente del registro']];
  sheet.getRange('E4').values = [[source]];
  sheet.getRange('A5').values = [['Registros']];
  sheet.getRange('B5').formulas = [[`=COUNTA(A${FIRST_ROW}:A${lastRow})`]];
  sheet.getRange(`A4:${lastCol}5`).format.font = { name: 'Arial', size: 10, color: '#000000' };
  sheet.getRange(`A${HEADER_ROW}:${lastCol}${HEADER_ROW}`).values = [headers];
  const safeRows = rows.length ? rows : [headers.map((_, i) => i === 0 ? 'REGISTRO_PENDIENTE' : '')];
  sheet.getRange(`A${FIRST_ROW}:${lastCol}${lastRow}`).values = safeRows.map((row) => row.map((v) => v == null ? null : typeof v === 'number' || typeof v === 'boolean' || v instanceof Date ? v : string(v)));
  const used = sheet.getRange(`A${HEADER_ROW}:${lastCol}${lastRow}`);
  used.format.font = { name: 'Arial', size: 10, color: '#202A33' };
  used.format.wrapText = true;
  used.format.verticalAlignment = 'center';
  used.format.rowHeight = 72;
  for (let i = 0; i < widths.length; i++) sheet.getRange(`${col(i)}1:${col(i)}${lastRow}`).format.columnWidth = widths[i];
  const header = sheet.getRange(`A${HEADER_ROW}:${lastCol}${HEADER_ROW}`);
  header.format.fill = '#17324D';
  header.format.font = { name: 'Arial', size: 10, bold: true, color: '#FFFFFF' };
  header.format.horizontalAlignment = 'center';
  header.format.rowHeight = 34;
  header.format.borders = { preset: 'inside', style: 'thin', color: '#FFFFFF' };
  const table = sheet.tables.add(`A${HEADER_ROW}:${lastCol}${lastRow}`, true, `StrategicUat${name.substring(0, 2)}`);
  table.showFilterButton = true;
  table.showBandedColumns = false;
  for (let row = FIRST_ROW; row <= lastRow; row++) {
    if ((row - FIRST_ROW) % 2) sheet.getRange(`A${row}:${lastCol}${row}`).format.fill = '#F5F7F8';
    const rowValues = safeRows[row - FIRST_ROW];
    const lines = Math.max(...rowValues.map((value, index) => string(value).split('\n').reduce((sum, line) => sum + Math.max(1, Math.ceil(line.length / Math.max(8, widths[index] * 0.9))), 0)));
    sheet.getRange(`A${row}:${lastCol}${row}`).format.rowHeight = Math.max(42, lines * 13 + 14);
  }
  sheet.freezePanes.freezeRows(HEADER_ROW);
  sheet.freezePanes.freezeColumns(2);
  sheet.getRange(`A${FIRST_ROW}:A${lastRow}`).format.font = { name: 'Arial', size: 10, bold: true, color: '#202A33' };
  tableMeta.push({ name, rows: rows.length, headers: headers.length, lastRow, lastCol });
  return sheet;
}

sheetTable(names[0], 'Procesos y autoridades del macroproceso estratégico',
  ['ID', 'Fase', 'Proceso', 'Prerrequisito ADMIN', 'Transacción USER', 'Entrada', 'Salida', 'Autoridad', 'Siguiente proceso', 'Dependencia', 'R', 'A', 'C e I'],
  register.process_matrix.map((v) => [v.process_id, v.phase, v.process, v.admin_prerequisite, v.user_transaction, v.input, v.output, v.authority, v.next_process, v.dependency_class, v.raci.responsible, v.raci.accountable, `C: ${string(v.raci.consulted)}. I: ${string(v.raci.informed)}`]),
  [10, 25, 38, 43, 34, 34, 34, 27, 23, 27, 27, 27, 42], 'Registro de 44 procesos y RACI. RACI propuesto sin firma organizacional.');

const caseSheet = sheetTable(names[1], 'Registro formal de casos UAT y alcance de las pruebas',
  ['UAT ID', 'Proceso de negocio', 'Precondiciones', 'Persona', 'Datos', 'Pasos', 'Resultado esperado', 'Resultado real', 'Evidencia y alcance', 'Estado', 'Defecto ID'],
  cases.map((v) => [v.uat_id, v.business_process, v.preconditions, v.persona, v.test_data, v.steps, v.expected_result, v.actual_result, v.evidence, ['PASS', 'FAIL', 'BLOCKED'].includes(v.status) ? v.status : 'BLOCKED', v.defect_id || '']),
  [10, 38, 58, 30, 43, 65, 65, 75, 75, 14, 22], 'Registro de escenarios más resultados explícitos del incremento. PASS técnico no es firma humana.');
const caseLast = HEADER_ROW + cases.length;
for (const [i, status] of ['PASS', 'FAIL', 'BLOCKED'].entries()) {
  caseSheet.getRange(`${col(i * 2 + 2)}5`).values = [[status]];
  caseSheet.getRange(`${col(i * 2 + 3)}5`).formulas = [[`=COUNTIFS(J${FIRST_ROW}:J${caseLast},"${status}")`]];
}
caseSheet.getRange(`J${FIRST_ROW}:J${caseLast}`).dataValidation = { rule: { type: 'list', values: ['PASS', 'FAIL', 'BLOCKED'] } };
caseSheet.getRange(`J${FIRST_ROW}:J${caseLast}`).conditionalFormats.add('containsText', { text: 'FAIL', format: { fill: '#FDE9E7', font: { color: '#9C1C1C', bold: true } } });
caseSheet.getRange(`J${FIRST_ROW}:J${caseLast}`).conditionalFormats.add('containsText', { text: 'BLOCKED', format: { fill: '#FFF2CC', font: { color: '#5F4300' } } });

sheetTable(names[2], 'Inventario de pantallas y endpoints por modo y autoridad',
  ['ID', 'Tipo', 'Ruta o endpoint', 'Modo', 'Módulo o pantalla', 'Propósito', 'Permiso', 'Estado de uso', 'Consumidor', 'Cobertura y cautela'],
  [
    ...routes.map((v, i) => [`FE-${i + 1}`, 'PANTALLA', v.route, v.mode, v.component, v.navigationTrail, v.permission, v.componentStatus, v.view, `${v.classification}. ${v.verification}`]),
    ...apis.map((v, i) => [`API-${i + 1}`, v.method, v.endpoint, v.mode, v.module, v.purpose, v.permission, v.live_deprecated, v.frontend_consumer, `${v.uat_coverage}. ${v.permission_precision}`]),
  ], [12, 14, 65, 29, 61, 43, 56, 37, 59, 65], 'Inventarios estáticos API y frontend. Tener endpoint o test no implica ejecución aprobada.');

sheetTable(names[3], 'Navegación canónica y contexto Workspace',
  ['ID', 'Modo', 'Fase', 'Orden', 'Ruta', 'Breadcrumb', 'Componente', 'Clasificación', 'Uso', 'Duplicidad', 'Retiro', 'Dependencias'],
  routes.map((v, i) => [`NAV-${i + 1}`, v.mode, v.phase, v.order, v.route, v.breadcrumb, v.component, v.classification, v.used, v.duplicateKind, v.removalCandidate, v.predecessorIds]),
  [12, 12, 9, 9, 62, 68, 70, 31, 12, 44, 12, 58], 'Blueprint canónico inspeccionado. Alias de landing no demuestra pantalla duplicada.');

sheetTable(names[4], 'Reglas implementadas y referencias de evidencia',
  ['Regla ID', 'Regla de negocio', 'Implementación o prueba de referencia', 'Tipo de evidencia'],
  register.business_rules.map((v) => [v.rule_id, v.rule, v.implementation_or_tests, v.status]),
  [13, 88, 90, 70], 'Catálogo de 26 reglas. Inspección de fuente separada del resultado ejecutado por caso.');

const defects = results.defects || [];
sheetTable(names[5], 'Defectos y acciones del cierre estratégico',
  ['Defecto ID', 'Clasificación', 'Severidad', 'Título', 'Resultado o impacto', 'Estado', 'Acción o workaround', 'Responsable', 'Evidencia'],
  defects.length ? defects.map((v) => [v.id || v.defect_id, v.classification, v.severity, v.title || v.summary, v.actual || v.description || v.summary, v.status, v.remediation || v.action || v.workaround, v.owner || '', v.evidence]) : [['REGISTRO_PENDIENTE', 'VALIDATION GAP', '', 'No hay registro consolidado en este corte', 'La ausencia de registro no prueba cero defectos', 'BLOCKED', 'Completar auditoría y resultados antes de liberar', '', resultPath]],
  [21, 30, 21, 55, 70, 34, 68, 25, 78], 'Hallazgos consolidados por Root. No se reclasifica un defecto como deuda técnica para ocultarlo.');

sheetTable(names[6], 'Candidatos de limpieza y disposición segura',
  ['ID', 'Área', 'Candidato', 'Clasificación', 'Evidencia', 'Acción o fundamento', 'Eliminado', 'Regresión de retiro'],
  [
    ...cleanupBackend.map((v, i) => [v.candidate_id || `BE-${i + 1}`, 'BACKEND', v.candidate, v.classification, v.evidence, v.rationale, Boolean(v.removed), v.regression_proves_removal_safe]),
    ...cleanupFrontend.map((v, i) => [`FE-${i + 1}`, 'FRONTEND', v.target, v.classification, v.evidence, v.action, false, 'No retiro autorizado por ausencia de referencia directa']),
  ], [16, 15, 72, 37, 80, 82, 14, 52], 'Inventario estático. Solo SAFE_TO_REMOVE con regresión y autorización admite retiro.');

const signoffNames = ['Enterprise Structure', 'Capital Planning', 'Idea y Proposal', 'Portfolio Governance', 'Business Case', 'FEL y PDRI', 'Risk y Permit', 'Funding y FIN', 'QRA contextual evidence', 'Gate Preparation', 'FID', 'Post FID boundary', 'ADMIN y USER', 'Navigation', 'Documentation'];
const checks = results.checks || [];
const criteriaRows = checks.map((v, i) => [v.id || `RC-${i + 1}`, v.title || v.criterion, 'TECHNICAL', v.actual || '', v.status || 'BLOCKED', v.evidence || '', '', null, '', null]);
for (const [i, title] of signoffNames.entries()) {
  // Root cannot manufacture authorized signatures; blanks intentionally remain editable.
  const signed = (results.signoffs || []).find((v) => (v.area || v.title) === title) || {};
  criteriaRows.push([`SIGN-${String(i + 1).padStart(2, '0')}`, title, 'BUSINESS_SIGNOFF', 'Aceptación por representante autorizado', signed.decision || '', signed.evidence || '', signed.authorized_signer || '', signed.signed_at ? new Date(signed.signed_at) : null, signed.signature_evidence || '', null]);
}
if (!checks.length) criteriaRows.unshift(['RC-PENDING', 'Registro técnico pendiente', 'TECHNICAL', 'Sin criterios consolidados no se libera', 'BLOCKED', '', '', null, '', null]);
const release = sheetTable(names[7], 'Criterios de liberación y firmas humanas',
  ['Criterio ID', 'Criterio', 'Tipo', 'Resultado técnico o condición', 'Estado o decisión editable', 'Evidencia técnica', 'Firmante autorizado', 'Fecha firma', 'Evidencia de firma', 'Estado calculado'],
  criteriaRows, [17, 48, 25, 72, 29, 78, 34, 20, 66, 22], 'Resultados técnicos explícitos y firmas autorizadas. Datos de firma vacíos significan pendiente, nunca aceptado.');
const releaseLast = HEADER_ROW + criteriaRows.length;
release.getRange(`H${FIRST_ROW}:H${releaseLast}`).setNumberFormat('yyyy-mm-dd');
release.getRange(`J${FIRST_ROW}:J${releaseLast}`).formulas = criteriaRows.map((_, i) => {
  const row = FIRST_ROW + i;
  return [`=IF(C${row}="BUSINESS_SIGNOFF",IF(AND(E${row}="ACCEPTED",G${row}<>"",H${row}<>"",I${row}<>""),"PASS","BLOCKED"),IF(E${row}="PASS","PASS",IF(E${row}="FAIL","FAIL","BLOCKED")))`];
});
const signoffStart = FIRST_ROW + criteriaRows.findIndex((v) => v[2] === 'BUSINESS_SIGNOFF');
release.getRange(`E${signoffStart}:I${releaseLast}`).format.fill = '#FFF2CC';
release.getRange(`E${signoffStart}:E${releaseLast}`).dataValidation = { rule: { type: 'list', values: ['ACCEPTED', 'REJECTED', 'PENDING'] } };
release.getRange('C5').values = [['Pendientes o fallos']];
release.getRange('D5').formulas = [[`=COUNTIFS(J${FIRST_ROW}:J${releaseLast},"BLOCKED")+COUNTIFS(J${FIRST_ROW}:J${releaseLast},"FAIL")`]];
release.getRange('F5').values = [['Conclusión calculada']];
release.getRange('G5').formulas = [[`=IF(D5=0,"REVIEW_RELEASE_DECISION","NO_GO")`]];
release.getRange('I5').values = [['Decisión registrada']];
release.getRange('J5').values = [[results.release_decision || 'NO_GO']];

// Test recalculation and the business-signature boundary without retaining test edits.
wb.recalculate();
const initialStatus = release.getRange(`J${signoffStart}`).values[0][0];
if (initialStatus !== 'BLOCKED' && !criteriaRows[signoffStart - FIRST_ROW][6]) throw new Error('Blank signature incorrectly marked accepted');
const oldDecision = release.getRange(`E${signoffStart}`).values;
release.getRange(`E${signoffStart}`).values = [['ACCEPTED']];
wb.recalculate();
if (release.getRange(`J${signoffStart}`).values[0][0] !== 'BLOCKED') throw new Error('Decision alone incorrectly accepts unsigned business area');
release.getRange(`E${signoffStart}`).values = oldDecision;
wb.recalculate();

await fs.mkdir(qaDir, { recursive: true });
const manifest = { output: outputName, rows: tableMeta, explicitUatStatusCounts: Object.fromEntries(['PASS', 'FAIL', 'BLOCKED'].map((s) => [s, cases.filter((v) => v.status === s).length])), signatureBoundary: 'ACCEPTED decision without signer/date/evidence remains BLOCKED', unsignedAreas: signoffNames.length - (results.signoffs || []).filter((v) => v.authorized_signer && v.signed_at && v.signature_evidence && v.decision === 'ACCEPTED').length };
const errorScan = await wb.inspect({ kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!', options: { useRegex: true, maxResults: 100 }, summary: 'final formula error scan', maxChars: 10000 });
await fs.writeFile(path.join(qaDir, 'formula-error-scan.ndjson'), errorScan.ndjson);
const inspected = await wb.inspect({ kind: 'table', range: `08_Release_Criteria!A4:J${Math.min(releaseLast, 13)}`, include: 'values,formulas', tableMaxRows: 10, tableMaxCols: 10, maxChars: 10000 });
await fs.writeFile(path.join(qaDir, 'release-formula-inspection.ndjson'), inspected.ndjson);
for (const meta of tableMeta) {
  // Each sheet's whole logical row is rendered across panels, retaining legible font size.
  const n = Math.ceil(meta.headers / 4);
  for (let panel = 0; panel < n; panel++) {
    const firstCol = panel * 4;
    const lastCol = Math.min(meta.headers - 1, firstCol + 3);
    const range = `${col(firstCol)}2:${col(lastCol)}${Math.min(meta.lastRow, FIRST_ROW + 3)}`;
    const preview = await wb.render({ sheetName: meta.name, range, scale: 1.5, format: 'png' });
    await fs.writeFile(path.join(qaDir, `${meta.name}-panel-${panel + 1}.png`), new Uint8Array(await preview.arrayBuffer()));
  }
}
await fs.writeFile(path.join(qaDir, 'manifest.json'), JSON.stringify(manifest, null, 2));
await fs.mkdir(outputDir, { recursive: true });
const exported = await SpreadsheetFile.exportXlsx(wb);
await exported.save(path.join(outputDir, outputName));
console.log(JSON.stringify({ output: path.join(outputDir, outputName), sheets: names, manifest }, null, 2));
