# taikan-agents

Source of truth for Taikan's always-on AI agents. Each agent is a
[Hermes Agent](https://hermes-agent.nousresearch.com/) instance running a
Claude model on Railway, one service per agent, with Telegram as the only
human interface.

This repo is a fork of
[lovexbytes/hermes-railway-template](https://github.com/lovexbytes/hermes-railway-template)
(upstream README: [docs/UPSTREAM-README.md](docs/UPSTREAM-README.md)). The
fork adds one thing: on every boot the entrypoint copies `souls/$BOT.md` to
`SOUL.md` and `config/$BOT.yaml` to `config.yaml`. Git wins. State on the
volume (`memories/`, `skills/`, `sessions/`, `cron/`, `state.db`, `auth.json`)
is never touched.

## Agents

| bot | model | job | status |
|---|---|---|---|
| `eng` | Claude Opus 5 | Sentry triage, Linear tickets, CI log reading, 07:30 digest | deployed |
| `marketing` | Claude Sonnet 5 | Hebrew launch post drafts, never posts | scaffold |
| `ops` | Claude Haiku 4.5 | daily quota + backup watchdog, alerts on threshold only | scaffold |
| `scout` | Claude Sonnet 5 | weekly competitor + industry report | scaffold |
| `analyst` | Claude Opus 5 | PostHog instrumentation quality, aggregate only | scaffold |
| `release` | Claude Haiku 4.5 | branded-app status, owner-safe preflight, and approved-operation nudge | available |

## Layout

```
souls/      one SOUL.md per agent          -> ${HERMES_HOME}/SOUL.md
config/     one config.yaml per agent      -> ${HERMES_HOME}/config.yaml
scripts/    bootstrap/deploy/logs plus restricted release API client and entrypoint
docs/       RESEARCH.md RUNBOOK.md UNVERIFIED.md
Dockerfile  upstream's, plus COPY souls/ and config/
```

Cron jobs are not declarative in Hermes; they are registered once per service
over Railway SSH. The exact commands are in [docs/RUNBOOK.md](docs/RUNBOOK.md).

## Daily use

```
scripts/bootstrap.sh eng        # create or converge the Railway service
git push                        # ships a soul or config change (auto-deploy)
scripts/logs.sh eng             # stream logs
scripts/deploy.sh eng --restart # kick a stuck gateway
```

Start with [docs/RUNBOOK.md](docs/RUNBOOK.md). Open questions are in
[docs/UNVERIFIED.md](docs/UNVERIFIED.md).
