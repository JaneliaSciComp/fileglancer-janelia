import { expect } from "@playwright/test";

export const PARENT_DIR_NAME =
  "NP31_R2_1_1_SS00090_Spab_546_Nplp1_647_1x_Central.zarr";
export const ZARR_DIR_NAME = "0";
const ZARR_PATH = `/nrs/opendata/ome-zarr-examples/fly-efish/NP31_R2_20240119/${PARENT_DIR_NAME}/${ZARR_DIR_NAME}`;

// These identify the test zarr directory in the Fileglancer database.
// Used by global-setup.js / global-teardown.js to manage test state.
export const ZARR_FSP_NAME = "nrs_opendata";
export const ZARR_RELATIVE_PATH = `ome-zarr-examples/fly-efish/NP31_R2_20240119/${PARENT_DIR_NAME}/${ZARR_DIR_NAME}`;

export const navigateToZarrDir = async (page) => {
  // Always start from /browse so this function is safe to call at any point
  // (initial load or mid-test re-navigation).
  await page.goto("/browse");

  const navigationInput = page.getByRole("textbox", {
    name: /path\/to\/folder/i,
  });
  await expect(navigationInput).toBeVisible();

  // Fill in the test path
  await navigationInput.fill(ZARR_PATH);

  // Click the Go button
  const goButton = page.getByRole("button", { name: /^Go$/i });
  await goButton.click();
  // Confirm new page fully loaded
  await page.waitForLoadState("domcontentloaded");
  // Verify we navigated to the test directory by looking in the bread crumbs
  await expect(
    page.getByRole("link", {
      name: PARENT_DIR_NAME,
    }),
  ).toBeVisible();
  // Wait for zarr metadata to load
  await expect(page.getByText(".zattrs")).toBeVisible();
};
