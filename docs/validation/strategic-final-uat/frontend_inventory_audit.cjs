/* Read-only product audit. Writes only derived files beside this script with --write. */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const cp = require('node:child_process');

const repo = path.resolve(__dirname, '../../..');
const outputName = process.argv.find(value => value.startsWith('--output='))?.slice('--output='.length);
if (outputName && !/^[a-z0-9-]+$/.test(outputName)) throw new Error('Output must be a local descriptive directory name.');
const outputDir = outputName ? path.join(__dirname, outputName) : __dirname;
const src = path.join(repo, 'frontend/src');
const ts = require(path.join(repo, 'frontend/node_modules/typescript'));
const slash = value => value.replaceAll('\\', '/');
const relative = value => slash(path.relative(repo, value));
const read = file => fs.readFileSync(file, 'utf8');
function files(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap(entry => {
    const file = path.join(dir, entry.name);
    return entry.isDirectory() ? files(file) : /\.(tsx?|jsx?)$/.test(file) ? [file] : [];
  });
}
const sourceFiles = files(src);
const productionFiles = sourceFiles.filter(file => !/\.(test|spec)\./.test(file));
const parsed = new Map(sourceFiles.map(file => [file, ts.createSourceFile(file, read(file), ts.ScriptTarget.Latest, true)]));
function visit(node, callback) { callback(node); ts.forEachChild(node, child => visit(child, callback)); }
function resolveImport(from, module) {
  if (!module.startsWith('.')) return null;
  const base = path.resolve(path.dirname(from), module);
  return [base, `${base}.ts`, `${base}.tsx`, path.join(base, 'index.ts'), path.join(base, 'index.tsx')]
    .find(file => parsed.has(file)) || null;
}
function line(sf, node) { return sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1; }
const importGraph = new Map();
for (const [file, sf] of parsed) {
  const imports = [];
  visit(sf, node => {
    if ((ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) && node.moduleSpecifier &&
        ts.isStringLiteral(node.moduleSpecifier) && !node.importClause?.isTypeOnly) {
      const resolved = resolveImport(file, node.moduleSpecifier.text);
      if (resolved) imports.push(resolved);
    }
    if (ts.isCallExpression(node) && node.expression.kind === ts.SyntaxKind.ImportKeyword &&
        node.arguments[0] && ts.isStringLiteral(node.arguments[0])) {
      const resolved = resolveImport(file, node.arguments[0].text);
      if (resolved) imports.push(resolved);
    }
  });
  importGraph.set(file, [...new Set(imports)]);
}
function reachable(file, seen = new Set()) {
  if (!file || seen.has(file)) return seen;
  seen.add(file);
  for (const next of importGraph.get(file) || []) reachable(next, seen);
  return seen;
}
const dependencyCache = new Map();
function dependencySet(file) {
  if (!dependencyCache.has(file)) dependencyCache.set(file, reachable(file));
  return dependencyCache.get(file);
}
const isApiFile = file => /(?:\/api(?:\/index)?|\/policyApi)\.ts$/.test(slash(file)) || slash(file).includes('/src/api/');

