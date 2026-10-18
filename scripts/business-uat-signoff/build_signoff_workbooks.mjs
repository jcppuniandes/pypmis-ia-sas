/** Controlled business-signoff workbooks. Author only after root markers. */
import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { FileBlob, SpreadsheetFile, Workbook } from '@oai/artifact-tool';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const dir = path.join(root, 'outputs/business-uat-signoff-20261018');
const qa = path.join(root, 'outputs/.qa/business-uat-signoff-20261018/workbooks');
const sourceName = 'P&Pmis_Strategic_Macroprocess_UAT_Traceability.xlsx';
const source = path.join(root, 'outputs/gate07j-controlled-class-b-20261016', sourceName);
const trackerName = 'P&Pmis_Strategic_Macroprocess_Business_UAT_Signoff_Tracker.xlsx';
const dataPath = path.join(root, 'docs/validation/business-uat-signoff-20261018/review-pack-data.json');
const baselinePath = path.join(root, 'docs/validation/business-uat-signoff-20261018/baseline.json');
const mode = process.argv.find(a => ['--inspect-source', '--author', '--verify-output'].includes(a));
if (!mode) throw new Error('Choose --inspect-source, --author or --verify-output');
await fs.mkdir(qa, { recursive: true });
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const sourceHash = digest(await fs.readFile(source));
if (sourceHash !== 'baad276e386ea9550b5bac0eafae8bf6e9910361ea29047da58d952ab5dd757a') throw new Error('Technical source changed');
const data = JSON.parse(await fs.readFile(dataPath, 'utf8'));
const baseline = JSON.parse(await fs.readFile(baselinePath, 'utf8'));
const titles = ['01_Signoff_Matrix','02_Acceptance_Conditions','03_Known_Findings','04_Evidence_Register','05_Document_Acceptance','06_Final_Release_Decision'];
const sourceViews = [['02_UAT_Cases','A7:D12'],['02_UAT_Cases','H35:J39'],['02_UAT_Cases','V35:Z39'],['08_Release_Criteria','E22:J27']];
async function render(wb, label, views) {
  for (const [sheetName, range] of views) {
    const blob = await wb.render({ sheetName, range, scale: 1, format: 'png' });
    await fs.writeFile(path.join(qa, `${label}-${sheetName}-${range.replaceAll(':','-')}.png`), new Uint8Array(await blob.arrayBuffer()));
  }
}
async function inspect(wb, label, views) {
  const overview = await wb.inspect({ kind:'workbook,sheet,table', maxChars:6500, tableMaxRows:3, tableMaxCols:5 });
  await fs.writeFile(path.join(qa, `${label}-inventory.ndjson`), overview.ndjson);
  for (const [sheet, range] of views) {
    const result = await wb.inspect({kind:'table',sheetId:sheet,range,include:'values,formulas',tableMaxRows:70,tableMaxCols:31,maxChars:18000});
    await fs.writeFile(path.join(qa,`${label}-${sheet}-${range.replaceAll(':','-')}.ndjson`),result.ndjson);
  }
}
if (mode === '--inspect-source') {
  const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(source));
  await inspect(wb, 'source', [['02_UAT_Cases','A7:Z58']]);
  await render(wb,'source',sourceViews);
  await fs.writeFile(path.join(qa,'source-cases.json'),JSON.stringify(wb.worksheets.getItem('02_UAT_Cases').getRange('A8:Z58').values,null,2));
  console.log(JSON.stringify({mode,sourceHash}));
  process.exit(0);
}
const styles = { navy:'#17324D', blue:'#244C70', ink:'#243547', muted:'#64748B', amber:'#FFF3CD', line:'#DCE3EB', pale:'#F3F6FA' };
function baseSheet(wb,name,title,lastCol,lastRow) {
  const s=wb.worksheets.add(name); s.showGridLines=false;
  s.getRange(`A1:${lastCol}${lastRow}`).format.font={name:'Arial',size:10,color:styles.ink};
  s.getRange(`A1:${lastCol}${lastRow}`).format.verticalAlignment='center';
  s.getRange(`A1:${lastCol}${lastRow}`).format.rowHeight=22;
  s.getRange('A2').values=[[title]]; s.getRange('A2').format.font={name:'Arial',size:14,bold:true,color:styles.navy};
  s.getRange(`A3:${lastCol}3`).format.borders={bottom:{style:'thin',color:styles.navy}};
  s.tabColor=name==='01_Signoff_Matrix'||name==='06_Final_Release_Decision'?styles.navy:styles.blue;
  return s;
}
function header(s,range,values){s.getRange(range).values=[values];s.getRange(range).format={fill:styles.navy,font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},wrapText:true,horizontalAlignment:'center',verticalAlignment:'center',rowHeight:42};}
function inputs(s,range){s.getRange(range).format.fill=styles.amber;s.getRange(range).format.wrapText=true;}
function widths(s,pairs,maxRow){for(const [c,w]of pairs)s.getRange(`${c}1:${c}${maxRow}`).format.columnWidth=w;}
function table(s,range,name){const t=s.tables.add(range,true,name);t.style='TableStyleMedium2';return t;}
function yesNo(s,range){s.getRange(range).dataValidation={rule:{type:'list',values:['YES','NO']}};}
function statusCf(s,range){s.getRange(range).conditionalFormats.add('containsText',{text:'PENDING',format:{fill:'#FFF3CD',font:{color:'#7A5100'}}});s.getRange(range).conditionalFormats.add('containsText',{text:'REJECT',format:{fill:'#FCE8E6',font:{color:'#9C2020',bold:true}}});}
const views=[
 ['01_Signoff_Matrix','A2:H12'],['01_Signoff_Matrix','I7:P12'],['01_Signoff_Matrix','A13:H22'],['01_Signoff_Matrix','A26:H29'],
 ['02_Acceptance_Conditions','A2:G12'],['02_Acceptance_Conditions','H7:Q12'],['02_Acceptance_Conditions','A13:G15'],['02_Acceptance_Conditions','H13:Q15'],
 ['03_Known_Findings','A2:F12'],['03_Known_Findings','G7:Q12'],['03_Known_Findings','A13:F15'],['03_Known_Findings','G13:Q15'],
 ['04_Evidence_Register','A2:F15'],['04_Evidence_Register','A16:F30'],
 ['05_Document_Acceptance','A2:G13'],['05_Document_Acceptance','H7:L13'],['05_Document_Acceptance','A50:G55'],['05_Document_Acceptance','A92:L97'],
 ['06_Final_Release_Decision','A2:D21'],['06_Final_Release_Decision','A24:D36'],['06_Final_Release_Decision','A40:F47'],['06_Final_Release_Decision','G40:K47'],['06_Final_Release_Decision','A48:F55'],['06_Final_Release_Decision','G48:K55'],['06_Final_Release_Decision','A59:F69'],
];
if(mode==='--verify-output'){
  const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(path.join(dir,trackerName)));
  const m=wb.worksheets.getItem(titles[0]);const f=wb.worksheets.getItem(titles[5]);
  const previousPeople=m.getRange('C8:N22').values;const previousRejections=f.getRange('A41:J55').values;
  const testDate=new Date('2026-10-18T12:00:00Z');
  for(let i=0;i<15;i++){
    m.getRange(`C${i+8}:N${i+8}`).values=[['SIMULATED_NOT_SIGNED','SIMULATED_ROLE','SIMULATED_ORG','SIMULATED_AUTHORITY',testDate,'REJECT','SIMULATED_REVIEW','SIMULATED_APPROVAL','','','','']];
    f.getRange(`A${i+41}:J${i+41}`).values=[[`SIMULATED_REJ_${i+1}`,data.areas[i].id,'SIMULATED_NOT_SIGNED','SIMULATED_REASON','SIMULATED_FLOW_EVIDENCE','S3','SIMULATED_REMEDIATION','OPEN','SIMULATED_MATERIAL_IMPACT','SIMULATED_APPROVAL']];
  }
  wb.recalculate();
  const capacityProof={scope:'SAVED_WORKBOOK_DISPOSABLE_IN_MEMORY_SIMULATION_NOT_EXPORTED',areas:f.getRange('B5').values[0][0],authorizedRejects:f.getRange('B10').values[0][0],registeredRejects:f.getRange('B19').values[0][0],state:f.getRange('B34').values[0][0]};
  capacityProof.pass=capacityProof.areas===15&&capacityProof.authorizedRejects===15&&capacityProof.registeredRejects===15&&capacityProof.state==='BUSINESS_REJECTED';
  m.getRange('C8:N22').values=previousPeople;f.getRange('A41:J55').values=previousRejections;wb.recalculate();
  capacityProof.restored=f.getRange('B5').values[0][0]===0&&f.getRange('B34').values[0][0]==='UAT_SIGNOFF_PENDING';
  await fs.writeFile(path.join(qa,'saved-15-rejections-capacity-check.json'),JSON.stringify(capacityProof,null,2));
  if(!capacityProof.pass||!capacityProof.restored)throw new Error('Saved-workbook rejection register boundary failed');
  await inspect(wb,'saved',[['01_Signoff_Matrix','A5:P22'],['06_Final_Release_Decision','A5:D36']]);
  const savedViews=process.argv.includes('--changed-layout-only')?views.filter(([s,r])=>
    (s===titles[0]&&r==='A26:H29')||(s===titles[5]&&['A2:D21','A24:D36'].includes(r))):views;
  await render(wb,'saved',savedViews);
  const trace=await SpreadsheetFile.importXlsx(await FileBlob.load(path.join(dir,sourceName)));
  if(!process.argv.includes('--changed-layout-only'))await render(trace,'trace-saved',[['02_UAT_Cases','AA7:AE15'],['02_UAT_Cases','AA35:AE39']]);
  console.log(JSON.stringify({mode,sourceUnchanged:digest(await fs.readFile(source))===sourceHash})); process.exit(0);
}
// Root records create/edit markers immediately before this command.
const wb=Workbook.create();
for(const [name,title,col,rows]of[
 [titles[0],'Business UAT sign-off','P',30],[titles[1],'Condiciones propuestas de aceptación','Q',18],
 [titles[2],'Hallazgos y observaciones por revisar','Q',18],[titles[3],'Evidencias propuestas para revisión','F',35],
 [titles[4],'Aceptación de documentación por área','L',100],[titles[5],'Determinación de liberación empresarial','K',71]
])baseSheet(wb,name,title,col,rows);
const matrix=wb.worksheets.getItem(titles[0]);
matrix.getRange('A5:E5').values=[['Áreas completas',null,'Áreas requeridas',15,'Avance']];
matrix.getRange('B5').formulas=[['=SUM(P8:P22)']];matrix.getRange('F5').formulas=[['=B5/D5']];matrix.getRange('F5').setNumberFormat('0%');
matrix.getRange('A5:F5').format.wrapText=true;matrix.getRange('A5:F5').format.rowHeight=42;
header(matrix,'A7:P7',['ID','Área de aceptación','Representante autorizado','Rol / cargo','Organización','Base de autoridad','Fecha de decisión','Decisión','Evidencia efectivamente revisada','Firma / aprobación','Condiciones IDs','Comentarios','Responsable de condición','Fecha objetivo','Evidencias propuestas (no revisadas)','Registro completo']);
matrix.getRange('A8:P22').values=data.areas.map(a=>[a.id,a.name,'','','','','','','','','','','','',a.evidence_proposed.join(', '),null]);
for(let r=8;r<=22;r++)matrix.getRange(`P${r}`).formulas=[[`=IF(AND(C${r}<>"",D${r}<>"",E${r}<>"",F${r}<>"",ISNUMBER(G${r}),OR(H${r}="ACCEPT",H${r}="ACCEPT_WITH_CONDITIONS",H${r}="REJECT"),I${r}<>"",J${r}<>"",IF(H${r}="ACCEPT_WITH_CONDITIONS",IF(COUNTIFS('${titles[1]}'!$A$8:$A$15,K${r})=1,AND(COUNTIFS('${titles[1]}'!$A$8:$A$15,K${r},'${titles[1]}'!$P$8:$P$15,1,'${titles[1]}'!$J$8:$J$15,"ACCEPTED_OPEN")>0,ISNUMBER(SEARCH(","&A${r}&",",","&SUBSTITUTE(INDEX('${titles[1]}'!$B$8:$B$15,MATCH(K${r},'${titles[1]}'!$A$8:$A$15,0))," ","")&",")),M${r}<>"",ISNUMBER(N${r})),FALSE),TRUE),IF(H${r}="REJECT",COUNTIFS('${titles[5]}'!$B$41:$B$55,A${r},'${titles[5]}'!$K$41:$K$55,1)>0,TRUE)),1,0)`]];
table(matrix,'A7:P22','BusinessSignoffAreas');inputs(matrix,'C8:N22');matrix.getRange('G8:G22').setNumberFormat('dd/mm/yyyy');matrix.getRange('N8:N22').setNumberFormat('dd/mm/yyyy');
matrix.getRange('H8:H22').dataValidation={rule:{type:'list',values:['ACCEPT','ACCEPT_WITH_CONDITIONS','REJECT']}};
matrix.getRange('K8:K22').dataValidation={rule:{type:'list',formula1:`'${titles[1]}'!$A$8:$A$15`}};
matrix.getRange('A8:P22').format.rowHeight=62;matrix.getRange('A8:P22').format.wrapText=true;
widths(matrix,[['A',10],['B',39],['C',26],['D',23],['E',24],['F',32],['G',18],['H',29],['I',38],['J',36],['K',25],['L',38],['M',28],['N',18],['O',32],['P',18]],30);
header(matrix,'A26:H26',['ID','Reconocimiento obligatorio','Áreas responsables','Respuesta autorizada','Representante','Base de autoridad','Fecha','Evidencia aprobación']);
matrix.getRange('A27:H29').values=[
 ['ACK01','S3-006: el filtro por responsable puede omitir Project.','BA02 / BA15','','','','',''],
 ['ACK02','4 MISSING no bloqueantes: environmental-social-readiness, land-access-readiness, stakeholder-readiness, technical-assurance. No se consideran satisfechos.','BA14','','','','',''],
 ['ACK03','Controles: aislamiento tenant, RBAC, SoD e independencia de publicación, QRA, Gate, FID, validación Class B e inicialización / activación.','BA01 / BA02 / BA14 / BA15','','','','',''],
];inputs(matrix,'D27:H29');yesNo(matrix,'D27:D29');matrix.getRange('G27:G29').setNumberFormat('dd/mm/yyyy');matrix.getRange('A27:H29').format.wrapText=true;matrix.getRange('A27:H29').format.rowHeight=110;
matrix.freezePanes.freezeRows(7);matrix.freezePanes.freezeColumns(2);statusCf(matrix,'H8:H22');

