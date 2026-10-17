/** Narrow Artifact Tool successor. Edit marker already recorded for this request. */
import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const name = 'P&Pmis_Strategic_Macroprocess_UAT_Traceability.xlsx';
const source = path.join(root, 'outputs/gate07j-controlled-class-b-20261015', name);
const output = path.join(root, 'outputs/gate07j-controlled-class-b-20261016', name);
const factsPath = path.join(root, 'docs/validation/gate07j-controlled-class-b/rebuild-results.json');
const qa = path.join(root, 'outputs/.qa/gate07j-controlled-class-b-rebuild/workbook');
const edit = process.argv.includes('--edit');
const saved = process.argv.includes('--verify-output');
if (edit && saved) throw new Error('Choose edit or saved-output inspection, never both');
await fs.mkdir(qa, { recursive: true });
const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(saved ? output : source));
const label = saved ? 'saved' : edit ? 'current' : 'source';
const views = [
  ['02_UAT_Cases', 'C35:G39'], ['02_UAT_Cases', 'H35:J39'],
  ['06_Defects', 'A10:D10'], ['06_Defects', 'E10:I10'],
  ['06_Defects', 'A21:D25'], ['06_Defects', 'E21:I25'],
  ['08_Release_Criteria', 'D9:J11'], ['08_Release_Criteria', 'D14:J16'],
  ['08_Release_Criteria', 'D18:J18'],
  ['08_Release_Criteria', 'D21:J22'],
  ['08_Release_Criteria', 'E22:J27'],
];
const inventory = await wb.inspect({
  kind: 'workbook,sheet,table', maxChars: 6500, tableMaxRows: 3, tableMaxCols: 5, tableMaxCellChars: 80,
});
await fs.writeFile(path.join(qa, `${label}-inventory.ndjson`), inventory.ndjson);
for (const [sheetName, range] of [
  ['02_UAT_Cases', 'A7:Z7'], ['02_UAT_Cases', 'A35:Z39'],
  ['06_Defects', 'A7:R25'], ['08_Release_Criteria', 'A7:M37'],
]) {
  const inspect = await wb.inspect({
    kind: 'table', range: `${sheetName}!${range}`, include: 'values,formulas',
    tableMaxRows: 32, tableMaxCols: 26, tableMaxCellChars: 180, maxChars: 20000,
  });
  await fs.writeFile(path.join(qa, `${label}-${sheetName}-${range.replaceAll(':', '-')}.ndjson`), inspect.ndjson);
}
if (!edit) {
  const renderViews = views.concat(saved ? [
    ['02_UAT_Cases', 'V35:Z39'], ['06_Defects', 'R10:R10'], ['06_Defects', 'R21:R25'],
    ['08_Release_Criteria', 'M9:M11'], ['08_Release_Criteria', 'M14:M16'],
    ['08_Release_Criteria', 'M18:M18'], ['08_Release_Criteria', 'M21:M22'],
  ] : []);
  for (const [sheetName, range] of renderViews) {
    const view = await wb.render({ sheetName, range, scale: 1, format: 'png' });
    await fs.writeFile(path.join(qa, `${label}-${sheetName}-${range.replaceAll(':', '-')}.png`), new Uint8Array(await view.arrayBuffer()));
  }
  console.log(JSON.stringify({ mode: label, source: saved ? output : source, rendered: renderViews.length }));
  process.exit(0);
}
// Authoring is invoked only after the root has authorized the final cut. The
// already-recorded managed edit marker belongs to this same logical request.
const factsBytes = await fs.readFile(factsPath);
const facts = JSON.parse(factsBytes.toString('utf8'));
if (facts.schema_version !== 1) throw new Error('Unsupported rebuild collector schema');
if (facts.release?.business_release_authorized || facts.release?.signoffs?.length) {
  throw new Error('This successor must not populate or infer human business acceptance');
}
const sourceDigest = createHash('sha256').update(await fs.readFile(source)).digest('hex');
const factsDigest = createHash('sha256').update(factsBytes).digest('hex');
const requiredCaseIds = ['A27', 'A28', 'A29', 'A30', 'A31'];
const newDefectRows = new Map([['UAT-S2-005', 24], ['UAT-S3-006', 25]]);
const requiredDefectIds = ['UAT-S2-003', 'UAT-S3-005', 'UAT-S4-006', 'UAT-ENV-001', ...newDefectRows.keys()];
const asText = (value) => Array.isArray(value) ? value.join('\n') : String(value ?? '');
const present = (value) => value !== null && value !== undefined && value !== '';
function uniqueById(items, label) {
  if (!Array.isArray(items)) throw new Error(`Missing collector array ${label}`);
  const result = new Map();
  for (const item of items) {
    if (!item.id || result.has(item.id)) throw new Error(`Missing or duplicate ${label} ID`);
    result.set(item.id, item);
  }
  return result;
}
function bogotaWallClock(value) {
  const instant = new Date(value);
  if (!value || Number.isNaN(instant.getTime())) throw new Error('A real collected_at timestamp is required');
  const fields = Object.fromEntries(new Intl.DateTimeFormat('en-GB', {
    timeZone: 'America/Bogota', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  }).formatToParts(instant).filter(part => part.type !== 'literal').map(part => [part.type, part.value]));
  // Excel dates have no timezone. Store the explicitly labelled Bogotá wall
  // clock as a typed Date, rather than exporting the UTC hour or a text serial.
  return new Date(Date.UTC(+fields.year, +fields.month - 1, +fields.day, +fields.hour, +fields.minute, +fields.second));
}
const checkpointDate = bogotaWallClock(facts.collected_at);
const caseFacts = uniqueById(facts.cases, 'cases');
const defectFacts = uniqueById(facts.defects, 'defects');
const releaseFacts = uniqueById(facts.releaseCriteria, 'releaseCriteria');
if (caseFacts.size !== 5 || requiredCaseIds.some(id => !caseFacts.has(id))) throw new Error('Only A27-A31 may change');
if (defectFacts.size !== 6 || requiredDefectIds.some(id => !defectFacts.has(id))) throw new Error('Unexpected defect scope');

