# Agent cost controls

On 2026-09-22, Saar reported 22 million tokens and an exhausted Anthropic
balance. Eng's logs confirm Opus background self-improvement and a credit
error in a `bg-review` thread at 16:50 Asia/Jerusalem. The exact foreground,
background, and cached-token split is still unverified. Eng was stopped and
its provider key revoked. Do not restore it merely because a build passes.

## Limits applied to every agent

| Control | Default | Enforcement |
| --- | --- | --- |
| Activation | Off | `TAIKAN_AGENT_ENABLED` must equal `true` |
| Model | eng uses Opus 5; ops/release Haiku 4.5; others Sonnet 5 | Config plus reviewed proxy model allowlist |
| Model calls per foreground turn | 12 | Hermes `agent.max_turns` and inherited iteration limit |
| Foreground time budget | 180 seconds | Hermes run budget; not a dollar limit |
| Input | 40,000 estimated tokens per request | Anthropic token counting before generation, including schemas/history |
| Compression | 24,000 tokens | Explicit threshold, smaller retained tail, one attempt |
| Output | 4,096 tokens per request, including thinking | Config and network-boundary clamp |
| Concurrent model requests | One | Proxy admission semaphore |
| Daily budget | $2 per UTC calendar day | Atomic persistent reservation before generation |
| Total budget | $10, no automatic reset | Same persistent ledger, across all days/restarts |
| Background review/curator | Off | Config and automatic-review runtime hook |
| Scheduled dispatch | Off | Runtime scheduler hook; persisted jobs are preserved |
| Delegation/scheduling tools | Disabled | Hermes disabled toolsets |
| Repeated failures/no progress | Hard stop after 2 identical failures or 3 same-tool failures | Hermes loop guard |
| Logs/file reads | 12,000 chars, 200 lines | Tool defaults; proxy rejects excessive aggregate input |

The limits are ceilings, not usage targets. No environment variable raises
the dollar caps: increasing them requires a reviewed code change. The total
budget does not reset at midnight or after a deployment. Each service has its
own ledger and cap; multiple services do not share a fleet-wide budget.

## Eng works only on request

Eng uses Opus 5 for foreground engineering. It waits for Saar's direct Slack
request, stays within that task, then proposes next steps and waits. No
preliminary audits, automatic monitoring, skill creation or self-improvement.
Necessary reading, implementation and verification belong to the requested
task; advisory requests do not authorize implementation. Linear writes also
require a request. Automatic review, curator and scheduled dispatch remain off.
Task scope is a soul instruction, not a security sandbox around shell access.

The existing step, time, context, output and spending ceilings remain in place.
Saar has not selected replacement budgets. Opus can reach the same dollar cap
sooner; this change does not promise uninterrupted completion. Changing the
model alone does not remove the 12-call / 180-second foreground limits.

## Spending boundary

`entrypoint.sh` starts `cost_guard.py` before writing Hermes's environment.
The supervisor retains the real Anthropic key. Its child receives a randomly
generated loopback credential and the local endpoint. Only bounded Messages
requests reach `api.anthropic.com`; alternate inference credentials are
rejected. Retries, compaction and other model calls using this managed key
share the same ledger. The proxy never retries an upstream generation.

The proxy calls the free token-counting endpoint, then atomically reserves
the full output budget and input with 25%/4,096-token headroom at the
most expensive supported cache-write rate. Completed requests settle from
provider-reported usage. Cache reads get their discounted rate; all cache
writes are conservatively charged at the one-hour rate. Metadata-only log
lines report accounted cost. No prompts, completions or keys enter the ledger.

Network errors, invalid usage, unfinished streams or charges exceeding the
reservation latch the gate off. Uncertain reservations are retained, including
after a crash. Even if Hermes retries, no further generation is admitted.
Bad/corrupt/unwritable ledgers prevent startup or admission. Budget failures
return a non-retryable API error that says to stop and seek owner review.

The ledger is `$HERMES_HOME/cost-guard/ledger.sqlite3`. **Do not delete or reset
it to resume work.** Inspect accounting and reconcile any uncertain calls
with Anthropic first. There is deliberately no agent-accessible reset tool.