const issues=[...data.findings,...data.ui_observations];
const conditions=wb.worksheets.getItem(titles[1]);
conditions.getRange('A5').values=[['Propuestas sin aceptación. ¿Bloquea liberación? describe el impacto vigente. Una resolución aprobada requiere documentar NO para dejar de bloquear.']];
header(conditions,'A7:P7',['Condición ID','Áreas propuestas','Hallazgo / observación ID','Descripción','Severidad técnica','¿Bloquea liberación?','Workaround propuesto','Responsable acordado','Fecha objetivo acordada','Estado empresarial','Aprobación evidencia','Persona autorizada','Base de autoridad','Fecha decisión','Justificación clasificación','Condición documentada']);
const mappedAreas={'UAT-S3-006':'BA02, BA15','UAT-S4-001':'BA01, BA02','UAT-S4-002':'BA08','UAT-S4-003':'BA02','UAT-S4-004':'BA14','UAT-S4-005':'BA01, BA02','OBS-UI-01':'BA14','OBS-UI-02':'BA15'};
conditions.getRange('A8:P15').values=issues.map((f,i)=>[`COND${String(i+1).padStart(2,'0')}`,mappedAreas[f.id],f.id,f.title,f.severity??'OBSERVATION','',f.workaround,'','','PROPOSED_NOT_ACCEPTED','','','','','',null]);
for(let r=8;r<=15;r++)conditions.getRange(`P${r}`).formulas=[[`=IF(AND(OR(J${r}="ACCEPTED_OPEN",J${r}="RESOLVED"),F${r}="NO",G${r}<>"",H${r}<>"",ISNUMBER(I${r}),K${r}<>"",L${r}<>"",M${r}<>"",ISNUMBER(N${r})),1,0)`]];
header(conditions,'Q7:Q7',['S1 / S2 abierto']);
for(let r=8;r<=15;r++)conditions.getRange(`Q${r}`).formulas=[[`=IF(AND(OR(LEFT(E${r},2)="S1",LEFT(E${r},2)="S2"),J${r}="ACCEPTED_OPEN"),1,0)`]];
table(conditions,'A7:Q15','BusinessAcceptanceConditions');inputs(conditions,'F8:F15');inputs(conditions,'H8:O15');yesNo(conditions,'F8:F15');conditions.getRange('J8:J15').dataValidation={rule:{type:'list',values:['PROPOSED_NOT_ACCEPTED','ACCEPTED_OPEN','RESOLVED','REJECTED']}};conditions.getRange('I8:I15').setNumberFormat('dd/mm/yyyy');conditions.getRange('N8:N15').setNumberFormat('dd/mm/yyyy');conditions.getRange('A8:Q15').format.wrapText=true;conditions.getRange('A8:Q15').format.rowHeight=110;
widths(conditions,[['A',15],['B',24],['C',22],['D',56],['E',20],['F',20],['G',68],['H',28],['I',20],['J',29],['K',35],['L',28],['M',34],['N',18],['O',45],['P',20],['Q',20]],18);conditions.freezePanes.freezeRows(7);conditions.freezePanes.freezeColumns(3);statusCf(conditions,'J8:J15');