const cases = wb.worksheets.getItem('02_UAT_Cases');
const caseRows = cases.getRange('A8:Z58').values;
if (cases.getRange('V7:Z7').values[0].some(present)) throw new Error('Case history destination is occupied');
cases.getRange('V7:Z7').copyFrom(cases.getRange('Q7:U7'), 'all');
cases.getRange('V7:Z7').values = [[
  'Estado previo reconstrucción', 'Resultado previo reconstrucción', 'Evidencia previa reconstrucción',
  'Reconstrucción Bogotá (UTC-5)', 'Evidencia de reconstrucción',
]];
const updatedCaseRows = [];
for (const id of requiredCaseIds) {
  const index = caseRows.findIndex(row => row[0] === id);
  if (index < 0 || caseRows[index].slice(21, 26).some(present)) throw new Error(`Missing case or occupied history ${id}`);
  const row = index + 8;
  const previous = caseRows[index];
  const item = caseFacts.get(id);
  if (!['PASS', 'FAIL', 'BLOCKED'].includes(item.status)) throw new Error(`Invalid formal status ${id}`);
  cases.getRange(`V${row}:Z${row}`).copyFrom(cases.getRange(`Q${row}:U${row}`), 'all');
  cases.getRange(`V${row}:Z${row}`).values = [[previous[9], previous[7], previous[8], checkpointDate, asText(item.evidence)]];
  cases.getRange(`Y${row}`).setNumberFormat('yyyy-mm-dd hh:mm');
  for (const [column, key] of [['C', 'preconditions'], ['F', 'steps'], ['G', 'expected']]) {
    if (present(item[key]) && asText(item[key]) !== previous[{ C: 2, F: 5, G: 6 }[column]]) {
      cases.getRange(`${column}${row}`).values = [[asText(item[key])]];
    }
  }
  const actual = item.backend_status ? `Backend: ${item.backend_status}. ${asText(item.actual)}` : asText(item.actual);
  cases.getRange(`H${row}:J${row}`).values = [[actual, asText(item.evidence), item.status]];
  cases.getRange(`V${row}:Z${row}`).format.wrapText = true;
  cases.getRange(`A${row}:Z${row}`).format.rowHeight = 180;
  updatedCaseRows.push(row);
}
for (const [col, width] of [['V', 24], ['W', 75], ['X', 75], ['Y', 28], ['Z', 75]]) {
  cases.getRange(`${col}1:${col}58`).format.columnWidth = width;
}

