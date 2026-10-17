/** Narrow revision of the retained UAT workbook using bundled Artifact Tool.
 * Run the edit authoring marker before --edit. --inspect is read-only.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const name = 'P&Pmis_Strategic_Macroprocess_UAT_Traceability.xlsx';
const source = path.join(root, 'outputs/strategic-final-uat-20261014', name);
const out = path.join(root, 'outputs/strategic-uat-remediation-20261015', name);
const qa = path.join(root, 'outputs/.qa/strategic-uat-remediation/workbook');
const verifyOutput = process.argv.includes('--verify-output');
const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(verifyOutput ? out : source));
const text = value => value == null ? '' : typeof value === 'string' ? value : JSON.stringify(value);
await fs.mkdir(qa, { recursive: true });
const summary = await wb.inspect({ kind: 'sheet,table', maxChars: 7000, tableMaxRows: 2, tableMaxCols: 5 });
await fs.writeFile(path.join(qa, verifyOutput ? 'saved-output-inventory.ndjson' : 'source-inventory.ndjson'), summary.ndjson);
const cases = wb.worksheets.getItem('02_UAT_Cases');
if (!process.argv.includes('--edit')) {
  const ranges = verifyOutput ? [['06_Defects', 'A16:D22'], ['06_Defects', 'E16:I22'], ['08_Release_Criteria', 'E22:J27'], ['08_Release_Criteria', 'A18:F18'], ['08_Release_Criteria', 'F18:K18']] : [['02_UAT_Cases', 'H7:K12'], ['06_Defects', 'A7:F11'], ['08_Release_Criteria', 'E7:J11']];
  for (const [sheetName, range] of ranges) {
    const view = await wb.render({ sheetName, range, scale: 1, format: 'png' });
    await fs.writeFile(path.join(qa, verifyOutput ? `saved-${sheetName}-${range.replaceAll(':', '-')}.png` : `source-${sheetName}.png`), new Uint8Array(await view.arrayBuffer()));
  }
  console.log(summary.ndjson);
  process.exit(0);
}

const facts = JSON.parse(await fs.readFile(path.join(root, 'docs/validation/strategic-uat-remediation/release-results.json'), 'utf8'));
const baselineRows = cases.getRange('A8:K58').values;
const updates = Object.fromEntries(facts.cases.map(value => [value.id, value]));
cases.getRange('L7:P7').values = [['Estado anterior 14 octubre', 'Resultado anterior', 'Evidencia anterior', 'Corte actual', 'Evidencia actual']];
cases.getRange('L7:P7').copyFrom(cases.getRange('G7:K7'), 'all');
cases.getRange('L7:P7').values = [['Estado anterior 14 octubre', 'Resultado anterior', 'Evidencia anterior', 'Corte actual', 'Evidencia actual']];
for (const [i, previous] of baselineRows.entries()) {
  const row = i + 8;
  const current = updates[previous[0]];
  cases.getRange(`L${row}:P${row}`).values = [[previous[9], previous[7], previous[8], '2026-10-15', current?.evidence || 'Sin nueva ejecución formal de este caso; consultar historial']];
  cases.getRange(`H${row}:J${row}`).values = [[current?.actual || 'Caso no reejecutado de manera formal en esta revisión; resultado previo preservado', current?.evidence || 'Historial de ejecución en columnas L a N', current?.status || 'BLOCKED']];
}
cases.getRange('L8:P58').format.font = { name: 'Arial', size: 10, color: '#202A33' };
cases.getRange('L7:P58').format.wrapText = true;
cases.getRange('L7:P58').format.verticalAlignment = 'center';
for (const [col, width] of [['L', 24], ['M', 75], ['N', 75], ['O', 20], ['P', 75]]) cases.getRange(`${col}1:${col}58`).format.columnWidth = width;
cases.getRange('A4').values = [['Corte actual 15 octubre 2026; historial en L a N']];

const defects = wb.worksheets.getItem('06_Defects');
const defectRows = defects.getRange('A1:O40').values;
// Match IDs, retaining row order and the historical text in an adjacent column.
for (let index = 0; index < defectRows.length; index++) {
  const id = defectRows[index][0];
  const update = facts.defects.find(value => value.id === id);
  if (!update) continue;
  const excelRow = index + 1;
  const header = defects.getRange('A7:O7').values[0];
  const statusColumn = header.findIndex(value => /estado/i.test(text(value)));
  const actualColumn = header.findIndex(value => /resultado|impacto/i.test(text(value)));
  if (statusColumn >= 0) defects.getCell(index, statusColumn).values = [[update.status]];
  if (actualColumn >= 0) defects.getCell(index, actualColumn).values = [[update.actual]];
  // Current evidence accompanies the new disposition; the complete previous
  // row, including its evidence, remains in the adjacent history column.
  if (update.evidence) defects.getRange(`I${excelRow}`).values = [[update.evidence]];
  defects.getRange(`P${excelRow}`).values = [[`Anterior ${update.prior_status}. ${text(defectRows[index])}`]];
}
defects.getRange('P7').values = [['Historial anterior 14 octubre']];
defects.getRange('P7').copyFrom(defects.getRange('A7'), 'all');
defects.getRange('P7').values = [['Historial anterior 14 octubre']];
defects.getRange(`P8:P${defectRows.length}`).format.wrapText = true;
defects.getRange(`P1:P${defectRows.length}`).format.columnWidth = 80;
const previousIds = new Set(defectRows.map(row => row[0]).filter(Boolean));
const newDefects = facts.defects.filter(value => !previousIds.has(value.id));
if (newDefects.length) {
  const added = newDefects.map(value => [value.id, value.classification, value.severity, value.title, value.actual, value.status, value.workaround, value.owner, value.evidence]);
  defects.tables.items[0].rows.add(null, added);
  defects.getRange('B5').formulas = [[`=COUNTA(A8:A${18 + newDefects.length})`]];
  for (let i = 0; i < added.length; i++) {
    const row = 19 + i;
    defects.getRange(`A${row}:I${row}`).copyFrom(defects.getRange('A18:I18'), 'all');
    defects.getRange(`A${row}:I${row}`).values = [added[i]];
    defects.getRange(`P${row}`).values = [['Nuevo hallazgo; sin disposición anterior']];
  }
}

const release = wb.worksheets.getItem('08_Release_Criteria');
const releaseValues = release.getRange('A1:J100').values;
release.getRange('K7').copyFrom(release.getRange('F7'), 'all');
release.getRange('K7').values = [['Criterio anterior 14 octubre']];
release.getRange('K1:K37').format.columnWidth = 80;
release.getRange('K7:K37').format.wrapText = true;
release.getRange('K8:K37').format.font = { name: 'Arial', size: 10, color: '#202A33' };
const criterionEvidence = {
  RC02: 'fresh-capital-owner-chain.json; Project canónico pending y timing actual; el caso A6 compuesto sigue BLOCKED',
  RC03: 'core-parent-focused-current.xml; strategic-shell-focused.xml; scope-authorization.md; API mantiene RBAC',
  RC04: 'fresh-capital-owner-chain.json; tenant4/Project16; Gate1 DRAFT/BLOCKED y sin FID',
  RC07: 'gate-evidence-blocker.json; cuatro referencias Class B sin presentación y validación independiente; no hay freeze/FID',
  RC08: 'operational-before.json y operational-after.json idénticos; captura final READ ONLY',
  RC09: 'operational-after.json; cabeza0068 conservada, sin migración nueva; no se atribuye un roundtrip nuevo',
  RC11: `scope-authorization.md; strategic-shell-focused.xml; browser-current-validation.json; App SHA${facts.app_change.actual_sha256}`,
  RC14: 'UAT-S2-003 OPEN; fresh-capital-owner-chain.json y gate-evidence-blocker.json',
};
for (let index = 7; index < releaseValues.length; index++) {
  const row = releaseValues[index];
  if (criterionEvidence[row[0]]) {
    const excelRow = index + 1;
    release.getRange(`K${excelRow}`).values = [[text(row)]];
    release.getRange(`F${excelRow}`).values = [[criterionEvidence[row[0]]]];
    release.getRange(`A${excelRow}:K${excelRow}`).format.rowHeight = 95;
    if (row[0] === 'RC11') {
      release.getRange(`B${excelRow}`).values = [['Blueprint canónico y ajuste USER autorizado']];
      release.getRange(`D${excelRow}`).values = [['Blueprint canónico conservado; ajuste mínimo App.tsx autorizado para acceso USER sin dashboard operativo']];
    }
    if (row[0] === 'RC07') release.getRange(`E${excelRow}`).values = [['BLOCKED']];
  }
  if (row[2] === 'BUSINESS_SIGNOFF') {
    // Preserve every existing blank signature field and its live formula.
    if (row[6] || row[7] || row[8]) throw new Error('Unexpected existing human signature; do not overwrite it');
  }
}
release.getRange('J5').values = [['NO_GO']];
release.getRange('A4').values = [['Corte 15 octubre 2026; firmas no inferidas']];
wb.recalculate();
const signRow = releaseValues.findIndex(value => value[2] === 'BUSINESS_SIGNOFF') + 1;
const before = release.getRange(`E${signRow}`).values;
release.getRange(`E${signRow}`).values = [['ACCEPTED']];
wb.recalculate();
if (release.getRange(`J${signRow}`).values[0][0] !== 'BLOCKED') throw new Error('Unsigned ACCEPTED incorrectly passes');
release.getRange(`E${signRow}`).values = before;
wb.recalculate();
const errors = await wb.inspect({ kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!', options: { useRegex: true, maxResults: 100 }, maxChars: 5000 });
await fs.writeFile(path.join(qa, 'formula-error-scan.ndjson'), errors.ndjson);
for (const [sheetName, range] of [['02_UAT_Cases', 'H7:L12'], ['02_UAT_Cases', 'L7:P12'], ['06_Defects', 'A7:F11'], ['08_Release_Criteria', 'E7:J11']]) {
  const view = await wb.render({ sheetName, range, scale: 1, format: 'png' });
  await fs.writeFile(path.join(qa, `current-${sheetName}-${range.replaceAll(':', '-')}.png`), new Uint8Array(await view.arrayBuffer()));
}
for (const range of ['A18:F18', 'F18:K18']) {
  const view = await wb.render({ sheetName: '08_Release_Criteria', range, scale: 1, format: 'png' });
  await fs.writeFile(path.join(qa, `current-08_Release_Criteria-${range.replaceAll(':', '-')}.png`), new Uint8Array(await view.arrayBuffer()));
}
await fs.mkdir(path.dirname(out), { recursive: true });
await (await SpreadsheetFile.exportXlsx(wb)).save(out);
await fs.writeFile(path.join(qa, 'edit-manifest.json'), JSON.stringify({ source, output: out, signature_boundary: 'ACCEPTED without name/date/evidence remains BLOCKED', historical_cases_retained: baselineRows.length, current_case_counts: facts.case_counts }, null, 2));
console.log(JSON.stringify({ output: out, cases: facts.case_counts, signatureTest: 'PASS' }));