const findings=wb.worksheets.getItem(titles[2]);findings.getRange('A5').values=[['6 hallazgos abiertos y 2 observaciones UI. Sin cierre ni aceptación por silencio.']];
header(findings,'A7:P7',['ID','Severidad técnica','Estado técnico','Impacto empresarial divulgado','Workaround propuesto','Evidencias propuestas','Disposición empresarial','Justificación / clasificación','Responsable acordado','Fecha objetivo','Representante autorizado','Base autoridad','Fecha decisión','Evidencia aprobación','Reconocimiento explícito','Revisión completa']);
findings.getRange('A8:P15').values=issues.map(f=>[f.id,f.severity??'OBSERVATION',f.status,f.impact,f.workaround,f.evidence_ids.join(', '),'','','','','','','','','',null]);
for(let r=8;r<=15;r++)findings.getRange(`P${r}`).formulas=[[`=IF(AND(OR(G${r}="ACCEPT_CONDITION",G${r}="RECLASSIFY_WITH_JUSTIFICATION"),H${r}<>"",I${r}<>"",ISNUMBER(J${r}),K${r}<>"",L${r}<>"",ISNUMBER(M${r}),N${r}<>"",O${r}="YES"),1,0)`]];
header(findings,'Q7:Q7',['S1 / S2 abierto']);
for(let r=8;r<=15;r++)findings.getRange(`Q${r}`).formulas=[[`=IF(AND(OR(LEFT(B${r},2)="S1",LEFT(B${r},2)="S2"),C${r}="OPEN"),1,0)`]];
table(findings,'A7:Q15','BusinessKnownFindings');inputs(findings,'G8:O15');findings.getRange('G8:G15').dataValidation={rule:{type:'list',values:['ACCEPT_CONDITION','REJECT_RELEASE','RECLASSIFY_WITH_JUSTIFICATION']}};yesNo(findings,'O8:O15');findings.getRange('J8:J15').setNumberFormat('dd/mm/yyyy');findings.getRange('M8:M15').setNumberFormat('dd/mm/yyyy');findings.getRange('A8:Q15').format.wrapText=true;findings.getRange('A8:Q15').format.rowHeight=130;findings.freezePanes.freezeRows(7);findings.freezePanes.freezeColumns(3);
widths(findings,[['A',22],['B',18],['C',23],['D',69],['E',66],['F',24],['G',38],['H',46],['I',28],['J',18],['K',28],['L',34],['M',18],['N',36],['O',22],['P',18],['Q',20]],18);statusCf(findings,'G8:G15');

