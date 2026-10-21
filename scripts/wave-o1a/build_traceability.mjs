/** O1A traceability in a bound Artifact Session, exported to the requested XLSX. */
import fs from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const qa = path.join(root, "outputs/.qa/wave-o1a-20261019/workbook");
const output = path.join(root, "outputs/wave-o1a-20261019/P&Pmis_Wave_O1A_Operational_Context_Traceability.xlsx");
const column = index => {
  let n = index + 1, result = "";
  while (n) { n -= 1; result = String.fromCharCode(65 + n % 26) + result; n = Math.floor(n / 26); }
  return result;
};
const navy = "#17324D", ink = "#243547", muted = "#64748B";

function cases(data, pattern) {
  const selected = data.cases.filter(row => pattern.test(row.class + "." + row.name));
  return selected.map((row, index) => [`TC-${String(index + 1).padStart(3, "0")}`, row.name, row.result, row.seconds, row.evidence]);
}

function requirementEvidence(number) {
  if ([4, 49].includes(number)) return "legacy-consumer-inventory.json";
  if ([5, 41].includes(number)) return "preservation-before.json; preservation-after.json; characterization-before.xml";
  if ([42, 43, 44, 45, 46, 48].includes(number)) return "postgresql-foundation-final3.xml; postgresql-owner-authority.xml";
  if (number === 47) return "chromium-release3/browser-uat.json";
  if (number === 50) return "migration-roundtrip.json; postgresql-migration.xml";
  if (number === 51) return "chromium-release3/browser-uat.json local_observations";
  if ([55, 56, 61].includes(number)) return "Technical Report.docx; Operational Context Traceability.xlsx";
  if (number >= 57) return "10_Release_Criteria; package-data.json";
  return "backend/app/modules/operational_context; postgresql-foundation-final3.xml; strategic-regression-isolated.xml";
}

function specifications(data) {
  const testHeaders = ["Caso", "Prueba ejecutada", "Resultado", "Tiempo s", "Evidencia"];
  const testWidths = [13, 76, 15, 12, 76];
  const roles = [
    ["Operational Administrator", "ADMIN", "Organización y asignación explícita", "Configurar y publicar perfiles; binding y períodos", "Publicación independiente según política"],
    ["Project Administrator", "USER", "Workspace canónico asignado", "Leer, vincular, abrir y revisar", "Reconciliación independiente según política"],
    ["Project Manager", "USER", "Workspace canónico asignado", "Leer, abrir, revisar, cerrar, publicar y reabrir", "El cerrador no publica por defecto"],
    ["Project Controls Manager", "USER", "Workspace canónico asignado", "Leer, abrir, revisar, cerrar, publicar y reabrir", "El cerrador no publica por defecto"],
    ["Planner Scheduler", "USER", "Workspace canónico asignado", "Leer, abrir y revisar", "Sin edición ADMIN ni publicación de período"],
    ["Cost Controller", "USER", "Workspace canónico asignado", "Leer, abrir y revisar", "No concede presupuesto ni autoridad de compromiso"],
    ["Progress Engineer", "USER", "Workspace canónico asignado", "Leer contexto", "No implementa aprobación de avance O1B"],
    ["Executive Viewer", "USER", "Workspace canónico asignado", "Solo lectura", "Transiciones y binding rechazados"],
    ["Existing organization administrator", "ADMIN", "Organización", "CLI explícito provisiona catálogo sin asignar actores", "No hay bootstrap de permisos en GET"],
  ];
  const legacy = data.legacy_consumers.map(row => [row.id, row.id.startsWith("FK-") ? "FK" : row.id.startsWith("FE-") ? "Frontend" : "Función", row.symbol || row.table || row.path, row.awareness, row.migration, `${row.path}:${row.line}`]);
  const apis = data.api.map(([method, route, command, source]) => [method, route, command, method === "GET" ? "Lectura" : "Idempotency-Key", method === "GET" || command === "open_period" || command === "create_profile" ? "No aplica" : "If-Match", source]);
  return [
    { name: "01_Requirements", title: "Requisitos Wave O1A", headers: ["Sección", "Requisito del prompt", "Resultado", "Referencia de verificación"], widths: [12, 72, 22, 105], rows: data.requirements.map(([id, title, status]) => [id, title, status, requirementEvidence(id)]) },
    { name: "02_Binding_Cases", title: "Casos de vinculación canónica y legacy", headers: testHeaders, widths: testWidths, rows: cases(data, /binding|bound_canonical|legacy_material|anonymous_background/i) },
    { name: "03_Authorization_Cases", title: "Autorización por modelo de gobierno", headers: testHeaders, widths: testWidths, rows: cases(data, /authorization|owner_authority|non_owner|governance|wrong_tenant_wrong_project|reserved_project|owner_to_direct/i) },
    { name: "04_Period_Cases", title: "Período común y revisiones", headers: testHeaders, widths: testWidths, rows: cases(data, /period|calendar|cadence|header|cutoff|data_date/i) },
    { name: "05_Admin_User", title: "Deberes de Admin y User", headers: ["Rol o actor", "Modo", "Alcance", "Operaciones", "Límite o SoD"], widths: [32, 12, 39, 62, 64], rows: roles },
    { name: "06_Legacy_Consumers", title: "Inventario estático de consumidores heredados", headers: ["ID", "Tipo", "Consumidor", "Consciencia", "Destino", "Referencia de origen"], widths: [14, 16, 55, 23, 30, 90], rows: legacy },
    { name: "07_API_Inventory", title: "API de contexto operacional", headers: ["Método", "Ruta", "Operación", "Reintento", "Concurrencia", "Fuente"], widths: [12, 90, 28, 24, 22, 88], rows: apis },
    { name: "08_Security", title: "Validaciones de seguridad y aislamiento", headers: testHeaders, widths: testWidths, rows: cases(data, /security|sod|permission|unauthorized|wrong_tenant|cross_tenant|immutable|raw_sql|generic_admin|legacy_configurator|reserved|dashboard|background/i) },
    { name: "09_Defects", title: "Hallazgos corregidos y límites documentados", headers: ["ID", "Clase", "Hallazgo", "Estado", "Resolución o límite"], widths: [15, 18, 75, 27, 91], rows: data.defects },
    { name: "10_Release_Criteria", title: "Liberación técnica y mediciones locales O1A", headers: ["ID", "Criterio o consulta", "Resultado", "N", "Mín ms", "Mediana ms", "Máx ms"], widths: [14, 80, 25, 10, 15, 15, 15], rows: [...data.release_criteria.map(row => [...row, null, null, null, null]), ...data.performance.map((row, i) => [`PERF-${i + 1}`, row[0], "LOCAL_NO_SLA", ...row.slice(1)])] },
  ];
}

