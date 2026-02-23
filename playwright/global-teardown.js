import { request } from "@playwright/test";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const AUTH_FILE = path.join(__dirname, ".auth/user.json");
const STATE_FILE = path.join(__dirname, ".auth/test-state.json");

async function globalTeardown(config) {
  const baseURL = config.projects[0].use.baseURL;

  if (!fs.existsSync(STATE_FILE)) {
    console.log("\nNo test state file found, skipping teardown.\n");
    return;
  }

  const state = JSON.parse(fs.readFileSync(STATE_FILE, "utf-8"));
  console.log("\nRestoring pre-test database state...");

  const apiContext = await request.newContext({
    baseURL,
    storageState: AUTH_FILE,
  });

  // Delete all data links that currently exist for this user
  const currentResp = await apiContext.get("/api/proxied-path");
  const currentPaths = (await currentResp.json()).paths ?? [];
  for (const link of currentPaths) {
    await apiContext.delete(`/api/proxied-path/${link.sharing_key}`);
  }

  // Recreate any data links that existed before the tests
  // Note: sharing_key values will differ from the originals
  for (const link of state.proxiedPaths) {
    const createResp = await apiContext.post(
      `/api/proxied-path?fsp_name=${encodeURIComponent(link.fsp_name)}&path=${encodeURIComponent(link.path)}`,
    );
    if (!createResp.ok()) {
      console.warn(
        `  Warning: failed to restore data link for ${link.path}: ${await createResp.text()}`,
      );
    }
  }
  console.log(`  Restored ${state.proxiedPaths.length} data link(s)`);

  // Delete all preferences that currently exist
  const currentPrefsResp = await apiContext.get("/api/preference");
  const currentPrefs = currentPrefsResp.ok()
    ? await currentPrefsResp.json()
    : {};
  for (const key of Object.keys(currentPrefs)) {
    await apiContext.delete(`/api/preference/${encodeURIComponent(key)}`);
  }

  // Restore all preferences that existed before the tests
  const savedPreferences = state.preferences ?? {};
  for (const [key, value] of Object.entries(savedPreferences)) {
    await apiContext.put(`/api/preference/${encodeURIComponent(key)}`, {
      data: value,
    });
  }
  console.log(
    `  Restored ${Object.keys(savedPreferences).length} preference(s)`,
  );

  await apiContext.dispose();

  fs.unlinkSync(STATE_FILE);
  console.log("Pre-test state restored.\n");
}

export default globalTeardown;