const evidence=wb.worksheets.getItem(titles[3]);evidence.getRange('A5').values=[['Referencias propuestas. Este registro no declara evidencia revisada por personas.']];header(evidence,'A7:F7',['ID','Evidencia','Tipo','Corte','Referencia controlada','Alcance y límite']);
const evidenceEnd=7+data.evidence_register.length;
evidence.getRange(`A8:F${evidenceEnd}`).values=data.evidence_register.map(e=>[e.id,e.title,e.kind,new Date(`${e.cut}T12:00:00Z`),e.path,e.boundary]);table(evidence,`A7:F${evidenceEnd}`,'BusinessEvidenceRegister');evidence.getRange(`D8:D${evidenceEnd}`).setNumberFormat('dd/mm/yyyy');evidence.getRange(`A8:F${evidenceEnd}`).format.wrapText=true;evidence.getRange(`A8:F${evidenceEnd}`).format.rowHeight=82;widths(evidence,[['A',10],['B',40],['C',29],['D',17],['E',76],['F',82]],35);evidence.freezePanes.freezeRows(7);evidence.freezePanes.freezeColumns(1);

const docs=wb.worksheets.getItem(titles[4]);docs.getRange('A5').values=[['90 decisiones documentales pendientes: 6 documentos por cada una de las 15 áreas.']];header(docs,'A7:L7',['Área ID','Área','Documento ID','Documento / revisión','Evidencia propuesta','Decisión documental','Correcciones / impacto','Representante autorizado','Base autoridad','Fecha revisión','Firma / aprobación','Registro completo']);
const docRows=[];for(const a of data.areas)for(const d of data.required_documents)docRows.push([a.id,a.name,d.id,`${d.name}\n${d.revision}`,d.evidence_id,'','','','','','',null]);docs.getRange('A8:L97').values=docRows;
for(let r=8;r<=97;r++)docs.getRange(`L${r}`).formulas=[[`=IF(AND(OR(F${r}="ACCEPTABLE",F${r}="ACCEPTABLE_WITH_CORRECTIONS"),H${r}<>"",I${r}<>"",ISNUMBER(J${r}),K${r}<>"",IF(F${r}="ACCEPTABLE_WITH_CORRECTIONS",G${r}<>"",TRUE)),1,0)`]];
table(docs,'A7:L97','BusinessDocumentAcceptance');inputs(docs,'F8:K97');docs.getRange('F8:F97').dataValidation={rule:{type:'list',values:['ACCEPTABLE','ACCEPTABLE_WITH_CORRECTIONS','NOT_ACCEPTABLE']}};docs.getRange('J8:J97').setNumberFormat('dd/mm/yyyy');docs.getRange('A8:L97').format.wrapText=true;docs.getRange('A8:L97').format.rowHeight=72;widths(docs,[['A',12],['B',35],['C',16],['D',58],['E',18],['F',37],['G',48],['H',29],['I',36],['J',18],['K',36],['L',18]],100);docs.freezePanes.freezeRows(7);docs.freezePanes.freezeColumns(3);statusCf(docs,'F8:F97');

