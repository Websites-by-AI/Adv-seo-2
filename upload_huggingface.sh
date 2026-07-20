#!/usr/bin/env bash
set -euo pipefail

SPACE_ID="${SPACE_ID:-SoSa123456/clinic-lead-agent}"
SOURCE_DIR="${1:-$(pwd)}"
WORK_DIR="${2:-$(pwd)/.hf-space-upload}"
SPACE_URL="https://huggingface.co/spaces/${SPACE_ID}"
GIT_URL="https://huggingface.co/spaces/${SPACE_ID}"

for cmd in git python tar; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "Missing required command: $cmd"; exit 1; }
done

if ! command -v hf >/dev/null 2>&1; then
  echo "Installing Hugging Face CLI..."
  python -m pip install --user --upgrade huggingface_hub
  export PATH="$HOME/.local/bin:$PATH"
fi

if ! hf auth whoami >/dev/null 2>&1; then
  echo "A browser-safe login prompt will follow. Create a WRITE token at:"
  echo "https://huggingface.co/settings/tokens"
  hf auth login
fi

git lfs install >/dev/null 2>&1 || true

if [ -d "$WORK_DIR/.git" ]; then
  echo "Updating existing clone..."
  git -C "$WORK_DIR" pull --rebase
else
  rm -rf "$WORK_DIR"
  git clone "$GIT_URL" "$WORK_DIR"
fi

# Remove old repository content while preserving .git.
find "$WORK_DIR" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +

# Copy project content, excluding local caches, credentials and Git metadata.
tar \
  --exclude='.git' \
  --exclude='.env' \
  --exclude='node_modules' \
  --exclude='__pycache__' \
  --exclude='*.zip' \
  -C "$SOURCE_DIR" -cf - . | tar -C "$WORK_DIR" -xf -

cd "$WORK_DIR"
git add -A

if git diff --cached --quiet; then
  echo "No changes to upload."
else
  if ! git config user.name >/dev/null || ! git config user.email >/dev/null; then
    echo "Git identity is missing. Run these commands once, then rerun this script:"
    echo 'git config --global user.name "Your Name"'
    echo 'git config --global user.email "you@example.com"'
    exit 1
  fi
  git commit -m "Deploy Clinic Signal to Hugging Face Space"
  git push origin main
fi

echo "Deployment pushed successfully."
echo "Space: $SPACE_URL"
echo "App URL (after build): https://sosa123456-clinic-lead-agent.hf.space"
