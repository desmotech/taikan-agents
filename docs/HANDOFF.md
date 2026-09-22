# HANDOFF - taikan-agents

> **Cost incident — 2026-09-22:** Eng is stopped and its key revoked.
> Agent startup now defaults off. Read [cost controls](COST-CONTROLS.md) before
> any activation. Automatic cron dispatch and background reviews are disabled;
> older scheduling instructions below do not enable them.


Current direction: every agent communicates with Saar through Slack. Start
with [ENG.md](ENG.md), [PRODUCT.md](PRODUCT.md), [RUNBOOK.md](RUNBOOK.md), and
[UNVERIFIED.md](UNVERIFIED.md).
`RESEARCH.md` and `UPSTREAM-README.md` preserve the original upstream research;
their alternative platform examples are not fleet setup instructions.

## Architecture and boundaries

- Verify configuration keys and CLI flags against documentation or source.
  Record anything unverified in `UNVERIFIED.md`; do not invent a setting.
- One Hermes instance per Railway service, one replica, one volume at `/data`.
- `HERMES_HOME=/data/.hermes`, `HOME=/data`; the volume never covers the install.
- Git supplies `SOUL.md` and `config.yaml` on each boot. Memories, sessions,
  skills, cron state, and auth state persist on the volume.
- Slack is the only human interface. Each agent has its own bot/app tokens,
  an explicit `SLACK_ALLOWED_USERS`, and a `SLACK_HOME_CHANNEL` destination.
  Both global and Slack allow-all settings stay disabled.
- No agent-to-agent or customer messaging. Follow the individual soul's
  authority; `eng` prepares engineering work and requests concrete approval
  before production actions.
- Never log tokens. Never run `hermes update` on Railway. Runtime upgrades
  change the pinned `HERMES_GIT_REF` through an approved deployment.
- The earlier `eng` deployment approval is superseded by the cost-incident stop. Other
  agents remain undeployed until Saar authorizes them. Do not create paid
  services or mutate production as part of soul authoring.

## Current work

The `eng` soul covers architecture, engineering, stability, on-call response,
and performance. Its config includes Sentry, Linear, GitHub, PostHog, and
Railway. Slack bootstrap applies to every agent; the gateway refuses to start
without both Slack tokens and an owner allowlist. Legacy platform environment
variables are removed before launching Hermes.

On 2026-09-22 the separate `taikan-agents` project and `eng` service were
observed running on Railway with a `/data` volume. Saar reported successful
Sentry and Railway OAuth setup. End-to-end Slack access and actual reads from
all integrations still need verification. Wait for CI was disabled at the last
inspection. The Sentry OAuth config correction and volume startup guard are
prepared locally; live manual MCP config edits are overwritten at boot until
the corresponding Git correction is published through an approved deployment.

Saar chose `product` next, covering all of Taikan as CPO. Its soul/config,
read-oriented GitHub/Linear/PostHog setup, knowledge workflow, and behavioral
acceptance scenarios are drafted. The first-run document inventory and product
brief have not been executed by a deployed agent. Customer research sources
and all product-service credentials remain to be connected. No product service,
cron job, agent-to-agent transport, or paid resource was created.

Follow [the deployment setup](RUNBOOK.md#github-ci-and-railway-deployment).
`scripts/bootstrap.sh` is an alternative owner-run deployment command, not a
local validation step or a prerequisite for GitHub deployments.

## Activation sequence

Prior deployment approval does not authorize restarting after the cost
incident. Follow [COST-CONTROLS.md](COST-CONTROLS.md#verification-before-reactivation)
first: reviewed code, offline tests, independent provider spending limit,
new dedicated key, then Saar's explicit enable/deploy instruction.

Use one new Slack thread and one bounded read-only task to calibrate usage.
Inspect account/project access and owner allowlisting. Automatic cron dispatch
stays off; stored jobs remain on the volume for inspection. Push monitoring
in WEBHOOKS.md is still a separate design. Retain independent provider alerts.
