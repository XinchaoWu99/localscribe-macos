const fs = require("node:fs");
const path = require("node:path");
const { defineConfig } = require("@playwright/test");

const edgeExecutablePath = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge";
const fakeMediaArgs = [
  "--use-fake-ui-for-media-stream",
  "--use-fake-device-for-media-stream",
];
const testHost = process.env.LOCALSCRIBE_TEST_HOST || "127.0.0.1";
const testPort = Number.parseInt(process.env.LOCALSCRIBE_TEST_PORT || process.env.LOCALSCRIBE_PORT || "8770", 10);
const baseURL = `http://${testHost}:${testPort}`;

const projects = [
  {
    name: "chromium",
    testIgnore: /edge-smoke\.spec\.js/,
    use: {
      browserName: "chromium",
      launchOptions: {
        args: fakeMediaArgs,
      },
    },
  },
];

if (fs.existsSync(edgeExecutablePath)) {
  projects.push({
    name: "edge-smoke",
    testMatch: /edge-smoke\.spec\.js/,
    use: {
      browserName: "chromium",
      launchOptions: {
        executablePath: edgeExecutablePath,
        args: fakeMediaArgs,
      },
    },
  });
}

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
    baseURL,
    headless: true,
    permissions: ["microphone"],
  },
  projects,
  webServer: {
    command: [
      "LOCALSCRIBE_ENGINE=mock",
      "LOCALSCRIBE_DATA_DIR=.playwright-data",
      `LOCALSCRIBE_HOST=${testHost}`,
      `LOCALSCRIBE_PORT=${testPort}`,
      "LOCALSCRIBE_ENABLE_VAD=0",
      "LOCALSCRIBE_ENABLE_CONTEXT_LINKING=0",
      "LOCALSCRIBE_ENABLE_POST_PROCESSING=0",
      "LOCALSCRIBE_ENABLE_SPEAKERS=0",
      ".venv/bin/python",
      "-m",
      "uvicorn",
      "localscribe.main:app",
      "--host",
      testHost,
      "--port",
      String(testPort),
      "--app-dir",
      "src",
    ].join(" "),
    cwd: path.resolve(__dirname),
    url: `${baseURL}/api/status`,
    reuseExistingServer: true,
    timeout: 45_000,
  },
});
