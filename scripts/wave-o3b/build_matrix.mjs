import assert from "node:assert/strict";
import fs from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { pathToFileURL } from "node:url";

const qa = path.resolve(import.meta.dirname, "../../outputs/.qa/wave-o3b-20261119");
const out = path.resolve(import.meta.dirname, "../../outputs/wave-o3b-quality-management-inspection-20261122");
const runtime = createRequire(path.join(qa, "artifact-20261122/artifact-entry.mjs"));
const { FileBlob, SpreadsheetFile, Workbook } = await import(pathToFileURL(runtime.resolve("@oai/artifact-tool")).href);
const data = JSON.parse(await fs.readFile(path.join(qa, "matrix-data.json"), "utf8"));
const renderName = process.argv[2] || "matrix-render";
assert.match(renderName, /^[A-Za-z0-9-]+$/);
const renderDirectory = path.join(qa, renderName);
const workbook = Workbook.create();
assert.equal(Object.keys(data).length, 20);
await fs.mkdir(renderDirectory, { recursive: true });
for (const [name, { title, headers, rows }] of Object.entries(data)) {
  const sheet = workbook.worksheets.add(name);
  sheet.showGridLines = false;
  const lastCol = String.fromCharCode(64 + headers.length);
  const lastRow = rows.length + 4;
  sheet.getRange(`A1:${lastCol}${lastRow}`).format.font = { name: "Arial", size: 11, color: "#172E42" };
  sheet.getRange("A2").values = [[title]];
  sheet.getRange("A2").format.font = { name: "Arial", size: 16, bold: true, color: "#000000" };
  sheet.getRange("A2").format.rowHeight = 32;
  sheet.getRange("A3").values = [["P&Pmis Construction AI   Corte 22 de noviembre de 2026"]];
  sheet.getRange(`A4:${lastCol}4`).values = [headers];
  sheet.getRange(`A5:${lastCol}${lastRow}`).values = rows;
  const table = sheet.tables.add(`A4:${lastCol}${lastRow}`, true, `O3B_${name.slice(0, 2)}`);
  table.style = "TableStyleMedium2";
  sheet.getRange(`A4:${lastCol}4`).format.font = { name: "Arial", size: 11, bold: true, color: "#FFFFFF" };
  for (let c = 0; c < headers.length; c++) {
    const col = String.fromCharCode(65 + c);
    const widths = name === "01_REQUIREMENTS" ? [14, 36, 42, 52, 38, 28] : name === "03_DOMAIN_MODEL" ? [30, 34, 68, 34, 42] : null;
    sheet.getRange(`${col}:${col}`).format.columnWidth = widths ? widths[c] : name === "16_TESTS" ? (c ? 13 : 45) : (c === 0 ? 29 : 47);
  }
  sheet.getRange(`A4:${lastCol}${lastRow}`).format.verticalAlignment = "center";
  sheet.getRange(`A4:${lastCol}4`).format.horizontalAlignment = "center";
  sheet.getRange(`A5:${lastCol}${lastRow}`).format.wrapText = true;
  sheet.getRange(`A5:${lastCol}${lastRow}`).format.autofitRows();
  sheet.getRange(`A4:${lastCol}4`).format.autofitRows();
  for (let r = 4; r <= lastRow; r++) {
    const row = sheet.getRange(`A${r}:${lastCol}${r}`);
    const height = row.format.rowHeightPx;
    assert.equal(typeof height, "number");
    row.format.rowHeightPx = Math.max(24, height + 6);
  }
  if (rows.length > 8) sheet.freezePanes.freezeRows(4);
  if (headers.length > 4) sheet.freezePanes.freezeColumns(1);
}
workbook.recalculate();
const scan = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#SPILL!", options: { useRegex: true, maxResults: 30 } });
await fs.writeFile(path.join(qa, "matrix-inspection.ndjson"), scan.ndjson);
for (const [name, { headers, rows }] of Object.entries(data)) {
  const preview = await workbook.render({ sheetName: name, range: `A1:${String.fromCharCode(64 + headers.length)}${5 + rows.length}`, scale: 1, format: "png" });
  await fs.writeFile(path.join(renderDirectory, name + ".png"), new Uint8Array(await preview.arrayBuffer()));
}
await fs.mkdir(out, { recursive: true });
const target = path.join(out, "P&Pmis_Wave_O3B_Quality_Management_Inspection_Traceability.xlsx");
await (await SpreadsheetFile.exportXlsx(workbook)).save(target);
const saved = await SpreadsheetFile.importXlsx(await FileBlob.load(target));
for (const [name, { headers, rows }] of Object.entries(data)) {
  assert.deepEqual(saved.worksheets.getItem(name).getRange(`A5:${String.fromCharCode(64 + headers.length)}${rows.length + 4}`).values, rows);
}
await fs.writeFile(path.join(renderDirectory, "export-proof.json"), JSON.stringify({status:"PASS", sheets:20, exported:true, reimported_values_equal:true, recalculated:true, rendered_sheets:Object.keys(data)}, null, 2));
console.log("Verified twenty sheets and saved XLSX");
