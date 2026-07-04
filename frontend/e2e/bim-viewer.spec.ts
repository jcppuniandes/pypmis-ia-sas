import { expect, test } from "@playwright/test";

test("BIM quantities module keeps one IFC viewer and one controlled quantity table", async ({ page }) => {
  test.setTimeout(300_000);

  await page.goto("/login");
  await page.getByLabel("User").fill("admin");
  await page.getByLabel("Password").fill("1234");
  await page.getByRole("button", { name: /sign in/i }).click();

  await expect(page.getByRole("region", { name: /project workspace and control flow/i })).toBeVisible();

  await page.getByRole("button", { name: /cantidades bim/i }).click();

  await expect(page.getByRole("region", { name: /cantidades bim module/i })).toBeVisible();
  await expect(page.getByRole("region", { name: /modelo ifc/i })).toBeVisible();
  await expect(page.getByTestId("ifc-geometry-viewer-canvas")).toBeVisible();
  await expect(page.getByText(/IFC geometry rendered from stored source file/i)).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("region", { name: /salud del visor ifc/i })).toBeVisible();
  await expect(page.getByRole("region", { name: /salud del visor ifc/i })).toContainText(/Capacidad navegador/i);
  await expect(page.getByRole("region", { name: /panel de operacion bim/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /Front IFC view/i })).toBeVisible();
  await page.getByRole("button", { name: /Front IFC view/i }).click();
  await expect(page.getByRole("region", { name: /panel de operacion bim/i })).toContainText(/FRONT \/ Orbitar/i);
  await page.getByRole("button", { name: /Section IFC model/i }).click();
  await expect(page.getByRole("group", { name: /Section axis/i })).toBeVisible();
  await page.getByRole("button", { name: /Section axis Z/i }).click();
  await expect(page.getByRole("region", { name: /panel de operacion bim/i })).toContainText(/Seccion Z/i);
  await expect(page.getByRole("region", { name: /arbol ifc/i })).toBeVisible();
  await expect(page.getByRole("region", { name: /propiedades del elemento ifc/i })).toBeVisible();
  await expect(page.getByRole("region", { name: /tabla de cantidades controladas/i })).toBeVisible();

  const canvas = page.getByTestId("ifc-geometry-viewer-canvas");
  await canvas.scrollIntoViewIfNeeded();
  const canvasBox = await canvas.boundingBox();
  expect(canvasBox).not.toBeNull();
  if (!canvasBox) return;

  const clickPoints = [
    [0.5, 0.5],
    [0.45, 0.45],
    [0.55, 0.45],
    [0.45, 0.55],
    [0.6, 0.55],
  ];
  const properties = page.getByRole("region", { name: /propiedades del elemento ifc/i });
  let hasGeometryQuantity = false;
  for (const [xRatio, yRatio] of clickPoints) {
    await page.mouse.click(canvasBox.x + canvasBox.width * xRatio, canvasBox.y + canvasBox.height * yRatio);
    if (await page.locator(".bimViewerSelectionBadge").isVisible().catch(() => false)) {
      await expect(properties).toContainText(/elemento seleccionado/i);
      const propertyText = await properties.textContent();
      const geometryApprovalButton = properties.getByRole("button", { name: /usar cantidad geometrica/i });
      if (
        /GeometryMesh(?:Area|Length|Volume)/i.test(propertyText ?? "") &&
        (await geometryApprovalButton.isVisible().catch(() => false))
      ) {
        hasGeometryQuantity = true;
        break;
      }
    }
  }

  const selectionBadge = page.locator(".bimViewerSelectionBadge");
  await expect(selectionBadge).toBeVisible();
  await expect(selectionBadge).toContainText(/elemento seleccionado/i);
  await expect(properties).toContainText(/elemento seleccionado/i);
  await expect(properties).toContainText(/cantidad controlada/i);
  await expect(properties).toContainText(/[\d,.]+\s+(ea|m2|m3|m|und)/i);
  await expect(properties).toContainText(/regla de medicion/i);
  await expect(properties).toContainText(/dimensiones geometricas/i);
  await expect(properties).toContainText(/[\d,.]+\s+x\s+[\d,.]+\s+x\s+[\d,.]+/i);
  await expect(properties).toContainText(/cantidad geometrica real/i);
  expect(hasGeometryQuantity).toBe(true);

  const geometryApproveButton = properties.getByRole("button", { name: /usar cantidad geometrica/i });
  await expect(geometryApproveButton).toBeVisible();
  await geometryApproveButton.click();
  await expect(page.getByText(/Medicion controlada aprobada/i)).toBeVisible();

  const quantityTable = page.getByRole("region", { name: /tabla de cantidades controladas/i });
  await expect(quantityTable).toContainText(/Medicion: Aprobada v/i);

  const wbsSelect = quantityTable.locator('select[aria-label^="WBS para"]').first();
  const cbsSelect = quantityTable.locator('select[aria-label^="CBS para"]').first();
  const fbsSelect = quantityTable.locator('select[aria-label^="FBS para"]').first();
  const packageSelect = quantityTable.locator('select[aria-label^="Paquete para"]').first();
  await expect(wbsSelect).toBeVisible();
  await wbsSelect.selectOption({ index: 1 });
  await cbsSelect.selectOption({ index: 1 });
  await fbsSelect.selectOption({ index: 1 });
  await packageSelect.selectOption({ index: 1 });
  const saveControlCodes = quantityTable.getByRole("button", { name: /guardar codigos/i }).first();
  await expect(saveControlCodes).toBeEnabled();
  await saveControlCodes.click();
  await expect(page.getByText(/Codigos de control asignados/i)).toBeVisible();
});
