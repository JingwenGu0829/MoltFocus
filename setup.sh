#!/usr/bin/env bash
set -euo pipefail

# ── MoltFocus Setup ──────────────────────────────────────────────
# Human-facing CLI that handles infra so the agent doesn't have to.
#
# What this does:
#   1. Installs dependencies (uv, python venv, pip packages)
#   2. Asks: demo mode or full setup?
#   3. Demo  → copies template data, starts server, you're done.
#   4. Full  → creates empty workspace, starts server,
#              then you point your agent at ONBOARD_AGENT_OPENCLAW.md.
# ─────────────────────────────────────────────────────────────────

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PORT="${PORT:-8787}"
HOST="${HOST:-0.0.0.0}"

# ── Colors ───────────────────────────────────────────────────────
bold()  { printf "\033[1m%s\033[0m" "$*"; }
green() { printf "\033[32m%s\033[0m" "$*"; }
cyan()  { printf "\033[36m%s\033[0m" "$*"; }
dim()   { printf "\033[2m%s\033[0m" "$*"; }

# ── Step 1: Dependencies ────────────────────────────────────────
echo ""
echo "$(bold '⚙  MoltFocus Setup')"
echo ""

# Check for uv
if ! command -v uv >/dev/null 2>&1; then
  echo "$(cyan 'Installing uv (Python package manager)...')"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# Create venv + install deps
if [ ! -d .venv ]; then
  echo "$(cyan 'Setting up Python environment...')"
  uv venv .venv
fi

source .venv/bin/activate
uv pip install -r ui/requirements.txt --quiet 2>/dev/null
echo "$(green '✓') Dependencies installed."
echo ""

# ── Step 2: Demo or Full? ──────────────────────────────────────
echo "$(bold 'How do you want to start?')"
echo ""
echo "  $(bold '1)') $(green 'Demo mode') — pre-filled sample data, see the UI immediately"
echo "  $(bold '2)') $(green 'Full setup') — your agent will personalize everything for you"
echo ""

while true; do
  read -rp "Choose [1/2]: " choice
  case "$choice" in
    1) MODE="demo"; break ;;
    2) MODE="full"; break ;;
    *) echo "Please enter 1 or 2." ;;
  esac
done

echo ""

# ── Step 3: Workspace ──────────────────────────────────────────

PLANNER_ROOT="${PLANNER_ROOT:-$HOME/planner}"

if [ "$MODE" = "demo" ]; then
  echo "$(cyan 'Setting up demo workspace...')"

  # Copy template into PLANNER_ROOT
  mkdir -p "$PLANNER_ROOT/planner/latest"
  mkdir -p "$PLANNER_ROOT/reflections"

  cp "$ROOT_DIR/template/planner/profile.yaml"              "$PLANNER_ROOT/planner/profile.yaml"
  cp "$ROOT_DIR/template/planner/tasks.yaml"                 "$PLANNER_ROOT/planner/tasks.yaml"
  cp "$ROOT_DIR/template/planner/latest/plan.md"             "$PLANNER_ROOT/planner/latest/plan.md"
  cp "$ROOT_DIR/template/planner/latest/checkin_draft.json"  "$PLANNER_ROOT/planner/latest/checkin_draft.json"
  cp "$ROOT_DIR/template/reflections/reflections.md"         "$PLANNER_ROOT/reflections/reflections.md"

  # Demo state with streak + history so the UI looks alive
  cat > "$PLANNER_ROOT/planner/state.json" <<'STATE'
{
  "streak": 3,
  "lastStreakDate": null,
  "lastRating": "good",
  "lastMode": "commit",
  "lastSummary": "[Good] Demo day: finished Deadline paper 2h, Important project 90m. Solid focus. Keep it up tomorrow.",
  "lastFinalizedDate": null,
  "history": [
    {"day": "demo-day-3", "rating": "good",  "mode": "commit",   "streakCounted": true, "doneCount": 3, "total": 4},
    {"day": "demo-day-2", "rating": "fair",   "mode": "commit",   "streakCounted": true, "doneCount": 2, "total": 5},
    {"day": "demo-day-1", "rating": "good",  "mode": "recovery", "streakCounted": true, "doneCount": 2, "total": 3}
  ]
}
STATE

  echo "$(green '✓') Demo workspace ready at $(bold "$PLANNER_ROOT")"

else
  # Full mode: create empty structure, agent fills it in
  echo "$(cyan 'Creating workspace directories...')"
  mkdir -p "$PLANNER_ROOT/planner/latest"
  mkdir -p "$PLANNER_ROOT/reflections"

  # Seed empty files so the server doesn't error on first load
  [ -f "$PLANNER_ROOT/planner/profile.yaml" ]      || echo "# Created by setup — your agent will fill this in" > "$PLANNER_ROOT/planner/profile.yaml"
  [ -f "$PLANNER_ROOT/planner/tasks.yaml" ]         || printf 'week_start: "mon"\ntasks: []\n' > "$PLANNER_ROOT/planner/tasks.yaml"
  [ -f "$PLANNER_ROOT/planner/state.json" ]         || echo '{"streak":0}' > "$PLANNER_ROOT/planner/state.json"
  [ -f "$PLANNER_ROOT/reflections/reflections.md" ] || printf '# Reflections (rolling)\n\nAppend newest entries at the top.\n\n---\n' > "$PLANNER_ROOT/reflections/reflections.md"

  echo "$(green '✓') Workspace created at $(bold "$PLANNER_ROOT")"
fi

# ── Step 4: Start server ───────────────────────────────────────
echo ""
echo "$(cyan 'Starting MoltFocus server...')"
echo ""

export PLANNER_ROOT HOST PORT

# Start in background, capture PID
python -m uvicorn ui.app:app --host "$HOST" --port "$PORT" &
SERVER_PID=$!

# Give it a moment to bind
sleep 2

if kill -0 "$SERVER_PID" 2>/dev/null; then
  echo "$(green '✓') Server running at $(bold "http://localhost:$PORT")"
else
  echo "Server failed to start. Check logs above." >&2
  exit 1
fi

# ── Step 5: What's next ───────────────────────────────────────
echo ""
echo "────────────────────────────────────────────────"

if [ "$MODE" = "demo" ]; then
  echo ""
  echo "  $(bold 'Demo is live!') Open $(cyan "http://localhost:$PORT") in your browser."
  echo ""
  echo "  When you're ready for the real thing, re-run:"
  echo "  $(dim './setup.sh')  and choose $(bold 'Full setup')."
  echo ""
else
  echo ""
  echo "  $(bold 'Server is live!') Open $(cyan "http://localhost:$PORT") in your browser."
  echo ""
  echo "  $(bold 'Next step:') Tell your agent to read:"
  echo "  $(cyan 'ONBOARD_AGENT_OPENCLAW.md')"
  echo ""
  echo "  The agent will ask you a few questions and set up"
  echo "  your profile, tasks, and daily planning schedule."
  echo ""
fi

echo "────────────────────────────────────────────────"
echo ""
echo "$(dim "Press Ctrl+C to stop the server.")"

# Keep script alive until Ctrl+C
wait "$SERVER_PID"
