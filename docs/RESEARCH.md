# Research notes

> Historical upstream research from 2026-08-29, not the current fleet setup.
> Taikan agents now use Slack exclusively. Current bootstrap and entrypoint
> behavior are documented in [RUNBOOK.md](RUNBOOK.md) and [ENG.md](ENG.md).
> Other platform examples below describe the original upstream capabilities.

Merged from three independent reads on 2026-08-29: the upstream template
source, the Hermes docs (site + repo at commit `217ab2f`, 2026-08-28), and
`railway --help` (CLI 5.45.7). Nothing here is from memory. Where the sources
were silent, the item is in `UNVERIFIED.md` instead.

## 1. The fork (upstream `lovexbytes/hermes-railway-template`, HEAD `83611df`, 2026-08-16)

Files: `Dockerfile`, `.dockerignore`, `.gitignore`, `railway.toml`, `README.md`,
`scripts/entrypoint.sh`. No config.yaml, no SOUL.md anywhere in the repo.

**Dockerfile.** Two-stage `python:3.11-slim`. Builder: `ARG HERMES_GIT_REF`
(no default; `test -n` fails the build if empty), `git fetch --depth 1 origin
$HERMES_GIT_REF` from `NousResearch/hermes-agent` into `/opt/hermes-agent`,
`pip install -e "/opt/hermes-agent[messaging,cron,cli,pty]"` into `/opt/venv`.
Tags, branches and SHAs all work. Runtime: `ENV HERMES_HOME=/data/.hermes
HOME=/data`, copies `/opt/venv` and `/opt/hermes-agent`, copies **only**
`scripts/entrypoint.sh` to `/app/scripts/`. `ENTRYPOINT ["tini","--"]`,
`CMD ["/app/scripts/entrypoint.sh"]`. Runs as root. No EXPOSE, no HEALTHCHECK.
Railway passes service variables into Dockerfile `ARG`s by name
(docs.railway.com/builds/dockerfiles#using-variables-at-build-time), which is
how `HERMES_GIT_REF` reaches the build.

**railway.toml.** `builder = "dockerfile"`, `restartPolicyType = "on_failure"`,
`requiredMountPath = "/data"`, variables `HERMES_HOME=/data/.hermes`, `HOME=/data`.

**entrypoint.sh (203 lines, `set -euo pipefail`), in order:**

1. L4-13: defaults `HERMES_HOME`, `HOME`; `mkdir -p` `$HERMES_HOME/{logs,sessions,cron,pairing}` and `/data/workspace`.
2. L159: exit 1 unless a provider key is set (`ANTHROPIC_API_KEY` counts).
3. L164: exit 1 unless `TELEGRAM_BOT_TOKEN`, `DISCORD_BOT_TOKEN` or Slack tokens are set.
4. L166 `migrate_legacy_messaging_cwd`: if a legacy `MESSAGING_CWD` exists (old `.env` or env) it patches `terminal.cwd` into config.yaml; else **creates config.yaml only if missing** with `terminal.{backend,cwd,timeout}` + `compression.{enabled,threshold}`.
5. L168-186: **overwrites** `${HERMES_HOME}/.env` from an explicit allowlist of env vars (provider keys, `TELEGRAM_*`, `DISCORD_*`, `SLACK_*`, `GATEWAY_ALLOW_ALL_USERS`, `GITHUB_TOKEN`, `TERMINAL_*`, ...). Not everything: e.g. `SENTRY_AUTH_TOKEN` is not copied. That is fine because Hermes also reads the process environment (docs: "reads environment variables from the process environment and, for user-managed secrets, from `~/.hermes/.env`"), and the script `exec`s without clearing env.
6. L188-193: writes `.initialized` on first run. Informational only; nothing is gated on it.
7. L195-199: stderr warning if no `*_ALLOWED_USERS` and no `*_ALLOW_ALL_USERS`.
8. L201-203: `unset MESSAGING_CWD`, **`exec hermes gateway`**.

### My diff against upstream

Kept everything. Added, so a future `git merge upstream/main` touches two spots:

- `Dockerfile`: two `COPY` lines after the entrypoint copy (`souls/` and `config/` -> `/app/`).
- `scripts/entrypoint.sh`: one block inserted between the allowlist warning (L199) and `echo "[bootstrap] Starting Hermes gateway..."`. It: fails if `BOT` is unset or `/app/souls/$BOT.md` / `/app/config/$BOT.yaml` is missing; logs `bot=`, `commit=$RAILWAY_GIT_COMMIT_SHA` (Railway-provided, docs.railway.com/variables/reference#git-variables) and `hermes_ref=`; `cp -f` both files. No secret is logged.
- `README.md` moved to `docs/UPSTREAM-README.md` (rename, content unchanged).

Effect on upstream's step 4: it still runs and may create/patch config.yaml, then
my copy overwrites it. To keep behaviour identical, every `config/*.yaml`
carries the same `terminal.cwd: /data/workspace` and `compression` block the
template would have generated. The legacy migration code is untouched.

To pull upstream later: `git fetch upstream && git merge upstream/main`. Conflicts
can only land in those two files.

## 2. Hermes (pinned `v2026.8.27` = 0.20.6, released 2026-08-27; weekly cadence)

**HERMES_HOME layout** (docs/user-guide/configuration#directory-structure):
`config.yaml`, `.env`, `auth.json`, `SOUL.md`, `memories/`, `skills/`, `cron/`
(`jobs.json`, `executions.db`, `output/`), `sessions/`, `logs/`, `state.db`
(+wal/shm), `pairing/`, `mcp-tokens/`, `home/`, `hooks/`, `skins/`, `scripts/`.
The entrypoint writes only `SOUL.md`, `config.yaml`, `.env`, `.initialized`.

**SOUL.md** (docs/user-guide/features/personality, guides/use-soul-with-hermes):
loaded only from `$HERMES_HOME/SOUL.md`, becomes slot #1 of the system prompt
verbatim, truncated at `context_file_max_chars` (default 20,000). Seeded on
first run if absent, never overwritten by Hermes. Changes apply at next session.

**Precedence** (configuration#configuration-precedence): CLI args > config.yaml
> .env > defaults. Secrets in `.env`, everything else in config.yaml.

**config.yaml keys used in this repo** (all quoted from docs):

```yaml
model:                      # integrations/providers#anthropic-native
  provider: anthropic
  default: claude-opus-5    # native ids use dashes, no "anthropic/" prefix
timezone: "Asia/Jerusalem"  # configuration#timezone; "affects cron scheduling"
terminal:                   # configuration#terminal-backend-configuration
  backend: local
  cwd: /data/workspace
  timeout: 180
compression: {enabled: true, threshold: 0.85}
memory:                     # configuration#memory-configuration
  memory_enabled: true
  user_profile_enabled: true
cron:
  wrap_response: false      # features/cron: removes header/footer on delivery
mcp_servers:                # reference/mcp-config-reference
  <name>:
    url: "https://..."      # HTTP transport
    headers: {Authorization: "Bearer ${ENV_VAR}"}   # ${VAR} resolves from .env / process env
    auth: oauth             # alternative; tokens -> mcp-tokens/<name>.json
    enabled: true
    timeout: 120
```

Linear's remote MCP (`https://mcp.linear.app/mcp`) is the docs' own OAuth
example. Tools appear as `mcp__<server>__<tool>`; `/reload-mcp` reloads.

**Gateway / Telegram** (reference/environment-variables, messaging/telegram):
`TELEGRAM_BOT_TOKEN`; `TELEGRAM_ALLOWED_USERS` = comma-separated **numeric**
user ids ("not your username"); `GATEWAY_ALLOW_ALL_USERS` default `false`;
`TELEGRAM_HOME_CHANNEL` = chat id for cron delivery ("your personal DM chat id
is the same as your user id"); `/sethome` sets it from chat. Unknown DM senders
get a pairing code (`unauthorized_dm_behavior: pair` default); approve with
`hermes pairing approve telegram <code>`. Token locks stop a second gateway on
the same bot token. Profiles doc: "Never point two agent processes at the same
profile (the same Hermes home)."

**Cron** (features/cron, reference/cli-commands#hermes-cron): not declarative.
Jobs live in `cron/jobs.json` (do not hand-edit). CLI:
`hermes cron create "<schedule>" "<prompt>" --name "<n>" --deliver telegram`
plus `--model --provider --skill --workdir --continuity`; `list`, `edit`,
`pause`, `resume`, `run`, `remove`, `status`, `tick`. `--deliver telegram`
goes to `TELEGRAM_HOME_CHANNEL`; `telegram:<chat_id>` targets a chat. A
response containing `[SILENT]` suppresses delivery. No per-job timezone flag;
the global `timezone:` key governs scheduling.

**CLI** (reference/cli-commands): `hermes config check|migrate|show|get|set`,
`hermes doctor [--fix]`, `hermes mcp add|list|test|login`, `hermes skills ...`,
`hermes pairing ...`, `hermes status`, `hermes backup --quick`. `hermes update`
git-pulls `main`: never on Railway; bump `HERMES_GIT_REF` instead.

**Docker page** (user-guide/docker): official image runs the gateway as user
`hermes` (uid 10000) and refuses root unless `HERMES_ALLOW_ROOT_GATEWAY=1`.
The template's image is not the official image and runs as root; see
UNVERIFIED #2.

## 3. Railway CLI 5.45.7 (all from `--help`)

Account: workspace `desmotech`, one existing project `Taikan`. Nothing was
created during research.

| step | command |
|---|---|
| link / create project | `railway link --project <name> --environment <env> --json`; `railway init --name <name> --json` |
| create service | `railway add --service <name> --variables K=V ... --json` (or `--repo owner/repo --branch main`) |
| connect GitHub (auto-deploy) | `railway service source connect --repo owner/repo --branch main --service <svc> --json` |
| volume | `railway volume add --service <svc> --mount-path /data --json`; `railway volume list --service <svc> --json` |
| variables | `railway variable set K=V K2=V2 --service <svc> --skip-deploys --json`; secret: `printf %s "$v" \| railway variable set KEY --stdin --service <svc> --skip-deploys` |
| replicas | `railway scale --service <svc> <region>=1` (per region; e.g. `eu-west=1`) |
| redeploy | `railway redeploy --service <svc> --from-source --yes` (`railway deploy` is templates, not this) |
| restart (no rebuild) | `railway restart --service <svc> --yes` |
| logs | `railway logs --service <svc> --latest [-n N] [--build] [--filter "@level:error"]` (streams unless `-n`/`--since`) |
| one-off command | `railway ssh --service <svc> -- hermes config migrate` |
| stop paying | `railway scale --service <svc> <region>=0`; `railway service delete --service <svc> --environment <env> --yes`; `railway volume delete --volume <id> --yes` |
| usage | `railway usage --json`, `railway usage limit set --target workspace --soft 20 --hard 40` |

`railway variable list --json|--kv` prints raw secret values; avoid in logs.

## 4. Costs (docs.railway.com/guides/estimate-ai-agent-costs#a-worksheet)

RAM $10/GB-month, vCPU $20/vCPU-month (metered per minute), volume
$0.15/GB-month, egress $0.05/GB. Hobby plan $5/month including $5 of usage.

## 5. Claude model ids

`claude-opus-5`, `claude-sonnet-5`, `claude-haiku-4-5`. Exact strings, no date
suffixes. Hermes passes them to the Anthropic API unchanged (UNVERIFIED #1).
