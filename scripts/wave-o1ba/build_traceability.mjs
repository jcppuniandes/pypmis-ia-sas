import fs from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";

const root = "C:/Users/Ricardo/Documents/GitHub/pypmis-ia-sas";
const qa = path.join(root, "outputs/.qa/wave-o1ba-20261020/workbook");
const navy = "#17324D";
const col = index => String.fromCharCode(65 + index);
const rowHeight = (values, widths) => Math.max(30, ...values.map((value, i) => Math.ceil(String(value ?? "").length / Math.max(8, widths[i] - 4)) * 15 + 12));

function specifications(data) {
  const tests = pattern => [
    ...data.cases.filter(row => pattern.test(row.name)).map((row, i) => [`TC-${String(i + 1).padStart(3, "0")}`, row.name, row.result, row.seconds, row.evidence]),
    ...data.browser.checks.filter(row => pattern.test(row.code)).map((row, i) => [`UI-${i + 1}`, row.code, row.result, null, "chromium-release4/browser-uat.json"]),
  ];
  const headers = ["Caso", "Prueba o comprobación", "Resultado", "Tiempo s", "Evidencia"];
  const widths = [13, 84, 23, 14, 84];
  const cases = (name, title, pattern) => ({ name, title, headers, widths, rows: tests(pattern) });
  return [
    {name:"01_Requirements", title:"Requisitos Scope O1B A", headers:["Sección", "Requisito del prompt", "Resultado", "Verificación"], widths:[13, 78, 23, 90], rows:data.requirements.map(row=>[...row,row[2]==="CLOSEOUT_MANIFEST"?"Cierre documental y entrega verificados en release-manifest.json y QA de artefactos finales.":"Paquete PostgreSQL Chromium y revisión de alcance; ver hojas temáticas y criterios de liberación."])},
    cases("02_IFC_Import", "Fuentes IFC y versiones", /ifc|bim|model_version|model_successor|source_model|USER_IFC|ORIGINAL_IFC/i),
    cases("03_Excel_Import", "Importación Excel y linaje de filas", /excel|EXCEL/i),
    cases("04_Scope_Items", "Scope Items y jerarquía canónica", /manual_scope|scope_hierarchy|scope_invalid|scope_write|scope_mapping|approved_change|source_quantity|SCOPE_MN/i),
    cases("05_Scope_Nature", "Naturaleza gobernada del alcance", /nature|Scope Nature|NATURES/i),
    cases("06_Scope_Revisions", "Revisiones y baselines inmutables", /revision_sod|baseline|BASELINE/i),
    cases("07_Execution_Strategy", "Estrategias rutas y segmentación", /strategy|STRATEGY/i),
    cases("08_Plan_Items", "Asignaciones y transformaciones Plan Items", /plan_many|PLAN_ALLOCATION|plan_item|allocation|group_split|plan_publication|current_scope/i),
    cases("09_Derived_3D", "Representación derivada y fuente intacta", /derived|DERIVED|ORIGINAL_IFC|source_bytes/i),
    cases("10_Admin_User", "ADMIN USER y deberes de los actores", /granular_roles|scope_write|generic_admin|scope_profile|ADMIN_PROFILE|INDEPENDENT_PROFILE|EXECUTIVE/i),
    cases("11_Security", "Seguridad y regresiones de protección", /denied|fail_closed|sod|immutable|raw_update|no_business|etag|idempot|wrong_tenant|cross_tenant|cross_project|generic_admin|legacy_configur|profile_latest|DIRECT_API|plan_publication|silent_source_unit/i),
    {name:"12_API", title:"Inventario de API canónica Scope", headers:["Método", "Ruta", "Operación", "Control de acceso", "Fuente"], widths:[13, 92, 65, 45, 64], rows:data.api},
    {name:"13_Defects", title:"Hallazgos resueltos y límites", headers:["ID", "Clase", "Hallazgo", "Estado", "Resolución o límite"], widths:[15, 19, 83, 28, 94], rows:data.defects},
    {name:"14_Release_Criteria", title:"Liberación y observaciones locales", headers:["ID", "Criterio u operación", "Resultado", "N", "Mín ms", "Mediana ms", "Máx ms", "Evidencia"], widths:[14, 85, 28, 10, 15, 15, 15, 92], rows:[...data.release_criteria.map(row=>[...row.slice(0,3),null,null,null,null,row[3]]), ...data.performance.map((row,i)=>[`PERF-${i+1}`,row[0],"LOCAL_NO_SLA",...row.slice(1),"Observaciones locales registradas; no SLA productivo"])]},
  ];
}

