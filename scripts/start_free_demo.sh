#!/usr/bin/env bash
# Free, short-lived public demo on GitHub Codespaces (2 cores / 8 GB).
# Uses only local Ollama and SQLite: no AI API key, payments, or VPN needed.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== Installing app requirements (first time may take a few minutes) ==="
python -m pip install -r requirements.txt

if ! command -v ollama >/dev/null 2>&1; then
  echo "=== Installing Ollama locally on the Codespace ==="
  curl -fsSL https://ollama.com/install.sh | sh
fi

mkdir -p "$HOME/.ollama" "$HOME/.local/share/gorkycode"
if ! curl -fsS --max-time 3 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "=== Starting Ollama ==="
  nohup ollama serve > "$HOME/.ollama/gorkycode-serve.log" 2>&1 &
fi

ready=0
for i in $(seq 1 60); do
  if curl -fsS --max-time 3 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
if [[ "$ready" -ne 1 ]]; then
  echo "ERROR: Ollama did not start. Log: $HOME/.ollama/gorkycode-serve.log" >&2
  exit 1
fi

echo "=== Downloading small free Russian-capable language model ==="
ollama pull qwen3:1.7b

# Make this a truly free, local-only test build. Avoid unintentionally calling paid APIs.
unset GIGACHAT_AUTH_KEY GIGACHAT_CREDENTIALS GIGACHAT_ACCESS_TOKEN GROQ_API_KEY
export APP_ENV=development
export OLLAMA_URL=http://127.0.0.1:11434/api/chat
export OLLAMA_MODEL=qwen3:1.7b
export WHISPER_MODEL_SIZE=tiny
export DATABASE_PATH="$HOME/.local/share/gorkycode/events.db"

echo "=== Starting Streamlit on 0.0.0.0:8501 ==="
echo "To share: in the Codespaces PORTS tab, make port 8501 PUBLIC."
echo "Note: all demo visitors share one local SQLite database."
exec python -m streamlit run app.py \
  --server.address=0.0.0.0 \
  --server.port=8501 \
  --server.headless=true
