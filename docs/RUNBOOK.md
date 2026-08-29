# Runbook

For the founder. Every command was checked against `railway --help` (5.45.7)
or the Hermes docs; see `RESEARCH.md` for sources.

## Telegram: bot token and your user id

1. Open Telegram, talk to `@BotFather`, send `/newbot`. Pick a name and a
   username ending in `bot` (one bot per agent, e.g. `taikan_eng_bot`). BotFather
   replies with a token like `123456:ABC-...`. That is `TELEGRAM_BOT_TOKEN`.
2. Your numeric user id: talk to `@userinfobot` (or `@getidsbot`); it replies
   with a number like `123456789`. That is `TELEGRAM_ALLOWED_USERS` and also
   `TELEGRAM_HOME_CHANNEL` (your DM chat id equals your user id). Never a
   username.
3. Open a chat with the new bot and press Start once, so it can message you.

## Add a new agent in four steps

1. `souls/<bot>.md`: five sections, under 100 lines, copy the shape of `eng.md`.
2. `config/<bot>.yaml`: copy the closest existing one, set `model.default`,
   add `mcp_servers` if it needs tools. Secrets go in as `${ENV_VAR}`.
3. `scripts/bootstrap.sh`: if the bot needs extra secrets, add a `case` line.
   Commit and push (the service builds from GitHub, so the files must be there).
4. `scripts/bootstrap.sh <bot>`, type the secrets at the prompts, then
   `scripts/logs.sh <bot>` and wait for `[bootstrap] Starting Hermes gateway...`.
   Send the bot a message on Telegram. If it needs cron, see below.

## Change a soul and ship it

Edit `souls/<bot>.md`, commit, `git push`. Railway rebuilds and redeploys the
service; the entrypoint copies the new file over `SOUL.md` on boot. Confirm with
`scripts/logs.sh <bot> -n 50` and look for `Installed SOUL.md and config.yaml`.
Same for `config/<bot>.yaml`. No `hermes` command is needed.

## Cron jobs (registered once per service, stored on the volume)

Hermes has no declarative cron files. Register over Railway SSH, once. They
persist in `/data/.hermes/cron/jobs.json` across deploys. `--deliver telegram`
sends to `TELEGRAM_HOME_CHANNEL`. Times are in the service's `timezone`
(`Asia/Jerusalem`).

```
# eng: morning digest 07:30
railway ssh --service eng -- hermes cron create "30 7 * * *" \
  "Morning digest: new Sentry error groups in the last 24h with likely cause, failed GitHub Actions runs on main with the failing step, Linear FIT tickets you opened. If nothing happened reply exactly: Quiet night." \
  --name "morning-digest" --deliver telegram

# ops: daily watchdog 08:00, silence is a pass
railway ssh --service ops -- hermes cron create "0 8 * * *" \
  "Run the daily checks from your soul: GitHub Actions minutes, Sentry quota, Railway usage, last night's Postgres backup in R2 (exists, under 26h old, non-zero, size vs previous). If every check passes reply exactly: [SILENT]. Otherwise report only the crossed thresholds." \
  --name "daily-watchdog" --deliver telegram

# scout: weekly report, Sunday 09:00
railway ssh --service scout -- hermes cron create "0 9 * * 0" \
  "Weekly market report: pricing and feature changes at Arbox, Boostaff, TrueCoach since last week, and up to five Israeli fitness industry news items. Diff against your memory. If nothing changed say so in one line." \
  --name "weekly-report" --deliver telegram
```

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
- Bot ignores you: check `TELEGRAM_ALLOWED_USERS` is your numeric id
  (`railway variable list --service eng`). Or approve a pairing code:
  `railway ssh --service eng -- hermes pairing list`.

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
2. `railway variable set HERMES_GIT_REF=v2026.9.x --service eng` (repeat per service). Variables changes trigger a deploy; or run `scripts/deploy.sh eng`.
3. After it boots: `railway ssh --service eng -- hermes config check`, and if it
   reports new options, `railway ssh --service eng -- hermes config migrate`.
   Note: `config.yaml` is overwritten from Git on the next boot, so copy any
   change migrate makes into `config/eng.yaml` and push it.
4. Update the default in `scripts/bootstrap.sh` and `.env.example`.

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