// Evaluate only navigation metadata and the renderer registry. JSX imports are
// inert identifiers: no React component, network request, browser or API runs.
const moduleCache = new Map();
function evaluate(file, stubs = false) {
  if (moduleCache.has(file)) return moduleCache.get(file).exports;
  const module = { exports: {} };
  moduleCache.set(file, module);
  const output = ts.transpileModule(read(file), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  const localRequire = name => {
    if (name === 'react/jsx-runtime') return { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) };
    const target = resolveImport(file, name);
    if (!target) throw new Error(`Unsupported executable dependency ${name} from ${relative(file)}`);
    if (stubs && !relative(target).includes('/navigation/strategicNavigationBlueprint')) {
      const component = function InertComponent() {};
      component.auditSource = relative(target);
      return { __esModule: true, default: component, StrategicBreadcrumb: component };
    }
    return evaluate(target);
  };
  vm.runInNewContext(`(function(require,module,exports){${output}\n})`, {}, { filename: file })(localRequire, module, module.exports);
  return module.exports;
}
const blueprintFile = path.join(src, 'features/enterprise-strategy/navigation/strategicNavigationBlueprint.ts');
const outletFile = path.join(src, 'features/enterprise-strategy/StrategicViewOutlet.tsx');
const navigation = evaluate(blueprintFile);
const renderers = evaluate(outletFile, true).STRATEGIC_VIEW_RENDERERS;
const placeholderSource = read(path.join(src, 'navigation/applicationNavigation.ts')).split('export const EMPTY_SUBMODULE_VIEWS')[1];
const placeholders = new Set([...placeholderSource.matchAll(/"([a-z0-9-]+)"/g)].map(match => match[1]));
const flat = [];
function flatten(nodes, trail = []) {
  for (const node of nodes) {
    const branch = [...trail, node];
    flat.push({ node, branch });
    flatten(node.children, branch);
  }
}
flatten(navigation.strategicNavigationBlueprint);
const grouped = new Map();
for (const item of flat) {
  const key = `${item.node.mode}:${item.node.view}`;
  if (!grouped.has(key)) grouped.set(key, []);
  grouped.get(key).push(item);
}
const rows = [...navigation.strategicRouteRegistry()].map(([route, info]) => {
  const canonical = navigation.strategicNodeForView(info.view, info.mode);
  const n = canonical.node;
  const rendered = renderers[info.view]?.({ token: 'AUDIT_INERT', view: info.view, mode: info.mode, canConfigure: true, onNavigate() {} });
  const component = rendered?.type?.auditSource || null;
  const dependencies = dependencySet(component && path.join(repo, component));
  return {
    route, view: info.view, mode: info.mode.toUpperCase(), classification: n.classification,
    permission: n.permission, phase: n.phase, order: n.order,
    menuOrdinal: flat.findIndex(item => item.node.id === n.id),
    orderPath: canonical.trail.map(item => item.order),
    navigationTrail: canonical.trail.map(item => item.label).join(' > '),
    breadcrumb: navigation.strategicBreadcrumb(info.view, info.mode).join(' > '),
    component: component || (placeholders.has(info.view) ? 'frontend/src/App.tsx:EmptySubmoduleScreen' : 'UNRESOLVED'),
    componentStatus: component ? 'RENDERER_REGISTERED' : placeholders.has(info.view) ? 'EXPLICIT_PLACEHOLDER' : 'MISSING_RENDERER',
    used: true, duplicateNodeCount: grouped.get(`${info.mode}:${info.view}`).length,
    duplicateKind: grouped.get(`${info.mode}:${info.view}`).length > 1 ? 'ANCESTOR_LANDING_ALIAS_SAME_ROUTE' : 'NONE',
    removalCandidate: false,
    workspaceTypes: [...n.workspaceTypes], governanceModels: [...n.governanceModels],
    predecessorIds: [...n.predecessorIds], parallelGroup: n.parallelGroup, convergesInto: n.convergesInto,
    apiDependencies: [...dependencies].filter(isApiFile).map(relative).sort(),
    compactModuleHeader: [...dependencies].some(file => file.endsWith('CompactModuleHeader.tsx')),
    sourceAuthority: relative(blueprintFile), verification: 'STATIC_METADATA_NOT_BUSINESS_UAT',
  };
}).sort((a, b) => a.mode.localeCompare(b.mode) || a.menuOrdinal - b.menuOrdinal);
const nodes = flat.map(({ node: n, branch }) => ({
  id: n.id, label: n.label, mode: n.mode.toUpperCase(), phase: n.phase, order: n.order,
  route: n.route, view: n.view, classification: n.classification, permission: n.permission,
  depth: branch.length - 1, trail: branch.map(item => item.label).join(' > '),
  orderPath: branch.map(item => item.order),
  canonical: navigation.strategicNodeForView(n.view, n.mode).node.id === n.id,
  workspaceTypes: [...n.workspaceTypes], governanceModels: [...n.governanceModels],
  predecessorIds: [...n.predecessorIds], parallelGroup: n.parallelGroup, convergesInto: n.convergesInto,
}));
const hiddenRenderers = Object.keys(renderers).filter(view => !rows.some(row => row.view === view)).map(view => ({
  view, route: null, component: renderers[view]({ token: 'AUDIT_INERT', view, mode: 'user', canConfigure: true, onNavigate() {} })?.type?.auditSource,
  classification: 'REQUIRES_DEPRECATION',
  evidence: 'Renderer registered but strategicNodeForView has no canonical node in either mode; outlet returns null before renderer invocation.',
}));

