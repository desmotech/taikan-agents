#!/usr/bin/env bash
# Tail logs for one bot. Streams by default; -n N fetches the last N lines instead.
# Usage: scripts/logs.sh <bot> [-n N] [--build]
set -euo pipefail
BOT="${1:-}"; shift || true
[[ -n "$BOT" ]] || { echo "usage: $0 <bot> [-n N] [--build]" >&2; exit 1; }
RAILWAY_ENV="${RAILWAY_ENV:-production}"
railway logs --service "$BOT" --environment "$RAILWAY_ENV" --latest "$@"