## What these controls do not guarantee

These are conservative **local accounting limits**, not a contractual cap on
an Anthropic invoice. Token counting is an estimate; prices can change. An
in-flight request can exceed its reservation if the provider's accounting
differs unexpectedly, after which the gate stops. Set and verify a separate
Anthropic workspace spending limit before enabling the bot. A rate limit
alone is not a spending limit. Use a dedicated workspace/key for this fleet,
not a shared key used by Claude Code or other apps.

This same-container proxy prevents accidental unmetered SDK calls with the
managed key. It is not a security sandbox against a hostile root process:
the agent still has shell access. It also does not meter external paid MCP,
search, infrastructure or other services. Provider-side limits are the
independent financial backstop.

This first guarded version accepts text and local client/MCP tools only.
Images/PDFs, provider-hosted tools, batch requests, fast/priority modes, unknown
models and unreviewed API fields are refused. A schema-heavy first request
can exceed 40k; narrow enabled MCP tools before increasing the limit. Earlier
compression preserves less verbatim history. A task may stop at the cap with
work unfinished; the agent should give the useful findings and next step.

## Verification before reactivation

1. Keep `TAIKAN_AGENT_ENABLED=false`, the deployment removed, and the old key
   revoked while reviewing/building. GitHub source remains an owner setting;
   this change does not reconnect it or re-enable autodeployment.
2. Run the offline test suite and the real-image compatibility smoke check.
   These tests use fake upstream responses and cannot spend model credits.
3. Set and verify the independent Anthropic workspace cap. Mint a new key
   dedicated to the agent. Supply it only through Railway's secret variable.
4. Only on Saar's explicit reactivation instruction, enable and deploy one
   agent. Keep all automatic schedules disabled. Use a new Slack thread with
   one small read-only task; avoid loading the incident's large old transcript.
5. Compare the proxy ledger with the provider's input, output, cache and cost
   totals. Verify bounded context, useful output, and a displayed budget stop
   before trusting unattended operation. No paid calibration has been run by
   this patch.

## Sources reviewed

- [Hermes config defaults](https://github.com/NousResearch/hermes-agent/blob/v2026.8.27/hermes_cli/config_defaults.py)
- [Hermes automatic review](https://github.com/NousResearch/hermes-agent/blob/v2026.8.27/agent/background_review.py)
- [Anthropic token counting](https://platform.claude.com/docs/en/build-with-claude/token-counting): free, but estimated counts.
- [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing): standard Opus 5 $5/$25, Sonnet 5 $2/$10 and Haiku 4.5 $1/$5 per million input/output tokens; cache multipliers.

CI verifies runtime integration against the built Hermes image. Unsupported
hook APIs fail closed instead of silently enabling scheduled/review work.

The Docker build verifies release `v2026.8.27` resolves to commit
`5fc308a70719a83cccdbba4c0e39c23f5a8239d5`. Moving the tag or overriding the
ref cannot silently replace the reviewed runtime. Runtime upgrades must update
the assertion and pass the compatibility smoke test.

## Verification recorded for this patch

2026-09-22: all 29 regression tests passed locally and inside the Python 3.11
Docker image with `--network none`. The native Hermes Anthropic adapter passed
streaming and non-streaming fake-provider requests and rejected a request once
the test budget was exhausted. The runtime hooks disabled automatic review
and scheduler dispatch. The final image exited disabled without credentials.
Asset validation, shell syntax, documentation links and diff whitespace passed.
No live provider request, Slack calibration, deployment, or provider cap change
was performed. Production eng has no active deployment; the key revocation is
owner-reported. Changes are prepared for review, not authorization to restart.

2026-09-22, request-only Opus revision: 31 offline regression tests passed
in the existing pinned Hermes image with networking disabled and current
repository scripts mounted read-only. The real Hermes adapter accepted
streaming/non-streaming Opus requests against a fake provider, accounted at
reviewed Opus rates, and rejected generation at the budget. Configuration and
whitespace validation passed. No live behavioral evaluation, paid model call,
new image build, push or deployment was performed for this revision.