// Inventory all client object methods, inherited governancePolicyApi methods,
// direct production property references, request templates and source locations.
// This is a CLIENT inventory, not a proof of server permission enforcement.
const routeApiDependencies = new Set(rows.flatMap(row => row.apiDependencies));
const apiFiles = productionFiles.filter(file => isApiFile(file) && (slash(file).includes('/features/') || routeApiDependencies.has(relative(file))));
const references = new Map();
for (const file of productionFiles) {
  const sf = parsed.get(file);
  visit(sf, node => {
    if (ts.isPropertyAccessExpression(node) && ts.isIdentifier(node.expression)) {
      const key = `${node.expression.text}.${node.name.text}`;
      if (!references.has(key)) references.set(key, []);
      references.get(key).push(`${relative(file)}:${line(sf, node)}`);
    }
  });
}
const policySf = parsed.get(path.join(src, 'features/risk-governance/policyApi.ts'));
let policyProperties = [];
visit(policySf, node => {
  if (ts.isFunctionDeclaration(node) && node.name?.text === 'governancePolicyApi') {
    visit(node, child => { if (ts.isReturnStatement(child) && child.expression && ts.isObjectLiteralExpression(child.expression)) policyProperties = [...child.expression.properties]; });
  }
});
const apiRows = [];
for (const file of apiFiles) {
  const sf = parsed.get(file);
  const constants = new Map();
  visit(sf, node => {
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.initializer && ts.isStringLiteral(node.initializer)) constants.set(node.name.text, node.initializer.text);
  });
  function pathText(expression, rootOverride) {
    let value = expression?.getText(sf) || 'UNKNOWN';
    if (rootOverride) value = value.replaceAll('${root}', rootOverride);
    for (const [key, replacement] of constants) value = value.replaceAll('${' + key + '}', replacement);
    return value;
  }
  function methodRow(objectName, prop, ownerSf = sf, rootOverride = null) {
    if (!ts.isPropertyAssignment(prop) && !ts.isMethodDeclaration(prop)) return;
    const method = prop.name.getText(ownerSf).replaceAll('"', '').replaceAll("'", '');
    const calls = [];
    visit(prop, node => {
      if (!ts.isCallExpression(node)) return;
      const expr = node.expression.getText(ownerSf);
      if (!/^(apiFetch|apiFetchWithResponse|listPage|list|request|fetch)/i.test(expr)) return;
      const endpointArg = expr === 'listPage' ? node.arguments[1] : node.arguments[0];
      let httpMethod = 'GET';
      visit(node, sub => {
        if (ts.isPropertyAssignment(sub) && sub.name.getText(ownerSf) === 'method') httpMethod = sub.initializer.getText(ownerSf).replaceAll('"', '').replaceAll("'", '');
      });
      let template = endpointArg?.getText(ownerSf) || 'UNKNOWN';
      if (rootOverride) template = template.replaceAll('${root}', rootOverride);
      for (const [key, replacement] of constants) template = template.replaceAll('${' + key + '}', replacement);
      calls.push({ endpointTemplate: template, httpMethod, requestHelper: expr, source: `${relative(ownerSf.fileName)}:${line(ownerSf, node)}` });
    });
    const refs = [...new Set(references.get(`${objectName}.${method}`) || [])];
    const modes = [...new Set(rows.filter(row => {
      const deps = dependencySet(path.join(repo, row.component.split(':')[0]));
      return refs.some(ref => deps.has(path.join(repo, ref.replace(/:\d+$/, ''))));
    }).map(row => row.mode))];
    const text = prop.getText(ownerSf);
    apiRows.push({
      object: objectName, method, module: relative(file), inheritedFrom: rootOverride ? 'governancePolicyApi' : null,
      requests: calls, source: `${relative(ownerSf.fileName)}:${line(ownerSf, prop)}`,
      frontendConsumers: refs, consumerModes: modes,
      consumerStatus: refs.length ? 'STILL_REFERENCED' : 'UNKNOWN_NO_DIRECT_PROPERTY_REFERENCE',
      permissionEvidence: 'BACKEND_AUTHORIZATION_NOT_PROVEN_BY_CLIENT_AUDIT',
      clientVersionHeader: /If-Match|versionHeaders|versionHeader|etag/i.test(text),
      clientIdempotencyHeader: /Idempotency|idempotency/i.test(text),
      uatCoverage: 'NOT_EXECUTED_BY_THIS_STATIC_AUDIT',
    });
  }
  visit(sf, node => {
    if (!ts.isVariableDeclaration(node) || !ts.isIdentifier(node.name) || !node.initializer) return;
    const exported = node.parent?.parent?.modifiers?.some(modifier => modifier.kind === ts.SyntaxKind.ExportKeyword);
    if (!exported || (!/Api$/.test(node.name.text) && !slash(file).includes('/src/api/'))) return;
    if (ts.isObjectLiteralExpression(node.initializer)) {
      for (const prop of node.initializer.properties) {
        if (ts.isSpreadAssignment(prop) && ts.isCallExpression(prop.expression) && prop.expression.expression.getText(sf) === 'governancePolicyApi') {
          const argument = prop.expression.arguments[0].getText(sf);
          const rootOverride = constants.get(argument) ?? argument.replaceAll('"', '').replaceAll("'", '');
          for (const p of policyProperties) methodRow(node.name.text, p, policySf, rootOverride);
        } else methodRow(node.name.text, prop);
      }
    } else if (ts.isCallExpression(node.initializer) && node.initializer.expression.getText(sf) === 'governancePolicyApi') {
      const argument = node.initializer.arguments[0].getText(sf);
      const rootOverride = constants.get(argument) ?? argument.replaceAll('"', '').replaceAll("'", '');
      for (const p of policyProperties) methodRow(node.name.text, p, policySf, rootOverride);
    }
  });
}

