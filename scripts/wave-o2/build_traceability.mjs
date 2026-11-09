import fs from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

const root = path.resolve(import.meta.dirname, "../..");
const qa = path.join(root, "outputs/.qa/wave-o2-20261109");
const require = createRequire(path.join(qa, "runtime-entry.mjs"));
const { Workbook, SpreadsheetFile } = await import(pathToFileURL(require.resolve("@oai/artifact-tool")).href);
const packageData = JSON.parse(await fs.readFile(path.join(qa, "package-data.json"), "utf8"));
const specs = packageData.sheets;
const workbook = Workbook.create();
const workspace = path.join(qa, "workbook");
await fs.mkdir(workspace, { recursive: true });
const manifest = [];
const col = (i) => String.fromCharCode(65 + i);

for (const [index, spec] of specs.entries()) {
  const sheet = workbook.worksheets.add(spec.name);
  const last = col(spec.headers.length - 1);
  const end = 7 + spec.rows.length;
  const cells = sheet.getRange(`A1:${last}${end}`);
  cells.format.font = { name: "Arial", size: 10, color: "#243746" };
  cells.format.rowHeight = 22;
  sheet.showGridLines = false;
  sheet.getRange("A2").values = [[spec.title]];
  sheet.getRange("A2").format.font = { name: "Arial", size: 14, bold: true, color: "#000000" };
  sheet.getRange(`A3:${last}3`).format.borders = { bottom: { style: "thin", color: "#17324D" } };
  sheet.getRange("A4").values = [["Wave O2   Validación de arquitectura   9 noviembre 2026"]];
  sheet.getRange("A4").format.font = { name: "Arial", size: 10, italic: true, color: "#536878" };
  sheet.getRange(`A7:${last}7`).values = [spec.headers];
  sheet.getRange(`A7:${last}7`).format = {
    fill: "#17324D", font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center", verticalAlignment: "center", rowHeight: 35, wrapText: true,
    borders: { insideVertical: { style: "thin", color: "#FFFFFF" } },
  };
  const body = sheet.getRange(`A8:${last}${end}`);
  body.values = spec.rows;
  body.format.wrapText = true;
  body.format.verticalAlignment = "center";
  for (const [i, width] of spec.widths.entries()) {
    sheet.getRange(`${col(i)}1:${col(i)}${end}`).format.columnWidth = width;
  }
  for (const [i, values] of spec.rows.entries()) {
    const row = sheet.getRange(`A${i + 8}:${last}${i + 8}`);
    row.format.rowHeight = Math.max(29, ...values.map((value, c) =>
      Math.ceil(String(value ?? "").length / Math.max(8, spec.widths[c] - 6)) * 15 + 12));
  }
  const nativeTable = sheet.tables.add(`A7:${last}${end}`, true, `O2Trace${index + 1}`);
  nativeTable.style = "TableStyleLight9";
  nativeTable.showFilterButton = true;
  sheet.freezePanes.freezeRows(7);
  if (spec.headers.length > 6) sheet.freezePanes.freezeColumns(2);
  if (index === 0 || index === 18) sheet.tabColor = "#17324D";
  manifest.push({ sheet: spec.name, rows: spec.rows.length, last_row: end, last_column: last });
}
workbook.recalculate();
const inspection = await workbook.inspect({ kind: "workbook,sheet,table", maxChars: 7000, tableMaxRows: 3, tableMaxCols: 4 });
await fs.writeFile(path.join(workspace, "inspection.ndjson"), inspection.ndjson);
const errors = await workbook.inspect({
  kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 30 }, maxChars: 3000,
});
await fs.writeFile(path.join(workspace, "errors.ndjson"), errors.ndjson);
await fs.writeFile(path.join(workspace, "expected-tables.json"), JSON.stringify(specs.map(s => ({ sheet: s.name, headers: s.headers, rows: s.rows })), null, 2));
await fs.writeFile(path.join(workspace, "build-manifest.json"), JSON.stringify({ sheets: manifest }, null, 2));
const previews = [];
for (const item of manifest) {
  for (let start = 1; start <= item.last_row; start += 14) {
    const range = `A${start}:${item.last_column}${Math.min(start + 13, item.last_row)}`;
    const file = `${item.sheet}-${String(start).padStart(3, "0")}.png`;
    const blob = await workbook.render({ sheetName: item.sheet, range, scale: 1.15, format: "png" });
    await fs.writeFile(path.join(workspace, file), new Uint8Array(await blob.arrayBuffer()));
    previews.push({ sheet: item.sheet, range, file });
  }
}
await fs.writeFile(path.join(workspace, "render-manifest.json"), JSON.stringify(previews, null, 2));
const target = path.join(root, "outputs/wave-o2-20261109/P&Pmis_Wave_O2_Master_Architecture_Traceability.xlsx");
await fs.mkdir(path.dirname(target), { recursive: true });
await (await SpreadsheetFile.exportXlsx(workbook)).save(target);
try { await fs.rename(target + ".inspect.ndjson", path.join(workspace, "export-inspection.ndjson")); }
catch (error) { if (error.code !== "ENOENT") throw error; }
console.log(JSON.stringify({ sheets: specs.length, rows: manifest.reduce((sum, row) => sum + row.rows, 0), previews: previews.length, output: target }));
