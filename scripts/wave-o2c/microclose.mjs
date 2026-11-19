import assert from "node:assert/strict";
import fs from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { pathToFileURL } from "node:url";

const root = path.resolve(import.meta.dirname, "../..");
const qa = path.join(root, "outputs/.qa/wave-o2c-20261113");
const runtime = createRequire(path.join(qa, "artifact-entry.mjs"));
const { FileBlob, SpreadsheetFile } = await import(pathToFileURL(runtime.resolve("@oai/artifact-tool")).href);
const name = "P&Pmis_Wave_O2B_Procurement_Materials_Logistics_Traceability1.xlsx";
const source = path.join(root, "outputs/wave-o2b", name);
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(source));
const decision = "WAVE_O2B_PROCUREMENT_MATERIALS_LOGISTICS_FOUNDATION_RELEASE_VALIDATED";
const ready = "READY_FOR_WAVE_O2C_CONTRACTS_COMMITMENTS_FOUNDATION";
const statuses = "O2B-G01 = CLOSED. O2B-G02 = CLOSED.";
const edits = {
  "00_README": { B8: `${decision}\n${statuses}\n${ready}`, B9: "Corte O2B.CLOSE-2 del 12 de noviembre de 2026. Evidencia final-a." },
  "01_REQUIREMENTS": {
    H52: "CLOSE-2 final-a: regresión, consumidores y Chromium acreditados.", I52: "Verificado",
    J52: "Migración histórica conservada como antecedente; las regresiones y Chromium tienen JUnit de cierre.",
    H57: statuses, I57: "Verificado", J57: "Cerraron los cuatro controles S2 y no quedaron S1/S2 abiertos.",
    H58: decision, I58: "Verificado", J58: ready,
    H59: "O2B.CLOSE-2 validado el 12 de noviembre de 2026.", I59: "Verificado",
    J59: "Habilita la preparación técnica de O2C. No implica despliegue.",
  },
  "16_RELEASE_CRITERIA": { B13: statuses, B14: `${decision}\n${ready}` },
};
const edit = process.argv[2] === "edit";
const previews = path.join(qa, edit ? "microclose-final" : "microclose-baseline");
await fs.mkdir(previews, { recursive: true });
if (edit) {
  for (const [sheet, values] of Object.entries(edits)) {
    for (const [cell, value] of Object.entries(values)) workbook.worksheets.getItem(sheet).getRange(cell).values = [[value]];
  }
  const summary = workbook.worksheets.getItem("00_README").getRange("B8");
  summary.format.wrapText = true;
  summary.format.rowHeight = 56;
  const checks = workbook.worksheets.getItem("01_REQUIREMENTS");
  for (const row of [52, 57, 58, 59]) {
    const range = checks.getRange(`H${row}:J${row}`);
    range.format.wrapText = true;
    if (range.format.rowHeight < 46) range.format.rowHeight = 46;
  }
  workbook.recalculate();
  const output = path.join(qa, "microclose-candidate");
  await fs.mkdir(output, { recursive: true });
  await (await SpreadsheetFile.exportXlsx(workbook)).save(path.join(output, name));
  await fs.writeFile(path.join(qa, "microclose-matrix-edits.json"), JSON.stringify(edits));
  assert.equal(workbook.worksheets.getItem("15_DEFECTS").getRange("C8:C9").values.flat().join(","), "CLOSED,CLOSED");
}
for (const [i, [sheetName, range]] of [
  ["00_README", "A7:B12"], ["01_REQUIREMENTS", "G50:J59"], ["16_RELEASE_CRITERIA", "A11:C14"],
].entries()) {
  const png = await workbook.render({ sheetName, range, scale: 1.05, format: "png" });
  await fs.writeFile(path.join(previews, `${i + 1}.png`), new Uint8Array(await png.arrayBuffer()));
}
