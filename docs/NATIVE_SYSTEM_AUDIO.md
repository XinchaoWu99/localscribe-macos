# Native macOS System Audio Capture

LocalScribe includes a small native helper under [`native/system-audio-helper`](/Users/xwu/Downloads/codex/localscribe/native/system-audio-helper) for system-audio capture without browser limitations.

It uses Apple's ScreenCaptureKit to capture macOS system audio, creates or attaches to a LocalScribe live session, and streams WAV chunks into the existing WebSocket pipeline.

## Why Use It

- Safari and other browsers are limited when capturing tab or system audio.
- ScreenCaptureKit gives you native macOS audio capture with the same LocalScribe backend and transcript UI.
- The browser can reopen the helper-created session from `Recent sessions`.

## Requirements

- macOS 13 or newer
- Xcode command line tools
- Screen Recording permission for the helper
- A running LocalScribe server on its configured host/port

## Build It

```bash
cd /Users/xwu/Downloads/codex/localscribe/native/system-audio-helper
swift build -c release
```

The binary will be written to:

```text
.build/release/localscribe-system-audio
```

## Run It

Start LocalScribe first:

```bash
cd /Users/xwu/Downloads/codex/localscribe
uv run localscribe --reload
```

If you start LocalScribe on a custom port, either:

- pass `--server http://127.0.0.1:<your-port>` to the helper
- or export `LOCALSCRIBE_PORT=<your-port>` before launching it

Then start native system-audio capture:

```bash
cd /Users/xwu/Downloads/codex/localscribe/native/system-audio-helper
.build/release/localscribe-system-audio --server http://127.0.0.1:<your-port>
```

The helper will:

1. request Screen Recording permission if needed
2. create a LocalScribe live session unless you pass `--session-id`
3. capture system audio from the selected display
4. stream audio chunks into `/ws/live/{session_id}`

Open Safari at `http://127.0.0.1:<your-port>` and use `Recent sessions` to open the live transcript.

## Useful Flags

List available displays:

```bash
.build/release/localscribe-system-audio --list-displays
```

Select a specific display:

```bash
.build/release/localscribe-system-audio --display-id 69733248
```

Attach to an existing LocalScribe live session:

```bash
.build/release/localscribe-system-audio --session-id YOUR_SESSION_ID
```

Disable speaker assignment:

```bash
.build/release/localscribe-system-audio --no-diarize
```

Set a language hint and prompt bias:

```bash
.build/release/localscribe-system-audio --language en --prompt "Project Atlas, WhisperKit, OpenAI"
```

Run for a fixed time:

```bash
.build/release/localscribe-system-audio --duration 15
```

## Loopback Alternative

If you prefer not to grant Screen Recording permission, you can still route macOS output through a loopback device and use the browser mic path:

1. install a loopback device such as BlackHole
2. route macOS output into that device
3. select the loopback device as the microphone input in LocalScribe

That path is simpler operationally, but the ScreenCaptureKit helper is the native route without browser capture limitations.
