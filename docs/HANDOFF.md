# HANDOFF - taikan-agents

Written 2026-08-29. Read this first, then `docs/RESEARCH.md`,
`docs/UNVERIFIED.md`, `docs/RUNBOOK.md`, `docs/WEBHOOKS.md`.

## Standing rules from the owner (do not violate)

1. **Never invent a config key or a CLI flag.** If you cannot verify it in the
   docs or the source, put it in `docs/UNVERIFIED.md` with the question, use a
   safe default, and say so. Five open questions beat one silent guess.
2. **Ask before spending money or creating anything in the Railway account.**
   Each service costs money. Only `eng` is approved for deployment.
   `marketing`, `ops`, `scout`, `analyst` stay scaffold-only until he says
   otherwise.
3. **Never log or echo a secret value.** Secrets are typed by the owner at a
   hidden prompt and piped to `railway variable set --stdin`. They must not
   enter an agent's context, the shell history, or a file.
4. Architecture is settled, do not redesign it: one Railway service per agent,
   one volume at `/data`, `HERMES_HOME=/data/.hermes`, `HOME=/data`, never
   mount the volume over the install dir, 1 replica, Git wins for `SOUL.md` and
   `config.yaml` on every boot, the entrypoint never touches
   `memories/ skills/ sessions/ cron/ state.db auth.json`,
   `GATEWAY_ALLOW_ALL_USERS=false` with an explicit `TELEGRAM_ALLOWED_USERS`,
   one bot token per agent, no agent-to-agent messaging, no agent talks to a
   customer, and **never run `hermes update` on Railway** - upgrade by bumping
   `HERMES_GIT_REF` and redeploying.

## Where things stand

- Repo `/home/saar/dev/taikan-agents`, remotes `origin=desmotech/taikan-agents`,
  `upstream=lovexbytes/hermes-railway-template`. Scaffold committed at `fcfd04b`
  and pushed. Steps 1-3 of the original plan (research, build, review) are DONE
  and approved.
- **Nothing exists in Railway yet.** No project, no service, no volume, no
  domain, no spend.
- Decision already made by the owner: `eng` goes in a **NEW Railway project
  named `taikan-agents`**, not inside the existing `Taikan` project.
- The owner is deploying from home. He runs the bootstrap himself because it
  prompts for secrets interactively.

## The immediate next step

The owner runs this in his own terminal (NOT you - it needs his keyboard for
the secret prompts):

    scripts/bootstrap.sh eng

Optionally prefixed with `RAILWAY_REGION=eu-west` to pin the replica in the
same pass; otherwise the script prints the manual replicas step.

The script is idempotent and will: create+link project `taikan-agents`, create
service `eng` with non-secret vars, add the `/data` volume, prompt for secrets,
then `railway service source connect` - which is what triggers the first build
and the first spend.

Variables it sets automatically: `BOT`, `HERMES_GIT_REF` (v2026.8.27),
`HERMES_HOME=/data/.hermes`, `HOME=/data`, `TZ=Asia/Jerusalem`,
`GATEWAY_ALLOW_ALL_USERS=false`.

Secrets it prompts for (empty input = skip): `ANTHROPIC_API_KEY`,
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS` (numeric id),
`TELEGRAM_HOME_CHANNEL` (same id), `SENTRY_AUTH_TOKEN`, `LINEAR_API_KEY`,
`GITHUB_TOKEN`.

Do NOT set any `WEBHOOK_*` variable yet. `config/eng.yaml` has no
`platforms.webhook` block, so they would be dead weight.

## What YOU do once he says it finished

1. `scripts/logs.sh eng --build` then `scripts/logs.sh eng` - read the build and
   the boot.
2. Confirm the bootstrap line appears:
   `[bootstrap] bot=eng commit=<sha> hermes_ref=v2026.8.27` followed by
   `[bootstrap] Installed SOUL.md and config.yaml from Git for bot=eng`.
3. **Watch for UNVERIFIED #1**: whether Hermes accepts the model id
   `claude-opus-5` (no date suffix). If the provider rejects it, the fix is in
   `config/eng.yaml` -> `model.default`, then redeploy.
4. **Watch for UNVERIFIED #2**: the gateway may refuse to run as root. The
   upstream image runs as root. If it refuses, the suspected switch is
   `HERMES_ALLOW_ROOT_GATEWAY=1` - **this is UNVERIFIED, confirm it in the
   Hermes source before setting it.** Do not guess an env var name.
5. Ask the owner to message the bot on Telegram and confirm it answers. If it
   asks for pairing, approve over SSH:
   `railway ssh --service eng -- hermes pairing approve telegram <code>`.
6. Volume durability test: write a marker, redeploy, confirm it survived.

       railway ssh --service eng -- sh -c 'echo ok > /data/.hermes/marker'
       scripts/deploy.sh eng
       railway ssh --service eng -- cat /data/.hermes/marker

   Also confirm `memories/`, `sessions/`, `state.db` still exist under
   `/data/.hermes` after the redeploy.
7. Register the morning digest (cron is CLI-only, it is not declarative):

       railway ssh --service eng -- hermes cron create "30 7 * * *" \
         "Morning digest per SOUL.md" --name morning-digest --deliver telegram

   Verify with `railway ssh --service eng -- hermes cron list`.
8. Give the owner the step-5 report he asked for: what was built, what is still
   unverified, and what you disagree with.

## Phase 2 - only after the plain boot is confirmed good

`docs/WEBHOOKS.md` has the full verified design for making `eng` proactive
(push triggers instead of polling). Do not start it before step 1-8 pass.
Order: add `platforms.webhook` to `config/eng.yaml` -> expose the domain with
`railway domain --port 8644 --service eng` -> wire the GitHub Actions route
(no shim needed, signature natively supported) -> write the Cloudflare Worker
that re-signs Sentry's `Sentry-Hook-Signature` as `X-Webhook-Signature`, then
wire the Sentry internal integration.

**First thing to check on the live container**, because it invalidates the
route configs if wrong: webhook-triggered runs get a restricted default
toolset (`web_search`, `web_extract`, `vision_analyze`, `clarify`) and cannot
see the MCP servers unless the route overrides `toolsets:`. The dynamic names
are believed to be `mcp-sentry`, `mcp-linear`, `mcp-github` but that is
UNVERIFIED - confirm against the running gateway before trusting any route to
investigate anything.

## Things not to do

- Do not run the bootstrap yourself; the secret prompts need the owner.
- Do not deploy any agent other than `eng`.
- Do not commit `.env` or any real token.
- Do not redesign the souls or the config layout; they were reviewed and
  approved as they are.