const defects = wb.worksheets.getItem('06_Defects');
const defectRows = defects.getRange('A8:R40').values;
if (defects.getRange('A23').values[0][0] !== 'UAT-ENV-001') throw new Error('Preserve the existing ENV record at row 23');
if (defects.getRange('R7').values[0].some(present)) throw new Error('Defect history destination is occupied');
defects.getRange('R7').copyFrom(defects.getRange('Q7'), 'all');
defects.getRange('R7').values = [['Disposición previa a reconstrucción']];
const updatedDefectRows = [];
for (const id of requiredDefectIds.filter(id => !newDefectRows.has(id))) {
  const index = defectRows.findIndex(row => row[0] === id);
  if (index < 0 || present(defectRows[index][17])) throw new Error(`Missing defect or occupied history ${id}`);
  const row = index + 8;
  const previous = defectRows[index];
  const item = defectFacts.get(id);
  defects.getRange(`R${row}`).copyFrom(defects.getRange(`Q${row}`), 'all');
  defects.getRange(`R${row}`).values = [[JSON.stringify({
    actual: previous[4], status: previous[5], action: previous[6], evidence: previous[8],
  })]];
  defects.getRange(`E${row}:G${row}`).values = [[asText(item.actual), item.status, asText(item.action)]];
  defects.getRange(`I${row}`).values = [[asText(item.evidence)]];
  defects.getRange(`R${row}`).format.wrapText = true;
  defects.getRange(`A${row}:R${row}`).format.rowHeight = row === 10 ? 290 : 230;
  updatedDefectRows.push(row);
}
for (const [id, row] of newDefectRows) {
  const newDefect = defectFacts.get(id);
  if (!newDefect.isNew || defectRows.some(record => record[0] === id) || defects.getRange(`A${row}:R${row}`).values[0].some(present)) {
    throw new Error(`Unexpected new integration/projection defect destination ${id}`);
  }
  const newDefectValues = [
    id, asText(newDefect.classification), asText(newDefect.severity), asText(newDefect.title),
    asText(newDefect.actual), newDefect.status, asText(newDefect.action),
    asText(newDefect.owner || 'Investment Decision y Project Workspace Governance'), asText(newDefect.evidence),
  ];
  defects.tables.items[0].rows.add(null, [newDefectValues]);
  defects.getRange(`A${row}:I${row}`).copyFrom(defects.getRange('A22:I22'), 'all');
  defects.getRange(`A${row}:I${row}`).values = [newDefectValues];
  defects.getRange(`R${row}`).copyFrom(defects.getRange('R22'), 'all');
  defects.getRange(`R${row}`).values = [[JSON.stringify({
    previous_record: null, new_defect: id, collected_at: facts.collected_at,
    note: 'Nuevo hallazgo documentado durante la reconstrucción autorizada; no reemplaza UAT-ENV-001 ni los defectos anteriores',
  })]];
  defects.getRange(`R${row}`).format.wrapText = true;
  defects.getRange(`A${row}:R${row}`).format.rowHeight = 230;
}
defects.getRange('R1:R40').format.columnWidth = 90;
defects.getRange('B5').formulas = [['=COUNTA(A8:A25)']];