export async function buildTraceability(workbook) {
  const dataBytes = await fs.readFile(path.join(root,"docs/validation/wave-o1ba-20261020/package-data.json"));
  const data = JSON.parse(dataBytes.toString("utf8"));
  await fs.mkdir(qa,{recursive:true});
  const manifest = [];
  const expectedTables = [];
  for (const [i, spec] of specifications(data).entries()) {
    if (!spec.rows.length) throw new Error(`Missing actual evidence for ${spec.name}`);
    const sheet = workbook.worksheets.add(spec.name);
    const lastCol = col(spec.headers.length-1), lastRow=7+spec.rows.length;
    sheet.showGridLines=false;
    sheet.getRange(`A1:${lastCol}${lastRow}`).format.font={name:"Arial",size:10,color:"#243746"};
    sheet.getRange(`A1:${lastCol}${lastRow}`).format.rowHeight=24;
    sheet.getRange("A2").values=[[spec.title]];
    sheet.getRange("A2").format.font={name:"Arial",size:14,bold:true,color:navy};
    sheet.getRange(`A3:${lastCol}3`).format.borders={bottom:{style:"thin",color:navy}};
    sheet.getRange("A4").values=[["Corte técnico 20 octubre 2026"]];
    sheet.getRange("A4").format.font={name:"Arial",size:10,italic:true,color:"#65758B"};
    sheet.getRange("A5").values=[["Evidencia ejecutada de O1B A. No implica aceptación de negocio ni despliegue en la base habitual."]];
    const header=sheet.getRange(`A7:${lastCol}7`);
    header.values=[spec.headers];
    header.format={fill:navy,font:{name:"Arial",size:10,bold:true,color:"#FFFFFF"},horizontalAlignment:"center",verticalAlignment:"center",wrapText:true,rowHeight:38};
    sheet.getRange(`A8:${lastCol}${lastRow}`).values=spec.rows;
    sheet.getRange(`A8:${lastCol}${lastRow}`).format.wrapText=true;
    sheet.getRange(`A8:${lastCol}${lastRow}`).format.verticalAlignment="top";
    for (let c=0;c<spec.widths.length;c++) sheet.getRange(`${col(c)}1:${col(c)}${lastRow}`).format.columnWidth=spec.widths[c];
    for (const [r,values] of spec.rows.entries()) {
      const range=sheet.getRange(`A${r+8}:${lastCol}${r+8}`);
      range.format.rowHeight=rowHeight(values,spec.widths);
      if(r%2) range.format.fill="#F3F6FA";
    }
    if(spec.headers.includes("Tiempo s")) {
      sheet.getRange(`D8:D${lastRow}`).setNumberFormat("0.000");
      sheet.getRange(`D8:D${lastRow}`).format.horizontalAlignment="center";
    }
    const status=spec.headers.findIndex(value=>value==="Resultado"||value==="Estado");
    if(status>=0) {
      const cells=sheet.getRange(`${col(status)}8:${col(status)}${lastRow}`);
      cells.conditionalFormats.add("containsText",{text:"FAIL",format:{fill:"#FCE8E6",font:{color:"#9C1C1C",bold:true}}});
      cells.conditionalFormats.add("containsText",{text:"PENDING",format:{fill:"#FFF3CD"}});
    }
    const nativeTable=sheet.tables.add(`A7:${lastCol}${lastRow}`,true,`ScopeTrace${i+1}`);
    nativeTable.showFilterButton=true;
    sheet.freezePanes.freezeRows(7);
    if(spec.rows.length>20)sheet.freezePanes.freezeColumns(1);
    if(i===0||i===13)sheet.tabColor=navy;
    manifest.push({sheet:spec.name,rows:spec.rows.length,columns:spec.headers.length,last_row:lastRow,last_column:lastCol});
    expectedTables.push({sheet:spec.name,headers:spec.headers,rows:spec.rows});
  }
  workbook.recalculate();
  const inspection=await workbook.inspect({kind:"workbook,sheet,table",maxChars:6000,tableMaxRows:2,tableMaxCols:5});
  await fs.writeFile(path.join(qa,"inspection.ndjson"),inspection.ndjson);
  const errors=await workbook.inspect({kind:"match",searchTerm:"#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!",options:{useRegex:true,maxResults:50},maxChars:2000});
  await fs.writeFile(path.join(qa,"errors.ndjson"),errors.ndjson);
  await fs.writeFile(path.join(qa,"build-manifest.json"),JSON.stringify({data_sha256:createHash("sha256").update(dataBytes).digest("hex"),sheets:manifest},null,2));
  await fs.writeFile(path.join(qa,"expected-tables.json"),JSON.stringify(expectedTables,null,2));
  return {sheets:manifest.length,records:manifest.reduce((total,sheet)=>total+sheet.rows,0)};
}

export async function renderTraceability(workbook) {
  const manifest=JSON.parse(await fs.readFile(path.join(qa,"build-manifest.json"),"utf8"));
  const previews=[];
  for(const sheet of manifest.sheets) {
    for(let start=1;start<=sheet.last_row;start+=18) {
      const range=`A${start}:${sheet.last_column}${Math.min(start+17,sheet.last_row)}`;
      const blob=await workbook.render({sheetName:sheet.sheet,range,scale:1.25,format:"png"});
      const file=`${sheet.sheet}-${String(start).padStart(3,"0")}.png`;
      await fs.writeFile(path.join(qa,file),new Uint8Array(await blob.arrayBuffer()));
      previews.push({sheet:sheet.sheet,range,file});
    }
  }
  await fs.writeFile(path.join(qa,"render-manifest.json"),JSON.stringify(previews,null,2));
  return {ranges:previews.length,directory:qa};
}
