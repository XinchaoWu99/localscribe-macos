const { test, expect } = require("@playwright/test");

test("transcript editors are writable and editable during active live recording", async ({ page }) => {
  await page.goto("/");
  await page.locator("#startButton").click();

  await expect(page.locator("#livePill")).toHaveText("Recording");
  await expect(page.locator("#liveTranscribingPanel")).toBeVisible();

  await expect(page.locator(".segment-editor").first()).toHaveValue(/captured in mock mode/, {
    timeout: 20000,
  });

  const editor = page.locator(".segment-editor").first();
  await expect(editor).toHaveJSProperty("readOnly", false);

  const editedText = "Edited while recording";
  await editor.fill(editedText);
  await expect(editor).toHaveValue(editedText);

  await page.locator("#stopButton").click();
  await expect(page.locator("#livePill")).toHaveText("Idle", { timeout: 20000 });
});

test("live session transcript editors stay writable", async ({ page, request }) => {
  const title = `E2E live editor ${Date.now()}`;
  const sessionId = await createNamedSession(request, title);

  await page.goto("/");
  await openSessionByTitle(page, title);

  await ingestLiveChunk(page, sessionId, 1, buildToneWavBase64({ durationMs: 1400 }));
  await page.reload();
  await openSessionByTitle(page, title);

  const editor = page.locator(".segment-editor").first();
  await expect(editor).toHaveValue(/Chunk 1 captured in mock mode/);
  await expect(editor).toHaveJSProperty("readOnly", false);
  await expect(page.locator(".segment-state").first()).toHaveText("Editable");
});

test("saving an edited live caption keeps the edit when later speech arrives", async ({ page, request }) => {
  const title = `E2E edited live caption ${Date.now()}`;
  const sessionId = await createNamedSession(request, title);

  await page.goto("/");
  await openSessionByTitle(page, title);

  await ingestLiveChunk(page, sessionId, 1, buildToneWavBase64({ durationMs: 1400 }));
  await page.reload();
  await openSessionByTitle(page, title);

  const editedText = "User-edited live caption";
  const firstEditor = page.locator(".segment-editor").first();
  await firstEditor.fill(editedText);

  const saveResponse = page.waitForResponse((response) => {
    if (response.request().method() !== "PATCH") {
      return false;
    }
    return /\/api\/sessions\/[^/]+\/segments\/[^/]+$/.test(new URL(response.url()).pathname);
  });
  await firstEditor.press("Tab");
  await saveResponse;

  await ingestLiveChunk(page, sessionId, 2, buildToneWavBase64({ durationMs: 1400, frequencyHz: 660 }));
  await page.reload();
  await openSessionByTitle(page, title);

  const editors = page.locator(".segment-editor");
  const states = page.locator(".segment-state");
  await expect(editors).toHaveCount(2);
  await expect(editors.nth(0)).toHaveValue(editedText);
  await expect(editors.nth(1)).toHaveValue(/Chunk 2 captured in mock mode/);
  await expect(states.nth(0)).toHaveText("Edited");
  await expect(states.nth(1)).toHaveText("Editable");
});

async function createNamedSession(request, title) {
  const createResponse = await request.post("/api/sessions");
  expect(createResponse.ok()).toBeTruthy();
  const createPayload = await createResponse.json();
  const sessionId = createPayload.session.sessionId;

  const renameResponse = await request.patch(`/api/sessions/${sessionId}`, {
    data: { title },
  });
  expect(renameResponse.ok()).toBeTruthy();
  return sessionId;
}

async function openSessionByTitle(page, title) {
  const inputs = page.locator(".session-title-input");
  await expect(inputs.first()).toBeVisible();
  const inputCount = await inputs.count();

  for (let index = 0; index < inputCount; index += 1) {
    const input = inputs.nth(index);
    if ((await input.inputValue()) !== title) {
      continue;
    }
    const card = input.locator("xpath=ancestor::article[contains(@class, 'session-card')]");
    await card.locator(".session-open").click();
    return;
  }

  throw new Error(`Could not find a session card titled "${title}".`);
}

async function ingestLiveChunk(page, sessionId, sequence, payload) {
  await page.evaluate(
    async ({ currentSessionId, currentSequence, currentPayload }) => {
      const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
      const target = `${wsProtocol}://${window.location.host}/ws/live/${currentSessionId}`;

      await new Promise((resolve, reject) => {
        const socket = new WebSocket(target);
        const timer = window.setTimeout(() => {
          socket.close();
          reject(new Error("Timed out waiting for live chunk processing."));
        }, 15000);

        socket.addEventListener("message", (event) => {
          const data = JSON.parse(event.data);
          if (data.type === "session_state") {
            socket.send(
              JSON.stringify({
                type: "audio_chunk",
                sequence: currentSequence,
                mimeType: "audio/wav",
                payload: currentPayload,
                diarize: false,
                linkContext: true,
                postProcess: false,
              }),
            );
            return;
          }
          if (data.type === "chunk_processed") {
            window.clearTimeout(timer);
            socket.close();
            resolve();
            return;
          }
          if (data.type === "error") {
            window.clearTimeout(timer);
            socket.close();
            reject(new Error(data.detail || "Live chunk failed."));
          }
        });

        socket.addEventListener("error", () => {
          window.clearTimeout(timer);
          reject(new Error("WebSocket connection failed."));
        });
      });
    },
    {
      currentSessionId: sessionId,
      currentSequence: sequence,
      currentPayload: payload,
    },
  );
}

function buildToneWavBase64({ durationMs, frequencyHz = 440, sampleRate = 16000 }) {
  const frameCount = Math.floor((durationMs / 1000) * sampleRate);
  const dataLength = frameCount * 2;
  const buffer = Buffer.alloc(44 + dataLength);

  buffer.write("RIFF", 0, "ascii");
  buffer.writeUInt32LE(36 + dataLength, 4);
  buffer.write("WAVE", 8, "ascii");
  buffer.write("fmt ", 12, "ascii");
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(1, 22);
  buffer.writeUInt32LE(sampleRate, 24);
  buffer.writeUInt32LE(sampleRate * 2, 28);
  buffer.writeUInt16LE(2, 32);
  buffer.writeUInt16LE(16, 34);
  buffer.write("data", 36, "ascii");
  buffer.writeUInt32LE(dataLength, 40);

  for (let index = 0; index < frameCount; index += 1) {
    const t = index / sampleRate;
    const sample = Math.sin(2 * Math.PI * frequencyHz * t) * 0.35;
    const clamped = Math.max(-1, Math.min(1, sample));
    buffer.writeInt16LE(Math.round(clamped * 0x7fff), 44 + index * 2);
  }

  return buffer.toString("base64");
}
