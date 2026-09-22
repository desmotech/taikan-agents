# eng: engineering wingman

> **Cost incident — 2026-09-22:** Eng is stopped and its key revoked.
> Agent startup now defaults off. Read [cost controls](COST-CONTROLS.md) before
> any activation. Automatic cron dispatch and background reviews are disabled;
> older scheduling instructions below do not enable them.


`eng` is Saar's lead architect and software engineer for system stability,
on-call response, and performance. [The soul](../souls/eng.md) is its operating
contract; [the config](../config/eng.yaml) declares its integrations.

## What is implemented here

- A soul that owns investigation, recommendations, local fixes, verification,
  and incident follow-through, with concise Slack communication.
- Sentry, Linear, and GitHub MCP entries retained; PostHog and Railway added.
- Slack credential prompts for every agent. The entrypoint requires Slack
  tokens and an explicit owner allowlist, and strips legacy platform variables.
- A Slack destination for the documented morning digest.
- CI validation and image build checks before Railway GitHub autodeploys.
  Follow [the first-deployment setup](RUNBOOK.md#github-ci-and-railway-deployment).

These are repository changes. Live credentials, Slack delivery, MCP access,
scheduled jobs, and deployed behavior have not been verified by this change.
Do not describe the agent as on-call coverage until the activation checks pass.
The fleet uses Slack exclusively; the original upstream transport research is
retained only as history.

## Authority

`eng` independently reads available telemetry and code, prepares local fixes
and tests, and creates or adds factual updates to deduplicated `FIT` issues.
It can explain architecture and recommend operational actions from a phone
conversation. It continues safe work while an action is awaiting approval.

Production mutations require explicit approval of a concrete action and target.
Commits, pushes, PR creation, merges, and releases follow the owner's request
and the affected repository's rules. The default GitHub token remains read-only:
code can be prepared locally, but publishing needs separately granted access
and authorization. A repo checkout and its build/test dependencies must be
available before the agent can claim it can implement or test a fix.

Soul instructions are behavioral policy, not an access-control layer. PostHog's
configured endpoint hides write tools; credential scopes should also restrict
access. Railway's OAuth grant may expose write-capable tools. Never present
the Railway integration as technically read-only or automatically remediating.

## Slack activation

Keep the existing Slack app and bot token. Hermes's native Slack adapter uses
the bot Web API for sending and Socket Mode for incoming events. A bot token
alone cannot provide this two-way connection.

Set these on the `eng` Railway service using the dashboard or hidden prompts:

| Variable | Purpose |
| --- | --- |
| `SLACK_BOT_TOKEN` | Existing bot OAuth token |
| `SLACK_APP_TOKEN` | Same app's Socket Mode token, with `connections:write` |
| `SLACK_ALLOWED_USERS` | Saar's member ID |
| `SLACK_HOME_CHANNEL` | Owner DM conversation or designated private channel ID |
| `GATEWAY_ALLOW_ALL_USERS` | `false` |
| `SLACK_ALLOW_ALL_USERS` | `false` |

Enable Socket Mode, incoming message events, and the app's Messages tab. Give
the bot the scopes required for the selected DM/channel setup; reinstall the
app after changing scopes. Invite it to the destination channel if needed.
Use the [Hermes Slack guide](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/slack/)
and the [pinned-version guide](https://github.com/NousResearch/hermes-agent/blob/v2026.8.27/website/docs/user-guide/messaging/slack.md).
Do not add a public webhook or use a personal Slack token for this setup.

Never paste tokens into Slack, Linear, this repository, or an agent prompt.
The entrypoint removes legacy platform variables from the gateway process and
regenerates its `.env` with Slack settings only. It does not delete Railway
variables or migrate persisted cron jobs. At the approved deployment, supply
Slack credentials first, remove obsolete variables in Railway, and change any
existing jobs to Slack delivery. Inspect the cron list before creating jobs
to avoid duplicate digests. There is no fallback to another chat platform.

## Integrations

| Integration | Authentication and verification |
| --- | --- |
| Sentry | Hosted MCP requires OAuth. Run `hermes mcp login sentry` in the deployed profile, then verify a real issue read. `SENTRY_AUTH_TOKEN` is for the REST API and is not used by this MCP configuration. |
| Linear | `LINEAR_API_KEY`, scoped to the `FIT` team and needed issue operations. Verify search/read without creating a test ticket. |
| PostHog | `POSTHOG_API_KEY` must be a personal key with access restricted to Taikan, not the ingestion/project key. The endpoint uses `readonly=true`. Verify project identity and a bounded aggregate query. |
| Railway | Remote MCP at `https://mcp.railway.com` with OAuth. Authorize only the intended Taikan projects. Project API tokens are not accepted by this endpoint. |
| GitHub | Existing `GITHUB_TOKEN`, read-only repository content and Actions access. Verify the target repo and one CI run. |

Railway does not need a CLI installed in the agent image with this transport.
Attach a persistent volume at `/data` before signing in. In the running
service's Hermes profile, complete both OAuth logins:

```sh
railway ssh --service eng
# Run inside the interactive remote shell:
hermes mcp login railway
hermes mcp login sentry
```

The owner opens each authorization URL in a local browser. The pinned Hermes
version supports pasting the final redirect URL back into its terminal prompt;
a localhost connection error in the browser is expected when using this method.
Paste it only into the login prompt, never into Slack or a shared log.
Credentials remain in `HERMES_HOME/mcp-tokens/` on the volume. The gateway
rechecks parked servers periodically; verify discovery and a real read after
login. Live login and refresh still require verification. This document is not
approval to deploy, restart, or change production credentials.

Inspect the actual discovered tools. The hosted Railway server exposes a
general-purpose `railway-agent` tool; it is capable of taking actions, so a
request to it is not a safe substitute for a direct log/metric read. If direct
reads are unavailable, report that coverage gap and arrange a verified read
path before declaring unattended Railway diagnosis ready. Any delegation to
`railway-agent` needs explicit owner approval of its scope.

Sources: [Railway MCP](https://docs.railway.com/ai/mcp-server),
[PostHog authentication and read-only mode](https://posthog.com/docs/model-context-protocol/faq),
[Linear MCP](https://linear.app/docs/mcp),
[Sentry MCP](https://mcp.sentry.dev/),
[Hermes MCP config](https://hermes-agent.nousresearch.com/docs/reference/mcp-config-reference/).

## Activation checks

First complete [cost reactivation prerequisites](COST-CONTROLS.md#verification-before-reactivation).
Run these as separate bounded tasks; no exhaustive single-turn audit.

1. Start a fresh Slack conversation after the approved deployment. Confirm
   eng identifies its expanded role and replies in the correct conversation.
2. Verify owner access and rejection of an unapproved user, including thread
   replies. Confirm allow-all overrides are disabled.
3. Ask for connected systems and their actual account/project/environment.
   Read one bounded result from each. An unavailable source must be reported
   as unavailable; a config entry is not a passing connection check.
4. Ask "Are we healthy?" It should report a time window, actual coverage,
   impact, and uncertainty. It must not equate missing data with health.
5. Use a clearly hypothetical incident: "Checkout is failing after a deploy."
   It should propose investigation and a concrete mitigation decision without
   executing a production change. Do not simulate with a real restart or write.
6. Ask for an architecture recommendation and a performance investigation.
   Expect code/context evidence, a recommendation, tradeoffs, and a measurable
   validation plan, not just error triage.
7. Instruct it to prepare a small local fix. Confirm checkout isolation,
   target-repo instructions, test evidence, and no unauthorized commit/push.
8. Verify the persistent cost ledger against Anthropic usage after the small
   calibration task. Confirm automatic scheduled dispatch remains disabled.
   Inspect existing jobs without running them.

Push alerts remain a separate, undeployed design in [WEBHOOKS.md](WEBHOOKS.md).
Retain independent provider alerts: an agent outage must not silence incident
detection. No new polling schedule or paid service is introduced here.
