# LocalScribe

LocalScribe is a local-first macOS live transcription workspace.

It runs a browser UI on your Mac, keeps inference local, supports real-time transcription, detects speaker changes, lets you rename speakers directly in the transcript, and can optionally run a local cleanup pass for punctuation and entity correction after each chunk.

## What it does

- Live microphone transcription in Safari
- Browser or shared-audio capture from the browser
- Native macOS system-audio capture with a ScreenCaptureKit helper
- Managed local WhisperKit server startup
- Whisper model installation and switching from the UI
- Speaker-aware segmentation, speaker markers, and editable speaker labels
- Context linking across live chunks
- Optional local post-processing with Ollama or MLX
- Saved sessions and export in TXT, Markdown, SRT, VTT, and JSON

## Best fit

LocalScribe is strongest on Apple Silicon Macs because it is designed around WhisperKit.

- Apple Silicon: preferred path
- Intel Mac: supported, but use `faster-whisper` instead of WhisperKit

## Install on a New macOS System

These steps assume a fresh Mac with no project dependencies installed yet.

### 1. Install Apple command line tools

```bash
xcode-select --install
```

### 2. Install Homebrew

If Homebrew is not installed yet, install it from [brew.sh](https://brew.sh), then confirm:

```bash
brew --version
```

### 3. Install system dependencies

```bash
brew install python@3.12 uv ffmpeg whisperkit-cli
```

What these are for:

- `python@3.12`: runtime for the app
- `uv`: environment and dependency manager
- `ffmpeg`: audio normalization and decoding
- `whisperkit-cli`: local WhisperKit server for Apple Silicon

### 4. Clone the repository

```bash
git clone <your-repo-url>
cd localscribe
```

### 5. Create the virtual environment

```bash
uv venv
source .venv/bin/activate
```

### 6. Install Python dependencies

```bash
uv sync --extra dev
```

### 7. Start the app

For Apple Silicon:

```bash
LOCALSCRIBE_ENGINE=whisperkit LOCALSCRIBE_WHISPER_MODEL=tiny uv run localscribe --reload
```

For Intel Macs:

```bash
LOCALSCRIBE_ENGINE=faster-whisper LOCALSCRIBE_FASTER_WHISPER_MODEL=base uv run localscribe --reload
```

### 8. Open the app in Safari

Open:

```text
http://127.0.0.1:8765
```

Then allow:

- microphone access for live mic capture
- screen recording or screen sharing permissions if you want browser/system-audio capture

### 9. Let the first model finish installing

On first launch:

- `tiny` is the fastest way to confirm the app works
- `large-v3-turbo` is the better day-to-day model once setup is stable
- the first model download can take a while and uses significant disk space

After the app is open, use the model panel to:

- see which models are installed
- install missing models
- switch the active model without leaving the UI

## First Run Workflow

1. Open the page in Safari.
2. Choose `Live microphone` or `Browser or system audio`.
3. Choose a scenario preset such as meeting, podcast, discussion, oral presentation, TV news, or interview.
4. Adjust `Live segment length`.
5. Click `New Session`.
6. Click `Start Mic`.
7. Watch speaker markers and the transcript timeline update in real time.

## Optional Features

### Native macOS system audio

For system output capture without browser limitations, use the helper in:

- [Native system audio guide](docs/NATIVE_SYSTEM_AUDIO.md)

### Optional local cleanup with Ollama

If you want a second local pass for punctuation and entity cleanup after each chunk:

```bash
export LOCALSCRIBE_ENABLE_POST_PROCESSING=1
export LOCALSCRIBE_POSTPROCESS_BACKEND=ollama
export LOCALSCRIBE_POSTPROCESS_MODEL=qwen2.5:3b-instruct
```

You also need a running local Ollama server with that model pulled.

### Optional local cleanup with MLX

If you prefer MLX:

```bash
export LOCALSCRIBE_ENABLE_POST_PROCESSING=1
export LOCALSCRIBE_POSTPROCESS_BACKEND=mlx
export LOCALSCRIBE_POSTPROCESS_MODEL=mlx-community/Qwen2.5-3B-Instruct-4bit
```

The default remains the faster no-op path, so real-time capture still works without any local LLM installed.

## Troubleshooting

### Safari shows no microphone devices

Click `Refresh Devices`, then grant microphone permission when Safari asks.

### Browser audio does not work reliably

Safari is strongest for microphone capture, not tab audio. For system output capture:

- use a loopback device
- or use the native ScreenCaptureKit helper

### WhisperKit does not start

Check that this works:

```bash
whisperkit-cli --help
```

If not, reinstall it:

```bash
brew reinstall whisperkit-cli
```

### You want a smaller fallback path

Use:

```bash
export LOCALSCRIBE_ENGINE=faster-whisper
export LOCALSCRIBE_FASTER_WHISPER_MODEL=base
```

## Documentation

- [Local run tutorial](docs/LOCAL_RUN_TUTORIAL.md)
- [Native system audio guide](docs/NATIVE_SYSTEM_AUDIO.md)

## Project layout

```text
localscribe/
  docs/
  native/
  src/localscribe/
    api/
    context/
    diarization/
    engines/
    exports/
    postprocess/
    speakers/
    static/
    storage/
    streaming/
  tests/
```

## Development

Run tests:

```bash
uv run pytest tests
```

Check the frontend script:

```bash
node --check src/localscribe/static/app.js
```

## License

This repository now includes the [MIT License](LICENSE).
