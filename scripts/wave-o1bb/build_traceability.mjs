import fs from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";
import { Workbook, SpreadsheetFile } from "@oai/artifact-tool";

const root = path.resolve(import.meta.dirname, "../..");
const qa = path.join(root, "outputs/.qa/wave-o1bb-20261020/workbook");
const data = JSON.parse(await fs.readFile(path.join(root, "docs/validation/wave-o1bb-20261020/package-data.json"), "utf8"));
const book = Workbook.create();
const headers = ["Caso", "Comprobación", "Resultado", "Tiempo s", "Evidencia"];
const widths = [13, 76, 22, 13, 70];
const cases = pattern => [
  ...data.cases.filter(row => pattern.test(row.name)).map((row, i) => [`TC-${i + 1}`, row.name, row.result, row.seconds, row.evidence]),
  ...(data.browser.checks || []).filter(row => pattern.test(row.code)).map((row, i) => [`UI-${i + 1}`, row.code, row.result, null, "chromium/browser-uat.json"]),
];
const themed = (name, title, pattern) => ({ name, title, headers, widths, rows: cases(pattern) });
const specs = [
  { name: "01_Requirements", title: "Requisitos de Schedule Foundation", headers: ["Sección", "Requisito", "Resultado", "Verificación"], widths: [13, 75, 23, 82], rows: data.requirements },
  themed("02_Schedule_Register", "Registros y versiones de cronograma", /register|version|USER_CANONICAL|CURRENT_ACCEPTED/i),
  themed("03_WBS", "Jerarquía WBS y mapeos de ejecución", /wbs|many_to_many|WBS_TREE/i),
  themed("04_Activities", "Actividades hitos y procedencia", /activities|milestone|manual_creation|source_data_date|float|WBS_TREE/i),
  themed("05_Calendars", "Calendarios y bases de duración", /calendar|8h|duration|CALENDARS_SIGNED/i),
  themed("06_Relationships", "Relaciones lags y enlaces externos", /relationship|lag|external|CALENDARS_SIGNED/i),
  themed("07_Constraints_Codes", "Restricciones y códigos", /constraint|code|CALENDARS_SIGNED/i),
  themed("08_P6_Import", "Importación gobernada XML y XER", /source|xml|xer|snapshot|file_upload|IMPORT|UPLOAD|CPM/i),
  themed("09_P6_Export", "Exportación XML y límites del subconjunto", /export|roundtrip|DOWNLOAD|REIMPORT/i),
  themed("10_Baselines", "Baselines aprobados y Current", /baseline|BASELINE|CURRENT/i),
  themed("11_Mappings", "M:N e integridad de los mapeos", /mapping|many_to_many|MAP|TRACEABILITY/i),
  themed("12_Schedule_Health", "Calidad del cronograma y consultas", /health|lookahead|quality|policy|invalid|CALENDARS_SIGNED/i),
  themed("13_Admin_User", "Configuración y operación", /profile|policy|read_roles|write_duties|ADMIN_|USER_CANONICAL/i),
  themed("14_Security", "Autorización y separación de funciones", /denied|wrong|sod|immut|etag|idempot|isolation|assignment|no_sql|forg|generic_admin|predecessor|INDEPENDENT/i),
  { name: "15_API", title: "API de Schedule canónica", headers: ["Método", "Ruta", "Operación", "Permiso"], widths: [13, 92, 57, 45], rows: data.api },
  { name: "16_Defects", title: "Hallazgos y límites comprobados", headers: ["ID", "Severidad", "Hallazgo", "Estado", "Tratamiento"], widths: [14, 17, 73, 23, 82], rows: data.defects },
  { name: "17_Release_Criteria", title: "Criterios de liberación y mediciones", headers: ["ID", "Criterio u operación", "Resultado", "Muestras", "Mín ms", "Mediana ms", "Máx ms", "Evidencia"], widths: [13, 67, 27, 13, 14, 14, 14, 70], rows: [...data.release_criteria.map(row => [row[0], row[1], row[2], null, null, null, null, row[3]]), ...data.performance.map((row, i) => [`PERF-${i + 1}`, row[0], "LOCAL_NO_SLA", ...row.slice(1), "Observación local aislada sin SLA productivo"])] },
];
await fs.mkdir(qa, { recursive: true });
const priorRender = JSON.parse(await fs.readFile(path.join(qa, "render-hashes.json"), "utf8").catch(() => "{}"));
const renderHashes = {};
const builderHash = createHash("sha256").update(await fs.readFile(new URL(import.meta.url))).digest("hex");
const expected = [], previews = [], manifest = [];
const col = index => String.fromCharCode(65 + index);
for (const [index, spec] of specs.entries()) {
  if (!spec.rows.length) throw new Error(`No evidence for ${spec.name}`);
  const sheet = book.worksheets.add(spec.name);
  const lastCol = col(spec.headers.length - 1), end = 7 + spec.rows.length;
  const all = sheet.getRange(`A1:${lastCol}${end}`);
  all.format.font = { name: "Arial", size: 10, color: "#243746" };
  all.format.rowHeight = 24;
  sheet.showGridLines = false;
  sheet.getRange("A2").values = [[spec.title]];
  sheet.getRange("A2").format.font = { name: "Arial", size: 14, bold: true, color: "#000000" };
  sheet.getRange(`A3:${lastCol}3`).format.borders = { bottom: { style: "thin", color: "#17324D" } };
  sheet.getRange("A4").values = [["Corte técnico 21 octubre 2026"]];
  sheet.getRange("A4").format.font = { name: "Arial", size: 10, italic: true, color: "#65758B" };
  sheet.getRange("A5").values = [["Alcance técnico aislado. Compatibilidad P6 limitada al subconjunto declarado."]];
  sheet.getRange(`A7:${lastCol}7`).values = [spec.headers];
  sheet.getRange(`A7:${lastCol}7`).format = { fill: "#17324D", font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", verticalAlignment: "center", rowHeight: 35, wrapText: true };
  sheet.getRange(`A8:${lastCol}${end}`).values = spec.rows;
  sheet.getRange(`A8:${lastCol}${end}`).format.wrapText = true;
  sheet.getRange(`A8:${lastCol}${end}`).format.verticalAlignment = "center";
  for (const [c, width] of spec.widths.entries()) sheet.getRange(`${col(c)}1:${col(c)}${end}`).format.columnWidth = width;
  for (const [r, values] of spec.rows.entries()) {
    const range = sheet.getRange(`A${r + 8}:${lastCol}${r + 8}`);
    range.format.rowHeight = Math.max(30, ...values.map((value, c) => Math.ceil(String(value ?? "").length / Math.max(8, spec.widths[c] - 4)) * 15 + 12));
    if (r % 2) range.format.fill = "#F3F6FA";
  }
  if (spec.headers.includes("Tiempo s")) sheet.getRange(`D8:D${end}`).setNumberFormat("0.000");
  if (index === 16) sheet.getRange(`D8:G${end}`).setNumberFormat("0.00");
  const status = spec.headers.findIndex(value => value === "Resultado" || value === "Estado");
  if (status >= 0) {
    const cells = sheet.getRange(`${col(status)}8:${col(status)}${end}`);
    cells.conditionalFormats.add("containsText", { text: "FAIL", format: { fill: "#FCE8E6", font: { color: "#9C1C1C", bold: true } } });
    cells.conditionalFormats.add("containsText", { text: "PENDING", format: { fill: "#FFF3CD" } });
  }
  sheet.tables.add(`A7:${lastCol}${end}`, true, `ScheduleTrace${index + 1}`).showFilterButton = true;
  sheet.freezePanes.freezeRows(7);
  if (spec.rows.length > 20) sheet.freezePanes.freezeColumns(1);
  if ([0, 16].includes(index)) sheet.tabColor = "#17324D";
  expected.push({ sheet: spec.name, headers: spec.headers, rows: spec.rows });
  manifest.push({ sheet: spec.name, rows: spec.rows.length, columns: spec.headers.length, last_row: end, last_column: lastCol });
}
book.recalculate();
await fs.writeFile(path.join(qa, "inspection.ndjson"), (await book.inspect({ kind: "workbook,sheet,table", maxChars: 6000, tableMaxRows: 2, tableMaxCols: 4 })).ndjson);
await fs.writeFile(path.join(qa, "errors.ndjson"), (await book.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!", options: { useRegex: true, maxResults: 30 }, maxChars: 2000 })).ndjson);
await fs.writeFile(path.join(qa, "expected-tables.json"), JSON.stringify(expected, null, 2));
await fs.writeFile(path.join(qa, "build-manifest.json"), JSON.stringify({ sheets: manifest }, null, 2));
for (const sheet of manifest) {
  const sheetSpec = specs.find(spec => spec.name === sheet.sheet);
  renderHashes[sheet.sheet] = createHash("sha256").update(JSON.stringify([builderHash, sheetSpec])).digest("hex");
  for (let start = 1; start <= sheet.last_row; start += 18) {
    const range = `A${start}:${sheet.last_column}${Math.min(start + 17, sheet.last_row)}`;
    const filename = `${sheet.sheet}-${String(start).padStart(3, "0")}.png`;
    const reused = priorRender[sheet.sheet] === renderHashes[sheet.sheet] && await fs.stat(path.join(qa, filename)).then(() => true).catch(() => false);
    if (!reused) {
      const png = await book.render({ sheetName: sheet.sheet, range, scale: 1.15, format: "png" });
      await fs.writeFile(path.join(qa, filename), new Uint8Array(await png.arrayBuffer()));
    }
    previews.push({ sheet: sheet.sheet, range, file: filename });
  }
}
await fs.writeFile(path.join(qa, "render-hashes.json"), JSON.stringify(renderHashes, null, 2));
await fs.writeFile(path.join(qa, "render-manifest.json"), JSON.stringify(previews, null, 2));
const output = path.join(root, "outputs/wave-o1bb-20261020/P&Pmis_Wave_O1B_B_Schedule_Foundation_Traceability.xlsx");
await fs.mkdir(path.dirname(output), { recursive: true });
await (await SpreadsheetFile.exportXlsx(book)).save(output);
console.log(JSON.stringify({ output, sheets: manifest.length, records: manifest.reduce((sum, item) => sum + item.rows, 0), preview_ranges: previews.length }));
