# Eng discussion and continuation context — 2026-09-22, updated 2026-09-28

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
- **The emergency limits are superseded.** The dollar caps described in the
  containment sections below were replaced on 2026-09-28; see
  [the productive-eng decision](#2026-09-28-decision-productive-eng).
- **Seer is not enabled.** Integration was discussed; no Seer run or setup
  occurred. It is optional future work, not part of the immediate restart.
- **No task-quality calibration has been performed.** Offline tests verify
  enforcement and compatibility, not usefulness on real engineering tasks.

The open question — how much work a requested task may use before eng must
ask Saar to continue — was answered on 2026-09-28: 40 model calls per Slack
message, then a summary checkpoint. Do not interpret a request to resume this
discussion as permission to change those values or to deploy.

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

## 2026-09-28 decision: productive eng

Saar answered the open limits question. The containment numbers recorded in
this document are superseded from this date; the incident record above is
unchanged.

His choices:

- **No local dollar caps.** The $2/UTC-day and $10-total limits, the pre-flight
  reservation, the token-count pre-check, the gate that stopped generation and
  the startup refusal for unfinished requests are removed. The Anthropic
  Console workspace spending limit, on a key dedicated to this fleet, is the
  only cap; it must be set and verified before reactivation.
- **Eng gets room to finish a task:** 40 model calls per Slack message,
  120,000-token context, 16,384 output tokens per call including thinking,
  compression at 80,000, `reasoning_effort: high`, an 1800-second run budget
  that only produces a wrap-up notice at 80%, a 600-second terminal timeout,
  and 40,000-character/800-line reads. Reaching 40 calls is a checkpoint:
  Hermes asks for a summary, the turn ends, Saar replies `continue`.
- **Eng's auxiliary side-calls run on Haiku 4.5** — title generation, memory
  query rewrite, approval, MCP, goal judging, vision, skills hub, profile
  describer and compression.
- **Other agents are unchanged:** 12 calls, 40,000 context, 4,096 output,
  compression at 24,000, 180-second wrap-up, low effort; their auxiliary calls
  use their own main model except compression on Haiku. Eng's values are the
  validator's fleet maxima — another agent may be lower, never higher.
- **The product CPO work stays bundled in PR #1.** It is not split out.

What the findings recorded below look like after this decision:

| Finding | Resolution |
| --- | --- |
| A transient 429/529 or a redeploy mid-request could leave the guard stopped, bricking the service until a human cleared its state | Provider 429/529/5xx errors pass through unchanged for Hermes to retry; no state survives a failure, so restarts and redeploys mid-request are safe |
| One model request at a time, overlapping requests rejected, aborting parallel Slack conversations and overlapping auxiliary calls | Parallel requests are allowed; the queueing recommendation is moot |
| Eng's auxiliary side-calls ran on its main model, paying Opus rates for title generation and similar work | They run on Haiku 4.5 |
| A 40,000-token input ceiling could be consumed by MCP tool schemas plus history before any real work | The 120,000-token context removes that risk |
| A denied approval had no explicit rule against reaching the same result another way | The eng soul now states that a denial ends that approach: no local harness, direct API call or different tool; report what was denied and wait |
| Images and PDFs were refused, which broke screenshots sent from a phone | Images and documents are accepted and accounted like other input |

Still open: no paid calibration. Opus at high reasoning effort with 16,384
output tokens has not been measured against the real API, and no provider
spending limit has been verified. Background review, curator, scheduled
dispatch and delegation stay disabled; they address the incident's actual
cause and are not part of this change.

## Implemented state in this PR

| Control | Current value / behavior |
| --- | --- |
| Activation | Off unless `TAIKAN_AGENT_ENABLED=true`; no reactivation authorized |
| eng main model | `claude-opus-5`, native Anthropic |
| Other agents | Product/marketing/scout/analyst Sonnet 5; ops/release Haiku 4.5 |
| eng auxiliary side-calls | `claude-haiku-4-5`; other agents use their main model, with compression on Haiku |
| Reasoning effort | eng `high`; other agents `low` |
| Model calls per Slack message | eng 40; other agents 12 |
| Run budget | eng 1800 s, other agents 180 s; a wrap-up notice at 80%, not a hard stop |
| Input ceiling | eng 120,000-token context; other agents 40,000, including history and tool schemas |
| Output ceiling | eng 16,384 tokens per call, other agents 4,096, including thinking |
| Compression | eng at 80,000 tokens, other agents at 24,000; bounded retained history |
| Concurrent model calls | Parallel requests allowed |
| Spending | No local cap; the Anthropic workspace limit on a dedicated key is the only one |
| Background review / curator | Disabled |
| Scheduled dispatch | Disabled at the runtime scheduler boundary; stored jobs preserved |
| Delegation / cron tools | Disabled |
| Repeated failure/no progress | Hard stops retained |
| Images and documents | Accepted, accounted like any other input |

The supervisor retains the real Anthropic key; Hermes receives a loopback
`taikan-local-…` credential. The guard admits only the three reviewed models,
forces the standard service tier, refuses alternate inference credentials and
provider-hosted paid server tools, clamps `max_tokens` to 16,384, and records
each completed call's usage and USD cost in
`$HERMES_HOME/cost-guard/usage.sqlite3`. Opus 5 standard rates were checked at
$5/M input and $25/M output; cache writes bill at 2x input and reads at 0.1x.
See [COST-CONTROLS.md](COST-CONTROLS.md).

That record is **visibility, not enforcement**: nothing stops a call because
of its price. It is neither a guaranteed provider invoice cap nor a
hostile-process security sandbox — the agent has shell access inside the same
container. A runaway task is bounded by the per-message call limit, the
runtime's failure detection and the provider cap. Paid MCP, search, Seer,
infrastructure and other external services are not included. Railway hosting
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
6. A denied approval ends that approach. Eng does not substitute a local
   harness, a direct API call or a different tool to reach the same result;
   it reports what was denied, what that blocks, and waits.

This is a soul/behavioral instruction, not a technical proof that an LLM will
never expand scope. The existing scheduler/review controls provide additional
runtime enforcement for those specific automatic paths. Necessary in-task
compression still uses model tokens; “no background work” does not mean
only one model call or zero auxiliary cost.

The budget question was answered numerically on 2026-09-28: no local dollar
cap, and a 40-call checkpoint in place of a spending stop. That still cannot
promise uninterrupted task completion. If Saar intends approval before every
implementation step rather than before follow-ups/scope changes, clarify that
distinction before further behavior changes.

## Quality, completion and parallelism findings

The containment configuration was not tuned for everyday engineering quality:
low reasoning, short outputs, early compression and a 12-call/3-minute
ceiling could stop a legitimate investigation or fix from finishing, and
restoring Opus alone would not have removed those constraints. The
2026-09-28 decision raised each of them for eng and unblocked images and
PDFs. Turning off background refinement still removes that refinement
capability, and turning off schedules still means no proactive monitoring;
both remain deliberate.

Hermes supports independent chat sessions and coordinates work within a
session. Its tool executor can run eligible independent tools concurrently.
The local guard no longer narrows that: parallel requests are allowed, so
overlapping Slack conversations and auxiliary calls proceed instead of being
aborted. The single-request admission rule, and the queueing work it would
have required, are gone. Separate services still have separate guards.

No benchmark established how these choices affect engineering accuracy or
completion rate. Offline tests do not substitute for representative tasks.

## Consequences of the limit changes

Decided on 2026-09-28. This is what each change buys and what it costs.

| Change | Benefit | Consequence |
| --- | --- | --- |
| 180 s → 1800 s run budget, wrap-up notice only | Long investigations and test runs can finish | Stuck work can run longer before anyone sees it |
| 12 → 40 model calls per message | More investigate/implement/verify cycles | Unsuccessful attempts accumulate more spend before the checkpoint |
| 40k → 120k context, 4k → 16k output, high effort | Real context and room to reason | Larger paid calls; provider model limits still apply |
| Local dollar caps removed | No local interruption mid-task | A requested task can drain the key's credits; the provider limit is the only stop |
| Failure/no-progress stops | Kept unchanged | Retained deliberately as the loop guard |

These follow the earlier recommendation: remove the arbitrary 3-minute
cutoff, raise the 12-call ceiling substantially while keeping a checkpoint,
give Opus useful context and output space, retain failure detection, and rely
on a verified provider cap as the financial backstop.

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
- The Opus containment revision passed **31 offline regression tests** in the
  pinned Hermes image with networking disabled and current repo code mounted
  read-only. The real native Anthropic adapter passed streaming/non-streaming
  fake-provider requests. That run exercised the dollar-cap mechanism that no
  longer exists. The productive-eng revision replaces those tests: 25 offline
  tests pass, and `verify_runtime.py` passes in the pinned image with
  `--network none`, including real main/side-call routing (side-calls on
  Haiku through the guard) and a relayed 529 followed by a successful call.
- Asset validation and whitespace checks passed. No paid model call, live
  Slack calibration, provider-limit change or deployment was performed.
- CI on the pushed revision is the authority for its new image build; verify
  the latest PR head rather than relying only on the older green commit.
- No representative task-quality, idle-behavior or multi-conversation tests
  have been run against a live eng service. Do not claim these verified.

Suggested continuation order, subject to Saar's choices:

1. **Done 2026-09-28:** the limits and the checkpoint are agreed and recorded
   above. Necessary task work stays distinct from autonomous follow-up work.
2. **Done:** reasoning, output, context and concurrent admission were settled
   together, not left to the Opus switch alone.
3. Implement the chosen controls and meaningful offline tests; update this
   record and the PR description to match the final design.
4. Verify the provider workspace cap and mint a dedicated new key. It is now
   the only spending limit. The recorded usage history is for reconciliation,
   not enforcement; reconcile it rather than deleting it.
5. Only after explicit reactivation approval, deploy eng and calibrate a small
   requested task in a fresh Slack thread; compare actual usage with the
   recorded per-day totals. Confirm the 40-call checkpoint produces a usable
   summary, that `continue` resumes, and that eng then waits.
6. Evaluate product and optional Seer integration separately when requested.

## References

- [Eng soul](../souls/eng.md), [eng config](../config/eng.yaml),
  [cost policy](COST-CONTROLS.md), [operations runbook](RUNBOOK.md),
  [unverified assumptions](UNVERIFIED.md).
- [Pinned Hermes runtime](https://github.com/NousResearch/hermes-agent/tree/5fc308a70719a83cccdbba4c0e39c23f5a8239d5)
  (release `v2026.8.27`; Docker asserts the peeled commit, not the annotated
  tag object).
- [Hermes tool executor](https://github.com/NousResearch/hermes-agent/blob/5fc308a70719a83cccdbba4c0e39c23f5a8239d5/agent/tool_executor.py).
- [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing),
  reviewed during this discussion on September 22, 2026.
- [Start Seer investigation](https://docs.sentry.io/api/seer/start-seer-issue-fix/)
  and [retrieve Seer results](https://docs.sentry.io/api/seer/retrieve-seer-issue-fix-state/),
  reviewed during the discussion; current implementation/billing still needs
  verification before use.