const final=wb.worksheets.getItem(titles[5]);
header(final,'A4:D4',['Control','Resultado','Referencia / regla','Alcance']);
const metrics=[
 ['Áreas completas',`=SUM('${titles[0]}'!P8:P22)`,'15 áreas con representante y aprobación explícita.','No basta escribir ACCEPT.'],
 ['Áreas requeridas',15,'Prompt sección5','No se infieren representantes.'],
 ['Avance', '=B5/B6','Completas / requeridas','Firma pendiente = no aceptación.'],
 ['ACCEPT registrado',`=COUNTIFS('${titles[0]}'!H8:H22,"ACCEPT",'${titles[0]}'!P8:P22,1)`,'Solo registros completos.','No cuenta texto sin autoridad/evidencia.'],
 ['ACCEPT_WITH_CONDITIONS registrado',`=COUNTIFS('${titles[0]}'!H8:H22,"ACCEPT_WITH_CONDITIONS",'${titles[0]}'!P8:P22,1)`,'Solo registros completos.','Condiciones deben existir y ser no bloqueantes.'],
 ['REJECT autorizado',`=COUNTIFS('${titles[0]}'!H8:H22,"REJECT",'${titles[0]}'!P8:P22,1)`,'Un rechazo material impide liberación.','Registrar detalle en tabla inferior.'],
 ['Áreas pendientes','=B6-B5','Área sin registro completo.','0/15 inicialmente.'],
 ['Condiciones aceptadas abiertas',`=COUNTIFS('${titles[1]}'!J8:J15,"ACCEPTED_OPEN",'${titles[1]}'!P8:P15,1)`,'No incluye propuestas.','Responsable y fecha deben ser acordados.'],
 ['Condiciones documentadas no bloqueantes',`=SUM('${titles[1]}'!P8:P15)`,'8 propuestas deben quedar expresamente dispuestas.','No se presupone aceptación.'],
 ['Condiciones aceptadas bloqueantes',`=COUNTIFS('${titles[1]}'!J8:J15,"ACCEPTED_OPEN",'${titles[1]}'!F8:F15,"YES",'${titles[1]}'!K8:K15,"<>",'${titles[1]}'!L8:L15,"<>",'${titles[1]}'!M8:M15,"<>",'${titles[1]}'!N8:N15,">0")`,'Condición abierta bloqueante con autoridad y aprobación.','RESOLVED con YES queda pendiente de aclarar, no rechazo automático.'],
 ['Hallazgos / observaciones revisados',`=SUM('${titles[2]}'!P8:P15)`,'8 registros con disposición, autoridad, owner y fecha.','S3-006 requiere reconocimiento explícito.'],
 ['Rechazos de hallazgo autorizados',`=COUNTIFS('${titles[2]}'!G8:G15,"REJECT_RELEASE",'${titles[2]}'!H8:H15,"<>",'${titles[2]}'!K8:K15,"<>",'${titles[2]}'!L8:L15,"<>",'${titles[2]}'!M8:M15,">0",'${titles[2]}'!N8:N15,"<>",'${titles[2]}'!O8:O15,"YES")`,'Rechazo documentado con razón, persona, autoridad y aprobación.','No cambia severidad técnica por fórmula.'],
 ['Documentos aceptables completos',`=SUM('${titles[4]}'!L8:L97)`,'6 documentos × 15 áreas = 90.','Correcciones deben estar descritas.'],
 ['Reconocimientos explícitos',`=COUNTIFS('${titles[0]}'!D27:D29,"YES",'${titles[0]}'!E27:E29,"<>",'${titles[0]}'!F27:F29,"<>",'${titles[0]}'!G27:G29,">0",'${titles[0]}'!H27:H29,"<>")`,'S3-006, cuatro MISSING, seguridad/SoD.','Datos y autoridad humanos no suministrados.'],
 ['Rechazos empresariales abiertos', '=SUM(K41:K55)','Registro inferior con aprobación y autoridad del área.','Sin rechazos aportados inicialmente.'],
];
final.getRange('A5:D19').values=metrics.map(([a,b,c,d])=>[a,typeof b==='string'&&b.startsWith('=')?null:b,c,d]);
metrics.forEach((m,i)=>{if(typeof m[1]==='string'&&m[1].startsWith('='))final.getRange(`B${i+5}`).formulas=[[m[1]]];});final.getRange('B7').setNumberFormat('0%');
// Runtime-baseline fields are supplied only by an actual read-only proof.
const runtimeSupplement=data.baseline_supplement_file?JSON.parse(await fs.readFile(path.join(root,data.baseline_supplement_file),'utf8')):null;
const privateProof=baseline.private_uat_runtime?.selected_business_state_currently_verified===true||(
  runtimeSupplement?.result==='PASS_CURRENT_PERSISTED_CONTINUITY_READ_ONLY'
  &&runtimeSupplement.selected_matches_delivery_20261016===true
  &&runtimeSupplement.all_eight_table_counts_and_row_md5_match===true
  &&runtimeSupplement.alembic_head==='20261011_0068');
