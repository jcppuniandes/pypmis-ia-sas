import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import { createHash } from "node:crypto";

const root = path.resolve(import.meta.dirname, "../..");
const qa = path.join(root, "outputs/.qa/wave-o3b-20261119/microclose");
const runtime = createRequire(path.join(root, "outputs/.qa/wave-o3b-20261119/artifact-entry.mjs"));
const { FileBlob, SpreadsheetFile } = await import(pathToFileURL(runtime.resolve("@oai/artifact-tool")).href);
const marker = "WAVE_O3A_CONSTRUCTION_FIELD_OPERATIONS_FOUNDATION_RELEASE_VALIDATED";
const source = path.join(root, "outputs/wave-o3a-construction-field-operations-20261119/P&Pmis_Wave_O3A_Construction_Field_Operations_Traceability.xlsx");
const target = path.join(root, "outputs/wave-o3a-documentary-closeout-20261119/P&Pmis_Wave_O3A_Construction_Field_Operations_Traceability_Documentary_Closeout.xlsx");
await fs.mkdir(qa, { recursive: true });
const original = await fs.readFile(source);
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(source));
const originalData = new Map();
for (let i = 0; i < 19; i++) {
  const sheet = workbook.worksheets.getItemAt(i);
  originalData.set(sheet.name, sheet.getRange("A1:H80").values);
}
for (const name of ["00_README", "18_RELEASE_CRITERIA"]) {
  const preview = await workbook.render({ sheetName: name, range: name === "00_README" ? "A1:C10" : "A1:D11", scale: 1, format: "png" });
  await fs.writeFile(path.join(qa, `${name}-before.png`), new Uint8Array(await preview.arrayBuffer()));
}
if (!process.argv.includes("--apply")) {
  console.log((await workbook.inspect({ kind: "sheet,table", maxChars: 2000, tableMaxRows: 2 })).ndjson);
  process.exit(0);
}
await fs.access(target).then(() => { throw new Error("Preserve existing documentary cut"); }, () => {});
workbook.worksheets.getItem("00_README").tables.items[0].rows.add(null, [
  ["Cierre técnico explícito", "Marcador documental del mismo corte histórico", marker],
  ["Deuda conservada", "Pendientes S3 no bloqueantes que permanecen abiertos", "O3A-S3-UI01 y O3A-S3-01 ABIERTO"],
]);
workbook.worksheets.getItem("18_RELEASE_CRITERIA").tables.items[0].rows.add(null, [
  ["Cierre técnico explícito", "Controles del corte histórico aprobados", "VALIDATED", marker],
  ["Deuda O3A", "No se declaran resueltos UI01 ni 01", "ABIERTO S3", "O3A-S3-UI01 y O3A-S3-01"],
]);
for (const [name, range] of [["00_README", "A11:C12"], ["18_RELEASE_CRITERIA", "A12:D13"]]) {
  const rows = workbook.worksheets.getItem(name).getRange(range);
  rows.format.wrapText = true;
  rows.format.autofitRows();
}
workbook.recalculate();
for (let i = 0; i < 19; i++) {
  const sheet = workbook.worksheets.getItemAt(i);
  const rows = sheet.getRange("A1:H80").values;
  const before = originalData.get(sheet.name);
  for (let r = 0; r < before.length; r++) for (let c = 0; c < 8; c++) {
    if (before[r]?.[c] !== null && before[r]?.[c] !== undefined && before[r]?.[c] !== "") assert.deepEqual(rows[r][c], before[r][c]);
  }
}
for (const [name, range] of [["00_README", "A1:C12"], ["18_RELEASE_CRITERIA", "A1:D13"]]) {
  const preview = await workbook.render({ sheetName: name, range, scale: 1, format: "png" });
  await fs.writeFile(path.join(qa, `${name}-after.png`), new Uint8Array(await preview.arrayBuffer()));
}
await (await SpreadsheetFile.exportXlsx(workbook)).save(target);
assert.deepEqual(await fs.readFile(source), original);
await fs.writeFile(path.join(qa, "matrix-proof.json"), JSON.stringify({ original_preserved: true, historical_values_unchanged: true, sheets: 19, changed_sheets: ["00_README", "18_RELEASE_CRITERIA"], release_marker: marker, original_sha256: createHash("sha256").update(original).digest("hex") }, null, 2));
console.log("Documentary matrix appended; historical values retained");
