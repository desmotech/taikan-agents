#!/usr/bin/env bash
# Create (or converge) one Railway service for one bot, from the desmotech/taikan-agents repo.
# Idempotent: safe to run twice. Every flag below was checked against `railway ... --help`
# (CLI 5.45.7). Steps with no CLI equivalent print the dashboard steps and continue.
#
# Usage:  scripts/bootstrap.sh <bot>            e.g. scripts/bootstrap.sh eng
# Env:    RAILWAY_PROJECT   project name to link or create   (default: taikan-agents)
#         RAILWAY_ENV       environment                      (default: production)
#         GITHUB_REPO       owner/repo of the fork           (default: desmotech/taikan-agents)
#         GIT_BRANCH        branch to auto-deploy            (default: main)
#         HERMES_GIT_REF    pinned Hermes tag                (default: v2026.8.27)
#         RAILWAY_REGION    region for `railway scale`, e.g. eu-west. Unset = print manual step.
set -euo pipefail

BOT="${1:-}"
[[ -n "$BOT" ]] || { echo "usage: $0 <bot>   (one of: $(ls souls | sed 's/\.md$//' | tr '\n' ' '))" >&2; exit 1; }
[[ -f "souls/$BOT.md" && -f "config/$BOT.yaml" ]] || { echo "error: souls/$BOT.md or config/$BOT.yaml missing" >&2; exit 1; }

RAILWAY_PROJECT="${RAILWAY_PROJECT:-taikan-agents}"
RAILWAY_ENV="${RAILWAY_ENV:-production}"
GITHUB_REPO="${GITHUB_REPO:-desmotech/taikan-agents}"
GIT_BRANCH="${GIT_BRANCH:-main}"
HERMES_GIT_REF="${HERMES_GIT_REF:-v2026.8.27}"

log() { printf '\n==> %s\n' "$*"; }
manual() { printf '\n!! No CLI equivalent. Do this in the dashboard:\n   %s\n' "$*"; }

# Prompt for a secret without echo; empty input = skip (keeps an existing value).
set_secret() {
  local key="$1" prompt="$2" value
  read -rs -p "$prompt (empty = skip): " value; echo
  if [[ -n "$value" ]]; then
    printf '%s' "$value" | railway variable set "$key" --stdin --service "$BOT" --environment "$RAILWAY_ENV" --skip-deploys --json >/dev/null
    echo "   set $key"
  else
    echo "   skipped $key"
  fi
}
set_plain() {
  local key="$1" prompt="$2" value
  read -r -p "$prompt (empty = skip): " value
  if [[ -n "$value" ]]; then
    railway variable set "$key=$value" --service "$BOT" --environment "$RAILWAY_ENV" --skip-deploys --json >/dev/null
    echo "   set $key=$value"
  else
    echo "   skipped $key"
  fi
}

log "Railway account"
railway whoami

log "Project: $RAILWAY_PROJECT"
if railway link --project "$RAILWAY_PROJECT" --environment "$RAILWAY_ENV" --json >/dev/null 2>&1; then
  echo "   linked existing project"
else
  echo "   not found, creating"
  railway init --name "$RAILWAY_PROJECT" --json >/dev/null
  railway link --project "$RAILWAY_PROJECT" --environment "$RAILWAY_ENV" --json >/dev/null
fi
railway status

log "Service: $BOT"
# `railway service list --json` shape is not documented; a plain name match is the
# conservative check (a false positive only skips creation, it never duplicates).
if railway service list --json 2>/dev/null | grep -q "\"$BOT\""; then
  echo "   exists"
else
  # Create the service empty (with the non-secret variables) BEFORE connecting the
  # repo, so the first build already has HERMES_GIT_REF and does not fail.
  railway add --service "$BOT" \
    --variables "BOT=$BOT" \
    --variables "HERMES_GIT_REF=$HERMES_GIT_REF" \
    --variables "HERMES_HOME=/data/.hermes" \
    --variables "HOME=/data" \
    --variables "TZ=Asia/Jerusalem" \
    --variables "GATEWAY_ALLOW_ALL_USERS=false" \
    --json >/dev/null
  echo "   created"