function height(values, widths) {
  const lines = values.map((value, index) => String(value ?? "").split("\n").reduce((n, line) => n + Math.max(1, Math.ceil(line.length / Math.max(5, widths[index] - 3))), 0));
  return Math.max(30, Math.max(...lines) * 15 + 12);
}

export async function buildTraceability(workbook) {
  const dataPath = path.join(root, "docs/validation/wave-o1a-20261019/package-data.json");
  const dataBytes = await fs.readFile(dataPath);
  const data = JSON.parse(dataBytes.toString("utf8"));
  await fs.mkdir(qa, { recursive: true });
  await fs.mkdir(path.dirname(output), { recursive: true });
  const specs = specifications(data);
  const manifest = [];
  for (const [index, spec] of specs.entries()) {
    const sheet = workbook.worksheets.add(spec.name);
    const lastColumn = column(spec.headers.length - 1), lastRow = 7 + spec.rows.length;
    const used = sheet.getRange(`A1:${lastColumn}${lastRow}`);
    used.format.font = { name: "Arial", size: 10, color: ink };
    used.format.verticalAlignment = "center";
    used.format.rowHeight = 24;
    sheet.showGridLines = false;
    if (index === 0 || index === 9) sheet.tabColor = navy;
    sheet.getRange("A2").values = [[spec.title]];
    sheet.getRange("A2").format.font = { name: "Arial", size: 14, bold: true, color: navy };
    sheet.getRange(`A3:${lastColumn}3`).format.borders = { bottom: { style: "thin", color: navy } };
    sheet.getRange("A4").values = [["Corte de validación 20 octubre 2026"]];
    sheet.getRange("A4").format.font = { name: "Arial", size: 10, italic: true, color: muted };
    sheet.getRange("A5").values = [[index === 5 ? "642 referencias directas de línea base con distinta granularidad; no equivalen a 642 funcionalidades." : "Fuente: evidencia PostgreSQL Chromium e inventario del paquete O1A; las firmas de negocio siguen pendientes."]];
    const header = sheet.getRange(`A7:${lastColumn}7`);
    header.values = [spec.headers];
    header.format = { fill: navy, font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", verticalAlignment: "center", wrapText: true, rowHeight: 38 };
    sheet.getRange(`A8:${lastColumn}${lastRow}`).values = spec.rows;
    sheet.getRange(`A8:${lastColumn}${lastRow}`).format.wrapText = true;
    sheet.getRange(`A8:${lastColumn}${lastRow}`).format.verticalAlignment = "top";
    for (let col = 0; col < spec.widths.length; col++) sheet.getRange(`${column(col)}1:${column(col)}${lastRow}`).format.columnWidth = spec.widths[col];
    for (const [rowIndex, values] of spec.rows.entries()) {
      const range = sheet.getRange(`A${rowIndex + 8}:${lastColumn}${rowIndex + 8}`);
      range.format.rowHeight = height(values, spec.widths);
      if (rowIndex % 2) range.format.fill = "#F3F6FA";
    }
    if (spec.headers.includes("Tiempo s")) {
      sheet.getRange(`D8:D${lastRow}`).setNumberFormat("0.000");
      sheet.getRange(`D8:D${lastRow}`).format.horizontalAlignment = "right";
    }
    const statusIndex = spec.headers.findIndex(value => value === "Resultado" || value === "Estado");
    if (statusIndex >= 0) {
      const status = sheet.getRange(`${column(statusIndex)}8:${column(statusIndex)}${lastRow}`);
      status.conditionalFormats.add("containsText", { text: "FAIL", format: { fill: "#FCE8E6", font: { color: "#9C1C1C", bold: true } } });
      status.conditionalFormats.add("containsText", { text: "PENDING", format: { fill: "#FFF3CD" } });
    }
    const nativeTable = sheet.tables.add(`A7:${lastColumn}${lastRow}`, true, `O1ATrace${index + 1}`);
    nativeTable.showFilterButton = true;
    sheet.freezePanes.freezeRows(7);
    if (spec.rows.length > 20) sheet.freezePanes.freezeColumns(1);
    manifest.push({ sheet: spec.name, rows: spec.rows.length, columns: spec.headers.length, widths: spec.widths, first_data_row: 8, last_row: lastRow, last_column: lastColumn });
  }
  workbook.recalculate();
  const inspection = await workbook.inspect({ kind: "workbook,sheet,table", maxChars: 7000, tableMaxRows: 3, tableMaxCols: 6 });
  await fs.writeFile(path.join(qa, "session-inspection.ndjson"), inspection.ndjson);
  const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!", options: { useRegex: true, maxResults: 50 }, maxChars: 2000 });
  await fs.writeFile(path.join(qa, "error-scan.ndjson"), errors.ndjson);
  // Artifact Session owns durable workbook state and the native export. Keep
  // file export outside this callback so no second workbook is reconstructed.
  const result = { output, data_sha256: createHash("sha256").update(dataBytes).digest("hex"), sheets: manifest };
  await fs.writeFile(path.join(qa, "build-manifest.json"), JSON.stringify(result, null, 2));
  return { output, sheets: manifest.length, records: manifest.reduce((n, sheet) => n + sheet.rows, 0) };
}

export async function verifyAndRender(workbook) {
  const manifest = JSON.parse(await fs.readFile(path.join(qa, "build-manifest.json"), "utf8"));
  const previews = [];
  for (const sheet of manifest.sheets) {
    for (let first = 1; first <= sheet.last_row; first += 18) {
      const last = Math.min(sheet.last_row, first + 17);
      const range = `A${first}:${sheet.last_column}${last}`;
      const blob = await workbook.render({ sheetName: sheet.sheet, range, scale: 1.25, format: "png" });
      const name = `${sheet.sheet}-${String(first).padStart(3, "0")}.png`;
      await fs.writeFile(path.join(qa, name), new Uint8Array(await blob.arrayBuffer()));
      previews.push({ sheet: sheet.sheet, range, file: name });
    }
  }
  await fs.writeFile(path.join(qa, "render-manifest.json"), JSON.stringify(previews, null, 2));
  return { sheets_reviewable: manifest.sheets.length, ranges: previews.length, preview_directory: qa };
}
