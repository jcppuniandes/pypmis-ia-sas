import { createRequire } from "node:module";
import fs from "node:fs/promises";
import path from "node:path";
const root=path.resolve(import.meta.dirname,"../..");
const {chromium,request}=createRequire(path.join(root,"frontend/package.json"))("@playwright/test");
const fixture=JSON.parse(await fs.readFile(path.join(root,"outputs/.qa/wave-o1ba-20261020/browser-fixture-release3.json"),"utf8"));
const api=await request.newContext();
const user=fixture.users.admin;
const response=await api.post("http://127.0.0.1:8852/api/v1/auth/login",{data:{email:user.email,tenant_id:user.tenant_id,password:"O1ba-disposable-only!"}});
if(response.status()!==200)throw new Error(`Login status ${response.status()}`);
const session=await response.json();
const browser=await chromium.launch({headless:true});
try{
  const context=await browser.newContext();
  await context.addInitScript(value=>localStorage.setItem("pypmis_auth",JSON.stringify({state:{token:value.access_token,user:value.user},version:0})),session);
  const page=await context.newPage();
  const errors=[];
  page.on("pageerror",error=>errors.push(error.message));
  page.on("requestfailed",request=>errors.push(`${request.method()} ${request.url()} ${request.failure()?.errorText}`));
  await page.goto("http://127.0.0.1:5512/app");
  await page.waitForLoadState("networkidle");
  console.log(JSON.stringify({url:page.url(),errors,body:(await page.locator("body").innerText()).slice(0,2400)}));
  await page.screenshot({path:path.join(root,"outputs/.qa/wave-o1ba-20261020/browser-start-diagnostic.png"),fullPage:true});
}finally{await browser.close();await api.dispose();}
