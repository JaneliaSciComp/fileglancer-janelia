import "dotenv/config";
import { defineConfig } from "@playwright/test";

export default defineConfig({
  globalSetup: "./global-setup.js",
  globalTeardown: "./global-teardown.js",
  reporter: [["html", "on-failure"]],
  use: {
    baseURL: "https://fileglancer-dev.int.janelia.org",
    storageState: ".auth/user.json",
    trace: "on-first-retry",
    video: "on",
    screenshot: "only-on-failure",
    permissions: ["clipboard-write"],
  },
  timeout: 20_000,
  navigationTimeout: 10_000,
  expect: {
    timeout: 20_000,
  },
});
