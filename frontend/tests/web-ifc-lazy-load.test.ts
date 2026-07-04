import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const appSource = readFileSync(resolve(process.cwd(), "src/App.tsx"), "utf8");
const viteConfig = readFileSync(resolve(process.cwd(), "vite.config.ts"), "utf8");

describe("web-ifc bundle guard", () => {
  it("loads the geometric IFC viewer lazily from the BIM module", () => {
    expect(appSource).not.toMatch(/import\s+BimIfcModelViewer\s+from\s+["']\.\/components\/BimIfcModelViewer["']/);
    expect(appSource).toContain('lazyWithModuleRecovery(() => import("./components/BimIfcModelViewer"))');
    expect(appSource).toContain("<LazyModuleErrorBoundary moduleName=\"Modelo IFC\">");
    expect(viteConfig).toContain('name: "bim-ifc-engine"');
    expect(viteConfig).toContain('name: "bim-three"');
    expect(viteConfig).toContain("chunkSizeWarningLimit: 3600");
  });
});
