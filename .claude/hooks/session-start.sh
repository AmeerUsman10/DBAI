#!/bin/bash
set -euo pipefail

# Only run in remote Claude Code on the web environments
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

echo "=== Session Start Hook: Setting up DBAI environment ==="

# ── 1. Install Fish shell ──────────────────────────────────────────────────────
if ! command -v fish &>/dev/null; then
  echo "Installing fish shell..."
  apt-get update -qq
  apt-get install -y -qq fish
  echo "Fish shell installed: $(fish --version)"
else
  echo "Fish shell already installed: $(fish --version)"
fi

# ── 2. Install Node.js dependencies (Miro API + ESLint) ───────────────────────
if [ -f "$CLAUDE_PROJECT_DIR/package.json" ]; then
  echo "Installing Node.js dependencies..."
  cd "$CLAUDE_PROJECT_DIR"
  npm install
  echo "Dependencies installed."
fi

# ── 3. Persist PATH so fish and node_modules/.bin are available ───────────────
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo 'export PATH="$PATH:/usr/bin:./node_modules/.bin"' >> "$CLAUDE_ENV_FILE"
fi

echo "=== Setup complete ==="
echo "  fish  : $(fish --version)"
echo "  miro  : $(node -e "const p=require('./node_modules/@mirohq/miro-api/package.json'); console.log(p.version);" 2>/dev/null || echo 'not yet available')"
