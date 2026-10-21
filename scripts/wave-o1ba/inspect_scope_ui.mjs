import { createRequire } from "node:module";
import fs from "node:fs/promises";
import path from "node:path";
const root = path.resolve(import.meta.dirname, "../..");
const require = createRequire(path.join(root, "frontend/package.json"));
const { chromium, request } = require("@playwright/test");
const fixture = JSON.parse(await fs.readFile(path.join(root, "outputs/.qa/wave-o1ba-20261020/browser-fixture-release.json"), "utf8"));
const api = await request.newContext();
const user = fixture.users.admin;
const login = await api.post("http://127.0.0.1:8852/api/v1/auth/login", {data:{email:user.email, tenant_id:user.tenant_id, password:"O1ba-disposable-only!"}});
if(login.status()!==200) throw new Error(`Login status ${login.status()}`);
const session = await login.json();
const browser = await chromium.launch({headless:true});
try {
  const context = await browser.newContext();
  await context.addInitScript(value=>localStorage.setItem("pypmis_auth",JSON.stringify({state:{token:value.access_token,user:value.user},version:0})),session);
  const page = await context.newPage();
  await page.goto(`http://127.0.0.1:5512/workspaces/${fixture.workspaces.direct.id}/scope-manager`);
  await page.getByLabel("Scope Code desde BIM",{exact:true}).waitFor({timeout:60000});
  await page.getByLabel("Seleccionar BIM Wall 1", {exact:true}).check();
  await page.getByLabel("Seleccionar BIM Wall 2", {exact:true}).check();
  const labels = await page.locator("label").evaluateAll(nodes=>nodes.map(node=>({label:node.textContent, tag:node.querySelector("input,select,textarea")?.tagName, options:[...node.querySelectorAll("option")].map(option=>({text:option.textContent,value:option.value}))})));
  console.log(JSON.stringify(labels.filter(value=>value.label?.includes("Medici")||value.label?.includes("Nature")||value.label?.includes("Cantidad"))));
  await page.screenshot({path:path.join(root,"outputs/.qa/wave-o1ba-20261020/inspect-model-ui.png"),fullPage:true});
} finally {await browser.close();await api.dispose();}
