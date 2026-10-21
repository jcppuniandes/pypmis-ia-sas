/** Architecture workbook only. No product modules, APIs, migrations or services. */
import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { FileBlob, SpreadsheetFile, Workbook } from '@oai/artifact-tool';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const inputPath = path.join(root, 'docs/architecture/operational/architecture-data.json');
const outputDir = path.join(root, 'outputs/operational-master-architecture-20261019');
const qaDir = path.join(root, 'outputs/.qa/operational-master-architecture-20261019/workbook');
const outputPath = path.join(outputDir, 'P&Pmis_Operational_Macroprocess_Domain_Map_and_Roadmap.xlsx');
const requiredSheets = [
  '01_Domain_Map', '02_Process_Map', '03_Admin_User_Matrix',
  '04_Owner_Contractor_Matrix', '05_Data_Ownership', '06_Integration_Matrix',
  '07_Current_Capabilities', '08_Gap_Analysis', '09_Wave_Prioritization',
  '10_Dependency_Map', '11_Legacy_Candidates', '12_Decisions',
];
const criteriaKeys = [
  'business_value', 'dependency_centrality', 'existing_capability_reuse',
  'implementation_complexity', 'data_model_risk', 'cross_domain_coupling',
  'strategic_integration_importance', 'owner_applicability',
  'contractor_applicability', 'reporting_value', 'user_urgency',
];
const palette = {
  navy: '#17324D', ink: '#243547', muted: '#64748B', pale: '#F3F6FA',
  amber: '#FFF3CD', error: '#FCE8E6', line: '#DCE3EB', white: '#FFFFFF',
};
const mode = process.argv.find(arg => ['--validate-data', '--author', '--verify-output'].includes(arg));
if (!mode) throw new Error('Select --validate-data, --author or --verify-output.');
if (mode === '--author' && !process.argv.includes('--authoring-marker-confirmed')) {
  throw new Error('Root must successfully record the one workbook create marker immediately before authoring.');
}
const dataBytes = await fs.readFile(inputPath);
const data = JSON.parse(dataBytes.toString('utf8'));
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
const column = index => {
  let n = index + 1;
  let result = '';
  while (n > 0) { n -= 1; result = String.fromCharCode(65 + n % 26) + result; n = Math.floor(n / 26); }
  return result;
};
function ensure(condition, message) { if (!condition) throw new Error(message); }
function presentationValue(value, compactReferences = false) {
  if (typeof value !== 'string' || !value.includes('\n')) return value;
  const lines = value.split('\n').map(line => line.trim());
  if (compactReferences && lines.every(line => /^(?:backend|frontend|scripts|docs)\/.+:\d+$/.test(line))) return lines.join('; ');
  return lines.every(line => /^[A-Z][A-Z0-9_-]*\d[A-Z0-9_-]*$/.test(line)) ? lines.join(', ') : value;
}

