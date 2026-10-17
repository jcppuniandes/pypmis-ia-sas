/** Scoped successor for the blocked Gate07J controlled Class B preflight.
 * --inspect and --verify-output are read-only. Run the managed edit marker once
 * before the first --edit invocation for this request.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const name = 'P&Pmis_Strategic_Macroprocess_UAT_Traceability.xlsx';
const source = path.join(root, 'outputs/strategic-uat-remediation-20261015', name);
const output = path.join(root, 'outputs/gate07j-controlled-class-b-20261015', name);
const qa = path.join(root, 'outputs/.qa/gate07j-controlled-class-b/workbook');
const factsPath = path.join(root, 'docs/validation/gate07j-controlled-class-b/preflight.json');
const facts = JSON.parse(await fs.readFile(factsPath, 'utf8'));
if (facts.status !== 'BLOCKED_UAT_DATABASE_NOT_AVAILABLE' || facts.current_tests.status !== 'NOT_RUN' || facts.current_browser.status !== 'NOT_RUN') {
  throw new Error('This narrow successor requires the recorded blocked preflight, not a business continuation');
}
const edit = process.argv.includes('--edit');
const saved = process.argv.includes('--verify-output');
if (edit && saved) throw new Error('Choose authoring or read-only saved verification');
await fs.mkdir(qa, { recursive: true });
const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(saved ? output : source));
const label = saved ? 'saved' : edit ? 'current' : 'source';
const ranges = [
  ['02_UAT_Cases', 'H35:K39'],
  ['06_Defects', 'A10:D10'],
  ['06_Defects', 'E10:I10'],
  ['06_Defects', 'A21:D23'],
  ['06_Defects', 'E21:I23'],
  ['08_Release_Criteria', 'E11:J11'],
  ['08_Release_Criteria', 'E14:J14'],
  ['08_Release_Criteria', 'E21:J21'],
];
const inventory = await wb.inspect({ kind: 'sheet,table', maxChars: 6000, tableMaxRows: 2, tableMaxCols: 5 });
await fs.writeFile(path.join(qa, `${label}-inventory.ndjson`), inventory.ndjson);
if (!edit) {
  for (const [sheetName, range] of ranges.concat(saved ? [
    ['02_UAT_Cases', 'Q35:U39'], ['06_Defects', 'Q10:Q10'], ['06_Defects', 'Q21:Q23'], ['08_Release_Criteria', 'L11:L14'],
  ] : [])) {
    const view = await wb.render({ sheetName, range, scale: 1, format: 'png' });
    await fs.writeFile(path.join(qa, `${label}-${sheetName}-${range.replaceAll(':', '-')}.png`), new Uint8Array(await view.arrayBuffer()));
  }
  console.log(JSON.stringify({ mode: label, source: saved ? output : source, rendered: ranges.length }));
  process.exit(0);
}

const cases = wb.worksheets.getItem('02_UAT_Cases');
const previousCases = cases.getRange('A35:U39').values;
const priorCaseIds = ['A27', 'A28', 'A29', 'A30', 'A31'];
if (previousCases.some((row, index) => row[0] !== priorCaseIds[index] || row.slice(16, 21).some(Boolean))) throw new Error('Unexpected case identity or occupied history');
cases.getRange('Q7:U7').copyFrom(cases.getRange('L7:P7'), 'all');
cases.getRange('Q7:U7').values = [['Estado previo al preflight', 'Resultado previo', 'Evidencia previa', 'Preflight Bogotá (UTC-5)', 'Evidencia de preflight']];
const evidence = 'preflight.json. BLOCKED_UAT_DATABASE_NOT_AVAILABLE. Tenant 4 / Project 16 no verificables en vivo. Pruebas y navegador NOT_RUN. Los JSON previos son historia, no sustituyen PostgreSQL';
const dispositions = [
  'BLOCKED_UAT_DATABASE_NOT_AVAILABLE. No se revalidó Gate07J ni se presentaron o validaron referencias Class B. La base UAT tmpfs está detenida y no dispone de PG_VERSION ni backup coincidente',
  'BLOCKED_UAT_DATABASE_NOT_AVAILABLE. La consistencia Business Case / Gate y su currentness no se pudieron verificar en vivo. El resultado anterior se conserva como histórico',
  'BLOCKED_UAT_DATABASE_NOT_AVAILABLE. Freeze no ejecutado. No se reconstruyó la cadena ni se reutilizaron snapshots como estados terminales',
  'BLOCKED_UAT_DATABASE_NOT_AVAILABLE. FID no ejecutado ni acreditado en esta continuación. No hay nueva decisión GO ni autorización de fondos',
  'BLOCKED_UAT_DATABASE_NOT_AVAILABLE. Post-FID no ejecutado. No se inicializó, activó ni modificó el Project operativo',
];
for (const [index, previous] of previousCases.entries()) {
  const row = index + 35;
  // Keep the documented Bogotá wall-clock date typed and explicitly formatted.
  // A raw ISO value is otherwise exported as a serial with General formatting.
  const localCheckpoint = new Date(`${facts.captured_at.slice(0, 23)}Z`);
  cases.getRange(`Q${row}:U${row}`).values = [[previous[9], previous[7], previous[8], localCheckpoint, evidence]];
  cases.getRange(`T${row}`).setNumberFormat('yyyy-mm-dd hh:mm');
  cases.getRange(`H${row}:J${row}`).values = [[dispositions[index], evidence, 'BLOCKED']];
}
for (const [col, width] of [['Q', 24], ['R', 75], ['S', 75], ['T', 28], ['U', 75]]) cases.getRange(`${col}1:${col}58`).format.columnWidth = width;
cases.getRange('Q35:U39').format.font = { name: 'Arial', size: 10, color: '#202A33' };
cases.getRange('Q35:U39').format.wrapText = true;
cases.getRange('Q35:U39').format.verticalAlignment = 'center';

const defects = wb.worksheets.getItem('06_Defects');
const defectRows = defects.getRange('A8:Q40').values;
defects.getRange('Q7').copyFrom(defects.getRange('P7'), 'all');
defects.getRange('Q7').values = [['Disposición previa al preflight']];
const ids = ['UAT-S2-003', 'UAT-S3-005', 'UAT-S4-006'];
for (const id of ids) {
  const index = defectRows.findIndex(row => row[0] === id);
  if (index < 0 || defectRows[index][16]) throw new Error(`Missing defect or occupied history: ${id}`);
  const row = index + 8;
  const previous = defectRows[index].slice(0, 16);
  const priorDisposition = { actual: previous[4], status: previous[5], evidence: previous[8] };
  if (id === 'UAT-S2-003') priorDisposition.workaround = previous[6];
  defects.getRange(`Q${row}`).values = [[JSON.stringify(priorDisposition)]];
  if (id === 'UAT-S2-003') {
    defects.getRange(`E${row}`).values = [['OPEN. El cierre Capital Owner A0–A31 sigue sin acreditarse. Esta continuación está bloqueada antes de comandos de negocio por pérdida de la base UAT tmpfs. No se rebajó política ni se reconstruyó upstream']];
    defects.getRange(`F${row}`).values = [['OPEN']];
    defects.getRange(`G${row}`).values = [['Recuperar el respaldo PostgreSQL exacto de la cadena UAT seleccionada. Si no existe, obtener autorización humana explícita para reconstruir por lifecycles gobernados en almacenamiento aislado persistente. No reconstruir ni repetir la cadena sin esa autorización']];
    defects.getRange(`I${row}`).values = [['preflight.json. BLOCKED_UAT_DATABASE_NOT_AVAILABLE. Fuentes y ensayos previos son históricos. Pruebas y navegador NOT_RUN']];
  } else {
    defects.getRange(`I${row}`).values = [[`${previous[8]}. Hallazgo histórico abierto. Sin fix ni revalidación en esta continuación: preflight.json, pruebas y navegador NOT_RUN`]];
  }
}
const env = [
  'UAT-ENV-001', 'VALIDATION_ENVIRONMENT', 'ENVIRONMENT BLOCKER',
  'La base PostgreSQL aislada de la cadena seleccionada no está disponible',
  'BLOCKED_UAT_DATABASE_NOT_AVAILABLE. Contenedor detenido con almacenamiento tmpfs, sin PG_VERSION ni montaje persistente. No se encontró backup coincidente en la búsqueda registrada. No se confirma un defecto de producto S1/S2',
  'OPEN_VALIDATION_ENVIRONMENT',
  'Aportar backup PostgreSQL de esta misma cadena o autorización humana explícita para reconstruir por lifecycles reales con almacenamiento aislado persistente. No restaurar snapshots JSON ni iniciar el tmpfs vacío',
  'Responsable del entorno UAT y aprobador de la continuidad',
  'preflight.json. selected_chain_verification NOT_VERIFIABLE. Cero comandos contra la cadena. Pruebas y navegador NOT_RUN',
];
if (defectRows.some(row => row[0] === env[0]) || defects.getRange('A23:I23').values[0].some(Boolean)) throw new Error('Unexpected environment defect destination');
defects.tables.items[0].rows.add(null, [env]);
defects.getRange('A23:I23').copyFrom(defects.getRange('A22:I22'), 'all');
defects.getRange('A23:I23').values = [env];
defects.getRange('Q23').values = [['Nuevo bloqueo del entorno de validación. No sustituye ni cierra defectos de producto previos']];
defects.getRange('B5').formulas = [['=COUNTA(A8:A23)']];
defects.getRange('Q1:Q40').format.columnWidth = 80;
for (const row of [10, 21, 22, 23]) {
  defects.getRange(`Q${row}`).format.font = { name: 'Arial', size: 10, color: '#202A33' };
  defects.getRange(`Q${row}`).format.wrapText = true;
  defects.getRange(`A${row}:Q${row}`).format.rowHeight = row === 23 ? 125 : 190;
}

const release = wb.worksheets.getItem('08_Release_Criteria');
const releaseRows = release.getRange('A8:L37').values;
release.getRange('L7').copyFrom(release.getRange('K7'), 'all');
release.getRange('L7').values = [['Criterio previo al preflight']];
const affected = ['RC04', 'RC07', 'RC14'];
for (const id of affected) {
  const index = releaseRows.findIndex(row => row[0] === id);
  if (index < 0 || releaseRows[index][11]) throw new Error(`Unexpected release criterion or occupied history: ${id}`);
  const row = index + 8;
  const previous = releaseRows[index];
  release.getRange(`L${row}`).values = [[JSON.stringify({ criterion: previous[0], prior_status: previous[4], prior_evidence: previous[5], prior_calculated_result: release.getRange(`J${row}`).values[0][0] })]];
  release.getRange(`E${row}`).values = [['BLOCKED']];
  release.getRange(`F${row}`).values = [[id === 'RC14'
    ? 'UAT-S2-003 sigue OPEN. UAT-ENV-001 es bloqueo de entorno, no S1/S2 de producto confirmado. preflight.json. Sin regresión nueva'
    : `${id === 'RC04' ? 'A0–A31 no completado' : 'Gate/FID no revalidado'}. preflight.json. BLOCKED_UAT_DATABASE_NOT_AVAILABLE. Pruebas y navegador NOT_RUN. Sin reconstrucción ni comandos de negocio`]];
}
release.getRange('L1:L37').format.columnWidth = 80;
for (const row of [11, 14, 21]) {
  release.getRange(`L${row}`).format.font = { name: 'Arial', size: 10, color: '#202A33' };
  release.getRange(`L${row}`).format.wrapText = true;
}
const signRows = releaseRows.map((row, i) => row[2] === 'BUSINESS_SIGNOFF' ? i + 8 : null).filter(Boolean);
for (const row of signRows) {
  if (release.getRange(`E${row}:I${row}`).values[0].some(Boolean)) throw new Error('Unexpected human signature input, preserving rather than overwriting');
}
wb.recalculate();
const signRow = signRows[0];
const original = release.getRange(`E${signRow}`).values;
release.getRange(`E${signRow}`).values = [['ACCEPTED']];
wb.recalculate();
if (release.getRange(`J${signRow}`).values[0][0] !== 'BLOCKED') throw new Error('Unsigned ACCEPTED passed');
release.getRange(`E${signRow}`).values = original;
wb.recalculate();
const errors = await wb.inspect({ kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!', options: { useRegex: true, maxResults: 100 }, maxChars: 5000 });
await fs.writeFile(path.join(qa, 'formula-error-scan.ndjson'), errors.ndjson);
await fs.mkdir(path.dirname(output), { recursive: true });
await (await SpreadsheetFile.exportXlsx(wb)).save(output);
await fs.writeFile(path.join(qa, 'edit-manifest.json'), JSON.stringify({
  source, output, preflight: factsPath, status: facts.status, tests: 'NOT_RUN', browser: 'NOT_RUN',
  cases_updated: priorCaseIds, new_environment_record: env[0], historical_signatures_preserved_blank: signRows.length,
  signature_boundary: 'ACCEPTED alone remains BLOCKED', release_criteria_updated: affected,
  historical_cases_unchanged_outside: 'A27–A31', history: 'Cases Q:U. Defects Q. Release L. All previous L:P / P / K history retained',
}, null, 2));
console.log(JSON.stringify({ output, status: facts.status, cases_updated: priorCaseIds, signoffs: signRows.length }));