const mismatches = rows.filter(row => row.mode === 'USER' && row.classification === 'ADMIN_CONFIGURATION' || row.mode === 'ADMIN' && row.classification === 'USER_TRANSACTION');
const missing = rows.filter(row => row.componentStatus === 'MISSING_RENDERER');
const duplicateIds = nodes.filter((n, i) => nodes.findIndex(other => other.id === n.id) !== i);
const unresolvedPredecessors = nodes.flatMap(n => n.predecessorIds.filter(id => !nodes.some(other => other.id === id)).map(id => ({ node: n.id, predecessor: id })));
const summary = {
  schemaVersion: 1, generatedAt: new Date().toISOString(),
  gitCommit: cp.execFileSync('git', ['rev-parse', 'HEAD'], { cwd: repo, encoding: 'utf8' }).trim(),
  method: 'INERT_METADATA_EVALUATION_AND_TYPESCRIPT_AST_NO_BACKEND_OR_BROWSER',
  blueprintSha256: crypto.createHash('sha256').update(read(blueprintFile)).digest('hex'),
  sourceFilesScanned: productionFiles.length, navigationNodes: nodes.length, canonicalRoutes: rows.length,
  userRoutes: rows.filter(row => row.mode === 'USER').length, adminRoutes: rows.filter(row => row.mode === 'ADMIN').length,
  reusedLandingAliasNodes: nodes.length - rows.length, modeClassificationMismatches: mismatches,
  missingRenderers: missing, explicitPlaceholders: rows.filter(row => row.componentStatus === 'EXPLICIT_PLACEHOLDER').map(row => row.route),
  duplicateIds, unresolvedPredecessors, hiddenRendererCount: hiddenRenderers.length,
  apiFiles: apiFiles.length, apiObjectMethods: apiRows.length,
  apiMethodsWithoutDirectProductionConsumer: apiRows.filter(row => !row.frontendConsumers.length).length,
  qualification: 'Static and mocked-component evidence only; NOT real Chromium/PostgreSQL UAT or authorized business sign-off.',
};
const supplementalRoutes = [
  { route: '/workspaces/:workspaceId/*', mode: 'USER', component: 'frontend/src/features/workspace-context/WorkspaceOperationalPage.tsx', scope: 'Backend-returned navigator codes; this shell does not render every canonical strategic module.', permission: 'RequireAuth + backend context', source: 'frontend/src/App.tsx:8157' },
  ...['create', 'requests', 'workspaces', 'review', 'overview'].map(view => ({ route: '/app/strategy/enterprise-explorer', internalState: `projectView=${view}`, mode: 'USER', component: 'frontend/src/features/enterprise-structure/components/ProjectCreationWorkspace.tsx', permission: 'Backend allowed_actions and request authority', source: 'frontend/src/features/enterprise-structure/pages/EnterpriseExplorerPage.tsx' })),
];
const componentRows = productionFiles.filter(file => file.endsWith('.tsx')).flatMap(file => {
  const directRoutes = rows.filter(row => row.component === relative(file)).map(row => row.route);
  const indirectRoutes = rows.filter(row => dependencySet(path.join(repo, row.component.split(':')[0])).has(file)).map(row => row.route);
  if (!indirectRoutes.length && !directRoutes.length) return [];
  const sf = parsed.get(file);
  const controls = {};
  visit(sf, node => {
    if (!ts.isJsxOpeningElement(node) && !ts.isJsxSelfClosingElement(node)) return;
    const tag = node.tagName.getText(sf);
    if (['button', 'input', 'select', 'textarea', 'table', 'dialog', 'h1', 'h2', 'h3', 'CompactModuleHeader'].includes(tag)) controls[tag] = (controls[tag] || 0) + 1;
  });
  return [{ component: relative(file), directRoutes, indirectRoutes, used: true, reusedAcrossRoutes: indirectRoutes.length > 1,
    duplicateStatus: 'REUSE_NOT_PROOF_OF_DUPLICATE_UI', removalCandidate: false, lexicalControlCounts: controls,
    backendAllowedActionsReference: /allowed_actions|can_initialize|can_activate/.test(read(file)),
    activeWorkspaceContextHook: /useActiveWorkspaceContext/.test(read(file)),
    verification: 'STATIC_JSX_COUNTS_NOT_RENDERED_ACCESSIBILITY_UAT' }];
});
const cleanupCandidates = [
  ...hiddenRenderers.map(item => ({ category: 'LEGACY_VIEW', target: item.view, classification: 'REQUIRES_DEPRECATION', evidence: item.evidence, action: 'Document migration/redirect intent; do not delete in validation.' })),
  { category: 'DUPLICATE_RESOLVER_ASSIGNMENT', target: 'BusinessCaseWorkspace initialViewRenderers group overridden by dedicated loop', classification: 'STILL_REFERENCED', evidence: 'StrategicViewOutlet.tsx initialViewRenderers includes BC group; later loop overwrites all BC entries to add onNavigate.', action: 'Small cleanup possible after dedicated equivalence regression; no deletion performed.' },
  { category: 'NAVIGATION_ALIAS', target: 'Ancestor and leaf nodes sharing one route', classification: 'STILL_REFERENCED', evidence: `${nodes.length - rows.length} repeated node-to-route representations; strategicNodeForView canonicalizes registry.`, action: 'Keep; not duplicate screens or competing authorities.' },
  { category: 'SECONDARY_NAVIGATOR_ORDER', target: 'ENTERPRISE_WORKSPACE_ORDER / PROJECT_WORKSPACE_ORDER', classification: 'STILL_REFERENCED', evidence: 'WorkspaceOperationalPage.tsx imports orderStrategicWorkspaceNavigator; backend module codes differ from ControlFlowView.', action: 'Compatibility adapter; do not create new navigation arrays.' },
  { category: 'TEST_ONLY_HELPER_IN_PRODUCTION', target: 'strategicNodeApplies', classification: 'UNKNOWN', evidence: 'Exported from canonical blueprint; direct production references absent, tests call applicability metadata only.', action: 'Determine intended UI applicability contract before removing; tests are not runtime enforcement.' },
  { category: 'LIVE_LEGACY_ADMIN_CREATION_ROUTE', target: '/app/admin/strategy/enterprise-workspace-structure', classification: 'REQUIRES_DEPRECATION', evidence: rows.find(row => row.view === 'enterprise-workspace-structure').component.includes('AdminConfigurationView') ? 'Composition Rules resolves legacy AdminConfigurationView live Workspace creation. Baseline S2 finding.' : 'Canonical route now resolves AdminEnterpriseStructurePage rules; legacy AdminConfigurationView creation branch remains in source but is not a strategic renderer.', action: 'Retain history; deprecated route intent documented. Backend must deny live PROJECT bypass. Do not delete historical API or data.' },
  ...apiRows.filter(row => !row.frontendConsumers.length).map(row => ({ category: 'API_METHOD_NO_DIRECT_CONSUMER', target: `${row.object}.${row.method}`, classification: 'UNKNOWN', evidence: row.source, action: 'Check dynamic member access, external clients, server and historical compatibility; absence of client reference is insufficient for deletion.' })),
];
function csv(records) {
  if (!records.length) return '';
  const keys = [...new Set(records.flatMap(record => Object.keys(record)))];
  const escape = value => '"' + (typeof value === 'object' && value !== null ? JSON.stringify(value) : String(value ?? '')).replaceAll('"', '""') + '"';
  return keys.map(escape).join(',') + '\n' + records.map(record => keys.map(key => escape(record[key])).join(',')).join('\n') + '\n';
}
if (process.argv.includes('--write')) {
  fs.mkdirSync(outputDir, { recursive: true });
  for (const [name, value] of Object.entries({ frontend_audit_summary: summary, frontend_navigation_nodes: nodes, frontend_routes: rows, frontend_components: componentRows, frontend_legacy_renderers: hiddenRenderers, frontend_api_consumers: apiRows, frontend_supplemental_routes: supplementalRoutes, frontend_cleanup_candidates: cleanupCandidates })) {
    fs.writeFileSync(path.join(outputDir, `${name}.json`), JSON.stringify(value, null, 2) + '\n');
    if (Array.isArray(value)) fs.writeFileSync(path.join(outputDir, `${name}.csv`), csv(value));
  }
  const guideLines = ['# Current strategic routes for guides', '', 'Derived from the actual blueprint; route presence is not business UAT acceptance.', ''];
  for (const mode of ['user', 'admin']) {
    guideLines.push(`## ${mode.toUpperCase()}`, '');
    for (const phase of navigation.strategicNavigationBlueprint.filter(item => item.mode === mode)) {
      guideLines.push(`### Phase ${phase.phase}: ${phase.label}`, '');
      for (const child of phase.children) guideLines.push(`- ${child.label}: ${child.route}`);
      guideLines.push('');
    }
  }
  guideLines.push('Project Creation / Initialization / Activation: USER Enterprise Explorer → Create Project / My Project Requests / My Project Workspaces; internal state on the same canonical Explorer route. Composition Rules resolution is recorded in frontend_routes.json; see before/after S2 finding evidence.', '');
  fs.writeFileSync(path.join(outputDir, 'frontend_guide_routes.md'), guideLines.join('\n'));
}
process.stdout.write(JSON.stringify(summary, null, 2) + '\n');