function validateData() {
  ensure(Array.isArray(data.workbook_sheets) && data.workbook_sheets.length === 12, 'Exactly 12 requested workbook sheets are required.');
  ensure(JSON.stringify(data.workbook_sheets.map(s => s.name)) === JSON.stringify(requiredSheets), 'Sheet names/order must match prompt.');
  for (const spec of data.workbook_sheets) {
    ensure(typeof spec.title === 'string' && spec.title.length > 0, `${spec.name}: missing title.`);
    if (spec.name === requiredSheets[8]) continue;
    ensure(Array.isArray(spec.headers) && spec.headers.length > 0, `${spec.name}: missing headers.`);
    ensure(new Set(spec.headers).size === spec.headers.length, `${spec.name}: duplicate headers.`);
    ensure(Array.isArray(spec.rows), `${spec.name}: missing rows.`);
    for (const [index, row] of spec.rows.entries()) {
      ensure(Array.isArray(row) && row.length === spec.headers.length, `${spec.name}: row ${index + 1} width mismatch.`);
      ensure(row.every(value => value === null || ['string', 'number', 'boolean'].includes(typeof value)), `${spec.name}: unsupported cell type.`);
    }
    if (spec.widths) ensure(spec.widths.length === spec.headers.length && spec.widths.every(w => Number.isFinite(w) && w >= 8 && w <= 100), `${spec.name}: invalid widths.`);
  }
  const p = data.prioritization;
  ensure(p && p.sheet === requiredSheets[8], 'Missing prioritization configuration.');
  ensure(Array.isArray(p.criteria) && p.criteria.length === 11, 'Exactly 11 prioritization criteria required.');
  ensure(JSON.stringify(p.criteria.map(c => c.key)) === JSON.stringify(criteriaKeys), 'Criteria keys/order must follow supplied prompt.');
  p.criteria.forEach((criterion, index) => {
    ensure(typeof criterion.label === 'string' && criterion.label && typeof criterion.rationale === 'string', `Criterion ${index + 1}: missing documentation.`);
    ensure(Number.isFinite(criterion.weight) && criterion.weight > 0, `Criterion ${index + 1}: weight must be positive.`);
    ensure(criterion.direction === (index >= 3 && index <= 5 ? 'penalty' : 'benefit'), `Criterion ${index + 1}: incorrect direction.`);
  });
  ensure(Math.abs(p.criteria.reduce((sum, criterion) => sum + criterion.weight, 0) - 1) < 1e-9, 'Prioritization weights must sum to 1.');
  ensure(Array.isArray(p.rows) && p.rows.length > 0, 'Prioritization domain rows required.');
  ensure(new Set(p.rows.map(r => r.domain_id)).size === p.rows.length, 'Duplicate prioritization domain ID.');
  for (const row of p.rows) {
    ensure(typeof row.domain_id === 'string' && row.domain_id && typeof row.domain_name === 'string', 'Missing prioritization identity.');
    for (const key of criteriaKeys) {
      const score = row.scores?.[key];
      ensure(score === null || (Number.isInteger(score) && score >= 1 && score <= 5), `${row.domain_id}/${key}: score must be source-supplied integer 1..5 or null.`);
    }
    ensure(typeof row.rationale === 'string' && typeof row.source_refs === 'string', `${row.domain_id}: score rationale and evidence required.`);
  }
  return { sheets: 12, prioritizationDomains: p.rows.length, criteria: 11, dataSha256: sha256(dataBytes) };
}
const inputSummary = validateData();
if (mode === '--validate-data') { console.log(JSON.stringify({ mode, ...inputSummary })); process.exit(0); }

