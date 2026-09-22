# Runbook

For the founder. Every command was checked against `railway --help` (5.45.7)
or the Hermes docs; see `RESEARCH.md` for sources.

## Slack: every agent

Every agent uses its own Slack bot connection. Set `SLACK_BOT_TOKEN`,
`SLACK_APP_TOKEN`, `SLACK_ALLOWED_USERS` (the owner's member ID), and
`SLACK_HOME_CHANNEL` (the DM conversation or private channel ID). Both
`GATEWAY_ALLOW_ALL_USERS` and `SLACK_ALLOW_ALL_USERS` must be `false`.
The entrypoint requires both tokens and a nonempty owner allowlist.

See [ENG.md](ENG.md#slack-activation) for app setup. The same Slack steps apply
to all agents; use separate app/bot tokens per agent. `eng` additionally uses
Sentry, PostHog, Railway, Linear, and GitHub. `product` uses GitHub docs/code,
Linear, PostHog aggregates, and public web research; its first-run knowledge
workflow is in [PRODUCT.md](PRODUCT.md). Live activation is separate from
editing souls or config.

## Add a new agent in four steps

1. `souls/<bot>.md`: define identity, ownership, communication, workflow, and
   authority. Keep it below Hermes's default 20,000-character context limit.
2. `config/<bot>.yaml`: copy the closest existing one, set `model.default`,
   add `mcp_servers` if it needs tools. Secrets go in as `${ENV_VAR}`.
3. `scripts/bootstrap.sh`: if the bot needs extra secrets, add a `case` line.
   Validate locally, then commit/push when authorized. The service builds from
   GitHub, so publishing to an existing service's branch can trigger deployment.
4. When deployment is authorized, add a service in the existing agent project
   using the GitHub setup below, with `BOT=<bot>` and its own Slack credentials
   and `/data` volume. `scripts/bootstrap.sh <bot>` is an alternative that also
   creates live resources. Confirm actual Slack delivery and integration reads.
   If it needs cron, see below.

## GitHub CI and Railway deployment

The normal deployment path is GitHub → Actions → Railway. The `CI` workflow
runs on pull requests and every push to `main`. It validates the fleet assets,
tests the entrypoint with fake credentials and isolated state, builds the actual
Dockerfile, and checks that Slack, MCP, and Anthropic dependencies import.
It does not connect to Slack, call a model, or deploy from GitHub Actions.

For the first deployment:

1. Create the separate `taikan-agents` Railway project. Add one service from
   `desmotech/taikan-agents`, named `eng`, connected to `main` at the repo root.
2. Mount a persistent volume at `/data` and keep one replica. The entrypoint
   checks Railway's `RAILWAY_VOLUME_MOUNT_PATH` and refuses an absent or wrong
   mount. Do not manually set this Railway-provided variable.
3. Set `BOT=eng`, `TZ=Asia/Jerusalem`, `GATEWAY_ALLOW_ALL_USERS=false`, and
   `SLACK_ALLOW_ALL_USERS=false`. Add `ANTHROPIC_API_KEY` and the Slack values
   from [ENG.md](ENG.md). Add the integration credentials there as available.
   Docker supplies `HOME=/data` and `HERMES_HOME=/data/.hermes`.
4. Enable **Wait for CI** in the service's source settings. Keep autodeploy
   enabled. Accept updated Railway GitHub App permissions if prompted.
5. Leave `HERMES_GIT_REF` unset so Railway uses the Dockerfile's tested pin.
   Confirm a green CI run, then inspect the first deployment's boot and perform
   [the activation checks](ENG.md#activation-checks).

The first source connection can start a build before these settings are ready;
the gateway refuses to start without its volume, Slack tokens, and owner allowlist.
Configure the service and deploy the latest passing commit once ready.

No Railway token belongs in GitHub Actions. Railway's repository integration
performs deployment. CI does not cancel `main` runs; failed validation/builds
must block deployment. [Railway's Wait for CI documentation](https://docs.railway.com/deployments/github-autodeploys)
describes its treatment of workflow conclusions.

Run the fast checks locally with Python 3.11 or newer:

```sh
python -m pip install -r requirements-ci.txt
python scripts/validate.py
python -m unittest discover -s tests -v
```

## Change a soul and ship it

Edit `souls/<bot>.md`, commit, `git push`. Railway rebuilds and redeploys the
service; the entrypoint copies the new file over `SOUL.md` on boot. Confirm with
`scripts/logs.sh <bot> -n 50` and look for `Installed SOUL.md and config.yaml`.
Same for `config/<bot>.yaml`. No `hermes` command is needed.

## Cron jobs (registered once per service, stored on the volume)

Hermes has no declarative cron files. Register over Railway SSH, once. They
persist in `/data/.hermes/cron/jobs.json` across deploys. `--deliver slack`
sends to `SLACK_HOME_CHANNEL`. Times are in the service's `timezone`
(`Asia/Jerusalem`).

Inspect `hermes cron list` first. If eng's morning digest already exists,
update its prompt and delivery using the installed `hermes cron edit --help`;
do not create a second job. The command below is for a missing job only.

```
# eng: morning digest 07:30
railway ssh --service eng -- hermes cron create "30 7 * * *" \
  "Morning digest per SOUL.md: unresolved incidents, new regressions, failed deploys or CI, performance changes, and decisions waiting on Saar. Read connected sources for the last 24h, link FIT issues, and report coverage gaps. Say Quiet night only after successful checks with no actionable findings." \
  --name "morning-digest" --deliver slack

# ops: daily watchdog 08:00, silence is a pass
railway ssh --service ops -- hermes cron create "0 8 * * *" \
  "Run the daily checks from your soul: GitHub Actions minutes, Sentry quota, Railway usage, last night's Postgres backup in R2 (exists, under 26h old, non-zero, size vs previous). If every check passes reply exactly: [SILENT]. Otherwise report only the crossed thresholds." \
  --name "daily-watchdog" --deliver slack

# scout: weekly report, Sunday 09:00
railway ssh --service scout -- hermes cron create "0 9 * * 0" \
  "Weekly market report: pricing and feature changes at Arbox, Boostaff, TrueCoach since last week, and up to five Israeli fitness industry news items. Diff against your memory. If nothing changed say so in one line." \
  --name "weekly-report" --deliver slack
```

### Release status monitor

Deploy with `scripts/bootstrap.sh release`. The only non-common variables are
`TAIKAN_RELEASE_API_URL` and an opaque `TAIKAN_RELEASE_ASSISTANT_TOKEN` minted
by the backend with read/preflight/nudge scope and an organization allowlist.
Do not copy credentials from any other bot into this service; the entrypoint
refuses Expo, store, signing, GitHub, database, and infrastructure credentials.

Register a read-only monitor if desired:

```
railway ssh --service release -- hermes cron create "*/15 * * * *" \
  "Monitor branded-app releases using release-client.py list. Report only status changes and actionable owner-safe blockers. Never execute an operation. If nothing changed reply exactly: [SILENT]." \
  --name "release-status-monitor" --deliver slack
```

Slack can never grant store-review or public-release approval. The bot may
only nudge an already-approved internal-upload operation after an explicit
human request; the backend rechecks the stored approval and dispatches the
protected workflow. Store review and public release remain manual console
actions recorded by an administrator.

Manage: `railway ssh --service <bot> -- hermes cron list|pause <id>|resume <id>|run <id>|remove <id>`.

## Logs and a stuck gateway

- Stream: `scripts/logs.sh eng`. Last 200 lines: `scripts/logs.sh eng -n 200`.
  Build logs: `scripts/logs.sh eng --build`. Errors only:
  `railway logs --service eng --latest --filter "@level:error"`.
- Hermes' own logs are on the volume: `railway ssh --service eng -- tail -n 100 /data/.hermes/logs/gateway.log`
  (secrets are redacted there by Hermes).
- Stuck (no replies, no errors): `scripts/deploy.sh eng --restart`. Restarts
  the container without rebuilding. The volume is untouched.
- Still stuck: `railway ssh --service eng -- hermes doctor`, then
  `scripts/deploy.sh eng` for a full rebuild from the latest commit.
- Bot ignores you: check `SLACK_ALLOWED_USERS` against your Slack member ID
  and follow [ENG.md](ENG.md). Inspect only the needed setting in the dashboard;
  `railway variable list` can expose every secret. Inspect pending pairing
  requests with `hermes pairing list`; approve only the verified owner.

### Startup warnings and deployment notifications

- `Early reject of unauthorized user U...`: incoming Slack events work, but
  that member ID is not allowed. Set `SLACK_ALLOWED_USERS` to the owner's raw
  member ID (comma-separated IDs for multiple authorized owners), with no
  quotes, mentions, display names, or channel IDs. Keep allow-all disabled.
- `Gateway shutting down` can be the old instance's notification during a
  deployment. Correlate its time with Railway's removed deployment and
  `Stopping Container` log; inspect the newest deployment before concluding
  the replacement failed.
- Railway reports stderr lines as errors even when Hermes labels them WARNING.
  Read the inner message and deployment status.
- Sentry and Railway MCP park until their first OAuth login. Follow
  [ENG.md](ENG.md#integrations) after attaching `/data`; a REST API token is
  not a substitute for Sentry MCP OAuth.
- SQLite's WAL-reset warning means Hermes selected `journal_mode=DELETE` to
  avoid the affected WAL path. It is not a startup failure. Fix the linked
  SQLite runtime in a tested image rebuild (3.51.3+ or a documented fixed
  backport); do not force WAL or run `hermes update` inside this pinned image.
  See [SQLite's advisory](https://sqlite.org/wal.html#walresetbug).
- Slack's missing `mpim:history` / `message.mpim` warning affects group DMs.
  One-to-one DMs and channels do not require group-DM access. If group DMs are
  needed, add `mpim:history` and `mpim:read`, subscribe to `message.mpim`, and
  reinstall the app. The `client` / `token` Bolt warning is nonfatal.

## Inspect the volume

```
railway ssh --service eng -- ls -la /data/.hermes
railway ssh --service eng -- cat /data/.hermes/SOUL.md        # should match souls/eng.md
railway ssh --service eng -- cat /data/.hermes/memories/MEMORY.md
railway ssh --service eng -- hermes cron list
railway ssh --service eng -- hermes status
railway volume list --service eng
```
`railway volume files list|download` can pull files without SSH.
`railway ssh --service eng -- hermes backup --quick` snapshots config, state.db,
`.env`, auth and cron jobs into `/data/.hermes/backups/`.

## Upgrading Hermes

Never run `hermes update` on Railway. It git-pulls `main` into the image, which
is thrown away on the next deploy and is not what Git says you run. Instead:

1. Pick a tag from https://github.com/NousResearch/hermes-agent/releases.
2. Update the Dockerfile's `HERMES_GIT_REF` default, `scripts/bootstrap.sh`, and
   `.env.example` together. Commit and push after approval; CI builds the new
   runtime before Railway deploys it. Remove any old Railway ref override so
   the service uses the tested Dockerfile default.
3. After it boots: `railway ssh --service eng -- hermes config check`, and if it
   reports new options, `railway ssh --service eng -- hermes config migrate`.
   Note: `config.yaml` is overwritten from Git on the next boot, so copy any
   change migrate makes into `config/eng.yaml` and push it.

Railway SSH is the way to run any one-off `hermes` command against a live
service: `railway ssh --service <bot> -- hermes <cmd>`.

## Cost per service, and stopping one

Railway meters RAM at ~$10/GB-month and CPU at ~$20/vCPU-month by the minute,
volume at $0.15/GB-month. A Hermes gateway idles at a few hundred MB and near
zero CPU, so expect roughly **$3-8/month per service** in compute, plus the
volume (under $1), plus the Hobby plan's $5 base which covers the first $5.
Model spend is separate and dominates: Opus 5 is $5/$25 per million input/output
tokens, Sonnet 5 $2/$10, Haiku 4.5 $1/$5. A daily cron on Opus that reads a lot
of Sentry can cost more than the service hosting it. Watch it:
`railway usage --json` and the Anthropic console. Set a hard cap once:
`railway usage limit set --target workspace --soft 20 --hard 40`.

Stop paying for one service, keep its memory: `railway scale --service scout eu-west=0`
(use the region shown in the dashboard). The volume still bills.
Remove it entirely: `railway service delete --service scout --environment production --yes`,
then `railway volume list` and `railway volume delete --volume <id> --yes`.
