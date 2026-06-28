# Local runner helper for path-check workflow

This script helps you run the `validate-paths` job from `.github/workflows/path-check.yml` locally using `act` (https://github.com/nektos/act).

Usage:
  1. Install Docker and act (https://github.com/nektos/act#installation).
  2. From the repository root run:
       bash scripts/run_path_check_locally.sh

What it does:
  - Generates a sample event JSON at `.github/workflows/event_push.json` (edit it to match the commit SHAs you want to compare).
  - Runs `act` with the `validate-paths` job using the provided event file.

Notes:
  - Replace the placeholder SHAs in the event JSON with real SHAs if you want git diffs to behave accurately.
  - If you want to emulate a pull_request event instead, update the event JSON accordingly and adjust the script command.

#!/usr/bin/env bash
set -euo pipefail

# Config
EVENT_FILE=".github/workflows/event_push.json"
GITHUB_ACTOR_VAL="${GITHUB_ACTOR:-sini1325}"
PLATFORM_MAP="ubuntu-latest=nektos/act-environments-ubuntu:18.04"
JOB_NAME="validate-paths"

# Check dependencies
if ! command -v act >/dev/null 2>&1; then
  echo "ERROR: act is not installed. Install it: https://github.com/nektos/act#installation"
  exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: Docker is not installed or not running. Install/start Docker first."
  exit 1
fi

# Create example event file (push event). Edit the before/after SHAs as needed.
cat > "$EVENT_FILE" <<'EOF'
{
  "before": "0000000000000000000000000000000000000000",
  "after": "0000000000000000000000000000000000000000",
  "ref": "refs/heads/main",
  "repository": {
    "full_name": "ohmyproject/m9p2-team1"
  },
  "pusher": {
    "name": "sini1325"
  }
}
EOF

echo "Wrote example event file to $EVENT_FILE (edit 'before' and 'after' SHAs if you want a real diff)
"

# Run act for the specific job
echo "Running act for job: $JOB_NAME (GITHUB_ACTOR=$GITHUB_ACTOR_VAL)"
act -j "$JOB_NAME" -e "$EVENT_FILE" -P "$PLATFORM_MAP" --env GITHUB_ACTOR="$GITHUB_ACTOR_VAL"

echo "Done. If the job fails due to missing secrets or services, read the workflow (.github/workflows/path-check.yml) and provide necessary secrets or run steps manually."