import { expect, test } from "@playwright/test";

test.describe("Data Link Operations", () => {
  test("Create new SSH key", async ({ page }) => {
    const newKeyBtn = page.getByRole("button", { name: "New Key" });
    const generateKeyBtn = page.getByRole("button", { name: "Generate Key" });
    const copyKeyBtn = page.getByRole("button", { name: "Copy Private Key" });
    const closeBtn = page.getByRole("button", { name: "Close" });

    await page.goto("/ssh-keys");
    await expect(newKeyBtn).toBeVisible();
    await newKeyBtn.click();

    await expect(generateKeyBtn).toBeVisible();
    await generateKeyBtn.click();

    await expect(copyKeyBtn).toBeVisible();
    await copyKeyBtn.click();
    await expect(
      page.getByText("Private key copied to clipboard"),
    ).toBeVisible();

    await expect(closeBtn).toBeVisible();
    await closeBtn.click();

    await expect(newKeyBtn).toBeVisible();
  });
});
