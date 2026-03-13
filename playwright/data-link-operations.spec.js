import { expect, test } from "@playwright/test";
import { navigateToZarrDir, ZARR_DIR_NAME } from "./utils";

// The name shown for this zarr directory in the Data Links table.
// Update if the UI shows a different label (e.g. full path vs. directory name).
const zarrDirName = ZARR_DIR_NAME;

test.describe("Data Link Operations", () => {
  test.beforeEach(async ({ page }) => {
    await navigateToZarrDir(page);
  });

  test("Create data link via viewer icon, delete via properties panel, recreate via properties panel, then delete via links page", async ({
    page,
  }) => {
    const neuroglancerLink = page.getByRole("link", {
      name: "Neuroglancer logo",
    });
    const dataLinkToggle = page.getByRole("checkbox", {
      name: /data link/i,
    });
    const confirmButton = page.getByRole("button", {
      name: /confirm|create|yes/i,
    });
    const confirmDeleteButton = page.getByRole("button", {
      name: /delete/i,
    });

    await test.step("Turn on automatic data links via the data link dialog", async () => {
      await expect(neuroglancerLink).toBeVisible();
      await neuroglancerLink.click();

      // Confirm the data link creation in the dialog
      await expect(confirmButton).toBeVisible();

      // Enable automatic data links
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

      // Look for the "Data Link" toggle in the properties panel to be checked
      await expect(dataLinkToggle).toBeVisible();
      await expect(dataLinkToggle).toBeChecked();
    });

    await test.step("Delete data link via properties panel", async () => {
      await dataLinkToggle.click();
      await expect(confirmDeleteButton).toBeVisible();
      await confirmDeleteButton.click();
      await expect(
        page.getByText("Successfully deleted data link"),
      ).toBeVisible();
      await expect(dataLinkToggle).not.toBeChecked();
    });

    await test.step("Recreate data link via properties panel", async () => {
      await dataLinkToggle.click();
      // Navigate back to the zarr directory to check data link status; the above click takes you to Neuroglancer
      await navigateToZarrDir(page);
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
});
