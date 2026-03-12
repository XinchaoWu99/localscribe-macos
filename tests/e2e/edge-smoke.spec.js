const { test, expect } = require("@playwright/test");

test("Edge can start live microphone capture and produce transcript text", async ({ page, request }) => {
  const settingsResponse = await request.patch("/api/settings/live", {
    data: { chunkMillis: 800 },
  });
  expect(settingsResponse.ok()).toBeTruthy();

  await page.goto("/");
  await page.locator('[data-entry-mode="microphone"]').click();
  await page.locator("#createSessionButton").click();

  await expect(page.locator("#sessionStatusText")).toHaveText("Session ready");
  await expect(page.locator("#startButton")).toHaveText("Start Live Microphone");

  await page.locator("#startButton").click();

  await expect(page.locator("#livePill")).toHaveText("Recording");
  await expect(page.locator("#sessionStatusText")).toHaveText(
    /Listening for speech|Buffering first chunk|Transcribing first text|Recording live/,
  );
  await expect(page.locator(".segment-editor").first()).toHaveValue(/Chunk 1 captured in mock mode/, {
    timeout: 20000,
  });

  await page.locator("#stopButton").click();
  await expect(page.locator("#livePill")).toHaveText("Idle", { timeout: 20000 });
});
