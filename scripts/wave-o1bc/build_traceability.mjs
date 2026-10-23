import fs from "node:fs/promises";
import path from "node:path";
import { Workbook, SpreadsheetFile } from "@oai/artifact-tool";

const root = path.resolve(import.meta.dirname, "../..");
const qa = path.join(root, "outputs/.qa/wave-o1bc-20261022/workbook");
const data = JSON.parse(await fs.readFile(path.join(root, "docs/validation/wave-o1bc-20261022/package-data.json"), "utf8"));
const book = Workbook.create();
const headers = ["Caso", "Comprobación", "Resultado", "Tiempo s", "Evidencia"];
const widths = [14, 82, 26, 13, 64];
const cases = (pattern) => [
  ...data.cases.filter((r) => pattern.test(r.name)).map((r, i) => [`TC-${i + 1}`, r.name, r.result, r.seconds, `${r.evidence} ${r.class}`]),
  ...data.browser.checks.filter((r) => pattern.test(r.code)).map((r, i) => [`UI-${i + 1}`, r.code, r.result, null, "Chromium real browser-uat.json"]),
];
const themed = (name, title, pattern) => ({ name, title, headers, widths, rows: cases(pattern) });
const specs = [
  { name: "01_Requirements", title: "Requisitos Cost Foundation", headers: ["ID", "Requisito", "Resultado", "Verificación"], widths: [14, 82, 26, 82], rows: data.requirements },
  themed("02_CBS", "Estructura de costos independiente de WBS", /cbs|hierarchy|CBS_COST_CODE/i),
  themed("03_Cost_Codes", "Diccionario y categorías de costo", /cost_code|category|categories|CBS_COST_CODE/i),
  themed("04_Control_Accounts", "Cuentas y responsabilidad de control", /control_account|mapping_project|CBS_COST_CODE/i),
  themed("05_Mappings", "Mapeos Scope Plan Package WBS Activity", /mapping|m_to_n|scope_times|SCOPE_PLAN_PACKAGE_MN/i),
  themed("06_APU_Rates", "APU tarifas y vigencias", /apu|rate_|rates_|unit_|effective|VERSIONED_EFFECTIVE/i),
  themed("07_Budget", "Versiones y aprobación del presupuesto", /budget|scope_times|pricing|reserve|CANDIDATE_ONLY/i),
  themed("08_Cost_Baseline", "Baseline de costo inmutable", /cost_baseline|baseline.*(candidate|phase|approv|immut)|BUDGET_BASELINE/i),
  themed("09_Phasing", "Distribución temporal y fuente Schedule", /phas|spread|curve|front_back|residual|SCHEDULE_AUTHORITY/i),
  themed("10_Commitments", "Compromisos y conciliación económica", /commitment|obligation|contract|included|call_off|subcontract|refresh|legal|origin/i),
  themed("11_Actuals", "Reconocimiento de costo y ajustes", /actual|recognition|adjust|negative|asof|historical|SOURCE_UNIQUE/i),
  { name: "12_Accruals", title: "Contrato diferido de devengos", headers: ["ID", "Capacidad", "Estado", "Límite"], widths: [14, 68, 32, 86], rows: [
      ["AC-01", "Accrual lifecycle", "DEFERRED_WITH_CONTRACT", "Contrato explícito sin mutación de devengo ni reversión ficticia"],
      ["AC-02", "Actual más Accrual", "NO_DOUBLE_COUNT", "Las vistas actuales contienen solo costo reconocido; no suman devengos estimados"],
      ...data.browser.checks.filter((r) => /ACCRUAL/.test(r.code)).map((r) => ["AC-UI", r.code, r.result, "Comprobación real del límite de interfaz"]),
    ] },
  themed("13_Currency", "Moneda conversión y conservación histórica", /currenc|fx_|decimal|money|aggregation|single_currency|two_currencies/i),
  themed("14_Admin_User", "Configuración y operación autorizada", /profile|admin|publication|config|policy|reserve|CATALOG/i),
  themed("15_Security", "Seguridad concurrencia y separación de funciones", /tenant|project_isolation|foreign|deni|deny|sod|privileged|independent|etag|idempot|immutable|no_write|unchanged|adoption|legacy_direct|HISTORY|AUTHOR/i),
  { name: "16_API", title: "Contratos API de Cost", headers: ["Método", "Ruta", "Operación", "Dominio"], widths: [14, 100, 68, 20], rows: data.api },
  { name: "17_Defects", title: "Defectos corregidos y límites", headers: ["ID", "Severidad", "Hallazgo", "Estado", "Tratamiento"], widths: [14, 18, 80, 32, 86], rows: data.defects },
  { name: "18_Release_Criteria", title: "Criterios y mediciones de liberación", headers: ["ID", "Criterio u operación", "Resultado", "Muestras", "Mín ms", "Mediana ms", "Máx ms", "Evidencia"], widths: [14, 78, 34, 13, 14, 14, 14, 70], rows: [
      ...data.release_criteria.map((r) => [r[0], r[1], r[2], null, null, null, null, r[3]]),
      ...data.performance.map((r, i) => [`PERF-${i + 1}`, r[0], "LOCAL_NO_SLA", ...r.slice(1), "API real del entorno aislado con tres muestras"]),
    ] },
];
await fs.mkdir(qa, { recursive: true });
const expected = [], manifest = [], previews = [];
const col = (i) => String.fromCharCode(65 + i);
for (const [index, spec] of specs.entries()) {
  if (!spec.rows.length) throw new Error(`Missing real evidence for ${spec.name}`);
  const sheet = book.worksheets.add(spec.name);
  const last = col(spec.headers.length - 1), end = 7 + spec.rows.length;
  const all = sheet.getRange(`A1:${last}${end}`);
  all.format.font = { name: "Arial", size: 10, color: "#243746" };
  all.format.rowHeight = 24;
  sheet.showGridLines = false;
  sheet.getRange("A2").values = [[spec.title]];
  sheet.getRange("A2").format.font = { name: "Arial", size: 14, bold: true, color: "#000000" };
  sheet.getRange(`A3:${last}3`).format.borders = { bottom: { style: "thin", color: "#17324D" } };
  sheet.getRange("A4").values = [["Cierre técnico 23 octubre 2026"]];
  sheet.getRange("A4").format.font = { name: "Arial", size: 10, italic: true, color: "#65758B" };
  sheet.getRange("A5").values = [["Validación técnica aislada sin aceptación de negocio firmada"]];
  sheet.getRange(`A7:${last}7`).values = [spec.headers];
  sheet.getRange(`A7:${last}7`).format = { fill: "#17324D", font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", verticalAlignment: "center", rowHeight: 35, wrapText: true };
  sheet.getRange(`A8:${last}${end}`).values = spec.rows;
  sheet.getRange(`A8:${last}${end}`).format.wrapText = true;
  sheet.getRange(`A8:${last}${end}`).format.verticalAlignment = "center";
  for (const [c, width] of spec.widths.entries()) sheet.getRange(`${col(c)}1:${col(c)}${end}`).format.columnWidth = width;
  for (const [r, values] of spec.rows.entries()) {
    const row = sheet.getRange(`A${r + 8}:${last}${r + 8}`);
    row.format.rowHeight = Math.max(30, ...values.map((v, c) => Math.ceil(String(v ?? "").length / Math.max(8, spec.widths[c] - 4)) * 15 + 12));
    if (r % 2) row.format.fill = "#F3F6FA";
  }
  if (spec.headers.includes("Tiempo s")) sheet.getRange(`D8:D${end}`).setNumberFormat("0.000");
  if (index === 17) { sheet.getRange(`D8:D${end}`).setNumberFormat("#,##0"); sheet.getRange(`E8:G${end}`).setNumberFormat("0.00"); }
  const status = spec.headers.findIndex((v) => ["Resultado", "Estado"].includes(v));
  if (status >= 0) {
    sheet.getRange(`${col(status)}8:${col(status)}${end}`).conditionalFormats.add("containsText", { text: "FAIL", format: { fill: "#FCE8E6", font: { color: "#9C1C1C", bold: true } } });
  }
  sheet.tables.add(`A7:${last}${end}`, true, `CostTrace${index + 1}`).showFilterButton = true;
  sheet.freezePanes.freezeRows(7);
  if (spec.rows.length > 20) sheet.freezePanes.freezeColumns(1);
  if ([0, 17].includes(index)) sheet.tabColor = "#17324D";
  expected.push({ sheet: spec.name, headers: spec.headers, rows: spec.rows });
  manifest.push({ sheet: spec.name, rows: spec.rows.length, columns: spec.headers.length, last_row: end, last_column: last });
}
book.recalculate();
await fs.writeFile(path.join(qa, "inspection.ndjson"), (await book.inspect({ kind: "workbook,sheet,table", maxChars: 6000, tableMaxRows: 2, tableMaxCols: 4 })).ndjson);
await fs.writeFile(path.join(qa, "errors.ndjson"), (await book.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!", options: { useRegex: true, maxResults: 30 }, maxChars: 2000 })).ndjson);
await fs.writeFile(path.join(qa, "expected-tables.json"), JSON.stringify(expected, null, 2));
await fs.writeFile(path.join(qa, "build-manifest.json"), JSON.stringify({ sheets: manifest }, null, 2));
for (const sheet of manifest) {
  for (let start = 1; start <= sheet.last_row; start += 18) {
    const range = `A${start}:${sheet.last_column}${Math.min(start + 17, sheet.last_row)}`;
    const file = `${sheet.sheet}-${String(start).padStart(3, "0")}.png`;
    const png = await book.render({ sheetName: sheet.sheet, range, scale: 1.15, format: "png" });
    await fs.writeFile(path.join(qa, file), new Uint8Array(await png.arrayBuffer()));
    previews.push({ sheet: sheet.sheet, range, file });
  }
}
await fs.writeFile(path.join(qa, "render-manifest.json"), JSON.stringify(previews, null, 2));
const output = path.join(root, "outputs/wave-o1bc-20261022/P&Pmis_Wave_O1B_C_Cost_Foundation_Traceability.xlsx");
await fs.mkdir(path.dirname(output), { recursive: true });
await (await SpreadsheetFile.exportXlsx(book)).save(output);
try { await fs.rename(output + ".inspect.ndjson", path.join(qa, "export-inspection.ndjson")); }
catch (error) { if (error.code !== "ENOENT") throw error; }
console.log(JSON.stringify({ output, sheets: manifest.length, records: manifest.reduce((sum, r) => sum + r.rows, 0), previews: previews.length }));
