import fs from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

const repo = path.resolve(import.meta.dirname, "../..");
const qa = path.join(repo, "outputs/.qa/wave-o2b-close-20261111/artifacts");
const moduleRoot = process.env.PYPMIS_CLOSE_ARTIFACT_RUNTIME || qa;
const require = createRequire(path.join(moduleRoot, "artifact-entry.mjs"));
const { FileBlob, SpreadsheetFile } = await import(pathToFileURL(require.resolve("@oai/artifact-tool")).href);
const filename = "P&Pmis_Wave_O2B_Procurement_Materials_Logistics_Traceability.xlsx";
const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(path.join(qa, "baseline", filename)));
const edit = process.argv[2] === "edit";
const previews = path.join(qa, edit ? "matrix-final" : "matrix-baseline");
await fs.mkdir(previews, { recursive: true });
const views = [
  ["00_README", "A6:B12"], ["01_REQUIREMENTS", "E32:J36"], ["01_REQUIREMENTS", "G48:J54"],
  ["08_INTEGRATIONS", "A7:C15"], ["12_COST_TRACEABILITY", "A7:C11"],
  ["14_TESTS", "A7:D14"], ["15_DEFECTS", "A7:C9"], ["16_RELEASE_CRITERIA", "A7:C14"],
];
if (edit) {
  const { patch, controls } = JSON.parse(await fs.readFile(path.join(qa, "matrix-edits.json"), "utf8"));
  for (const [name, values] of Object.entries(patch)) {
    const sheet = wb.worksheets.getItem(name);
    for (const [cell, value] of Object.entries(values)) sheet.getRange(cell).values = [[value]];
  }
  const defects = wb.worksheets.getItem("15_DEFECTS");
  defects.getRange("C8:C9").conditionalFormats.addCustom('C8="OPEN"', { fill: "#FFF0CE", font: { color: "#724700" } });
  const release = wb.worksheets.getItem("16_RELEASE_CRITERIA");
  const end = 7 + controls.length;
  const title = release.getRange("E2");
  title.values = [["Controles de cierre O2B"]];
  title.format.font = { name: "Arial", size: 14, bold: true, color: "#172E45" };
  const widths = [23, 40, 39, 40, 50, 17, 13, 59];
  for (let i = 0; i < widths.length; i++) {
    const col = String.fromCharCode(69 + i);
    release.getRange(`${col}1:${col}${end}`).format.columnWidth = widths[i];
  }
  const area = release.getRange(`E8:L${end}`);
  area.values = controls;
  area.format.font = { name: "Arial", size: 10, color: "#243746" };
  area.format.wrapText = true;
  area.format.verticalAlignment = "center";
  for (const [i, row] of controls.entries()) {
    release.getRange(`E${i + 8}:L${i + 8}`).format.rowHeight = Math.max(
      i === 3 ? 65 : 34,
      ...row.map((cell, j) => Math.ceil(cell.length / Math.max(8, widths[j] - 6)) * 14 + 10)
    );
  }
  const header = release.getRange("E7:L7");
  header.values = [["ID", "Requisito", "Implementación", "Prueba", "Evidencia", "Resultado", "Estado", "Observación"]];
  header.format = {
    fill: "#17324D", font: { name: "Arial", size: 10, color: "#FFFFFF", bold: true },
    horizontalAlignment: "center", verticalAlignment: "center", wrapText: true,
    borders: { insideVertical: { style: "thin", color: "#FFFFFF" } },
  };
  const table = release.tables.add(`E7:L${end}`, true, "O2BCloseControls");
  table.style = "TableStyleLight9";
  table.showFilterButton = true;
  release.getRange(`K8:K${end}`).conditionalFormats.addCustom('K8="OPEN"', { fill: "#FFF0CE", font: { color: "#724700" } });
  wb.recalculate();
  const summary = await wb.inspect({ kind: "region", sheetId: "16_RELEASE_CRITERIA", range: `E7:L${end}`, maxChars: 7500 });
  await fs.writeFile(path.join(previews, "inspection.ndjson"), summary.ndjson);
  const errors = await wb.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true } });
  await fs.writeFile(path.join(previews, "formula-scan.ndjson"), errors.ndjson);
  const candidate = path.join(qa, "candidate");
  await fs.mkdir(candidate, { recursive: true });
  await (await SpreadsheetFile.exportXlsx(wb)).save(path.join(candidate, filename));
  for (const [start, stop] of [[7, 14], [15, end]]) {
    views.push(["16_RELEASE_CRITERIA", `E${start}:H${stop}`], ["16_RELEASE_CRITERIA", `I${start}:L${stop}`]);
  }
}
for (const [idx, [sheetName, range]] of views.entries()) {
  const picture = await wb.render({ sheetName, range, scale: 1.05, format: "png" });
  await fs.writeFile(path.join(previews, `${idx + 1}-${sheetName}.png`), new Uint8Array(await picture.arrayBuffer()));
}
console.log(`${views.length} rangos revisables en ${previews}`);