header(final,'A23:D23',['Baseline y requisitos','Resultado','Referencia','Nota']);
final.getRange('A24:D31').values=[
 ['Commit congelado',baseline.frozen_commit,'E08 / baseline.json','Sin cambios funcionales durante esta preparación.'],
 ['Alembic head', '20261011_0068','E08','Sin migración nueva.'],
 ['Código sin cambios',baseline.code_baseline_unchanged?'UNCHANGED':'NOT_VERIFIED','E08','Hashes de producto y fixtures comparados.'],
 ['Estado UAT persistente actual',privateProof?'UNCHANGED_OR_REVALIDATED':'NOT_CURRENTLY_VERIFIED',runtimeSupplement?'E23':'E08','Continuidad material SQL18. No es nueva ejecución E2E ni cálculo de readiness.'],
 ['Project14 preservado',baseline.operational?.matches_previous_observation?'UNCHANGED':'NOT_VERIFIED','E08','id14 / PRJ-PPMIS / PRJ-PYP-PPMIS / active / versión1.'],
 ['S1 / S2 abiertos técnicos',0,'E06 / E07','Baseline técnico; reclasificación empresarial requiere nueva revisión.'],
 ['Baseline posterior revalidado', '', '', 'Al cambiar código/política, invalidar afectadas y documentar retest.'],
 ['Aprobación documental del paquete', '', '', 'No sustituye las 90 revisiones por área.'],
];
final.getRange('B29').formulas=[[`=SUM('${titles[2]}'!Q8:Q15,'${titles[1]}'!Q8:Q15)`]];
inputs(final,'B30:C31');final.getRange('B30').dataValidation={rule:{type:'list',values:['REVALIDATED']}};final.getRange('B31').dataValidation={rule:{type:'list',values:['ASSEMBLED_AND_REVIEWED']}};
header(final,'A33:D33',['Conclusión calculada','Resultado','Regla','Acción']);
final.getRange('A34').values=[['Decisión empresarial']];
final.getRange('B34').formulas=[[`=IF(OR(B10>0,B14>0,B16>0,B19>0),"BUSINESS_REJECTED",IF(OR(B5<15,B13<8,B15<8,B17<90,B18<3,AND(B12>0,B9=0),AND(B9>0,B12=0),B26<>"UNCHANGED",AND(B27<>"UNCHANGED_OR_REVALIDATED",OR(B30<>"REVALIDATED",C30="")),B28<>"UNCHANGED",B29>0,B31<>"ASSEMBLED_AND_REVIEWED",C31=""),"UAT_SIGNOFF_PENDING",IF(B9>0,"BUSINESS_ACCEPTED_WITH_CONDITIONS","BUSINESS_ACCEPTED")))`]];
final.getRange('C34:D34').values=[['Falla cerrada ante firmas, evidencias o disposiciones pendientes.','No existe autorización empresarial aportada.']];
final.getRange('A35').values=[['Estado exacto']];final.getRange('B35').formulas=[['=IF(B34="BUSINESS_REJECTED","STRATEGIC_MACROPROCESS_BUSINESS_UAT_REJECTED",IF(B34="BUSINESS_ACCEPTED","STRATEGIC_MACROPROCESS_READY_FOR_BUSINESS_RELEASE",IF(B34="BUSINESS_ACCEPTED_WITH_CONDITIONS","STRATEGIC_MACROPROCESS_READY_FOR_BUSINESS_RELEASE_WITH_CONDITIONS","STRATEGIC_MACROPROCESS_TECHNICALLY_READY_UAT_SIGNOFF_PENDING")))']];
final.getRange('A36').values=[['Único siguiente incremento']];final.getRange('B36').formulas=[['=IF(B34="BUSINESS_REJECTED","REMEDIATE THE SMALLEST BUSINESS-REJECTED GAP",IF(OR(B34="BUSINESS_ACCEPTED",B34="BUSINESS_ACCEPTED_WITH_CONDITIONS"),"BEGIN OPERATIONAL MACROPROCESS DESIGN","COMPLETE AUTHORIZED BUSINESS UAT SIGN-OFF"))']];
header(final,'A40:J40',['Rechazo ID','Área ID','Representante','Motivo material','Flujo afectado / evidencia','Severidad','Remediación requerida','Estado','Impacto liberación','Aprobación referencia']);
final.getRange('A41:J55').values=Array.from({length:15},()=>Array(10).fill(''));inputs(final,'A41:J55');final.getRange('H41:H55').dataValidation={rule:{type:'list',values:['OPEN','RESOLVED','SUPERSEDED_BY_AUTHORIZED_GOVERNANCE']}};
header(final,'K40:K40',['Registro autorizado completo']);
for(let r=41;r<=55;r++)final.getRange(`K${r}`).formulas=[[`=IF(AND(A${r}<>"",B${r}<>"",C${r}<>"",D${r}<>"",E${r}<>"",F${r}<>"",G${r}<>"",H${r}="OPEN",I${r}<>"",J${r}<>"",COUNTIFS('${titles[0]}'!$A$8:$A$22,B${r},'${titles[0]}'!$C$8:$C$22,C${r},'${titles[0]}'!$D$8:$D$22,"<>",'${titles[0]}'!$E$8:$E$22,"<>",'${titles[0]}'!$F$8:$F$22,"<>",'${titles[0]}'!$G$8:$G$22,">0",'${titles[0]}'!$J$8:$J$22,"<>")>0),1,0)`]];
final.getRange('A5:D20').format.wrapText=true;final.getRange('A5:D20').format.rowHeight=43;final.getRange('A24:D31').format.wrapText=true;final.getRange('A24:D31').format.rowHeight=45;final.getRange('A34:D36').format.wrapText=true;final.getRange('A34:D36').format.rowHeight=72;final.getRange('A41:J55').format.wrapText=true;final.getRange('A41:J55').format.rowHeight=60;
widths(final,[['A',40],['B',68],['C',54],['D',67],['E',45],['F',18],['G',45],['H',31],['I',36],['J',42],['K',26]],71);statusCf(final,'B34:B36');
header(final,'A59:F59',['Validación técnica histórica 16 Oct','PASS','FAIL','ERROR','SKIP','Evidencia']);
const testOrder=[['Broad backend','broad','E09'],['Chromium','browser','E10'],['Controlled Class B','class_b','E14'],['Post FID bridge','bridge','E07'],['Canonical guards','canonical','E07'],['Post activation currentness','postactivation','E07'],['Frontend presentation','frontend','E07'],['Legacy FID focused','legacy','E07']];
final.getRange('A60:F67').values=testOrder.map(([label,key,ref])=>{const c=baseline.historical_test_counts[key];return[label,c.PASS,c.FAIL,c.ERROR,c.SKIP,ref];});
final.getRange('A60:F67').format.rowHeight=26;final.getRange('A69').values=[['Los enfocados no se suman al broad. Continuidad SQL 18 Oct no es nueva ejecución E2E ni aceptación humana.']];

