const fs = require("node:fs");
const path = require("node:path");
const { defineConfig } = require("@playwright/test");

const edgeExecutablePath = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge";

module.exports = defineConfig({
  testDir: "./tests/e2e",
  timeout: 45_000,
  expect: {
    timeout: 10_000,
  },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:8770",
    browserName: "chromium",
    headless: true,
    launchOptions: fs.existsSync(edgeExecutablePath)
      ? { executablePath: edgeExecutablePath }
      : {},
  },
  webServer: {
    command: [
      "LOCALSCRIBE_ENGINE=mock",
      "LOCALSCRIBE_DATA_DIR=.playwright-data",
      "LOCALSCRIBE_ENABLE_VAD=0",
      "LOCALSCRIBE_ENABLE_CONTEXT_LINKING=0",
      "LOCALSCRIBE_ENABLE_POST_PROCESSING=0",
      "LOCALSCRIBE_ENABLE_SPEAKERS=0",
      ".venv/bin/python",
      "-m",
      "uvicorn",
      "localscribe.main:app",
      "--host",
      "127.0.0.1",
      "--port",
      "8770",
      "--app-dir",
      "src",
    ].join(" "),
    cwd: path.resolve(__dirname),
    url: "http://127.0.0.1:8770",
    reuseExistingServer: true,
    timeout: 45_000,
  },
});