fi

log "Non-secret variables (converge)"
railway variable set \
  "BOT=$BOT" "HERMES_GIT_REF=$HERMES_GIT_REF" "HERMES_HOME=/data/.hermes" "HOME=/data" \
  "TZ=Asia/Jerusalem" "GATEWAY_ALLOW_ALL_USERS=false" \
  --service "$BOT" --environment "$RAILWAY_ENV" --skip-deploys --json >/dev/null
echo "   BOT HERMES_GIT_REF HERMES_HOME HOME TZ GATEWAY_ALLOW_ALL_USERS"

log "Volume at /data"
if railway volume list --service "$BOT" --environment "$RAILWAY_ENV" --json 2>/dev/null | grep -q '"/data"'; then
  echo "   exists"
else
  railway volume add --service "$BOT" --environment "$RAILWAY_ENV" --mount-path /data --json >/dev/null
  echo "   created"
fi

log "Secrets (typed here, never read from a file, never echoed)"
set_secret ANTHROPIC_API_KEY   "ANTHROPIC_API_KEY"
set_secret TELEGRAM_BOT_TOKEN  "TELEGRAM_BOT_TOKEN (from @BotFather)"
set_plain  TELEGRAM_ALLOWED_USERS "TELEGRAM_ALLOWED_USERS (your numeric Telegram user id)"
set_plain  TELEGRAM_HOME_CHANNEL  "TELEGRAM_HOME_CHANNEL (same id; where cron output is delivered)"
case "$BOT" in
  eng)     set_secret SENTRY_AUTH_TOKEN "SENTRY_AUTH_TOKEN"; set_secret LINEAR_API_KEY "LINEAR_API_KEY"; set_secret GITHUB_TOKEN "GITHUB_TOKEN (read-only PAT)";;
  ops)     set_secret GITHUB_TOKEN "GITHUB_TOKEN"; set_secret SENTRY_AUTH_TOKEN "SENTRY_AUTH_TOKEN"; set_secret RAILWAY_API_TOKEN "RAILWAY_API_TOKEN"
           set_secret R2_ACCESS_KEY_ID "R2_ACCESS_KEY_ID"; set_secret R2_SECRET_ACCESS_KEY "R2_SECRET_ACCESS_KEY"
           set_plain R2_ENDPOINT "R2_ENDPOINT"; set_plain R2_BACKUP_BUCKET "R2_BACKUP_BUCKET";;
  analyst) set_secret POSTHOG_API_KEY "POSTHOG_API_KEY (personal API key, read scopes)";;
  release) set_plain TAIKAN_RELEASE_API_URL "TAIKAN_RELEASE_API_URL (https://api.taikan.fit)"
           set_secret TAIKAN_RELEASE_ASSISTANT_TOKEN "TAIKAN_RELEASE_ASSISTANT_TOKEN (backend-scoped, read/preflight/nudge only)";;
esac

log "Source: GitHub $GITHUB_REPO@$GIT_BRANCH (auto-deploy on push)"
# Connecting the repo is what triggers the first deploy. Re-running is harmless.
railway service source connect --repo "$GITHUB_REPO" --branch "$GIT_BRANCH" --service "$BOT" --environment "$RAILWAY_ENV" --json >/dev/null
echo "   connected"

log "Replicas = 1"
if [[ -n "${RAILWAY_REGION:-}" ]]; then
  railway scale --service "$BOT" --environment "$RAILWAY_ENV" "$RAILWAY_REGION=1" --json >/dev/null
  echo "   $RAILWAY_REGION=1"
else
  manual "Service $BOT -> Settings -> Deploy -> Replicas: confirm it is 1 (the default). Or re-run with RAILWAY_REGION=eu-west."
fi

manual "Service $BOT -> Settings -> Deploy -> Restart policy: On failure (railway.toml sets this too)."

log "Done. Watch the first deploy:"
echo "   scripts/logs.sh $BOT"
