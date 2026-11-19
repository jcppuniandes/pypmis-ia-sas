import assert from "node:assert/strict";
import fs from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { pathToFileURL } from "node:url";

const qa = path.resolve(import.meta.dirname, "../../outputs/.qa/wave-o2c-20261118");
const candidate = path.join(qa, "final-candidate");
const renderDir = path.join(qa, "final-matrix-render");
const runtime = createRequire(path.join(qa, "artifact-entry.mjs"));
const { FileBlob, SpreadsheetFile, Workbook } = await import(pathToFileURL(runtime.resolve("@oai/artifact-tool")).href);
const data = JSON.parse(await fs.readFile(path.join(candidate, "matrix-data.json"), "utf8"));
const workbook = Workbook.create();
await fs.mkdir(renderDir, { recursive: true });
assert.equal(Object.keys(data).length, 17);
for (const [name, [title, rows]] of Object.entries(data)) {
  const sheet = workbook.worksheets.add(name);
  sheet.showGridLines = false;
  const last = 4 + rows.length;
  sheet.getRange("A2").values = [[`O2C ${title}`]];
  const banner = sheet.getRange("A2:C2");
  banner.format.font.color = "#122D43";
  banner.format.font.bold = true;
  banner.format.font.size = 16;
  banner.format.rowHeight = 36;
  sheet.getRange("A3").values = [["P&Pmis Construction AI"]];
  sheet.getRange("A3:C3").format.font.color = "#445B6A";
  sheet.getRange("A4:C4").values = [["Control", "Alcance / evidencia", "Resultado / frontera"]];
  sheet.getRange(`A5:C${last}`).values = rows;
  const table = sheet.tables.add(`A4:C${last}`, true, `T_O2C_${name.slice(0, 2)}`);
  table.style = "TableStyleMedium2";
  sheet.getRange("A:A").format.columnWidth = 28;
  sheet.getRange("B:B").format.columnWidth = 62;
  sheet.getRange("C:C").format.columnWidth = 56;
  sheet.getRange(`A5:C${last}`).format.wrapText = true;
  sheet.getRange(`A5:C${last}`).format.autofitRows();
  sheet.getRange(`A5:C${last}`).format.verticalAlignment = "center";
  if (rows.length > 10) sheet.freezePanes.freezeRows(4);
}
workbook.recalculate();
const errorCheck = await workbook.inspect({
  kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#SPILL!",
  options: { useRegex: true, maxResults: 30 }, summary: "O2C final error scan",
});
await fs.writeFile(path.join(qa, "matrix-error-scan.ndjson"), errorCheck.ndjson);
for (const [name, [, rows]] of Object.entries(data)) {
  if (process.argv.includes("--changed-only") && !["11_PROGRESS_TRACEABILITY", "12_SCHEDULE_TRACEABILITY", "14_TESTS"].includes(name)) continue;
  const last = 4 + rows.length;
  const rendered = await workbook.render({ sheetName: name, range: `A1:C${last}`, scale: 0.85, format: "png" });
  await fs.writeFile(path.join(renderDir, name + ".png"), new Uint8Array(await rendered.arrayBuffer()));
}
const target = path.join(candidate, "P&Pmis_Wave_O2C_Contracts_Commitments_Traceability.xlsx");
await (await SpreadsheetFile.exportXlsx(workbook)).save(target);
const verified = await SpreadsheetFile.importXlsx(await FileBlob.load(target));
for (const [name, [, rows]] of Object.entries(data)) {
  assert.deepEqual(verified.worksheets.getItem(name).getRange(`A5:C${4 + rows.length}`).values, rows);
}
console.log(`Verified ${Object.keys(data).length} sheets`);
