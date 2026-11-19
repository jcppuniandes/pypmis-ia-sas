import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { pathToFileURL } from "node:url";

const repo = path.resolve(import.meta.dirname, "../..");
const qa = path.join(repo, "outputs/.qa/wave-o2b-close2-20261112");
const artifacts = path.join(qa, "artifacts");
const moduleRoot = process.env.PYPMIS_CLOSE_ARTIFACT_RUNTIME || artifacts;
const require = createRequire(path.join(moduleRoot, "artifact-entry.mjs"));
const { FileBlob, SpreadsheetFile } = await import(pathToFileURL(require.resolve("@oai/artifact-tool")).href);

const baseName = "P&Pmis_Wave_O2B_Procurement_Materials_Logistics_Traceability.xlsx";
const outputName = baseName.replace(/\.xlsx$/, "1.xlsx");
const source = path.join(repo, "outputs/wave-o2b", baseName);
const expectedBase = "2353b74947627d13ffd93b51b1671ff58fd66a5c808715303c00f19a75aecb23";
const digest = async file => createHash("sha256").update(await fs.readFile(file)).digest("hex");
assert.equal(await digest(source), expectedBase, "Unexpected baseline workbook; do not overwrite newer work");

const [, , mode, attempt = "final-a"] = process.argv;
assert(["inspect", "edit"].includes(mode) && /^[a-z0-9][a-z0-9-]{0,31}$/.test(attempt));
const views = [
  ["00_README", "A7:B12", "readme"],
  ["01_REQUIREMENTS", "G48:J54", "requirements"],
  ["14_TESTS", "A10:D14", "tests"],
  ["15_DEFECTS", "A7:C9", "defects"],
  ["16_RELEASE_CRITERIA", "A7:C14", "release"],
  ["16_RELEASE_CRITERIA", "E7:H14", "criteria-1"],
  ["16_RELEASE_CRITERIA", "I7:L14", "outcomes-1"],
  ["16_RELEASE_CRITERIA", "E15:H23", "criteria-2"],
  ["16_RELEASE_CRITERIA", "I15:L23", "outcomes-2"],
];
const release = "16_RELEASE_CRITERIA";
const previews = path.join(artifacts, mode === "edit" ? `matrix-final-${attempt}` : "matrix-baseline");
await fs.mkdir(previews, { recursive: true });
const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(source));

const mandatory = {
  "CLOSE-PG-O1": {
    requirement: "Regresión operacional O1 completa en PostgreSQL",
    implementation: "Catálogo operacional y contrato Gate06D",
    test: "Suite O1 completa sin exclusiones",
  },
  "CLOSE-PROG-LINEAGE": {
    requirement: "Conservar historial y rechazar la readopción de evidencia sustituida",
    implementation: "Linaje de fuente y bitácora de Progress",
    test: "test_procurement_close2_progress.py",
  },
  "CLOSE-FCST-SOURCES": {
    requirement: "Adoptar dos pronósticos nativos y rechazar sus referencias obsoletas",
    implementation: "Hito de fabricación y observación de despacho",
    test: "test_procurement_close2_forecast.py",
  },
  "CLOSE-AUTH-WRITE": {
    requirement: "Impedir escrituras nativas de Procurement en las tres autoridades",
    implementation: "Permisos nativos y huellas SQL comparadas",
    test: "test_procurement_close2_auth.py",
  },
};
const accepted = row => ["CLOSED", "PASS"].includes(row.status);
const status = row => accepted(row) ? "CLOSED" : "OPEN";
const outcome = row => accepted(row) ? "PASS" : row.result === "FAIL" ? "FAIL" : "No acreditado";
const cells = {};
const set = (name, address, value) => {
  assert.equal(typeof value, "string", `${name}!${address} must be text`);
  const area = wb.worksheets.getItem(name).getRange(address);
  assert.notEqual(area.formulas[0][0]?.[0], "=", `Do not overwrite a formula: ${name}!${address}`);
  if (area.values[0][0] !== value) {
    (cells[name] ??= {})[address] = value;
    area.values = [[value]];
  }
};
const toText = (value, fallback) => Array.isArray(value)
  ? value.length ? value.join("\n") : fallback
  : typeof value === "string" && value.trim() ? value : fallback;

