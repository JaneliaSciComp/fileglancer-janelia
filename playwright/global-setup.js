import { chromium, request } from "@playwright/test";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const AUTH_FILE = path.join(__dirname, ".auth/user.json");
export const STATE_FILE = path.join(__dirname, ".auth/test-state.json");
const EXPIRY_BUFFER_SECONDS = 300;

function isAuthFileValid() {
  if (!fs.existsSync(AUTH_FILE)) return false;
  try {
    const authData = JSON.parse(fs.readFileSync(AUTH_FILE, "utf-8"));
    const sessionCookie = authData.cookies?.find(
      (c) => c.name === "fg_session",
    );
    return (
      sessionCookie?.expires &&
      sessionCookie.expires > Date.now() / 1000 + EXPIRY_BUFFER_SECONDS
    );
  } catch {
    return false;
  }
}

async function saveAndCleanTestState(baseURL) {
  if (fs.existsSync(STATE_FILE)) {
    console.log(
      "\nWarning: test-state.json already exists — previous teardown may have failed." +
        " Skipping state save to preserve original state.\n",
    );
    return;
  }

  console.log("\nSaving and cleaning pre-test database state...");
  const apiContext = await request.newContext({
    baseURL,
    storageState: AUTH_FILE,
  });

  // Fetch all existing data links for this user
  const proxiedPathsResp = await apiContext.get("/api/proxied-path");
  const proxiedPaths = (await proxiedPathsResp.json()).paths ?? [];

  // Fetch all preferences
  const prefsResp = await apiContext.get("/api/preference");
  const preferences = prefsResp.ok() ? await prefsResp.json() : {};

  // Write state file before making any changes
  fs.writeFileSync(
    STATE_FILE,
    JSON.stringify({ proxiedPaths, preferences }, null, 2),
  );
  console.log(
    `  Saved ${proxiedPaths.length} data link(s), ${Object.keys(preferences).length} preference(s)`,
  );

  // Delete the test data links so tests start from a clean slate
  for (const link of proxiedPaths) {
    await apiContext.delete(`/api/proxied-path/${link.sharing_key}`);
  }

  // Delete all preferences so tests start from a clean slate
  for (const key of Object.keys(preferences)) {
    await apiContext.delete(`/api/preference/${encodeURIComponent(key)}`);
  }

  await apiContext.dispose();
  console.log("Pre-test state saved. Database cleaned for tests.\n");
}

async function globalSetup(config) {
  const baseURL = config.projects[0].use.baseURL;

  if (!isAuthFileValid()) {
    fs.mkdirSync(path.dirname(AUTH_FILE), { recursive: true });

    if (process.env.FGC_TEST_API_KEY) {
      const context = await request.newContext({ baseURL });
      const response = await context.post("/api/auth/test-login", {
        headers: {
          "X-API-Key": process.env.FGC_TEST_API_KEY,
          "X-API-Username": "jacs",
        },
      });

      if (!response.ok()) {
        const body = await response.text();
        throw new Error(`test-login failed (${response.status()}): ${body}`);
      }

      await context.storageState({ path: AUTH_FILE });
      await context.dispose();
      console.log(`\nLogged in as ${username} via API key.\n`);
    } else {
      console.log("\nNo API key set. Opening browser for manual Okta login...");
      console.log(
        "Please complete the MFA challenge in the browser window that opens.\n",
      );

      const browser = await chromium.launch({ headless: false });
      const context = await browser.newContext();
      const page = await context.newPage();

      await page.goto(`${baseURL}/api/auth/login?next=/browse`);
      await page.waitForURL(`${baseURL}/browse`, { timeout: 120_000 });

      await context.storageState({ path: AUTH_FILE });
      await browser.close();

      console.log("Login successful. Auth state saved.\n");
    }
  } else {
    const expiry = JSON.parse(
      fs.readFileSync(AUTH_FILE, "utf-8"),
    ).cookies?.find((c) => c.name === "fg_session")?.expires;
    console.log(
      `\nReusing cached auth state (expires: ${new Date(expiry * 1000).toLocaleString()})\n`,
    );
  }

  await saveAndCleanTestState(baseURL);
}

export default globalSetup;