const release = wb.worksheets.getItem('08_Release_Criteria');
const releaseRows = release.getRange('A8:M37').values;
if (release.getRange('M7').values[0].some(present)) throw new Error('Release history destination is occupied');
release.getRange('M7').copyFrom(release.getRange('L7'), 'all');
release.getRange('M7').values = [['Criterio previo a reconstrucción']];
const updatedReleaseRows = [];
for (const [id, item] of releaseFacts) {
  const index = releaseRows.findIndex(row => row[0] === id);
  if (index < 0 || releaseRows[index][2] !== 'TECHNICAL' || present(releaseRows[index][12])) {
    throw new Error(`Unexpected technical release criterion or occupied history ${id}`);
  }
  const row = index + 8;
  const previous = releaseRows[index];
  if (!['PASS', 'FAIL', 'BLOCKED'].includes(item.status)) throw new Error(`Invalid release status ${id}`);
  release.getRange(`M${row}`).copyFrom(release.getRange(`L${row}`), 'all');
  release.getRange(`M${row}`).values = [[JSON.stringify({
    criterion: id, prior_condition: previous[3], prior_status: previous[4], prior_evidence: previous[5],
    prior_calculated_result: release.getRange(`J${row}`).values[0][0],
  })]];
  release.getRange(`D${row}:F${row}`).values = [[asText(item.actual), item.status, asText(item.evidence)]];
  release.getRange(`M${row}`).format.wrapText = true;
  release.getRange(`A${row}:M${row}`).format.rowHeight = 130;
  updatedReleaseRows.push(row);
}
release.getRange('M1:M37').format.columnWidth = 90;
const signRows = releaseRows.map((row, index) => row[2] === 'BUSINESS_SIGNOFF' ? index + 8 : null).filter(Boolean);
if (signRows.length !== 15) throw new Error('Expected exactly fifteen retained human sign-off areas');
for (const row of signRows) {
  if (release.getRange(`E${row}:I${row}`).values[0].some(present)) throw new Error('Preserve unexpected human inputs; never erase or fabricate signatures');
}
wb.recalculate();
const signRow = signRows[0];
const originalDecision = release.getRange(`E${signRow}`).values;
release.getRange(`E${signRow}`).values = [['ACCEPTED']];
wb.recalculate();
if (release.getRange(`J${signRow}`).values[0][0] !== 'BLOCKED') throw new Error('Unsigned ACCEPTED incorrectly passed');
release.getRange(`E${signRow}`).values = originalDecision;
wb.recalculate();
for (const row of signRows) {
  if (release.getRange(`E${row}:I${row}`).values[0].some(present) || release.getRange(`J${row}`).values[0][0] !== 'BLOCKED') {
    throw new Error('Human sign-off boundary changed');
  }
}
const errors = await wb.inspect({
  kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',
  options: { useRegex: true, maxResults: 100 }, maxChars: 5000,
});
await fs.writeFile(path.join(qa, 'formula-error-scan.ndjson'), errors.ndjson);
await fs.mkdir(path.dirname(output), { recursive: true });
await (await SpreadsheetFile.exportXlsx(wb)).save(output);
if (createHash('sha256').update(await fs.readFile(source)).digest('hex') !== sourceDigest) throw new Error('Reference source bytes changed');
for (const sidecar of [output + '.inspect.ndjson', output.replace(/\.xlsx$/, '.inspect.ndjson')]) {
  if (await fs.stat(sidecar).then(() => true).catch(() => false)) {
    await fs.rename(sidecar, path.join(qa, `export-inspection-${Date.now()}.ndjson`));
  }
}
await fs.writeFile(path.join(qa, 'edit-manifest.json'), JSON.stringify({
  source, source_sha256: sourceDigest, output, facts: factsPath, facts_sha256: factsDigest,
  collected_at: facts.collected_at, release: facts.release, cases_updated: requiredCaseIds,
  case_rows: updatedCaseRows, defects_updated: requiredDefectIds, defect_rows: updatedDefectRows.concat([...newDefectRows.values()]),
  release_criteria_updated: [...releaseFacts.keys()], release_rows: updatedReleaseRows,
  history: { cases: 'V:Z', defects: 'R', release: 'M' },
  previous_history_retained: { cases: 'L:U', defects: 'P:Q', release: 'K:L' },
  native_defect_table: 'A7:I23 to A7:I25', human_signoff_areas_blank: signRows.length,
  signature_boundary: 'ACCEPTED alone remains BLOCKED',
}, null, 2));
console.log(JSON.stringify({ output, status: facts.release.status, cases_updated: requiredCaseIds, signoffs: signRows.length }));
