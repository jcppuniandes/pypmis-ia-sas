import fs from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import { createHash } from "node:crypto";

const root = path.resolve(import.meta.dirname, "../..");
const qa = path.join(root, "outputs/.qa/wave-o2b");
const require = createRequire(path.join(qa, "runtime-entry.mjs"));
const { Workbook, SpreadsheetFile } = await import(pathToFileURL(require.resolve("@oai/artifact-tool")).href);
const data = path.join(qa, "traceability-data.json");
const specs = JSON.parse(await fs.readFile(data, "utf8"));
const workbook = Workbook.create();
const previewDir = path.resolve(qa, process.env.O2B_WORKBOOK_PREVIEW || "workbook");
if (!previewDir.startsWith(qa + path.sep)) throw Error("Expected private O2B QA folder");
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
  sheet.getRange("A4").values = [["Wave O2B   P&Pmis Construction AI   11 noviembre 2026"]];
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
    sheet.getRange(`A${i + 8}:${last}${i + 8}`).format.rowHeight = Math.max(27, ...values.map((value, c) =>
      Math.ceil(String(value ?? "").length / Math.max(8, spec.widths[c] - 7)) * 15 + 11));
  }
  const table = sheet.tables.add(`A7:${last}${end}`, true, `O2BTrace${index + 1}`);
  table.style = "TableStyleLight9";
  table.showFilterButton = true;
  if (spec.rows.length > 12) sheet.freezePanes.freezeRows(7);
  if (index === 0) sheet.tabColor = "#536878";
  if (index === 1 || index === 16) sheet.tabColor = "#17324D";
  const statusIndex = spec.headers.indexOf("Estado");
  if (statusIndex >= 0) {
    const s = col(statusIndex);
    const statuses = sheet.getRange(`${s}8:${s}${end}`);
    statuses.conditionalFormats.addCustom(`OR(${s}8="Pendiente",${s}8="Parcial")`,
      { fill: "#FFF0CE", font: { color: "#724700" } });
  }
  for (let start = 1; start <= end; start += 14) {
    const stop = Math.min(start + 13, end);
    const ranges = last === "J" ? [`A${start}:E${stop}`, `F${start}:J${stop}`] : [`A${start}:${last}${stop}`];
    for (const [j, range] of ranges.entries()) {
      previews.push({ sheet: spec.name, range, file: `${spec.name}-${String(start).padStart(3, "0")}-${j + 1}.png` });
    }
  }
}
workbook.recalculate();
const summary = await workbook.inspect({ kind: "workbook,sheet,table", maxChars: 7000, tableMaxRows: 3, tableMaxCols: 4 });
await fs.writeFile(path.join(previewDir, "inspection.ndjson"), summary.ndjson);
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 300 },
});
await fs.writeFile(path.join(previewDir, "formula-scan.ndjson"), errors.ndjson);
for (const { sheet, range, file } of previews) {
  const blob = await workbook.render({ sheetName: sheet, range, scale: 1.1, format: "png" });
  await fs.writeFile(path.join(previewDir, file), new Uint8Array(await blob.arrayBuffer()));
}
const target = path.join(root, "outputs/wave-o2b/P&Pmis_Wave_O2B_Procurement_Materials_Logistics_Traceability.xlsx");
await fs.mkdir(path.dirname(target), { recursive: true });
await (await SpreadsheetFile.exportXlsx(workbook)).save(target);
const digest = async (file) => createHash("sha256").update(await fs.readFile(file)).digest("hex");
await fs.writeFile(path.join(previewDir, "render-provenance.json"), JSON.stringify({
  workbook_sha256: await digest(target),
  traceability_data_sha256: await digest(data),
  images: Object.fromEntries(await Promise.all(previews.map(async ({ file }) => [file, await digest(path.join(previewDir, file))]))),
  previews,
}, null, 2));
console.log(`${specs.length} hojas; ${previews.length} rangos renderizados`);
