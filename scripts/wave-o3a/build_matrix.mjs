import assert from "node:assert/strict";
import fs from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { pathToFileURL } from "node:url";

const qa = path.resolve(import.meta.dirname, "../../outputs/.qa/wave-o3a-20261118");
const out = path.resolve(import.meta.dirname, "../../outputs/wave-o3a-construction-field-operations-20261119");
const runtime = createRequire(path.join(qa, "artifact-entry.mjs"));
const { FileBlob, SpreadsheetFile, Workbook } = await import(pathToFileURL(runtime.resolve("@oai/artifact-tool")).href);
const data = JSON.parse(await fs.readFile(path.join(qa, "matrix-data.json"), "utf8"));
const workbook = Workbook.create();
assert.equal(Object.keys(data).length, 19);
await fs.mkdir(path.join(qa, "matrix-render"), { recursive: true });
for (const [name, { title, headers, rows }] of Object.entries(data)) {
  const sheet = workbook.worksheets.add(name);
  sheet.showGridLines = false;
  const lastCol = String.fromCharCode(64 + headers.length);
  const lastRow = rows.length + 4;
  sheet.getRange(`A1:${lastCol}${lastRow}`).format.font = { name: "Arial", size: 11, color: "#172E42" };
  sheet.getRange("A2").values = [[title]];
  sheet.getRange("A2").format.font = { name: "Arial", size: 16, bold: true, color: "#000000" };
  sheet.getRange("A2").format.rowHeight = 32;
  sheet.getRange("A3").values = [["P&Pmis Construction AI O3A"]];
  sheet.getRange(`A4:${lastCol}4`).values = [headers];
  sheet.getRange(`A5:${lastCol}${lastRow}`).values = rows;
  const table = sheet.tables.add(`A4:${lastCol}${lastRow}`, true, `O3A_${name.slice(0, 2)}`);
  table.style = "TableStyleMedium2";
  sheet.getRange(`A4:${lastCol}4`).format.font = { name: "Arial", size: 11, bold: true, color: "#FFFFFF" };
  for (let c = 0; c < headers.length; c++) {
    const col = String.fromCharCode(65 + c);
    sheet.getRange(`${col}:${col}`).format.columnWidth = name === "15_TESTS" ? (c ? 13 : 40) : (c === 0 ? 28 : 44);
  }
  sheet.getRange(`A4:${lastCol}${lastRow}`).format.verticalAlignment = "center";
  sheet.getRange(`A4:${lastCol}4`).format.horizontalAlignment = "center";
  sheet.getRange(`A5:${lastCol}${lastRow}`).format.wrapText = true;
  sheet.getRange(`A5:${lastCol}${lastRow}`).format.autofitRows();
  if (rows.length > 8) sheet.freezePanes.freezeRows(4);
}
workbook.recalculate();
const scan = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#SPILL!", options: { useRegex: true, maxResults: 30 } });
await fs.writeFile(path.join(qa, "matrix-inspection.ndjson"), scan.ndjson);
for (const [name, { headers, rows }] of Object.entries(data)) {
  const image = await workbook.render({ sheetName: name, range: `A1:${String.fromCharCode(64 + headers.length)}${4 + rows.length}`, scale: 1, format: "png" });
  await fs.writeFile(path.join(qa, "matrix-render", name + ".png"), new Uint8Array(await image.arrayBuffer()));
}
const target = path.join(out, "P&Pmis_Wave_O3A_Construction_Field_Operations_Traceability.xlsx");
await (await SpreadsheetFile.exportXlsx(workbook)).save(target);
const saved = await SpreadsheetFile.importXlsx(await FileBlob.load(target));
for (const [name, { headers, rows }] of Object.entries(data)) {
  assert.deepEqual(saved.worksheets.getItem(name).getRange(`A5:${String.fromCharCode(64 + headers.length)}${rows.length + 4}`).values, rows);
}
console.log("Verified 19 sheets and saved XLSX");
