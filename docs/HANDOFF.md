# HANDOFF - taikan-agents

Current direction: every agent communicates with Saar through Slack. Start
with [ENG.md](ENG.md), [RUNBOOK.md](RUNBOOK.md), and [UNVERIFIED.md](UNVERIFIED.md).
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
- Only `eng` has deployment approval recorded in the original handoff. Other
  agents remain undeployed until Saar authorizes them. Do not create paid
  services or mutate production as part of soul authoring.

## Current work

The `eng` soul covers architecture, engineering, stability, on-call response,
and performance. Its config includes Sentry, Linear, GitHub, PostHog, and
Railway. Slack bootstrap applies to every agent; the gateway refuses to start
without both Slack tokens and an owner allowlist. Legacy platform environment
variables are removed before launching Hermes.

Saar confirmed the agent project does not yet exist. First deployment uses a
separate `taikan-agents` project linked to this repo, with Railway waiting for
GitHub CI. Follow [the deployment setup](RUNBOOK.md#github-ci-and-railway-deployment).
Live credentials, integration access, Slack delivery, and deployed behavior
remain unverified. `scripts/bootstrap.sh` is an alternative owner-run deployment
command, not a local validation step or a prerequisite for GitHub deployments.

## Activation sequence

1. Follow ENG's Slack activation steps using the existing bot token and a
   Socket Mode app token. Complete each integration's authentication.
2. At the approved deployment, verify the boot logs and a fresh owner Slack
   conversation. Test the owner allowlist and actual tool access.
3. Inspect persisted cron jobs. Change existing destinations to Slack; do not
   register a duplicate morning digest. The runbook gives a create command
   only for a missing job.
4. Verify the 07:30 Asia/Jerusalem digest and volume persistence. Report any
   coverage gap before calling eng ready for on-call use.
5. Push triggers in [WEBHOOKS.md](WEBHOOKS.md) remain a separate, undeployed
   phase. Retain independent provider alerts while they are unconfigured.