if (mode === "edit") {
  const decisionPath = path.join(qa, "release", `decision-${attempt}.json`);
  const run = JSON.parse((await fs.readFile(decisionPath, "utf8")).replace(/^\uFEFF/, ""));
  assert.equal(run.attempt ?? attempt, attempt);
  assert(["OPEN", "CLOSED"].includes(run.g01) && ["OPEN", "CLOSED"].includes(run.g02));
  assert(["WAVE_O2B_RELEASE_BLOCKED", "WAVE_O2B_PROCUREMENT_MATERIALS_LOGISTICS_FOUNDATION_RELEASE_VALIDATED"].includes(run.decision));
  const rows = new Map(wb.worksheets.getItem(release).getRange("E8:E23").values.map(([id], index) => [id, index + 8]));
  const result = new Map([...run.controls, ...(run.matrix_regressions ?? [])].map(row => [row.id, row]));
  for (const id of Object.keys(mandatory)) assert(result.has(id), `Missing decision for ${id}`);

  set("00_README", "B8", `${run.decision}. G01: ${run.g01}. G02: ${run.g02}.`);
  set("00_README", "B9", `Corte O2B.CLOSE-2 ${attempt}. Evidencia final: wave-o2b-close2-20261112.`);
  set("00_README", "B10", "CLOSE-2 actualiza los S2 y sus controles de salida. Los registros marcados «Corte anterior» son históricos.");
  set("15_DEFECTS", "B8", `Regresión y navegador: ${run.g01}. Ver CLOSE-PG-O1 y criterios de liberación.`);
  set("15_DEFECTS", "B9", `Adopción y separación de autoridad: ${run.g02}. Ver los tres controles de consumidores.`);
  set("15_DEFECTS", "C8", run.g01);
  set("15_DEFECTS", "C9", run.g02);
  set(release, "E2", "Controles de cierre O2B CLOSE 2");
  set(release, "B13", `G01: ${run.g01}. G02: ${run.g02}.`);
  set(release, "C13", run.g01 === "CLOSED" && run.g02 === "CLOSED" ? "Verificado" : "Parcial");
  set(release, "B14", run.decision);
  set(release, "C14", run.decision === "WAVE_O2B_RELEASE_BLOCKED" ? "Pendiente" : "Verificado");
  if (run.readiness) {
    set(release, "B14", `${run.decision}\n${run.readiness}`);
    const cell = wb.worksheets.getItem(release).getRange("B14");
    cell.format.wrapText = true;
    if (cell.format.rowHeight < 56) cell.format.rowHeight = 56;
  }

  for (const [id, index] of rows) {
    const row = result.get(id);
    if (!row) {
      const old = wb.worksheets.getItem(release).getRange(`I${index}`).values[0][0];
      if (old) set(release, `I${index}`, `Corte anterior: ${old}`);
      continue;
    }
    assert(["OPEN", "CLOSED", "PASS", "FAIL", "PENDING"].includes(row.status), `Unknown status for ${id}`);
    if (mandatory[id]) {
      const meta = mandatory[id];
      set(release, `F${index}`, row.requirement ?? meta.requirement);
      set(release, `G${index}`, row.implementation ?? meta.implementation);
      set(release, `H${index}`, row.test ?? meta.test);
    }
    set(release, `I${index}`, toText(row.evidence, "Sin evidencia final"));
    set(release, `J${index}`, outcome(row));
    set(release, `K${index}`, status(row));
    const observation = toText(row.observation, accepted(row) ? "Ver evidencia final del control." : "Consultar acción pendiente en la decisión final.");
    const next = accepted(row) ? "" : toText(row.action, "");
    set(release, `L${index}`, [observation, next && `Acción: ${next}`].filter(Boolean).join("\n"));
  }

  const o1 = result.get("CLOSE-PG-O1");
  const o1Evidence = toText(o1.evidence, "Sin evidencia final");
  set("14_TESTS", "C13", `CLOSE-PG-O1: ${outcome(o1)}`);
  set("14_TESTS", "D13", o1Evidence);
  set("01_REQUIREMENTS", "I49", accepted(o1) ? "Verificado" : "Pendiente");
  set("01_REQUIREMENTS", "J49", `Cierre O1: ${status(o1)}. Ver CLOSE-PG-O1 en 16_RELEASE_CRITERIA.`);
  for (const [id, index] of [["CLOSE-PG-O2A", 12], ["CLOSE-WEB-O2B", 14]]) {
    const row = result.get(id);
    if (row) {
      set("14_TESTS", `C${index}`, `${id}: ${outcome(row)}`);
      set("14_TESTS", `D${index}`, toText(row.evidence, "Sin evidencia final"));
    } else {
      const previous = wb.worksheets.getItem("14_TESTS").getRange(`D${index}`).values[0][0];
      if (previous) set("14_TESTS", `D${index}`, `Corte anterior: ${previous}`);
    }
  }
  if (result.has("CLOSE-P14")) set(release, "C10", accepted(result.get("CLOSE-P14")) ? "Verificado" : "Pendiente");
  if (result.has("CLOSE-WEB-O2A") || result.has("CLOSE-WEB-O2B")) {
    const chromium = [result.get("CLOSE-WEB-O2A"), result.get("CLOSE-WEB-O2B")];
    set(release, "C11", chromium.every(row => row && accepted(row)) ? "Verificado" : "Pendiente");
  }

  // Preserve all original styles and row sizes unless a changed text actually needs another line.
  const readable = name => wb.worksheets.getItem(name);
  const columnCharacters = { F: 39, G: 39, H: 39, I: 48, L: 55 };
  for (const [id, index] of rows) {
    if (!(id in mandatory) && !result.has(id)) continue;
    const maxLines = Math.max(...Object.entries(columnCharacters).map(([column, width]) => {
      const value = readable(release).getRange(`${column}${index}`).values[0][0];
      return String(value ?? "").split("\n").reduce((sum, line) => sum + Math.max(1, Math.ceil(line.length / width)), 0);
    }));
    const range = readable(release).getRange(`E${index}:L${index}`);
    if (maxLines > 2 && range.format.rowHeight < 14 * maxLines + 11) range.format.rowHeight = 14 * maxLines + 11;
  }
  wb.recalculate();
  const errors = await wb.inspect({
    kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
    options: { useRegex: true, maxResults: 300 },
  });
  await fs.writeFile(path.join(previews, "formula-scan.ndjson"), errors.ndjson);
  const candidate = path.join(artifacts, "candidate", outputName);
  await fs.mkdir(path.dirname(candidate), { recursive: true });
  await (await SpreadsheetFile.exportXlsx(wb)).save(candidate);
  await fs.writeFile(path.join(artifacts, "matrix-edits.json"), JSON.stringify({
    attempt, cells, baseline_sha256: expectedBase, candidate_sha256: await digest(candidate),
  }, null, 2));
}

for (const [sheetName, range, name] of views) {
  const blob = await wb.render({ sheetName, range, scale: 1.05, format: "png" });
  await fs.writeFile(path.join(previews, `${name}.png`), new Uint8Array(await blob.arrayBuffer()));
}
console.log(`Matrix ${mode}: ${views.length} views in ${previews}`);