function rowHeight(values, widths) {
  const needed = values.map((value, index) => {
    const text = String(value ?? '');
    const effectiveWidth = Math.max(6, (widths[index] ?? 26) - 3);
    return text.split('\n').reduce((sum, line) => sum + Math.max(1, Math.ceil(line.length / effectiveWidth)), 0);
  });
  return Math.max(32, Math.max(...needed) * 15 + 12);
}
function baseSheet(sheet, spec, lastColumn, lastRow) {
  const used = sheet.getRange(`A1:${lastColumn}${lastRow}`);
  used.format.font = { name: 'Arial', size: 10, color: palette.ink };
  used.format.verticalAlignment = 'center';
  used.format.rowHeight = 24;
  sheet.showGridLines = false;
  sheet.getRange('A2').values = [[spec.title]];
  sheet.getRange('A2').format.font = { name: 'Arial', size: 14, bold: true, color: palette.navy };
  sheet.getRange(`A3:${lastColumn}3`).format.borders = { bottom: { style: 'thin', color: palette.navy } };
  if (spec.source_note) {
    sheet.getRange('A4').values = [[spec.source_note]];
    sheet.getRange('A4').format.font = { name: 'Arial', size: 10, italic: true, color: palette.muted };
  }
  if ([requiredSheets[0], requiredSheets[8], requiredSheets[11]].includes(spec.name)) sheet.tabColor = palette.navy;
}
function header(sheet, range, values) {
  sheet.getRange(range).values = [values];
  sheet.getRange(range).format = {
    fill: palette.navy, font: { name: 'Arial', size: 10, bold: true, color: palette.white },
    horizontalAlignment: 'center', verticalAlignment: 'center', wrapText: true, rowHeight: 48,
  };
}
function genericSheet(sheet, spec, index) {
  const headerRow = spec.header_row ?? 7;
  const firstRow = headerRow + 1;
  const lastRow = Math.max(firstRow, headerRow + spec.rows.length);
  const lastColumn = column(spec.headers.length - 1);
  const widths = [...(spec.widths ?? spec.headers.map((_, col) => col === 0 ? 15 : col === 1 ? 30 : 40))];
  // Long repository references need readable widths rather than invalid >409pt Excel rows.
  if (spec.name === '07_Current_Capabilities') { widths[8] = 80; widths[9] = 45; widths[10] = 20; }
  baseSheet(sheet, spec, lastColumn, lastRow);
  header(sheet, `A${headerRow}:${lastColumn}${headerRow}`, spec.headers);
  const presentedRows = spec.rows.map(row => row.map((value, col) => presentationValue(value, spec.name === '07_Current_Capabilities' && col === 8)));
  if (spec.rows.length) sheet.getRange(`A${firstRow}:${lastColumn}${lastRow}`).values = presentedRows;
  sheet.getRange(`A${firstRow}:${lastColumn}${lastRow}`).format.wrapText = true;
  sheet.getRange(`A${firstRow}:${lastColumn}${lastRow}`).format.verticalAlignment = 'top';
  for (let col = 0; col < widths.length; col += 1) {
    sheet.getRange(`${column(col)}1:${column(col)}${lastRow}`).format.columnWidth = widths[col];
  }
  for (let row = firstRow; row <= lastRow; row += 1) {
    const values = presentedRows[row - firstRow] ?? [];
    sheet.getRange(`A${row}:${lastColumn}${row}`).format.rowHeight = spec.row_heights?.[row - firstRow] ?? rowHeight(values, widths);
  }
  if (spec.rows.length) {
    const table = sheet.tables.add(`A${headerRow}:${lastColumn}${lastRow}`, true, `OperationalArchitecture${index + 1}`);
    table.style = 'TableStyleMedium2';
    table.showBandedColumns = false;
  }
  for (const format of spec.formats ?? []) {
    const col = column(format.column);
    sheet.getRange(`${col}${firstRow}:${col}${lastRow}`).setNumberFormat(format.number_format);
  }
  for (const inputCol of spec.input_columns ?? []) {
    const col = column(inputCol);
    sheet.getRange(`${col}${firstRow}:${col}${lastRow}`).format.fill = palette.amber;
  }
  if (spec.rows.length > 6) sheet.freezePanes.freezeRows(headerRow);
  if (spec.headers.length > 5) sheet.freezePanes.freezeColumns(Math.min(2, spec.headers.length));
  return { sheet: spec.name, headerRow, firstRow, lastRow, lastColumn, widths };
}

