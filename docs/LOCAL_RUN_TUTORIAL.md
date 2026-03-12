# LocalScribe Local Run Guide

LocalScribe is a browser-based transcription workspace that runs on your Mac and keeps the audio path local. It supports:

- live microphone transcription
- offline file transcription
- speaker-aware transcript segmentation
- optional speaker enrollment for repeated voices

This guide covers the fastest and most reliable way to run LocalScribe locally on macOS.

If you want native macOS system-audio capture instead of browser capture, also see [docs/NATIVE_SYSTEM_AUDIO.md](/Users/xwu/Downloads/codex/localscribe/docs/NATIVE_SYSTEM_AUDIO.md).

## What You Get

When LocalScribe is running locally, you can:

- open the app in Safari at `http://127.0.0.1:8765`
- choose a microphone or loopback audio device
- capture live speech and see transcript segments appear in real time
- upload recordings for offline transcription
- copy the resulting transcript directly from the browser
- reopen saved sessions after restarting the app
- download transcript exports as TXT, Markdown, SRT, VTT, or JSON

By default, the app prefers a managed local WhisperKit server when `whisperkit-cli` is installed, and falls back to local `faster-whisper` otherwise.

## System Requirements

- macOS on Apple Silicon or Intel
- Python 3.11 to 3.13
- `ffmpeg` installed and available on `PATH`
- internet access for the first model download

Recommended:

- Safari for microphone capture
- a loopback audio device if you want to transcribe Mac speaker output as an input source

## Install Prerequisites

### 1. Confirm Python

```bash
python3 --version
```

You should see Python `3.11`, `3.12`, or `3.13`.

### 2. Confirm ffmpeg

```bash
ffmpeg -version
```

If `ffmpeg` is missing and you use Homebrew:

```bash
brew install ffmpeg
```

### 3. Move into the app folder

```bash
cd /Users/xwu/Downloads/codex/localscribe
```

## First-Time Setup

### 1. Create the virtual environment

```bash
uv venv
```

### 2. Activate it

```bash
source .venv/bin/activate
```

### 3. Install dependencies

```bash
uv sync
```

This installs the web app, the local transcription runtime, Silero VAD, and supporting packages.

## Start the App

Run:

```bash
uv run localscribe --reload
```

Expected output:

```text
Uvicorn running on http://127.0.0.1:8765
```

Once that appears, open:

```text
http://127.0.0.1:8765
```

## Recommended Launch Workflow

### Safari Workflow

Safari is the recommended browser for microphone-based transcription.

1. Open `http://127.0.0.1:8765`
2. Allow microphone access when Safari asks
3. In the app, keep `Capture source` set to `Microphone input`
4. Click `Refresh Devices`
5. Choose your microphone or loopback input
6. Click `New Session`
7. Click `Start Mic`

As you speak, transcript segments will appear in the transcript timeline.

### Browser or Screen Audio

The app also includes a `Browser or screen audio` mode. This depends on browser support for screen-sharing audio tracks.

Practical guidance:

- Safari: use microphone mode for reliability
- Chromium-based browsers: better choice for tab or screen audio capture
- If you want Mac speaker output inside Safari, route that output into a loopback input and select it from the microphone device list

## Live Transcription Walkthrough

### Step 1. Configure the session

Use the left-side controls:

- `Capture source`: choose microphone input for the most stable path
- `Chunk length`: shorter feels more live, longer is usually more stable
- `Language hint`: optional, for example `en`
- `Prompt bias`: optional, useful for names, acronyms, and domain vocabulary
- `Try to assign speakers automatically`: leave enabled if you want diarization behavior

### Step 2. Start a session

Click:

```text
New Session
```

This creates a live session on the backend.

### Step 3. Start recording

Click:

```text
Start Mic
```

What happens next:

- the browser captures audio locally
- LocalScribe converts each short chunk into clean WAV audio
- the backend normalizes the audio with `ffmpeg`
- the local Whisper engine transcribes the chunk
- the transcript timeline updates in the browser

