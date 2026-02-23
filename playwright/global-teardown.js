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

  // Restore the areDataLinksAutomatic preference to its original value
  if (state.autoLinksPreference !== null) {
    await apiContext.put("/api/preference/areDataLinksAutomatic", {
      data: state.autoLinksPreference,
    });
    console.log(
      `  Restored areDataLinksAutomatic=${JSON.stringify(state.autoLinksPreference)}`,
    );
  } else {
    // Preference was absent before tests; delete it in case tests set it
    const checkResp = await apiContext.get(
      "/api/preference/areDataLinksAutomatic",
    );
    if (checkResp.ok()) {
      await apiContext.delete("/api/preference/areDataLinksAutomatic");
      console.log("  Removed areDataLinksAutomatic (was absent before tests)");
    }
  }

  await apiContext.dispose();

  fs.unlinkSync(STATE_FILE);
  console.log("Pre-test state restored.\n");
}

export default globalTeardown;