function scoreFormulaLayout(workbook, sheet, spec) {
  const p = data.prioritization;
  const headerRow = 9;
  const firstRow = 10;
  const lastRow = firstRow + p.rows.length - 1;
  const widths = [16, 32, ...Array(11).fill(15), 26, 18, 18, 16, 13, 22, 55, 55];
  baseSheet(sheet, spec, 'U', lastRow);
  sheet.getRange('A4').values = [['Escala 1–5. Mayor score indica prioridad propuesta. No autoriza desarrollo.']];
  sheet.getRange('A5:B7').values = [['Peso', 'Suma de pesos'], ['Signo', null], ['Control de pesos', null]];
  sheet.getRange('B6').formulas = [['=SUM(C5:M5)']];
  sheet.getRange('B6').setNumberFormat('0.0%');
  sheet.getRange('B7').formulas = [['=IF(AND(COUNT(C5:M5)=11,MIN(C5:M5)>0,ABS(SUM(C5:M5)-1)<0.000000001),"VALID","INVALID_WEIGHTS")']];
  sheet.getRange('B7').conditionalFormats.add('containsText', { text: 'INVALID', format: { fill: palette.error, font: { color: '#9C2020', bold: true } } });
  sheet.getRange('A5:B6').format.wrapText = true;
  sheet.getRange('A5:B6').format.rowHeight = 32;
  sheet.getRange('C5:M5').values = [p.criteria.map(c => c.weight)];
  sheet.getRange('C6:M6').values = [p.criteria.map(c => c.direction === 'benefit' ? 1 : -1)];
  sheet.getRange('C5:M5').format.fill = palette.amber;
  sheet.getRange('C5:M5').setNumberFormat('0.0%');
  sheet.getRange('C6:M6').setNumberFormat('0');
  const headers = ['Dominio ID', 'Dominio', ...p.criteria.map(c => c.label), 'Validación de puntuaciones', 'Beneficio ponderado', 'Penalización ponderada', 'Score normalizado 0–100', 'Ranking', 'Wave propuesta', 'Justificación', 'Fuentes'];
  header(sheet, `A${headerRow}:U${headerRow}`, headers);
  sheet.getRange(`A${firstRow}:U${lastRow}`).values = p.rows.map(r => [
    r.domain_id, r.domain_name, ...criteriaKeys.map(key => r.scores[key]), null, null, null, null, null,
    r.wave_proposed ?? '', `${data.domains.find(domain => domain.id === r.domain_id).rationale}\nDetalle íntegro en nota.`, r.source_refs,
  ]);
  p.rows.forEach((row, index) => {
    const address = `T${firstRow + index}`;
    workbook.notes.add({
      id: `${sheet.name}:${address}`,
      target: { cell: { sheetName: sheet.name, sheetId: sheet.sheetId, address } },
      authorId: '', createdAt: '', body: { plainText: row.rationale },
    });
  });
  sheet.getRange(`C${firstRow}:M${lastRow}`).format.fill = palette.amber;
  sheet.getRange(`C${firstRow}:M${lastRow}`).setNumberFormat('0');
  sheet.getRange(`A${firstRow}:U${lastRow}`).format.wrapText = true;
  sheet.getRange(`A${firstRow}:U${lastRow}`).format.verticalAlignment = 'top';
  sheet.getRange(`O${firstRow}:Q${lastRow}`).setNumberFormat('0.00');
  sheet.getRange(`R${firstRow}:R${lastRow}`).setNumberFormat('0');
  const weightValid = '$B$7="VALID"';
  for (let row = firstRow; row <= lastRow; row += 1) {
    const integerChecks = criteriaKeys.map((_, index) => `IF(ISNUMBER(${column(index + 2)}${row}),MOD(${column(index + 2)}${row},1)=0,FALSE)`).join(',');
    sheet.getRange(`N${row}`).formulas = [[`=IF(NOT(${weightValid}),"PESOS_INVALIDOS",IF(COUNTBLANK(C${row}:M${row})>0,"FALTAN_PUNTUACIONES",IF(AND(COUNT(C${row}:M${row})=11,MIN(C${row}:M${row})>=1,MAX(C${row}:M${row})<=5,${integerChecks}),"COMPLETO","PUNTUACION_INVALIDA")))`]];
    sheet.getRange(`O${row}`).formulas = [[`=IF(N${row}="COMPLETO",SUMPRODUCT(C${row}:E${row},$C$5:$E$5)+SUMPRODUCT(I${row}:M${row},$I$5:$M$5),"")`]];
    sheet.getRange(`P${row}`).formulas = [[`=IF(N${row}="COMPLETO",SUMPRODUCT(F${row}:H${row},$F$5:$H$5),"")`]];
    sheet.getRange(`Q${row}`).formulas = [[`=IF(N${row}="COMPLETO",ROUND(100*(O${row}-P${row}-(SUM($C$5:$E$5)+SUM($I$5:$M$5)-5*SUM($F$5:$H$5)))/(4*SUM($C$5:$M$5)),8),"")`]];
    sheet.getRange(`R${row}`).formulas = [[`=IF(ISNUMBER(Q${row}),RANK(Q${row},$Q$${firstRow}:$Q$${lastRow},0),"")`]];
    sheet.getRange(`A${row}:U${row}`).format.rowHeight = rowHeight(sheet.getRange(`A${row}:U${row}`).values[0], widths);
  }
  sheet.getRange(`N${firstRow}:N${lastRow}`).conditionalFormats.add('notContainsText', { text: 'COMPLETO', format: { fill: palette.amber, font: { color: '#7A5100' } } });
  sheet.getRange(`C${firstRow}:M${lastRow}`).dataValidation = { rule: { type: 'whole', operator: 'between', formula1: 1, formula2: 5 } };
  const table = sheet.tables.add(`A${headerRow}:U${lastRow}`, true, 'OperationalWavePriorities');
  table.style = 'TableStyleMedium2';
  sheet.freezePanes.freezeRows(headerRow); sheet.freezePanes.freezeColumns(2);
  widths.forEach((width, index) => { sheet.getRange(`${column(index)}1:${column(index)}${lastRow}`).format.columnWidth = width; });
  const documentationRow = lastRow + 3;
  header(sheet, `A${documentationRow}:E${documentationRow}`, ['Criterio', 'Justificación del peso', 'Dirección', 'Peso', 'Interpretación de escala']);
  const methodRows = p.criteria.map(c => [c.label, c.rationale, c.direction === 'benefit' ? 'Beneficio (+1)' : 'Penalización (−1)', null, c.scale_description ?? (c.direction === 'benefit' ? '1 bajo, 5 alto. Mayor valor aumenta prioridad.' : '1 bajo, 5 alto. Mayor valor reduce prioridad.')]);
  sheet.getRange(`A${documentationRow + 1}:E${documentationRow + 11}`).values = methodRows;
  p.criteria.forEach((criterion, index) => { sheet.getRange(`D${documentationRow + 1 + index}`).formulas = [[`=${column(index + 2)}$5`]]; });
  sheet.getRange(`D${documentationRow + 1}:D${documentationRow + 11}`).setNumberFormat('0.0%');
  sheet.getRange(`A${documentationRow + 1}:E${documentationRow + 11}`).format.wrapText = true;
  methodRows.forEach((row, index) => { sheet.getRange(`A${documentationRow + 1 + index}:E${documentationRow + 1 + index}`).format.rowHeight = rowHeight(row, widths.slice(0, 5)); });
  sheet.getRange(`A${documentationRow + 13}`).values = [['Score = 100 × (beneficio − penalización − mínimo teórico) / (máximo teórico − mínimo teórico).']];
  sheet.getRange(`A${documentationRow + 14}`).values = [['Mínimo: beneficio 1, penalización 5. Máximo: beneficio 5, penalización 1. Empates: mismo rango.']];
  sheet.getRange(`A${documentationRow + 15}`).values = [['Score calculado con 8 decimales para evitar desempates por ruido numérico; mostrado con 2. Ordene la tabla por ranking para comparar.']];
  return { sheet: spec.name, headerRow, firstRow, lastRow, lastColumn: 'U', widths, documentationRow, renderLastRow: documentationRow + 15 };
}