wb.recalculate();
// Exercise the actual spreadsheet formulas only in memory, then restore all
// editable values before rendering/export. No simulated acceptance is saved.
const mutable=[
 [matrix,'C8:N22'],[matrix,'D27:H29'],[conditions,'F8:F15'],[conditions,'H8:O15'],
 [findings,'G8:O15'],[findings,'B8:B15'],[conditions,'E8:E15'],[docs,'F8:K97'],[final,'B30:C31'],[final,'A41:J55'],
];
const originals=mutable.map(([s,r])=>[s,r,s.getRange(r).values]);
const restore=()=>{for(const[s,r,values]of originals)s.getRange(r).values=values;wb.recalculate();};
const simulatedDate=new Date('2026-10-18T12:00:00Z');
function completeAreas(count=15,decision='ACCEPT'){
  for(let i=0;i<count;i++)matrix.getRange(`C${i+8}:N${i+8}`).values=[[
    'SIMULATED_NOT_SIGNED','SIMULATED_ROLE','SIMULATED_ORG','SIMULATED_AUTHORITY',simulatedDate,
    decision,'SIMULATED_REVIEW_E01','SIMULATED_APPROVAL',decision==='ACCEPT_WITH_CONDITIONS'?'COND01':'','',
    decision==='ACCEPT_WITH_CONDITIONS'?'SIMULATED_OWNER':'',decision==='ACCEPT_WITH_CONDITIONS'?simulatedDate:'',
  ]];
}
function completeReviewPrerequisites(){
  for(let r=8;r<=15;r++){
    conditions.getRange(`F${r}`).values=[['NO']];
    conditions.getRange(`H${r}:O${r}`).values=[['SIMULATED_OWNER',simulatedDate,'RESOLVED','SIMULATED_APPROVAL','SIMULATED_REP','SIMULATED_AUTHORITY',simulatedDate,'SIMULATED_REVIEW']];
    findings.getRange(`G${r}:O${r}`).values=[['ACCEPT_CONDITION','SIMULATED_JUSTIFICATION','SIMULATED_OWNER',simulatedDate,'SIMULATED_REP','SIMULATED_AUTHORITY',simulatedDate,'SIMULATED_APPROVAL','YES']];
  }
  for(let r=8;r<=97;r++)docs.getRange(`F${r}:K${r}`).values=[['ACCEPTABLE','','SIMULATED_REP','SIMULATED_AUTHORITY',simulatedDate,'SIMULATED_APPROVAL']];
  for(let r=27;r<=29;r++)matrix.getRange(`D${r}:H${r}`).values=[['YES','SIMULATED_REP','SIMULATED_AUTHORITY',simulatedDate,'SIMULATED_APPROVAL']];
  final.getRange('B30:C31').values=[['REVALIDATED','SIMULATED_PROOF_NOT_APPROVAL'],['ASSEMBLED_AND_REVIEWED','SIMULATED_PACK_REVIEW']];
}
const scenarios=[];
function scenario(name,prepare,expected){
  restore();prepare();wb.recalculate();
  const actual=final.getRange('B34').values[0][0];
  const completed=final.getRange('B5').values[0][0];
  scenarios.push({name,expected,actual,completed,pass:actual===expected,scope:'DISPOSABLE_IN_MEMORY_SIMULATION_NOT_SAVED'});
  if(actual!==expected){
    matrix.getRange('Q9:U9').formulas=[[
      `=COUNTIFS('${titles[1]}'!$A$8:$A$15,K9,'${titles[1]}'!$B$8:$B$15,"*BA02*",'${titles[1]}'!$P$8:$P$15,1,'${titles[1]}'!$J$8:$J$15,"ACCEPTED_OPEN")`,
      `=COUNTIFS('${titles[1]}'!$A$8:$A$15,K9,'${titles[1]}'!$P$8:$P$15,1,'${titles[1]}'!$J$8:$J$15,"ACCEPTED_OPEN")`,
      `=ISNUMBER(SEARCH(A9,INDEX('${titles[1]}'!$B$8:$B$15,MATCH(K9,'${titles[1]}'!$A$8:$A$15,0))))`,
      '=ISNUMBER(N9)','=M9<>""',
    ]];wb.recalculate();
    console.error(JSON.stringify({scenario:name,actual,expected,matrixRow9:matrix.getRange('A9:P9').values,condition:conditions.getRange('A8:P8').values,metrics:final.getRange('A5:B31').values}));
    console.error(JSON.stringify({probe:matrix.getRange('Q9:U9').values}));
    throw new Error(`Formula scenario ${name}: ${actual} != ${expected}`);
  }
}
scenario('All fields blank',()=>{},'UAT_SIGNOFF_PENDING');
scenario('ACCEPT text only',()=>{matrix.getRange('H8:H22').values=[['ACCEPT']];},'UAT_SIGNOFF_PENDING');
scenario('14 of 15 complete',()=>{completeReviewPrerequisites();completeAreas(14);},'UAT_SIGNOFF_PENDING');
scenario('15 ACCEPT but one missing approval',()=>{completeReviewPrerequisites();completeAreas();matrix.getRange('J22').values=[['']];},'UAT_SIGNOFF_PENDING');
scenario('15 ACCEPT but findings unreviewed',()=>{completeAreas();},'UAT_SIGNOFF_PENDING');
scenario('Authorized material REJECT',()=>{completeAreas();matrix.getRange('H8').values=[['REJECT']];final.getRange('A41:J41').values=[['SIMULATED_REJ','BA01','SIMULATED_NOT_SIGNED','SIMULATED_REASON','SIMULATED_WORKFLOW_EVIDENCE','S3','SIMULATED_REMEDIATION','OPEN','SIMULATED_MATERIAL_IMPACT','SIMULATED_APPROVAL']];},'BUSINESS_REJECTED');
scenario('Accepted release-blocking condition',()=>{completeReviewPrerequisites();completeAreas();conditions.getRange('F8').values=[['YES']];conditions.getRange('J8').values=[['ACCEPTED_OPEN']];},'BUSINESS_REJECTED');
scenario('Nonblocking condition missing owner/date',()=>{completeReviewPrerequisites();completeAreas();conditions.getRange('H8:I8').values=[['','']];},'UAT_SIGNOFF_PENDING');
scenario('All ACCEPT and all review obligations satisfied',()=>{completeReviewPrerequisites();completeAreas();},'BUSINESS_ACCEPTED');
function markAwc(row=9,condition='COND01'){
  matrix.getRange(`H${row}`).values=[['ACCEPT_WITH_CONDITIONS']];matrix.getRange(`K${row}`).values=[[condition]];
  matrix.getRange(`M${row}:N${row}`).values=[['SIMULATED_OWNER',simulatedDate]];
}
scenario('Documented nonblocking accepted condition in authorized area',()=>{completeReviewPrerequisites();conditions.getRange('J8').values=[['ACCEPTED_OPEN']];completeAreas();markAwc();},'BUSINESS_ACCEPTED_WITH_CONDITIONS');
scenario('All approvals but missing four-MISSING acknowledgment',()=>{completeReviewPrerequisites();completeAreas();matrix.getRange('D28').values=[['']];},'UAT_SIGNOFF_PENDING');
scenario('All approvals but missing document approval',()=>{completeReviewPrerequisites();completeAreas();docs.getRange('K97').values=[['']];},'UAT_SIGNOFF_PENDING');
scenario('REJECT text without material rejection register',()=>{completeReviewPrerequisites();completeAreas();matrix.getRange('H8').values=[['REJECT']];},'UAT_SIGNOFF_PENDING');
scenario('All 15 ACCEPT cannot silently become WITH_CONDITIONS',()=>{completeReviewPrerequisites();completeAreas();conditions.getRange('J8').values=[['ACCEPTED_OPEN']];},'UAT_SIGNOFF_PENDING');
scenario('AWC unknown condition ID',()=>{completeReviewPrerequisites();completeAreas();conditions.getRange('J8').values=[['ACCEPTED_OPEN']];markAwc(9,'UNKNOWN');},'UAT_SIGNOFF_PENDING');
scenario('AWC condition belongs to a different area',()=>{completeReviewPrerequisites();completeAreas();conditions.getRange('J8').values=[['ACCEPTED_OPEN']];markAwc(10,'COND01');},'UAT_SIGNOFF_PENDING');
scenario('AWC without an accepted open condition',()=>{completeReviewPrerequisites();completeAreas();markAwc();},'UAT_SIGNOFF_PENDING');
scenario('RESOLVED condition with contradictory blocking YES stays pending',()=>{completeReviewPrerequisites();completeAreas();conditions.getRange('F8').values=[['YES']];},'UAT_SIGNOFF_PENDING');
scenario('Open S2 finding cannot be accepted away',()=>{completeReviewPrerequisites();completeAreas();findings.getRange('B8').values=[['S2 CRITICAL']];},'UAT_SIGNOFF_PENDING');
scenario('Accepted S2 condition cannot be treated as nonblocking release',()=>{completeReviewPrerequisites();completeAreas();conditions.getRange('J8').values=[['ACCEPTED_OPEN']];conditions.getRange('E8').values=[['S2 CRITICAL']];markAwc();},'UAT_SIGNOFF_PENDING');
restore();
if(final.getRange('B5').values[0][0]!==0||final.getRange('B34').values[0][0]!=='UAT_SIGNOFF_PENDING')throw new Error('Simulation not fully restored');
await fs.writeFile(path.join(qa,'formula-scenarios.json'),JSON.stringify({simulation_only:true,scenarios,all_pass:scenarios.every(s=>s.pass),restored_human_approvals:0,native_excel_not_executed:true},null,2));
const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:100},summary:'signoff final error scan'});
await fs.writeFile(path.join(qa,'tracker-formula-errors.ndjson'),errors.ndjson);
await inspect(wb,'current',[['01_Signoff_Matrix','A5:P22'],['06_Final_Release_Decision','A5:D36']]);
if(!process.argv.includes('--final-output-only'))await render(wb,'current',views);
await fs.mkdir(dir,{recursive:true});
await (await SpreadsheetFile.exportXlsx(wb)).save(path.join(dir,trackerName));

