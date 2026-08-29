#!/usr/bin/env bash
# Redeploy one bot from the latest commit on its connected branch.
# Normal path is `git push` (auto-deploy). Use this to force a rebuild, e.g. after
# changing HERMES_GIT_REF in Railway, or to redeploy without a new commit.
# Usage: scripts/deploy.sh <bot> [--restart]
#   --restart   restart the running deployment without rebuilding (picks up nothing
#               from Git; useful for a stuck gateway)
set -euo pipefail
BOT="${1:-}"; MODE="${2:-}"
[[ -n "$BOT" ]] || { echo "usage: $0 <bot> [--restart]" >&2; exit 1; }
RAILWAY_ENV="${RAILWAY_ENV:-production}"
if [[ "$MODE" == "--restart" ]]; then
  railway restart --service "$BOT" --environment "$RAILWAY_ENV" --yes
else
  railway redeploy --service "$BOT" --environment "$RAILWAY_ENV" --from-source --yes
fi