function buildViews(layout, spec) {
  if (spec.render_ranges?.length) return spec.render_ranges.map(range => [spec.name, range]);
  const views = [];
  const groups = [];
  let startCol = 0;
  let span = 0;
  layout.widths.forEach((width, index) => {
    if (span + width > 145 && index > startCol) { groups.push([startCol, index - 1]); startCol = index; span = 0; }
    span += width;
  });
  groups.push([startCol, layout.widths.length - 1]);
  for (let startRow = 2; startRow <= layout.lastRow; startRow += 12) {
    const endRow = Math.min(layout.lastRow, startRow + 11);
    for (const [start, end] of groups) views.push([spec.name, `${column(start)}${startRow}:${column(end)}${endRow}`]);
  }
  if (layout.documentationRow) {
    views.push([spec.name, `A${layout.documentationRow}:E${layout.documentationRow + 5}`], [spec.name, `A${layout.documentationRow + 6}:E${layout.documentationRow + 11}`], [spec.name, `A${layout.documentationRow + 13}:L${layout.documentationRow + 15}`]);
  }
  return views;
}
async function renderViews(workbook, label, views) {
  const files = [];
  for (const [sheetName, range] of views) {
    const image = await workbook.render({ sheetName, range, scale: 1, format: 'png' });
    const imagePath = path.join(qaDir, `${label}-${sheetName}-${range.replaceAll(':', '-')}.png`);
    await fs.writeFile(imagePath, new Uint8Array(await image.arrayBuffer()));
    files.push({ sheetName, range, path: path.relative(root, imagePath).replaceAll('\\', '/') });
  }
  return files;
}
async function inspectWorkbook(workbook, label) {
  const inventory = await workbook.inspect({ kind: 'workbook,sheet,table', maxChars: 12000, tableMaxRows: 2, tableMaxCols: 4 });
  await fs.writeFile(path.join(qaDir, `${label}-inventory.ndjson`), inventory.ndjson);
  const errors = await workbook.inspect({ kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!', options: { useRegex: true, maxResults: 300 }, summary: 'Unexpected formula error scan' });
  await fs.writeFile(path.join(qaDir, `${label}-formula-error-scan.ndjson`), errors.ndjson);
  return { inventory: inventory.ndjson, formulaErrors: errors.ndjson };
}
function independentScore(scores, criteria) {
  if (criteria.some(c => !Number.isFinite(c.weight) || c.weight <= 0)) return null;
  if (Math.abs(criteria.reduce((sum, criterion) => sum + criterion.weight, 0) - 1) >= 1e-9) return null;
  if (criteria.some(c => !Number.isInteger(scores[c.key]) || scores[c.key] < 1 || scores[c.key] > 5)) return null;
  let signed = 0; let minimum = 0; let weight = 0;
  for (const criterion of criteria) {
    const benefit = criterion.direction === 'benefit';
    signed += scores[criterion.key] * criterion.weight * (benefit ? 1 : -1);
    minimum += criterion.weight * (benefit ? 1 : -5); weight += criterion.weight;
  }
  return 100 * (signed - minimum) / (4 * weight);
}
async function verifyScores(workbook, layout) {
  const sheet = workbook.worksheets.getItem(requiredSheets[8]);
  const outputs = [];
  for (const [index, row] of data.prioritization.rows.entries()) {
    const actual = sheet.getRange(`Q${layout.firstRow + index}`).values[0][0];
    const expected = independentScore(row.scores, data.prioritization.criteria);
    ensure(expected === null ? actual === '' || actual === null : typeof actual === 'number' && Math.abs(actual - expected) < 1e-8, `${row.domain_id}: saved/current score differs from independent calculation.`);
    outputs.push({ domain: row.domain_id, expected, actual });
  }
  return outputs;
}
async function scoringScenarios(workbook, layout) {
  const sheet = workbook.worksheets.getItem(requiredSheets[8]);
  const inputRange = `C${layout.firstRow}:M${layout.lastRow}`;
  const original = sheet.getRange(inputRange).values;
  const originalWeights = sheet.getRange('C5:M5').values;
  const results = [];
  const current = row => ({ validation: sheet.getRange(`N${row}`).values[0][0], score: sheet.getRange(`Q${row}`).values[0][0], rank: sheet.getRange(`R${row}`).values[0][0], dependent: sheet.getRange(`O${row}:R${row}`).values[0] });
  const empty = value => value === null || value === '';
  const record = (name, pass, observed) => { results.push({ name, pass, observed }); ensure(pass, `Disposable scoring scenario failed: ${name}`); };
  const restore = () => { sheet.getRange(inputRange).values = original; sheet.getRange('C5:M5').values = originalWeights; workbook.recalculate(); };
  const row = layout.firstRow;
  try {
    for (const [name, value, validation] of [
      ['blank_not_zero', null, 'FALTAN_PUNTUACIONES'], ['zero_invalid', 0, 'PUNTUACION_INVALIDA'],
      ['six_invalid', 6, 'PUNTUACION_INVALIDA'], ['fraction_invalid', 1.5, 'PUNTUACION_INVALIDA'],
      ['text_invalid', 'NOT_A_SCORE', 'PUNTUACION_INVALIDA'],
    ]) {
      restore(); sheet.getRange(`C${row}`).values = [[value]]; workbook.recalculate();
      const observed = current(row); record(name, observed.validation === validation && observed.dependent.every(empty), observed);
    }
    const worst = data.prioritization.criteria.map(c => c.direction === 'benefit' ? 1 : 5);
    const best = data.prioritization.criteria.map(c => c.direction === 'benefit' ? 5 : 1);
    restore(); sheet.getRange(`C${row}:M${row}`).values = [worst]; workbook.recalculate();
    record('worst_equals_zero', typeof current(row).score === 'number' && Math.abs(current(row).score) < 1e-8, current(row));
    sheet.getRange(`C${row}:M${row}`).values = [best]; workbook.recalculate();
    record('best_equals_100', typeof current(row).score === 'number' && Math.abs(current(row).score - 100) < 1e-8, current(row));
    for (const [name, value] of [['blank_weight_invalid', null], ['negative_weight_invalid', -0.15], ['weights_sum_not_1_invalid', 0.14]]) {
      restore(); sheet.getRange('C5').values = [[value]]; workbook.recalculate();
      const observed = current(row); record(name, observed.validation === 'PESOS_INVALIDOS' && observed.dependent.every(empty), observed);
    }
    restore(); sheet.getRange(inputRange).values = original.map(() => [...worst]);
    sheet.getRange(`C${row}:M${row}`).values = [best]; workbook.recalculate();
    const before = current(row);
    sheet.getRange(`C${row}:M${row}`).values = [worst]; sheet.getRange(`C${row + 1}:M${row + 1}`).values = [best]; workbook.recalculate();
    const after = current(row);
    record('input_change_updates_rank', before.rank === 1 && after.rank === 2, { before, after });
  } finally { restore(); }
  const scores = await verifyScores(workbook, layout);
  record('original_inputs_and_results_restored', JSON.stringify(sheet.getRange(inputRange).values) === JSON.stringify(original) && JSON.stringify(sheet.getRange('C5:M5').values) === JSON.stringify(originalWeights), { restoredScoreRows: scores.length });
  return { scope: 'DISPOSABLE_IN_MEMORY_SCORING_TESTS_NOT_EXPORTED_OR_APPROVED', results, passed: results.filter(result => result.pass).length, failed: results.filter(result => !result.pass).length };
}

await fs.mkdir(qaDir, { recursive: true });
if (mode === '--verify-output') {
  const manifest = JSON.parse(await fs.readFile(path.join(qaDir, 'build-manifest.json'), 'utf8'));
  ensure(manifest.dataSha256 === inputSummary.dataSha256, 'Input data changed since authoring.');
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(outputPath));
  workbook.recalculate();
  const scoringLayout = manifest.layouts.find(layout => layout.sheet === requiredSheets[8]);
  const beforeHash = sha256(await fs.readFile(outputPath));
  const scenarios = await scoringScenarios(workbook, scoringLayout);
  ensure(sha256(await fs.readFile(outputPath)) === beforeHash, 'Disposable verification changed the saved deliverable.');
  await fs.writeFile(path.join(qaDir, 'formula-scenarios.json'), JSON.stringify(scenarios, null, 2));
  const scores = await verifyScores(workbook, scoringLayout);
  await inspectWorkbook(workbook, 'saved');
  const sheetOption = process.argv.find(arg => arg.startsWith('--changed-sheet='));
  const changedSheet = sheetOption?.split('=')[1];
  if (changedSheet) ensure(requiredSheets.includes(changedSheet), 'Unknown changed sheet.');
  const selectedViews = changedSheet ? manifest.views.filter(([sheetName]) => sheetName === changedSheet) : manifest.views;
  const reused = changedSheet ? manifest.views.filter(([sheetName]) => sheetName !== changedSheet).map(([sheetName, range]) => ({ sheetName, range, path: path.relative(root, path.join(qaDir, `saved-${sheetName}-${range.replaceAll(':', '-')}.png`)).replaceAll('\\', '/') })) : [];
  const beforeHashes = await Promise.all(reused.map(async view => ({ ...view, beforeSha256: sha256(await fs.readFile(path.join(root, view.path))) })));
  const renders = await renderViews(workbook, 'saved', selectedViews);
  const preservedRenders = await Promise.all(beforeHashes.map(async view => ({ ...view, afterSha256: sha256(await fs.readFile(path.join(root, view.path))) })));
  ensure(preservedRenders.every(view => view.beforeSha256 === view.afterSha256), 'An unchanged-sheet PNG changed during the bounded render.');
  const renderHashes = await Promise.all([...renders, ...reused].map(async view => ({ ...view, sha256: sha256(await fs.readFile(path.join(root, view.path))) })));
  await fs.writeFile(path.join(qaDir, 'saved-verification.json'), JSON.stringify({ dataSha256: inputSummary.dataSha256, outputSha256: sha256(await fs.readFile(outputPath)), scores, renders: renderHashes, preservedRenders, reusedUnchangedViews: reused.length, visualReview: 'PENDING_HUMAN_VISUAL_REVIEW' }, null, 2));
  console.log(JSON.stringify({ mode, renders: renders.length, reusedUnchangedViews: reused.length, scores: scores.length })); process.exit(0);
}

const workbook = Workbook.create();
for (const spec of data.workbook_sheets) workbook.worksheets.add(spec.name);
const layouts = data.workbook_sheets.map((spec, index) => {
  const sheet = workbook.worksheets.getItem(spec.name);
  return spec.name === requiredSheets[8] ? scoreFormulaLayout(workbook, sheet, spec) : genericSheet(sheet, spec, index);
});
const views = layouts.flatMap((layout, index) => buildViews(layout, data.workbook_sheets[index]));
workbook.recalculate();
const scores = await verifyScores(workbook, layouts[8]);
await inspectWorkbook(workbook, 'authored');
await fs.mkdir(outputDir, { recursive: true });
const file = await SpreadsheetFile.exportXlsx(workbook);
await file.save(outputPath);
try {
  await fs.rename(`${outputPath}.inspect.ndjson`, path.join(qaDir, 'export-inspect.ndjson'));
} catch (error) { if (error.code !== 'ENOENT') throw error; }
await fs.writeFile(path.join(qaDir, 'build-manifest.json'), JSON.stringify({
  ...inputSummary, outputPath: path.relative(root, outputPath).replaceAll('\\', '/'),
  outputSha256: sha256(await fs.readFile(outputPath)), layouts, views, scores,
  methodology: 'Proposed architecture prioritization only. No business, investment, release or implementation approval implied.',
  visualReview: 'PENDING_SAVED_RENDER_AND_HUMAN_VISUAL_REVIEW',
}, null, 2));
console.log(JSON.stringify({ mode, path: outputPath, sheets: layouts.length, scoreRows: scores.length }));