const trace=await SpreadsheetFile.importXlsx(await FileBlob.load(source));
const cases=trace.worksheets.getItem('02_UAT_Cases');
if(cases.getRange('AA7:AE58').values.flat().some(v=>v!==null&&v!==''&&v!==undefined))throw new Error('Trace successor destination occupied');
const mappingPath=path.join(root,'docs/validation/business-uat-signoff-20261018/uat-case-area-mapping.json');
const mapping=JSON.parse(await fs.readFile(mappingPath,'utf8'));
const caseData=cases.getRange('A8:Z58').values;
const mappingById=new Map(mapping.cases.map(c=>[c.case_id,c]));
if(mappingById.size!==51||caseData.some(r=>!mappingById.has(r[0])))throw new Error('51 exact UAT case mappings required');
cases.getRange('AA7:AE7').copyFrom(cases.getRange('V7:Z7'),'all');
cases.getRange('AA7:AE7').values=[['Área de aceptación empresarial','Decisión empresarial','Evidencia aprobación empresarial','Condición ID','Formulario / tracker propuesto']];
cases.getRange('AA8:AE58').copyFrom(cases.getRange('V8:Z58'),'all');
cases.getRange('AA8:AE58').values=caseData.map(r=>{const m=mappingById.get(r[0]);return[m.area_ids.join(', '),'','','',`${trackerName} / 01_Signoff_Matrix / ${m.area_ids.join(', ')}. Preparado sin aprobación.`];});
cases.getRange('AB8:AB58').dataValidation={rule:{type:'list',values:['ACCEPT','ACCEPT_WITH_CONDITIONS','REJECT']}};
for(const[c,w]of[['AA',35],['AB',29],['AC',44],['AD',24],['AE',78]])cases.getRange(`${c}1:${c}58`).format.columnWidth=w;
cases.getRange('AA7:AE58').format.wrapText=true;
cases.getRange('AA8:AE58').setNumberFormat('@');
trace.recalculate();
if(!process.argv.includes('--final-output-only'))await render(trace,'trace-current',[['02_UAT_Cases','AA7:AE15'],['02_UAT_Cases','AA35:AE39']]);
await (await SpreadsheetFile.exportXlsx(trace)).save(path.join(dir,sourceName));
if(digest(await fs.readFile(source))!==sourceHash)throw new Error('Immutable source changed');
await fs.writeFile(path.join(qa,'build-manifest.json'),JSON.stringify({source,source_sha256:sourceHash,data_sha256:digest(await fs.readFile(dataPath)),baseline_sha256:digest(await fs.readFile(baselinePath)),tracker:path.join(dir,trackerName),traceability:path.join(dir,sourceName),human_approvals:0,formula_engine:'Artifact Tool (not native Excel)',created_at:new Date().toISOString()},null,2));
console.log(JSON.stringify({mode,tracker:path.join(dir,trackerName),traceability:path.join(dir,sourceName),sourceUnchanged:true}));
