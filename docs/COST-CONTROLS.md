# Agent cost controls

On 2026-09-22, Saar reported 22 million tokens and an exhausted Anthropic
balance. Eng's logs confirm Opus background self-improvement and a credit
error in a `bg-review` thread at 16:50 Asia/Jerusalem. The exact foreground,
background, and cached-token split is still unverified. Eng was stopped and
its provider key revoked.

The containment that followed that incident — local dollar caps, pre-flight
reservations, and a gate that stopped generation — is **superseded** by Saar's
2026-09-28 decision. The automatic-work controls (no background review, no
curator, no scheduled dispatch, no delegation) are unchanged and still the
part that addresses the incident's actual cause. Reactivation still requires
a verified provider spending limit on a dedicated key.

## The only spending cap is the provider's

There are no local dollar limits. The **Anthropic Console workspace spending
limit, on a key dedicated to this fleet, is the single cap on what an agent
can spend.** It must be set and verified before any agent is enabled; see
[ANTHROPIC-CONSOLE.md](ANTHROPIC-CONSOLE.md).

The local guard records what every completed call cost. That record is
**visibility, not enforcement**: nothing in this repository stops a call
because of its price. A runaway task is bounded by the per-message call
limit, the runtime's failure detection, and the provider cap — not by a
local ledger.

## Limits applied to every agent

| Control | eng | Other agents | Enforcement |
| --- | --- | --- | --- |
| Activation | Off | Off | `TAIKAN_AGENT_ENABLED` must equal `true` |
| Spending | Provider workspace limit | Provider workspace limit | Anthropic Console, dedicated key; no local cap |
| Model | Opus 5 | Sonnet 5; ops/release Haiku 4.5 | Config plus reviewed proxy allowlist |
| Auxiliary side-calls | Haiku 4.5 | Own main model; compression on Haiku 4.5 | Config `auxiliary.*` |
| Model calls per Slack message | 40 | 12 | Hermes `agent.max_turns` |
| Context | 120,000 tokens | 64,000 tokens | `model.context_length` |
| Output per call, including thinking | 16,384 tokens | 4,096 tokens | Config, plus a 16,384 clamp at the network boundary |
| Compression | At 80,000 tokens | At 24,000 tokens | Explicit threshold, bounded retained tail |
| Reasoning effort | high | low | Config |
| Run budget | 1800 s | 180 s | Soft wrap-up notice at 80%, **not** a hard stop |
| Terminal command timeout | 600 s | 180 s | Config |
| File reads / tool output | 40,000 chars, 800 lines | 12,000 chars, 200 lines | Config |
| Background review / curator | Off | Off | Config and automatic-review runtime hook |
| Scheduled dispatch | Off | Off | Runtime scheduler hook; persisted jobs are preserved |
| Delegation / scheduling tools | Disabled | Disabled | Hermes disabled toolsets |
| Repeated failures / no progress | Hard stop after 2 identical failures or 3 same-tool failures | Same | Hermes loop guard |

The validator treats eng's numbers as **fleet maxima**: another agent may be
configured lower, never higher. Context must be at least 64,000 tokens, the
minimum Hermes accepts; the 24,000-token compression threshold keeps other
agents compact. Raising a maximum is a reviewed code change.

## The 40-call checkpoint

Eng gets 40 model calls per Slack message. When it reaches them, Hermes asks
the model for a summary and the turn ends. That is a checkpoint, not a
failure: Saar reads the summary and replies `continue` to proceed. The soul
tells eng to use the calls the task needs rather than stopping early, and to
end the checkpoint summary with what is verified, what is left and its next step.

The 1800-second run budget produces a wrap-up notice at 80% (about 24
minutes) and does not terminate the turn.

## Eng works only on request

Eng uses Opus 5 for foreground engineering. It waits for Saar's direct Slack
request, stays within that task, then proposes next steps and waits. No
preliminary audits, automatic monitoring, skill creation or self-improvement.
Necessary reading, implementation and verification belong to the requested
task; advisory requests do not authorize implementation. Linear writes also
require a request. Automatic review, curator and scheduled dispatch remain off.
Task scope is a soul instruction, not a security sandbox around shell access.

A denied approval ends that approach. Eng must not route around a denial with
a local harness, a direct API call or a different tool; it reports what was
denied, what that blocks, and waits.

## What the guard still does

`entrypoint.sh` starts `cost_guard.py` before writing Hermes's environment.
The supervisor stays root and retains the real Anthropic key. It runs Hermes
(and every shell command the agent starts) as the unprivileged `hermes` user
(uid 10001), which cannot read root's `/proc/<pid>/environ` or memory. Hermes
receives a randomly generated loopback `taikan-local-…` credential and the
local endpoint, so an SDK call cannot reach the provider unmetered. On every
boot the supervisor gives `/data` to `hermes` (repairing files an operator
wrote as root) except its own `/data/cost-guard/`, which stays root-only. The
guard:

- rejects alternate inference provider credentials, including
  `CLAUDE_CODE_OAUTH_TOKEN`;
- removes stored inference credentials from `auth.json` at gateway start
  (pool entries and provider logins that would reach a provider directly);
  MCP OAuth tokens in `mcp-tokens/` are untouched;
