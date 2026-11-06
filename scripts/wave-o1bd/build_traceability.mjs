import fs from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

const artifactRequire = createRequire(path.join(import.meta.dirname, "runtime-node/runtime-entry.mjs"));
const { Workbook, SpreadsheetFile } = await import(pathToFileURL(artifactRequire.resolve("@oai/artifact-tool")).href);

const root = path.resolve(import.meta.dirname, "../..");
const qa = path.join(root, "outputs/.qa/wave-o1bd-20261104/workbook");
const data = JSON.parse(await fs.readFile(path.join(root, "docs/validation/wave-o1bd-20261104/package-data.json"), "utf8"));
const book = Workbook.create();
const headers = ["Caso", "Comprobación", "Resultado", "Tiempo s", "Evidencia"];
const widths = [14, 82, 26, 13, 64];
const cases = (pattern) => [
  ...data.cases.filter((r) => r.evidence === "progress-final-junit.xml" && pattern.test(r.name)).map((r, i) => [`TC-${i + 1}`, r.name, r.result, r.seconds, `${r.evidence} ${r.class}`]),
  ...data.browser.checks.filter((r) => pattern.test(r.code)).map((r, i) => [`UI-${i + 1}`, r.code, r.result, null, "Chromium real browser-uat.json"]),
];
const themed = (name, title, pattern) => ({ name, title, headers, widths, rows: cases(pattern) });
const specs = [
  { name: "01_Requirements", title: "Requisitos Progress y Baseline Integration", headers: ["ID", "Requisito", "Resultado", "Verificación"], widths: [14, 82, 26, 82], rows: data.requirements },
  { name: "02_Progress_Types", title: "Siete tipos de avance con fuentes separadas", headers: ["Tipo", "Autoridad", "Unidad", "Regla"], widths: [22, 64, 22, 96], rows: data.progress_types },
  themed("03_Quantity_Progress", "Cantidades acumuladas delta y denominador", /quantity|denominator|unit|delta|cumulative|overrun/i),
  themed("04_Physical_Progress", "Métodos y aprobación del avance físico", /physical|manual|assessment|approve|certif/i),
  themed("05_Schedule_Progress", "Avance consumido desde Schedule", /schedule|data_date|SCHEDULE/i),
  themed("06_Cost_Progress", "Costo reconocido y base de control", /cost|actual|currency|COST/i),
  themed("07_Earned_Progress", "Base física aprobada del valor ganado", /earned|evm|EV_|EVM/i),
  themed("08_Weighted_Progress", "Ponderación gobernada y prevención de solapamientos", /weight|overlap|aggregation|aggregate/i),
  themed("09_Milestones_ROC", "Hitos pasos y reglas de crédito", /milestone|rule|credit|step|ROC/i),
  themed("10_Periods", "Captura congelación cierre y publicación", /period|freeze|frozen|cumulative|delta|rework|REVIEW|PUBLISHED/i),
  themed("11_Baseline_Bundle", "Referencias y consistencia de líneas base", /bundle|baseline|drift|source.*hash|successor/i),
  themed("12_EVM", "PV EV AC y salvaguardas de cálculo", /evm|earned|zero|division|missing|EVM/i),
  themed("13_AWP_Progress", "Consumo de paquetes y actividades mapeadas", /package|awp|activity|ready|release/i),
  themed("14_4D_Integration", "Superposición aprobada y semántica 4D", /four_d|overlay|nature|temporary|ifc|4D/i),
  themed("15_Admin_User", "Configuración y operación por ámbito", /profile|publication|admin|config|policy|CATALOG/i),
  themed("16_Security", "Permisos independencia e inmutabilidad", /tenant|project|foreign|deni|sod|independent|etag|idempot|immutable|no_write|unchanged|adoption|legacy|permission|scope/i),
  { name: "17_API", title: "Contratos API de Progress", headers: ["Método", "Ruta", "Operación", "Dominio"], widths: [14, 100, 68, 20], rows: data.api },
  { name: "18_Defects", title: "Correcciones verificadas y límites", headers: ["ID", "Severidad", "Hallazgo", "Estado", "Tratamiento"], widths: [14, 18, 80, 32, 86], rows: data.defects },
  { name: "19_Release_Criteria", title: "Criterios y observaciones de liberación", headers: ["ID", "Criterio u operación", "Resultado", "Muestras", "Mín ms", "Mediana ms", "Máx ms", "Evidencia"], widths: [14, 78, 34, 13, 14, 14, 14, 70], rows: [
    ...data.release_criteria.map((r) => [r[0], r[1], r[2], null, null, null, null, r[3]]),
    ...data.performance.map((r, i) => [`PERF-${i + 1}`, r[0], "LOCAL_NO_SLA", ...r.slice(1), "API real aislada tres muestras por operación"]),
  ] },
];
await fs.mkdir(qa, { recursive: true });
const expected = [], manifest = [], previews = [];
const col = (i) => String.fromCharCode(65 + i);
for (const [index, spec] of specs.entries()) {
  if (!spec.rows.length) throw new Error(`Missing real evidence for ${spec.name}`);
  const sheet = book.worksheets.add(spec.name);
  const last = col(spec.headers.length - 1), end = 7 + spec.rows.length;
  const all = sheet.getRange(`A1:${last}${end}`);
  all.format.font = { name: "Arial", size: 10, color: "#243746" };
  all.format.rowHeight = 24;
  sheet.showGridLines = false;
  sheet.getRange("A2").values = [[spec.title]];
  sheet.getRange("A2").format.font = { name: "Arial", size: 14, bold: true, color: "#000000" };
  sheet.getRange(`A3:${last}3`).format.borders = { bottom: { style: "thin", color: "#17324D" } };
  sheet.getRange("A4").values = [["Cierre técnico 5 noviembre 2026"]];
  sheet.getRange("A4").format.font = { name: "Arial", size: 10, italic: true, color: "#65758B" };
  sheet.getRange("A5").values = [["Validación técnica aislada sin aceptación de negocio firmada"]];
  sheet.getRange(`A7:${last}7`).values = [spec.headers];
  sheet.getRange(`A7:${last}7`).format = { fill: "#17324D", font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", verticalAlignment: "center", rowHeight: 35, wrapText: true };
  sheet.getRange(`A8:${last}${end}`).values = spec.rows;
  sheet.getRange(`A8:${last}${end}`).format.wrapText = true;
  sheet.getRange(`A8:${last}${end}`).format.verticalAlignment = "center";
  for (const [c, width] of spec.widths.entries()) sheet.getRange(`${col(c)}1:${col(c)}${end}`).format.columnWidth = width;
  for (const [r, values] of spec.rows.entries()) {
    const row = sheet.getRange(`A${r + 8}:${last}${r + 8}`);
    row.format.rowHeight = Math.max(30, ...values.map((v, c) => Math.ceil(String(v ?? "").length / Math.max(8, spec.widths[c] - 4)) * 15 + 12));
    if (r % 2) row.format.fill = "#F3F6FA";
  }
  if (spec.headers.includes("Tiempo s")) sheet.getRange(`D8:D${end}`).setNumberFormat("0.000");
  if (index === 18) { sheet.getRange(`D8:D${end}`).setNumberFormat("#,##0"); sheet.getRange(`E8:G${end}`).setNumberFormat("0.00"); }
  const status = spec.headers.findIndex((v) => ["Resultado", "Estado"].includes(v));
  if (status >= 0) {
    sheet.getRange(`${col(status)}8:${col(status)}${end}`).conditionalFormats.add("containsText", { text: "FAIL", format: { fill: "#FCE8E6", font: { color: "#9C1C1C", bold: true } } });
  }
  sheet.tables.add(`A7:${last}${end}`, true, `ProgressTrace${index + 1}`).showFilterButton = true;
  sheet.freezePanes.freezeRows(7);
  if (spec.rows.length > 20) sheet.freezePanes.freezeColumns(1);
  if ([0, 18].includes(index)) sheet.tabColor = "#17324D";
  expected.push({ sheet: spec.name, headers: spec.headers, rows: spec.rows });
  manifest.push({ sheet: spec.name, rows: spec.rows.length, columns: spec.headers.length, last_row: end, last_column: last });
}
book.recalculate();
await fs.writeFile(path.join(qa, "inspection.ndjson"), (await book.inspect({ kind: "workbook,sheet,table", maxChars: 6000, tableMaxRows: 2, tableMaxCols: 4 })).ndjson);
await fs.writeFile(path.join(qa, "errors.ndjson"), (await book.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!", options: { useRegex: true, maxResults: 30 }, maxChars: 2000 })).ndjson);
await fs.writeFile(path.join(qa, "expected-tables.json"), JSON.stringify(expected, null, 2));
await fs.writeFile(path.join(qa, "build-manifest.json"), JSON.stringify({ sheets: manifest }, null, 2));
for (const sheet of manifest) {
  for (let start = 1; start <= sheet.last_row; start += 18) {
    const range = `A${start}:${sheet.last_column}${Math.min(start + 17, sheet.last_row)}`;
    const file = `${sheet.sheet}-${String(start).padStart(3, "0")}.png`;
    const png = await book.render({ sheetName: sheet.sheet, range, scale: 1.15, format: "png" });
    await fs.writeFile(path.join(qa, file), new Uint8Array(await png.arrayBuffer()));
    previews.push({ sheet: sheet.sheet, range, file });
  }
}
await fs.writeFile(path.join(qa, "render-manifest.json"), JSON.stringify(previews, null, 2));
const output = path.join(root, "outputs/wave-o1bd-20261104/P&Pmis_Wave_O1B_D_Progress_and_Baseline_Integration_Traceability.xlsx");
await fs.mkdir(path.dirname(output), { recursive: true });
await (await SpreadsheetFile.exportXlsx(book)).save(output);
try { await fs.rename(output + ".inspect.ndjson", path.join(qa, "export-inspection.ndjson")); }
catch (error) { if (error.code !== "ENOENT") throw error; }
console.log(JSON.stringify({ output, sheets: manifest.length, records: manifest.reduce((sum, r) => sum + r.rows, 0), previews: previews.length }));
