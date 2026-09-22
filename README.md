# taikan-agents

> **Cost incident — 2026-09-22:** Eng is stopped and its key revoked.
> Agent startup now defaults off. Read [cost controls](docs/COST-CONTROLS.md) before
> any activation. Automatic cron dispatch and background reviews are disabled;
> older scheduling instructions below do not enable them.


Source of truth for Taikan's always-on AI agents. Each agent is a
[Hermes Agent](https://hermes-agent.nousresearch.com/) instance running a
Claude model on Railway, one service per agent, with Slack as the human
interface for every agent.

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
| `eng` | Claude Sonnet 5 | Lead architect and engineer; stability, on-call, performance; Slack wingman | stopped after cost incident; guarded changes pending |
| `product` | Claude Sonnet 5 | CPO across Taikan: vision, priorities, research, risk, specs, and outcomes | soul/config drafted; not deployed |
| `marketing` | Claude Sonnet 5 | Hebrew launch post drafts, never posts | scaffold |
| `ops` | Claude Haiku 4.5 | daily quota + backup watchdog, alerts on threshold only | scaffold |
| `scout` | Claude Sonnet 5 | weekly competitor + industry report | scaffold |
| `analyst` | Claude Sonnet 5 | PostHog instrumentation quality, aggregate only | scaffold |
| `release` | Claude Haiku 4.5 | branded-app status, owner-safe preflight, and approved-operation nudge | available |

## Layout

```
souls/      one SOUL.md per agent          -> ${HERMES_HOME}/SOUL.md
config/     one config.yaml per agent      -> ${HERMES_HOME}/config.yaml
scripts/    bootstrap/deploy/logs plus restricted release API client and entrypoint
docs/       RESEARCH.md RUNBOOK.md UNVERIFIED.md
Dockerfile  upstream's, plus COPY souls/ and config/
```

Automatic cron dispatch is disabled. Existing schedules remain stored for
inspection; [cost controls](docs/COST-CONTROLS.md) govern any reactivation.

## Daily use

GitHub Actions checks every pull request and push to `main`: shell/Python
syntax, agent YAML and soul assets, gateway startup/access controls, and the
Docker image with its Slack, MCP, and Anthropic dependencies. No production
credentials are needed in GitHub.

After explicit reactivation approval, link Railway's `eng` service to this
repo's `main` branch and enable **Wait for CI** in service settings. Railway builds and deploys after CI succeeds.
See [the deployment setup](docs/RUNBOOK.md#github-ci-and-railway-deployment).

```
git push                        # ships a soul or config change (auto-deploy)
scripts/logs.sh eng             # stream logs
scripts/deploy.sh eng --restart # kick a stuck gateway
```

The Dockerfile pins Hermes by default. Keep `HERMES_GIT_REF` unset in Railway
to build the same runtime CI tests. Change the pin in Git when upgrading.

Start with [docs/RUNBOOK.md](docs/RUNBOOK.md). Open questions are in
[docs/UNVERIFIED.md](docs/UNVERIFIED.md).

For `eng`'s authority, integrations, and Slack activation, read
[souls/eng.md](souls/eng.md) and [docs/ENG.md](docs/ENG.md). Configuration in
this repo does not establish live tool access or install monitoring jobs.

For `product`'s decision process, document knowledge, and first assignment, read
[souls/product.md](souls/product.md) and [docs/PRODUCT.md](docs/PRODUCT.md).
[Acceptance scenarios](docs/PRODUCT-EVALS.md) check its judgment after activation.
