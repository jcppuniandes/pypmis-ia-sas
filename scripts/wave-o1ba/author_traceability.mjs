import fs from "node:fs/promises";
import path from "node:path";
import { Workbook, SpreadsheetFile } from "@oai/artifact-tool";
import { buildTraceability, renderTraceability } from "./build_traceability.mjs";

// The live session is bound to the retained O1A book and has no documented
// separate-book creation option. A failed callback was rolled back and its
// original sheet inspected. Keep that book intact and author this new file.
const root=path.resolve(import.meta.dirname,"../..");
const workbook=Workbook.create();
console.log(JSON.stringify(await buildTraceability(workbook)));
console.log(JSON.stringify(await renderTraceability(workbook)));
const output=path.join(root,"outputs/wave-o1ba-20261020/P&Pmis_Wave_O1B_A_Scope_Foundation_Traceability.xlsx");
await fs.mkdir(path.dirname(output),{recursive:true});
await (await SpreadsheetFile.exportXlsx(workbook)).save(output);
console.log(JSON.stringify({output}));
