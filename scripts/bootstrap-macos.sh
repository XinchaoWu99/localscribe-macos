#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

need_command() {
  command -v "$1" >/dev/null 2>&1
}

print_step() {
  printf '\n[%s] %s\n' "$1" "$2"
}

print_step "1/5" "Checking Homebrew"
if ! need_command brew; then
  echo "Homebrew is required. Install it from https://brew.sh and rerun this script."
  exit 1
fi

print_step "2/5" "Installing required packages"
brew install python@3.12 uv ffmpeg node

print_step "3/5" "Installing Apple Silicon WhisperKit runtime when available"
if [[ "$(uname -m)" == "arm64" ]]; then
  brew install whisperkit-cli
else
  echo "Skipping whisperkit-cli because this Mac is not Apple Silicon."
fi

print_step "4/5" "Creating virtual environment and syncing Python dependencies"
cd "$ROOT_DIR"
uv venv
uv sync --extra dev

print_step "5/5" "Done"
cat <<'EOF'

Next steps:

1. Activate the environment:
   source .venv/bin/activate

2. Start the app:
   LOCALSCRIBE_ENGINE=whisperkit LOCALSCRIBE_WHISPER_MODEL=tiny uv run localscribe --reload

3. Open Safari or Edge:
   http://127.0.0.1:8765

Local AI assistant:

- Install Ollama:
  brew install ollama
- Pull the default assistant model:
  ollama pull qwen2.5:3b-instruct
- LocalScribe starts Ollama automatically when the app launches.

EOF
