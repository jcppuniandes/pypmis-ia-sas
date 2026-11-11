import fs from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import { createHash } from "node:crypto";

const root = path.resolve(import.meta.dirname, "../..");
const qa = path.join(root, "outputs/.qa/wave-o2a-20261109");
const require = createRequire(path.join(qa, "runtime-entry.mjs"));
const { Workbook, SpreadsheetFile } = await import(pathToFileURL(require.resolve("@oai/artifact-tool")).href);
const specs = JSON.parse(await fs.readFile(path.join(qa, "traceability-data.json"), "utf8"));
const workbook = Workbook.create();
const previewDir = path.join(qa, "workbook");
await fs.mkdir(previewDir, { recursive: true });
const previews = [];
const col = (i) => String.fromCharCode(65 + i);
for (const [index, spec] of specs.entries()) {
  const sheet = workbook.worksheets.add(spec.name);
  const last = col(spec.headers.length - 1);
  const end = spec.rows.length + 7;
  const canvas = sheet.getRange(`A1:${last}${end}`);
  canvas.format.font = { name: "Arial", size: 10, color: "#243746" };
  canvas.format.rowHeight = 22;
  sheet.showGridLines = false;
  sheet.getRange("A2").values = [[spec.title]];
  sheet.getRange("A2").format.font = { name: "Arial", size: 14, bold: true, color: "#172E45" };
  sheet.getRange(`A3:${last}3`).format.borders = { bottom: { style: "thin", color: "#17324D" } };
  sheet.getRange("A4").values = [["Wave O2A   P&Pmis Construction AI   10 noviembre 2026"]];
  sheet.getRange("A4").format.font = { name: "Arial", size: 10, italic: true, color: "#536878" };
  sheet.getRange(`A7:${last}7`).values = [spec.headers];
  sheet.getRange(`A7:${last}7`).format = {
    fill: "#17324D", font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center", verticalAlignment: "center", rowHeight: 34, wrapText: true,
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
    sheet.getRange(`A${i + 8}:${last}${i + 8}`).format.rowHeight = Math.max(29, ...values.map((value, c) =>
      Math.ceil(String(value ?? "").length / Math.max(8, spec.widths[c] - 6)) * 15 + 12));
  }
  const table = sheet.tables.add(`A7:${last}${end}`, true, `O2ATrace${index + 1}`);
  table.style = "TableStyleLight9";
  table.showFilterButton = true;
  sheet.freezePanes.freezeRows(7);
  if (index === 0 || index === 14) sheet.tabColor = "#17324D";
  if (spec.headers.at(-1) === "Resultado") {
    const statuses = sheet.getRange(`${last}8:${last}${end}`);
    statuses.conditionalFormats.addCustom(`OR(${last}8="FAIL",${last}8="STALE")`, { fill: "#FEE4E2", font: { bold: true, color: "#912018" } });
    statuses.conditionalFormats.addCustom(`${last}8="PENDING"`, { fill: "#FFF0CE", font: { color: "#724700" } });
  }
  for (let start = 1; start <= end; start += 14) {
    const range = `A${start}:${last}${Math.min(start + 13, end)}`;
    previews.push({ sheet: spec.name, range, file: `${spec.name}-${String(start).padStart(3, "0")}.png` });
  }
}
workbook.recalculate();
const summary = await workbook.inspect({ kind: "workbook,sheet,table", maxChars: 6500, tableMaxRows: 3, tableMaxCols: 4 });
await fs.writeFile(path.join(previewDir, "inspection.ndjson"), summary.ndjson);
for (const { sheet, range, file } of previews) {
  const blob = await workbook.render({ sheetName: sheet, range, scale: 1.1, format: "png" });
  await fs.writeFile(path.join(previewDir, file), new Uint8Array(await blob.arrayBuffer()));
}
await fs.writeFile(path.join(previewDir, "render-manifest.json"), JSON.stringify(previews, null, 2));
const target = path.join(root, "outputs/wave-o2a-20261109/P&Pmis_Wave_O2A_Engineering_Foundation_Traceability.xlsx");
await fs.mkdir(path.dirname(target), { recursive: true });
await (await SpreadsheetFile.exportXlsx(workbook)).save(target);
const digest = async (file) => createHash("sha256").update(await fs.readFile(file)).digest("hex");
const imageHashes = {};
for (const { file } of previews) imageHashes[file] = await digest(path.join(previewDir, file));
await fs.writeFile(path.join(previewDir, "render-provenance.json"), JSON.stringify({
  workbook_sha256: await digest(target),
  traceability_data_sha256: await digest(path.join(qa, "traceability-data.json")),
  images: imageHashes,
}, null, 2));
try { await fs.rename(target + ".inspect.ndjson", path.join(previewDir, "export-inspection.ndjson")); }
catch (error) { if (error.code !== "ENOENT") throw error; }
console.log(JSON.stringify({ sheets: specs.length, rows: specs.reduce((sum, spec) => sum + spec.rows.length, 0), previews: previews.length, output: target }));
