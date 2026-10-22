import fs from "node:fs/promises";
import path from "node:path";
import { Workbook, SpreadsheetFile } from "@oai/artifact-tool";

const root = path.resolve(import.meta.dirname, "../..");
const qa = path.join(root, "outputs/.qa/wave-o1bb1-20261021/workbook");
const data = JSON.parse(await fs.readFile(path.join(root, "docs/validation/wave-o1bb1-20261021/package-data.json"), "utf8"));
const book = Workbook.create();
const headers = ["Caso", "Comprobación", "Resultado", "Tiempo s", "Evidencia"];
const widths = [14, 82, 20, 13, 64];
const cases = pattern => [
  ...data.cases.filter(row => pattern.test(row.name)).map((row, i) => [`TC-${i + 1}`, row.name, row.result, row.seconds, row.evidence]),
  ...data.browser.checks.filter(row => pattern.test(row.code)).map((row, i) => [`UI-${i + 1}`, row.code, row.result, null, "chromium/browser-uat.json"]),
];
const themed = (name, title, pattern) => ({ name, title, headers, widths, rows: cases(pattern) });
const specs = [
  { name: "01_Requirements", title: "Requisitos AWP readiness y 4D", headers: ["ID", "Requisito", "Resultado", "Verificación"], widths: [14, 82, 20, 82], rows: data.requirements },
  themed("02_CWA", "Áreas de construcción", /cwa|CWA_CONTAINER/i),
  themed("03_Work_Packages", "Paquetes y ciclo de vida", /package|types|release|complete_closed|ALL_FIVE/i),
  themed("04_Package_Mappings", "Mapeos Scope Plan Package Activity", /mapping|many_to_many|MN_MAPPING/i),
  themed("05_Package_Dependencies", "Dependencias de ejecución", /dependenc|cycle|graph/i),
  themed("06_Execution_Constraints", "Restricciones de ejecución", /constraint|clear|waiver|BLOCKER/i),
  themed("07_Readiness", "Evaluación y preparación del frente", /readiness|assess|READY|release_sod/i),
  themed("08_Schedule_Integration", "Integración sin mutación de Schedule", /schedule|source_mutation|period|baseline|SCHEDULED/i),
  themed("09_4D_Mappings", "Fuentes y mapeos 4D", /four_d|source|traceability|filter|derived|FOUR_D/i),
  themed("10_4D_State_Rules", "Semánticas y estados 4D", /nature|temporary|maintenance|install|remove|state|date|semantic/i),
  themed("11_Admin_User", "Configuración y operación", /profile|configuration|policy|ADMIN|AUTHOR|generic_admin/i),
  themed("12_Security", "Ámbito permisos y separación de funciones", /tenant|scope_tenant|rbac|sod|etag|idempot|immutable|bypass|zero_business|no_mutation|unchanged|read_queries|AUTHOR/i),
  { name: "13_API", title: "API de AWP readiness y 4D", headers: ["Método", "Ruta", "Operación", "Dominio"], widths: [14, 100, 58, 22], rows: data.api },
  { name: "14_Defects", title: "Defectos y límites", headers: ["ID", "Severidad", "Hallazgo", "Estado", "Tratamiento"], widths: [14, 17, 78, 24, 82], rows: data.defects },
  { name: "15_Release_Criteria", title: "Criterios y mediciones de liberación", headers: ["ID", "Criterio u operación", "Resultado", "Muestras", "Mín ms", "Mediana ms", "Máx ms", "Evidencia"], widths: [14, 76, 26, 13, 14, 14, 14, 66], rows: [...data.release_criteria.map(row => [row[0], row[1], row[2], null, null, null, null, row[3]]), ...data.performance.map((row, i) => [`PERF-${i + 1}`, row[0], "LOCAL_NO_SLA", ...row.slice(1), "Entorno aislado no escala productiva"])] },
];
await fs.mkdir(qa, { recursive: true });
const expected = [], previews = [], manifest = [];
const col = index => String.fromCharCode(65 + index);
for (const [index, spec] of specs.entries()) {
  if (!spec.rows.length) throw new Error(`No evidence for ${spec.name}`);
  const sheet = book.worksheets.add(spec.name);
  const last = col(spec.headers.length - 1), end = 7 + spec.rows.length;
  const all = sheet.getRange(`A1:${last}${end}`);
  all.format.font = { name: "Arial", size: 10, color: "#243746" };
  all.format.rowHeight = 24;
  sheet.showGridLines = false;
  sheet.getRange("A2").values = [[spec.title]];
  sheet.getRange("A2").format.font = { name: "Arial", size: 14, bold: true, color: "#000000" };
  sheet.getRange(`A3:${last}3`).format.borders = { bottom: { style: "thin", color: "#17324D" } };
  sheet.getRange("A4").values = [["Corte técnico 21 octubre 2026"]];
  sheet.getRange("A4").format.font = { name: "Arial", size: 10, italic: true, color: "#65758B" };
  sheet.getRange("A5").values = [["Validación técnica aislada sin firmas de aceptación de negocio"]];
  sheet.getRange(`A7:${last}7`).values = [spec.headers];
  sheet.getRange(`A7:${last}7`).format = { fill: "#17324D", font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", verticalAlignment: "center", rowHeight: 35, wrapText: true };
  sheet.getRange(`A8:${last}${end}`).values = spec.rows;
  sheet.getRange(`A8:${last}${end}`).format.wrapText = true;
  sheet.getRange(`A8:${last}${end}`).format.verticalAlignment = "center";
  for (const [column, width] of spec.widths.entries()) sheet.getRange(`${col(column)}1:${col(column)}${end}`).format.columnWidth = width;
  for (const [row, values] of spec.rows.entries()) {
    const range = sheet.getRange(`A${row + 8}:${last}${row + 8}`);
    range.format.rowHeight = Math.max(30, ...values.map((value, c) => Math.ceil(String(value ?? "").length / Math.max(8, spec.widths[c] - 4)) * 15 + 12));
    if (row % 2) range.format.fill = "#F3F6FA";
  }
  if (spec.headers.includes("Tiempo s")) sheet.getRange(`D8:D${end}`).setNumberFormat("0.000");
  if (index === 14) {
    sheet.getRange(`D8:D${end}`).setNumberFormat("#,##0");
    sheet.getRange(`E8:G${end}`).setNumberFormat("0.00");
  }
  const status = spec.headers.findIndex(value => ["Resultado", "Estado"].includes(value));
  if (status >= 0) {
    const cells = sheet.getRange(`${col(status)}8:${col(status)}${end}`);
    cells.conditionalFormats.add("containsText", { text: "FAIL", format: { fill: "#FCE8E6", font: { color: "#9C1C1C", bold: true } } });
    cells.conditionalFormats.add("containsText", { text: "PENDING", format: { fill: "#FFF3CD" } });
  }
  sheet.tables.add(`A7:${last}${end}`, true, `AwpTrace${index + 1}`).showFilterButton = true;
  sheet.freezePanes.freezeRows(7);
  if (spec.rows.length > 20) sheet.freezePanes.freezeColumns(1);
  if ([0, 14].includes(index)) sheet.tabColor = "#17324D";
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
    const filename = `${sheet.sheet}-${String(start).padStart(3, "0")}.png`;
    const selected = process.argv.find(arg => arg.startsWith("--rerender-sheet="))?.split("=")[1];
    const existing = await fs.stat(path.join(qa, filename)).then(() => true).catch(() => false);
    if (!selected || selected === sheet.sheet || !existing) {
      const png = await book.render({ sheetName: sheet.sheet, range, scale: 1.15, format: "png" });
      await fs.writeFile(path.join(qa, filename), new Uint8Array(await png.arrayBuffer()));
    }
    previews.push({ sheet: sheet.sheet, range, file: filename });
  }
}
await fs.writeFile(path.join(qa, "render-manifest.json"), JSON.stringify(previews, null, 2));
const output = path.join(root, "outputs/wave-o1bb1-20261021/P&Pmis_Wave_O1B_B1_AWP_Readiness_4D_Traceability.xlsx");
await fs.mkdir(path.dirname(output), { recursive: true });
await (await SpreadsheetFile.exportXlsx(book)).save(output);
console.log(JSON.stringify({ output, sheets: manifest.length, records: manifest.reduce((sum, item) => sum + item.rows, 0), previews: previews.length }));
