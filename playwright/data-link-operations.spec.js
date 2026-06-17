import { expect, test } from "@playwright/test";
import { navigateToZarrDir, ZARR_DIR_NAME } from "./utils";

// The name shown for this zarr directory in the Data Links table.
// Update if the UI shows a different label (e.g. full path vs. directory name).
const zarrDirName = ZARR_DIR_NAME;
const subDirName = "1";

const deleteLinkViaPropertiesPanel = async (
  page,
  dataLinkToggle,
  confirmDeleteButton,
  propertiesPanel,
) => {
  await dataLinkToggle.click();
  await expect(confirmDeleteButton).toBeVisible();
  await confirmDeleteButton.click();
  await expect(page.getByText("Successfully deleted data link")).toBeVisible();
  await expect(dataLinkToggle).not.toBeChecked();
};

test.describe("Data Link Operations", () => {
  // Locators are recreated in beforeEach so each test gets fresh handles bound
  // to its own page. Declared at describe scope so test bodies can see them.
  let neuroglancerLink;
  let dataLinkToggle;
  let confirmButton;
  let confirmDeleteButton;
  let propertiesPanel;

  test.beforeEach(async ({ page }) => {
    await navigateToZarrDir(page);

    propertiesPanel = page
      .locator('[role="complementary"]')
      .filter({ hasText: "Properties" });

    neuroglancerLink = page.getByAltText(/neuroglancer/i);

    dataLinkToggle = page.getByRole("checkbox", {
      name: /data link/i,
    });
    confirmButton = page.getByRole("button", {
      name: /confirm|create|yes/i,
    });
    confirmDeleteButton = page.getByRole("button", {
      name: /delete/i,
    });
  });

  test("Create data link via viewer icon, delete via properties panel, recreate via properties panel, then delete via links page", async ({
    page,
  }) => {
    await test.step("Data link format defaults to transparent path", async () => {
      await neuroglancerLink.click();

      // Confirm the data link creation in the dialog
      await expect(confirmButton).toBeVisible();

      // Check that the data link format is set to "Transparent path" in the dialog
      const advancedSettingsAccordion = page.getByRole("button", {
        name: /advanced settings/i,
      });
      await advancedSettingsAccordion.click();
      const fullPathInput = page.getByLabel("Full path");
      await expect(fullPathInput).toBeChecked();
    });

    await test.step("Change data link format to directory name only", async () => {
      const nameOnlyInput = page.getByLabel("Directory name only");
      await nameOnlyInput.click();
      await expect(nameOnlyInput).toBeChecked();
    });

    await test.step("Turn on automatic data links via the data link dialog", async () => {
      const autoLinkCheckbox = page.getByRole("checkbox", {
        name: "Enable automatic data link creation",
      });
      await autoLinkCheckbox.click();
      await expect(autoLinkCheckbox).toBeChecked();
      await expect(
        page.getByText("Enabled automatic data links"),
      ).toBeVisible();
    });

    await test.step("Create data link via data link dialog", async () => {
      await confirmButton.click();
      await expect(
        page.getByText("Data link created successfully"),
      ).toBeVisible();

      // Navigate back to the zarr directory to check data link status; the above click takes you to Neuroglancer
      await navigateToZarrDir(page);
      await page.waitForLoadState("domcontentloaded");

      // Look for the "Data Link" toggle in the properties panel to be checked
      await expect(dataLinkToggle).toBeVisible();
      await expect(dataLinkToggle).toBeChecked();
    });

    await test.step("Delete data link via properties panel", async () => {
      await deleteLinkViaPropertiesPanel(
        page,
        dataLinkToggle,
        confirmDeleteButton,
        propertiesPanel,
      );
    });

    await test.step("Recreate data link via properties panel", async () => {
      await dataLinkToggle.click();
      // Navigate back to the zarr directory to check data link status; the above click takes you to Neuroglancer
      await navigateToZarrDir(page);
      await expect(page.getByAltText(/neuroglancer/i)).toBeVisible();
      await expect(dataLinkToggle).toBeChecked();
    });

    await test.step("Delete the link via action menu on links page", async () => {
      const linksNavButton = page.getByRole("link", { name: "Data links" });
      await linksNavButton.click();

      await expect(page.getByRole("heading", { name: /links/i })).toBeVisible();
      const linkRow = page.getByText(zarrDirName, { exact: true });
      await expect(linkRow).toBeVisible();

      const actionMenuButton = page
        .getByTestId("data-link-actions-cell")
        .getByRole("button");
      await actionMenuButton.click();
      const deleteLinkOption = page.getByRole("menuitem", { name: /unshare/i });
      await deleteLinkOption.click();
      // Confirm deletion
      await expect(confirmDeleteButton).toBeVisible();
      await confirmDeleteButton.click();

      // Verify the link is removed from the table
      await expect(linkRow).not.toBeVisible();
    });

    await test.step("Copy link works when automatic links is on and no data link exists yet", async () => {
      await navigateToZarrDir(page);

      const copyLinkIcon = page.getByRole("button", { name: "Copy data URL" });
      await expect(copyLinkIcon).toBeVisible();

      await copyLinkIcon.click();
      await expect(page.getByText("Copied!")).toBeVisible();
      await expect(
        page.getByText("Data link created successfully"),
      ).toBeVisible();
    });
  });

  test("Data link created for subdirectory clicked from parent shows subdirectory name", async ({
    page,
  }) => {
    // Click the second subdirectory row, on folder cell to populate properties panel without navigating in
    await page.getByRole("cell", { name: "Folder" }).nth(1).click();

    // Wait for properties panel to show the subdirectory name
    await expect(
      propertiesPanel.getByText(subDirName, { exact: true }),
    ).toBeVisible({ timeout: 10000 });

    // Wait for the data link toggle to appear
    const dataLinkToggle = propertiesPanel.getByRole("checkbox", {
      name: /data link/i,
    });
    await expect(dataLinkToggle).toBeVisible({ timeout: 10000 });

    // Click the toggle to create a data link
    await dataLinkToggle.click();

    // When automatic data link creation is off, toggling opens a confirmation
    // dialog that must be confirmed before the link is created.
    const createButton = page.getByRole("button", {
      name: /create data link/i,
    });
    if (await createButton.isVisible().catch(() => false)) {
      await createButton.click();
    }

    await expect(
      page.getByText("Data link created successfully"),
    ).toBeVisible();

    // Navigate to the Data links page
    const linksNavButton = page.getByRole("link", { name: "Data links" });
    await linksNavButton.click();

    await expect(page.getByRole("heading", { name: /links/i })).toBeVisible();

    // Verify the data link has the subdirectory name, not the parent directory name
    const linkRow = page.getByText(subDirName, { exact: true });
    await expect(linkRow).toBeVisible({ timeout: 10000 });
  });

  test("Viewer icon creates data link for current directory even when subdirectory row is selected", async ({
    page,
  }) => {
    //delete existing parent directory link
    await deleteLinkViaPropertiesPanel(
      page,
      dataLinkToggle,
      confirmDeleteButton,
      propertiesPanel,
    );

    // Click the second subdirectory row, on folder cell to populate properties panel without navigating in
    await page.getByRole("cell", { name: "Folder" }).nth(1).click();

    // Verify subdirectory name is selected in properties panel
    await expect(
      propertiesPanel.getByText(subDirName, { exact: true }),
    ).toBeVisible();

    // Click the Neuroglancer viewer icon — this should create a data link
    // for the zarr directory (currentFileOrFolder), not for s0 (propertiesTarget)
    await neuroglancerLink.click();

    await expect(
      page.getByText("Data link created successfully"),
    ).toBeVisible();

    // Navigate back to check the data link on the links page
    await page.goto("/browse", { waitUntil: "domcontentloaded" });
    const linksNavButton = page.getByRole("link", { name: "Data links" });
    await linksNavButton.click();

    await expect(page.getByRole("heading", { name: /links/i })).toBeVisible();

    // The data link should be for the zarr directory, not the 0 subdirectory
    await expect(page.getByText(zarrDirName, { exact: true })).toBeVisible();
  });
});