- admits only `claude-opus-5`, `claude-sonnet-5` and `claude-haiku-4-5`;
- exposes that reviewed allowlist through authenticated `GET /v1/models` for
  Hermes model discovery (local metadata, not proof of upstream account access);
- forces the standard service tier, refusing batch, fast and priority modes;
- refuses provider-hosted paid server tools;
- clamps `max_tokens` to 16,384;
- records each completed call's usage and USD cost.

Images and documents in messages are allowed; they are accounted like any
other input.

Provider errors — 429, 529 and 5xx — are passed through unchanged so that
Hermes applies its own retry and backoff. Nothing latches off, no state
survives a failure, and a restart or redeploy in the middle of a request is
safe. Parallel requests are allowed: separate Slack conversations and
auxiliary calls run concurrently.

Accounting uses the standard rates: Opus 5 $5/$25, Sonnet 5 $2/$10 and Haiku
4.5 $1/$5 per million input/output tokens, with cache writes at 2x input and
cache reads at 0.1x. Each call logs one metadata-only line:

```
[cost-guard] usd=<this call> today_usd=<UTC day total> model=<model id>
```

No prompts, completions or keys are written anywhere.

## Reading recorded spend

The record is `/data/cost-guard/usage.sqlite3` (root-only), table `calls`, with
columns `id`, `day`, `model`, `usd_micro` and `usage`. Per-day totals, from a
root shell such as `railway ssh`:

```sh
python3 -c "import sqlite3; [print(*r) for r in sqlite3.connect('/data/cost-guard/usage.sqlite3').execute(
  'SELECT day, round(sum(usd_micro)/1e6,2) FROM calls GROUP BY day')]"
```

Deleting this file loses history and nothing else; it does not unblock work,
because it never blocked any. Reconcile it against the Console's own usage
rather than trusting either alone.

## What these controls do not guarantee

Local accounting is not a contractual cap on an Anthropic invoice. Prices can
change and provider accounting is authoritative. **Set and verify the separate
Anthropic workspace spending limit before enabling the bot.** A rate limit is
not a spending limit. Use a dedicated workspace and key for this fleet, not a
shared key used by Claude Code or other apps.

User separation keeps the key away from the agent's shell, but the agent
still has shell access as `hermes` and holds its other integration tokens
(GitHub, Linear, PostHog); it is not a sandbox against a container escape.
The guard does not meter external paid MCP, search, infrastructure or other
services. Railway compute and storage bill separately. Provider-side limits
are the independent financial backstop.

The agent cannot install system packages (`apt`) or into `/opt/venv`. It can
install npm CLIs globally (prefix `/data/.npm-global`, on `PATH`) and create
Python virtualenvs under `/data/workspace`.

A task can still end at the 40-call checkpoint with work unfinished; the agent
gives its useful findings and the next step, and Saar decides whether to
continue. Compression at 80,000 tokens preserves less verbatim history than
the full 120,000-token window.

## Verification before reactivation

1. Keep `TAIKAN_AGENT_ENABLED=false`, the deployment removed, and the old key
   revoked while reviewing/building. GitHub source remains an owner setting;
   this change does not reconnect it or re-enable autodeployment.
2. Run the offline test suite and the real-image compatibility smoke check.
   These tests use fake upstream responses and cannot spend model credits.
3. **Set and verify the Anthropic workspace spending limit.** It is now the
   only cap. Mint a new key dedicated to the agent and supply it only through
   Railway's secret variable.
4. Only on Saar's explicit reactivation instruction, enable and deploy one
   agent. Keep all automatic schedules disabled. Use a new Slack thread with
   one small read-only task; avoid loading the incident's large old transcript.
5. Compare the recorded per-day totals with the Console's input, output, cache
   and cost figures. Confirm the 40-call checkpoint produces a usable summary
   and that `continue` resumes. No paid calibration has been run by this patch.

## Sources reviewed

- [Hermes config defaults](https://github.com/NousResearch/hermes-agent/blob/v2026.8.27/hermes_cli/config_defaults.py)
- [Hermes automatic review](https://github.com/NousResearch/hermes-agent/blob/v2026.8.27/agent/background_review.py)
- [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing): standard Opus 5 $5/$25, Sonnet 5 $2/$10 and Haiku 4.5 $1/$5 per million input/output tokens; cache multipliers.

CI verifies runtime integration against the built Hermes image. Unsupported
hook APIs fail closed instead of silently enabling scheduled/review work.

The Docker build verifies release `v2026.8.27` resolves to commit
`5fc308a70719a83cccdbba4c0e39c23f5a8239d5`. Moving the tag or overriding the
ref cannot silently replace the reviewed runtime. Runtime upgrades must update
the assertion and pass the compatibility smoke test.

## Verification history

2026-09-22 (superseded containment): 29, then 31, offline regression tests
passed locally and inside the pinned Hermes image with `--network none`. The
native Anthropic adapter passed streaming and non-streaming fake-provider
requests, and the runtime hooks disabled automatic review and scheduler
dispatch. Those runs exercised the dollar-cap mechanism that no longer exists.
No live provider request, Slack calibration, deployment or provider cap change
was performed in either revision.

2026-09-28: no paid model call, live Slack calibration, provider-limit change,
image push or deployment has been performed for the productive-eng revision.
Opus at high reasoning effort with 16,384 output tokens has not been
calibrated against the real API; see [UNVERIFIED.md](UNVERIFIED.md).