### Step 4. Stop recording

Click:

```text
Stop
```

The current session remains visible in the browser so you can continue reviewing the transcript.

## Offline File Transcription

Use this mode when you already have a recording.

### 1. Choose a file

In the `Upload A Recording` section:

- drag an audio file onto the drop zone
- or click and browse manually

### 2. Run transcription

Click:

```text
Transcribe File
```

The result will appear in the main transcript area with timestamps and speaker labels when available.

## Speaker Enrollment

Speaker enrollment is designed for recurring discussions where the same people appear often.

### 1. Start or create a live session

The app expects speaker enrollment to happen during an active or existing live session.

### 2. Add a name

Enter a name such as:

- `Jane`
- `Host`
- `PM`

### 3. Add a short voice sample

Use a short clip with clear speech, ideally:

- 5 to 15 seconds
- low background noise
- one speaker only

### 4. Click `Enroll Speaker`

That voice can then be matched to later transcript segments.

## Default Runtime Behavior

By default, LocalScribe uses:

- engine: `auto`
- preferred local backend: managed WhisperKit when `whisperkit-cli` is installed
- fallback backend: `faster-whisper`
- speech gating: Silero VAD

You can override that with environment variables before launching:

```bash
brew install whisperkit-cli
export LOCALSCRIBE_ENGINE=whisperkit
export LOCALSCRIBE_WHISPER_MODEL=large-v3-turbo
uv run localscribe --reload
```

That starts the browser app on `127.0.0.1:8765` and automatically launches `whisperkit-cli serve` on `127.0.0.1:8080`.

If you want the smaller fallback backend instead:

```bash
export LOCALSCRIBE_ENGINE=faster-whisper
export LOCALSCRIBE_FASTER_WHISPER_MODEL=base
export LOCALSCRIBE_FASTER_WHISPER_COMPUTE_TYPE=int8
uv run localscribe --reload
```

## Best Practices

### For the most reliable live transcript

- use Safari
- use `Microphone input`
- keep chunk length around `2000` to `3000` ms
- provide a language hint if you already know it
- add domain-specific names to the prompt field

### For Mac speaker output transcription

- install a loopback audio device
- route system output to that loopback device
- pick that device in `Microphone device`

### For higher transcript quality

- use a quieter room
- keep the microphone close to the speaker
- avoid heavily clipped audio
- use offline file mode for longer recordings you want cleaned up

## Troubleshooting

### The page loads, but live transcription does not start

Check:

- Safari was granted microphone access
- the correct input device is selected
- the server is still running in the terminal

### ffmpeg errors appear in the terminal

Confirm:

```bash
ffmpeg -version
```

If the command fails, reinstall `ffmpeg`.

### The first transcription is slow

That is expected if WhisperKit or `faster-whisper` is downloading the model for the first time.

### WhisperKit is selected but not ready

Check:

- `whisperkit-cli` is installed: `whisperkit-cli serve --help`
- the app status endpoint: `curl http://127.0.0.1:8765/api/status`
- WhisperKit logs: `.localscribe-data/runtime/whisperkit-server.log`

### I want browser or tab audio, not my microphone

Use one of these options:

- choose `Browser or screen audio` in a Chromium-based browser
- or create a loopback audio input on macOS and use `Microphone input` with that device selected

### I want better quality than the default model

Start with:

```bash
export LOCALSCRIBE_FASTER_WHISPER_MODEL=small
uv run localscribe --reload
```

Larger models may improve quality but will run more slowly.

## Stop the App

In the terminal running LocalScribe, press:

```bash
Ctrl+C
```

## Quick Start Summary

If you just want the shortest reliable local path:

```bash
cd /Users/xwu/Downloads/codex/localscribe
uv venv
source .venv/bin/activate
uv sync
uv run localscribe --reload
```

Then open `http://127.0.0.1:8765` in Safari, choose `Microphone input`, refresh devices, pick your mic, create a session, and start recording.
