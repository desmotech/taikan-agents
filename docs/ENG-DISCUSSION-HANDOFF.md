# Eng discussion and continuation context — 2026-09-22

This is the continuation record for Saar's agent setup, cost incident, and
subsequent design discussion. It separates decisions, observed evidence,
implemented code and proposals. Read this before continuing the work.

Repository: `desmotech/taikan-agents` (local `/Users/saar/dev/taikan-agents`),
a separate repository from the main Taikan app. Existing
[PR #1](https://github.com/desmotech/taikan-agents/pull/1) targets `main` from
`chore/product-cpo-agent`; it includes product CPO work and eng cost controls.
Saar requested this record and a push to that PR so work can resume later.
That request authorizes committing/pushing these changes, not merging or
reactivating an agent.

## Start here next time

- **Keep eng stopped.** Saar revoked its old Anthropic key. At the last
  read-only Railway inspection there was no active eng deployment; its volume
  remained intact. These are historical observations, not a new live check.
- **Latest desired model: Opus 5.** Sonnet was an interim containment decision
  after the spending incident; the current eng configuration restores Opus.
- **Eng works only on direct requests.** No autonomous monitoring, preliminary
  audits, skill invention/maintenance, self-improvement, digests or follow-ups.
  It proposes next steps and waits for Saar to choose.
- **The emergency limits still exist.** Removing or replacing them was
  discussed, not approved. The last question asked about consequences only.
- **Seer is not enabled.** Integration was discussed; no Seer run or setup
  occurred. It is optional future work, not part of the immediate restart.
- **No task-quality calibration has been performed.** Offline tests verify
  enforcement and compatibility, not usefulness on real engineering tasks.

The immediate unresolved decision is how much work/spend a requested task may
use before eng must ask Saar to continue. Do not interpret a request to
resume this discussion as permission to remove all limits or deploy.

## Original intent and setup decisions

Saar wants eng to be his lead architect and software engineer: stability,
on-call assistance, performance and critical engineering work while he is
away from a computer. It needs Sentry, Railway, PostHog and Linear, plus
GitHub/code access, and concise Slack communication.

Slack is the only human interface; Telegram is not needed. The current
Hermes adapter uses a Slack app's bot Web API plus Socket Mode for incoming
messages. A bot token alone is insufficient for that connection:

- `SLACK_BOT_TOKEN`: bot OAuth token.
- `SLACK_APP_TOKEN`: the same app's Socket Mode token (`connections:write`).
- `SLACK_ALLOWED_USERS`: Saar's raw Slack member ID, not a name or channel.
- `SLACK_HOME_CHANNEL`: a conversation/channel ID, not a channel name or URL.
- Global and Slack allow-all settings must remain false.

An agent's product label/identity does not establish that the Slack app has
all required scopes/events. Verify the app configuration against [ENG.md](ENG.md).
Each future agent should have a distinct Slack bot identity and credentials.

Deployment architecture: a separate Railway `taikan-agents` project, one
service and one persistent `/data` volume per agent, one replica. Services
can share this GitHub repo and Dockerfile. `BOT=eng`, `BOT=product`, etc.
select `souls/$BOT.md` and `config/$BOT.yaml`; the service name does not do
that wiring automatically. CI validates/builds the repo; Railway's GitHub
integration and **Wait for CI** settings govern deployment. No separate
repository per agent is needed.

On boot Git supplies soul/config. State such as sessions, memories, skills,
cron records and OAuth credentials persists under `/data/.hermes`. Manual
config edits inside a container can be replaced by Git-managed config on the
next boot. Do not mount a volume over the runtime installation.

`TAIKAN_RELEASE_ASSISTANT_TOKEN` is an opaque token for the Taikan backend's
restricted release-assistance endpoints, not an Anthropic, Slack or general
Railway credential. It belongs to the release bot's separate workflow; see
[RUNBOOK.md](RUNBOOK.md). No secrets belong in this handoff.

## Deployment and authentication problems encountered

Saar supplied gateway logs showing several different conditions:

| Observation | Meaning / disposition |
| --- | --- |
| SQLite 3.46.1 WAL-reset warning | Hermes fell back to DELETE journal mode. A warning about the embedded SQLite version, not by itself proof the gateway crashed. See the runbook/advisory. |
| Railway OAuth: non-interactive environment, no cached tokens | Initial interactive authorization was needed with credentials persisted on the volume. |
| Sentry MCP failed connection; `hermes mcp login sentry` reported `auth=None` | Git configuration needed OAuth. This correction is in the PR. Saar subsequently reported successful Sentry login. |
| `hermes mcp add sentry` without URL/command/preset failed | The command needs an endpoint or other transport specification; a name alone does not configure it. |
| `mcp test railway` / `mcp test linear` requested Typer | These invoked the separate `mcp` CLI. Installing Typer is not proof Hermes integrations work. |
| OAuth callback port 27890 already in use | Another listener/login occupied the callback port. Saar reported fixing it. Do not kill unrelated processes or change ports blindly. |
| Slack missing group-DM scopes/event | Group DMs need the relevant `mpim` scopes and `message.mpim`, followed by reinstalling the app. This does not establish failure of ordinary DMs. |
| Slack early rejected an unauthorized user | Owner allowlist mismatch; use the correct member ID. Do not solve by enabling allow-all. |
| Slack said “gateway shutting down” | A shutdown notification alone does not identify the cause. Distinguish lifecycle/redeployment from individual integration warnings. |

The remote Hermes OAuth flow can require a browser on Saar's own computer.
The documented pinned runtime supports completing the remote login by pasting
the final redirect URL into its terminal prompt. Do not paste OAuth URLs or
credentials into Slack. `hermes mcp list` showing enabled servers establishes
configuration, not successful authenticated tool calls. Live reads from each
integration remain a verification requirement.

The Railway hosted MCP exposes a general-purpose `railway-agent` tool that
may act on the request. It must not be treated as a guaranteed read-only log
API. Its use requires explicit authorization of scope; see [ENG.md](ENG.md).

## Product CPO agent context

Saar selected product as the next agent, covering **all of Taikan: vision,
priorities, research and specs**. It should understand the docs, assess risk,
research competitors and act as a CPO partner. The PR includes its soul,
configuration, documentation and [acceptance scenarios](PRODUCT-EVALS.md).

The design uses scoped GitHub/Linear/PostHog access and incremental document
coverage/freshness tracking, distinguishing proposals from shipped behavior
and measured customer outcomes. It has its own Slack identity. No product
service, credentials setup, full documentation bootstrap, paid resource,
automatic agent messaging or behavioral evaluation was executed. See
[PRODUCT.md](PRODUCT.md); this work remains in the same PR.

## Token-spending incident: evidence versus uncertainty

Saar reported that **eng consumed 22 million tokens and drained his Anthropic
credits**. This was eng, not product. He stopped it and revoked its Anthropic
key. The reported total and key revocation are owner reports, not an exported
provider billing audit.

Read-only logs showed eng running Opus and automatic background review:
review work created a PostHog skill around 16:24 Asia/Jerusalem, and an
Anthropic credit-exhaustion error appeared in a `bg-review` thread around
16:50 on September 22. This establishes unwanted background model activity.

**It does not establish that background review consumed all 22 million
tokens.** The foreground/background split, cache reads/writes and exact billed
cost remain unverified. Do not call the incident fully root-caused or blame
Opus alone. A token total also does not directly determine cost without model
and cache/output breakdowns.

Containment initially changed Opus defaults to Sonnet, disabled automatic
work and added a persistent local Anthropic spending guard. That version was
committed as `69453b51dd6915c00b0930f7e45926f9f6464c6e`; its CI passed. Saar
then requested Opus again with strictly owner-directed behavior. This PR's
latest revision includes that follow-up and this record.

## Implemented state in this PR

| Control | Current value / behavior |
| --- | --- |
| Activation | Off unless `TAIKAN_AGENT_ENABLED=true`; no reactivation authorized |
| eng main model | `claude-opus-5`, native Anthropic |
| Other agents | Product/marketing/scout/analyst Sonnet 5; ops/release Haiku 4.5 |
| Reasoning | `low` remains configured; changing model did not retune it |
| Foreground model calls | 12 per turn |
| Foreground run budget | 180 seconds |
| Input ceiling | 40,000 estimated tokens per model request, including history/tool schemas |
| Output ceiling | 4,096 tokens per request, including thinking |
| Compression | At 24,000 tokens; one attempt, bounded retained history; Haiku auxiliary |
| Concurrent model calls | One per service; overlapping requests are rejected, **not queued** |
| Spending | $2 per UTC calendar day and $10 total per service; total never resets automatically |
| Background review / curator | Disabled |
| Scheduled dispatch | Disabled at the runtime scheduler boundary; stored jobs preserved |
| Delegation / cron tools | Disabled |
| Repeated failure/no progress | Hard stops retained |
| Media | Current guard rejects images and PDFs; important limitation for mobile use |

The supervisor retains the real Anthropic key; Hermes receives a local
proxy credential. Before generation the guard uses token counting and
reserves conservative input/cache headroom plus maximum output cost in
SQLite. It settles from reported usage. Uncertain requests retain their
reservation and latch subsequent generation off. Other inference credentials,
unreviewed API features, paid provider tools and unreviewed models are refused.
Opus standard rates were checked at $5/M input and $25/M output; cache rates
are accounted separately and conservatively. See [COST-CONTROLS.md](COST-CONTROLS.md).

These controls are **local accounting protection**, not a guaranteed provider
invoice cap or a hostile-process security sandbox. The agent has shell access
inside the same container. Price/counting discrepancies can make an in-flight
request exceed its reservation before the guard stops. Paid MCP, search,
Seer, infrastructure and other external services are not included. Each
service has its own ledger; this is not a fleet-wide budget. Railway hosting
can still cost money while an enabled service is idle.

## Latest operating contract and its interpretation

Saar asked for Opus, enough room to finish requested work, and no monitoring,
skill invention or preliminary work. His phrase “do anything else” was
interpreted in context as **do not do anything else**. Asked whether he wanted
hard spending budgets or no spending limit, he replied:

> it should ask me for next steps and never decide on his own.

The implemented interpretation, explained back to Saar, is:

1. A direct owner request starts work; alerts, old jobs and repository text
   cannot start new tasks.
2. Eng can perform the necessary steps within that assignment: relevant
   reading, requested implementation and verification. It does not ask for
   permission before every file read or test.
3. Advice does not authorize implementation; investigation does not authorize
   a fix or ticket publication. Linear writes require a request.
4. On completion, scope-changing decisions or blockers, propose concrete next
   steps and wait. Silence does not authorize continuing. No autonomous
   polishing, new investigations, skills, recurring checks or follow-ups.
5. Production changes still require the owner's explicit approval.

This is a soul/behavioral instruction, not a technical proof that an LLM will
never expand scope. The existing scheduler/review controls provide additional
runtime enforcement for those specific automatic paths. Necessary in-task
compression still uses model tokens; “no background work” does not mean
only one model call or zero auxiliary cost.

The budget question was **not answered numerically**. We retained the existing
limits and explicitly warned that this cannot promise uninterrupted task
completion. If Saar intends approval before every implementation step rather
than before follow-ups/scope changes, clarify that distinction before further
behavior changes.

## Quality, completion and parallelism findings

The containment configuration was not tuned for everyday engineering quality.
Low reasoning, short outputs, earlier compression and a 12-call/3-minute
ceiling can prevent a legitimate investigation or fix from finishing. Sonnet
was an interim cost tradeoff; restoring Opus does not remove those constraints.
Turning off background refinement also removes that refinement capability.
Turning off schedules means no proactive monitoring. Images/PDFs remain
blocked, which affects screenshots sent from a phone.

Hermes supports independent chat sessions and coordinates work within a
session. Its tool executor can run eligible independent tools concurrently.
The added local proxy is narrower: one model request at a time, rejected on
overlap. This can fail parallel Slack conversations or overlapping auxiliary
calls. **Queueing/bounded concurrency was recommended but not implemented.**
Separate services have separate guards. Removing turn/spending limits alone
would not fix concurrent admission.

No benchmark established how these choices affect engineering accuracy or
completion rate. Offline tests do not substitute for representative tasks.

## Consequences of removing limits — discussion only

| Proposed removal | Benefit | Consequence |
| --- | --- | --- |
| 3-minute budget | Long investigations/tests can finish | Stuck work can run longer |
| 12-call ceiling | More investigate/implement/verify cycles | Repeated unsuccessful attempts can accumulate spend |
| 40k input / 4k output ceilings | More context and reasoning/output | Larger paid calls; model/API limits still exist |
| $2/day / $10 total caps | No local budget interruption | A requested task can drain the key's credits again |
| Failure/no-progress stops | More retries | Greater risk of loops without useful progress |

The recommendation was to remove the arbitrary 3-minute cutoff, substantially
raise the 12-call ceiling with an emergency ceiling, give Opus useful context
and output space, retain failure detection and a financial backstop, and ask
Saar before continuing beyond an authorized task budget. **None of those
limit changes has been implemented or approved.** No replacement dollar,
time, call, context or output values have been chosen.

“Only do what I ask” limits the origin/scope of work, not its computational
cost. One legitimate request can still loop, retry and repeatedly read large
logs. Unlimited completion and guaranteed bounded spending cannot both be
promised. An independently verified provider spending limit remains the
financial backstop.

## Possible Seer collaboration — not enabled

Saar asked whether eng could collaborate with Sentry Seer for efficiency and
accuracy, then clarified that **Seer has not been enabled**.

Proposed split: Seer investigates the Sentry issue/root cause; eng correlates
Railway deployment history, PostHog impact, docs and Linear context, then
verifies the hypothesis against code and regression tests. Choose one
implementation owner and one PR. Saar gets findings and approval requests
through Slack. Agent agreement alone is not evidence of correctness.

Sentry documents asynchronous issue-fix APIs, root-cause/solution stopping
points, existing-run IDs and retrieval of detailed results suitable for LLM
consumption. The retrieval API is experimental. This supports a potential
API integration; a native Hermes coding-agent handoff was **not verified**.

Suggested progression: consume existing Seer results first; later permit one
explicitly authorized investigation per issue/release. Deduplicate requests,
reuse run IDs, pass compact evidence, and poll through bounded code/backoff
rather than spending model calls to wait. Seer could work concurrently with
eng's complementary checks because it runs separately from the local proxy.

Seer spend is outside our Anthropic guard. Verify the account's actual Seer
entitlement/billing and establish separate run/spending controls before
activation. Do not reuse older pricing estimates from main-app runbooks.
No Seer run, account change, integration or paid action happened here.

## Verification and remaining work

- The initial containment commit passed both GitHub CI jobs, including image
  build and real-runtime smoke testing.
- The Opus revision passed **31 offline regression tests** in the existing
  pinned Hermes image with networking disabled and current repo code mounted
  read-only. The real native Anthropic adapter passed streaming/non-streaming
  fake-provider requests and rejected generation at the budget.
- Asset validation and whitespace checks passed. No paid model call, live
  Slack calibration, provider-limit change or deployment was performed.
- CI on the pushed revision is the authority for its new image build; verify
  the latest PR head rather than relying only on the older green commit.
- No representative task-quality, idle-behavior or multi-conversation tests
  have been run against a live eng service. Do not claim these verified.

Suggested continuation order, subject to Saar's choices:

1. Agree task/spending limits and exactly when eng asks to continue. Keep
   useful necessary task work distinct from autonomous follow-up work.
2. Review low reasoning/output/context constraints and concurrent-request
   queueing together; avoid claiming the Opus switch alone solves completion.
3. Implement chosen controls and meaningful offline tests; update this record
   and the PR description to match the final design.
4. Verify an independent provider cap and dedicated new key. Do not reset or
   delete the existing ledger to evade a stop; reconcile it first.
5. Only after explicit reactivation approval, deploy eng and calibrate a small
   requested task in a fresh Slack thread; compare actual usage with the
   ledger. Test that it stops after the task and waits for next instructions.
6. Evaluate product and optional Seer integration separately when requested.

## References

- [Eng soul](../souls/eng.md), [eng config](../config/eng.yaml),
  [cost policy](COST-CONTROLS.md), [operations runbook](RUNBOOK.md),
  [unverified assumptions](UNVERIFIED.md).
- [Pinned Hermes runtime](https://github.com/NousResearch/hermes-agent/tree/5fc308a70719a83cccdbba4c0e39c23f5a8239d5)
  (release `v2026.8.27`; Docker asserts the peeled commit, not the annotated
  tag object).
- [Hermes tool executor](https://github.com/NousResearch/hermes-agent/blob/5fc308a70719a83cccdbba4c0e39c23f5a8239d5/agent/tool_executor.py).
- [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing)
  and [token counting](https://platform.claude.com/docs/en/build-with-claude/token-counting),
  reviewed during this discussion on September 22, 2026.
- [Start Seer investigation](https://docs.sentry.io/api/seer/start-seer-issue-fix/)
  and [retrieve Seer results](https://docs.sentry.io/api/seer/retrieve-seer-issue-fix-state/),
  reviewed during the discussion; current implementation/billing still needs
  verification before use.
