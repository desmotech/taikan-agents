# Proactive triggers (webhook design note)

Research-only. Nothing here is deployed. Verified against
NousResearch/hermes-agent @ main (`gateway/platforms/webhook.py`,
`gateway/platforms/webhook_filters.py`) and the Hermes + Sentry docs.
Add the config in this file only AFTER a plain `eng` boot is confirmed good.
The current role and authority are in [ENG.md](ENG.md) and `souls/eng.md`;
the trigger wiring below still needs live verification.

## Why not cron polling

`hermes cron create "every 5m"` works (verified: relative, interval, 5-field
cron and ISO formats are all accepted). But it costs one model run per tick
forever, to usually discover nothing. Push is cheaper and faster.

## Hermes webhook platform (verified)

`platforms.webhook.enabled: true`, `extra.{host,port,secret,routes,rate_limit,
max_body_bytes,script_timeout_seconds}`. Port default 8644 (`WEBHOOK_PORT` env
var also read; Railway's own `PORT` is NOT read - set it explicitly).
Host default `None` = listens on all interfaces v4+v6, which is what Railway
needs; no config change required.

Runs alongside the Slack connection in the same gateway process.

POST `/webhooks/<route>` returns **202 immediately** and runs the agent in a
background task. This is what makes Sentry viable at all: Sentry treats >1s as
a timeout, and an agent run is far slower.

Per-route fields: `events`, `secret` (required, falls back to global),
`profile`, `prompt`, `filters`, `script`, `skills`, `toolsets`, `deliver`,
`deliver_extra`, `deliver_only`, `enabled`.

Status codes: unknown route 404, disabled route 403, bad/missing signature 401,
body >1MB 413, unparseable 400, rate limited 429 (default 30/min per route),
duplicate delivery id 200 (1h TTL), filter rejected 200 (no agent run, free).

### Prompt templating

`{a.b.c}` dot-notation into the payload; `{__raw__}` = whole body as JSON,
truncated to 4000 chars. Missing keys are left as literal `{key}`, no error.

### !! Webhook runs get a RESTRICTED toolset by default

The default webhook toolset `hermes-webhook` is only `web_search`,
`web_extract`, `vision_analyze`, `clarify`. A webhook-triggered run therefore
CANNOT see Sentry, Linear or GitHub unless the route overrides it. MCP servers
appear as dynamic toolset names `mcp-<server>`, so an investigating route needs
roughly:

    toolsets: ["mcp-sentry", "mcp-github", "mcp-linear", "web"]

UNVERIFIED: the exact resolved names for our three MCP servers. Confirm on the
live container (`hermes` toolset listing) before trusting a route to
investigate anything. A route with the default toolset will produce confident
answers with no tool access, which is the worst failure mode available.

### Cheaper model per route (verified, optional)

A route's `profile:` binds it to a separate Hermes profile with its own
`config.yaml`, and each profile carries its own `model:`. So webhook triage can
run on Haiku while Slack chat stays on Opus. Requires
`gateway.multiplex_profiles: true`, a created profile, and the route served at
`/p/<profile>/webhooks/<route>`. Adds real complexity - only worth it if
webhook volume makes Opus spend hurt.

## Signature validation (the Sentry blocker)

Recognised headers, in order: svix (`svix-id`/`svix-timestamp`/`svix-signature`),
`linear-signature`, GitHub `X-Hub-Signature-256`, GitLab `X-Gitlab-Token`,
generic v2 `X-Webhook-Signature-V2` + `X-Webhook-Timestamp` (300s window),
generic v1 `X-Webhook-Signature`. No recognised header + a secret configured
=> reject.

Sentry signs with `Sentry-Hook-Signature` (HMAC-SHA256 hex over the raw body,
plus `Sentry-Hook-Resource` and `Sentry-Hook-Timestamp`). That header name is
NOT in Hermes's list, so Sentry gets 401 as-is - even though the crypto is
byte-identical to the accepted generic v1 scheme.

Fix: a Cloudflare Worker that verifies `Sentry-Hook-Signature` with the Sentry
integration Client Secret, then re-signs the body under `X-Webhook-Signature`
with the Hermes route secret. ~20 lines, free tier, and Sentry never touches
the Railway host.

`secret: "INSECURE_NO_AUTH"` exists but the gateway REFUSES TO START if it is
combined with a non-loopback bind. Do not look for a way around this.

## Routes to configure

### 1. GitHub Actions -> /webhooks/ci  (no shim needed)

Repo -> Settings -> Webhooks -> Add webhook. Content type application/json,
secret = route secret, individual event: Workflow runs.

`workflow_run` fires 3x per run (requested / in_progress / completed).
Filtering is required or you pay for 3 agent runs per push. Verified syntax -
a top-level list is AND'ed, and `conclusion` is null on the first two
deliveries, so this matches only completed-and-failed on main:

    ci:
      events: ["workflow_run"]
      secret: "<github-webhook-secret>"
      filters:
        - field: "payload.workflow_run.conclusion"
          equals: "failure"
        - field: "payload.workflow_run.head_branch"
          equals: "main"
      toolsets: ["mcp-github", "mcp-linear"]   # names UNVERIFIED, see above
      prompt: |
        CI failed on main. Workflow: {workflow_run.name}
        Run: {workflow_run.html_url}
        Read the failing step's logs, quote the real error line, and say
        whether it is code, infra, or flake. Do not open a ticket; ask first.
      deliver: "slack"

Operators available: `exists`, `missing`, `equals`, `not_equals`, `contains`,
`in`, `in_file`, `regex`. Explicit `all`/`any`/`not` groups nest.
No numeric comparison operators.

### 2. Sentry -> /webhooks/sentry  (via Worker)

Sentry -> Settings -> Developer Settings -> Custom Integrations -> New Internal
Integration. Permissions: Issue & Event = Read only. Webhooks: check `issue`.
Save, then copy the Client Secret (for the Worker) and the token.

Note: the `error` resource requires a Business/Enterprise plan; `issue`
(which covers "a new issue is created") does not.

If volume or spend becomes a problem, move the filtering server-side: an Issue
Alert rule with condition "A new issue is created" (internally
`FirstSeenEventCondition`) plus a "notify a service" action, so Sentry never
calls for noise it could have dropped itself.

### 3. Linear - skip

eng uses Linear as its incident ledger; no Linear trigger is configured. A webhook
with no consumer is just more attack surface. (`linear-signature` is natively
supported if this ever changes.)

### 4. Railway deploy failures - candidate, blocked on research

A failed prod deploy is on-call relevant, but whether Railway signs its
webhooks, and with which header, is UNVERIFIED. Do not wire until confirmed.

## Escalation policy, not just plumbing

The webhook is the nerve; the judgement stays in SOUL.md. Intended behaviour:
investigate on arrival using direct read tools, and notify Saar on Slack at the
impact-based escalation bar in `souls/eng.md`. Everything else folds into the
07:30 digest. Deduplicated incident tickets and factual updates are permitted
by the soul; production actions require explicit approval. The CI route above
deliberately narrows its run to diagnosis without ticket creation.

Keep one plain Sentry alert rule going to email/Slack independently. If the
container is down, so is agent-based paging; the siren must not depend on the
analyst.

## Domain

`railway domain --port 8644 --service eng` (verified flag) gives an HTTPS
`*.up.railway.app` host. Sufficient - security is the HMAC, not URL obscurity.
A custom domain only earns its keep once several agents take inbound; if so,
put it on the Worker and keep Railway as a private backend.
