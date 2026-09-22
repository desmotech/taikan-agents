# product: Taikan's CPO

> **Cost incident — 2026-09-22:** Eng is stopped and its key revoked.
> Agent startup now defaults off. Read [cost controls](COST-CONTROLS.md) before
> any activation. Automatic cron dispatch and background reviews are disabled;
> older scheduling instructions below do not enable them.


`product` covers all of Taikan: vision, portfolio priorities, customer problems,
research, risk, specifications, and outcome reviews. Saar makes company
commitments; product gives him an evidence-backed recommendation he can act on
from Slack. Eng supplies engineering feasibility and operational judgment.

## The three parts

1. **Soul:** [souls/product.md](../souls/product.md) defines judgment, ownership,
   evidence standards, risk assessment, and authority.
2. **Knowledge:** GitHub gives it the canonical docs and relevant code at a
   known revision; Linear gives current planning context; PostHog provides
   aggregate behavioral evidence. It builds an index with actual read coverage
   instead of embedding hundreds of changing documents into the soul.
3. **Continuity:** a small product notebook on `/data` keeps approved direction,
   decisions, risks, research, and draft specs with provenance. This notebook
   is working memory, not a second authoritative roadmap.

No new vector database is needed for this first version. Start with source
discovery, direct retrieval, and compact summaries. Evaluate retrieval failures
before adding another indexing service. A soul/config file alone does not
connect private repositories, ingest documents, or install monitoring.

## Source map and freshness

Start in `desmotech/taikan`. Discover the default branch and resolve it to a
commit. Enumerate the documentation tree, handling pagination/truncation, and
read sources at that revision so one brief does not accidentally mix revisions.
For a new substantive question, compare the current head and refresh affected
sources. Use the GitHub MCP or the image's `gh` CLI with the scoped token;
there is no preinstalled Taikan checkout in the agent image.

| Topic | Initial source paths in `desmotech/taikan` |
| --- | --- |
| Reading rules and vocabulary | `AGENTS.md`, `CLAUDE.md`, `docs/README.md`, `docs/overview/glossary.md` |
| Vision, segments, portfolio | `docs/overview/product-vision.md`, `personas.md`, `roadmap.md` |
| Surface and dependency map | `docs/architecture/overview.md`, `mobile.md`, `auth.md`, `i18n.md` |
| Acquisition and activation | `docs/features/minisites/`, `leads-crm/`, `exports-imports/`, `onboarding/` |
| Operator business workflows | `docs/features/payments/`, `subscriptions-plans/`, `platform-billing/`, `memberships/`, `analytics/`, `insights/` |
| Training and member value | `docs/features/scheduling-bookings/`, `daily-programming/`, `program-templates/`, `workout-assignments/`, `workout-results/`, `goals/` |
| Cross-cutting experience | `docs/features/dashboard-shell/`, `forms/`, `users-auth/`, `spotter-agent/`, `messages-comments/`, `push-notifications/` |
| Decisions and constraints | `docs/decisions/`, relevant `docs/runbooks/`, `docs/features/legal/` |
| Measurement | `docs/features/event-tracking/`, `docs/architecture/observability.md`, then actual PostHog event coverage |
| History | `docs/_archive/`, explicitly labelled historical |

This table is a navigation starting point, not an exhaustive list. The local
source inventory on 2026-09-22 contained 311 Markdown files and 46 feature
folders. The agent must discover the actual current inventory and track
discovered/read/stale/missing coverage. Index other formats too; record any
format it cannot read instead of treating it as covered.

For native behavior, inspect the separate `desmotech/taikan-mobile` repository's
instructions, README, docs, and relevant implementation. Source paths are
locations to verify, not claims that features are enabled in production.

The authoring review found conflicting descriptions that make good activation
checks: overview docs place native mobile in the future, while architecture
docs describe the separate Expo app; the roadmap lists reporting as upcoming,
while analytics docs describe an implemented default-OFF reporting flag.
Product must surface and investigate these conflicts. Neither source alone
establishes what a particular customer can use today.

Feedback/interview/support repositories are not connected in this scaffold.
Add owner-approved, redacted sources when available. Do not replace missing
customer evidence with the founder's hypothesis or public competitor copy.

## Runtime and access

[config/product.yaml](../config/product.yaml) uses `claude-sonnet-5` through
Anthropic, matching eng's configured model, with:

| Access | Purpose | Initial scope |
| --- | --- | --- |
| GitHub MCP + CLI | Docs, code, issues/PR evidence and revisions | Dedicated token restricted to needed repositories, contents/metadata read; add issue/PR read only when needed. MCP requests `X-MCP-Readonly: true`. |
| Linear MCP | Current projects, issues, milestones, linked planning docs | Dedicated API key with only Read permission, restricted to the actual Taikan team(s). |
| PostHog MCP | Adoption, funnels, retention, and instrumentation evidence | Personal API key restricted to Taikan and required read scopes; endpoint includes `readonly=true`. |
| Hermes web search/extract | Current public competitor and market evidence | Verify the selected backend and fetch a primary source. The existing entrypoint supports `FIRECRAWL_API_KEY` if a key is needed. |
| Slack | Saar's conversation with this agent | Its own bot/app tokens, explicit owner allowlist, and DM/private-channel destination. |

Read-only endpoint settings reduce available tools; credential scopes also
matter because a terminal is available. Soul rules alone are not a technical
permission boundary. Do not share eng's broader credentials or OAuth store.
Product receives no Railway, Sentry, database, payment-provider, or release
credentials. Publishing issue/spec drafts is an explicitly authorized later
capability; default credentials cannot perform those writes.

Public web tools are for public research. Keep private docs, unpublished
strategy, internal issue text, customer data, and identifying quotes out of
search queries and third-party extraction payloads. The model/MCP access used
to read approved internal sources is separate from a public research query.

Sources for connector settings:
[GitHub read-only mode](https://github.com/github/github-mcp-server/blob/main/docs/server-configuration.md#read-only-mode),
[Linear API-key authentication](https://linear.app/docs/mcp),
[PostHog MCP access](https://posthog.com/docs/model-context-protocol/faq),
[Hermes web tools](https://hermes-agent.nousresearch.com/docs/user-guide/features/web-search).
Live compatibility and credentials still require testing in the deployed image.

## First deployment and first conversation

First complete [cost reactivation prerequisites](COST-CONTROLS.md#verification-before-reactivation).
When Saar authorizes deployment, create a service named `product` in the
existing `taikan-agents` project, using the same GitHub repo/root and main
branch. Set `BOT=product`, use one replica, attach its own `/data` volume, and
enable Wait for CI. Follow [RUNBOOK.md](RUNBOOK.md#github-ci-and-railway-deployment).
The bootstrap script also supports `product`, but it creates live resources;
do not run it as a local validation command.

Use the common `ANTHROPIC_API_KEY` and Slack variable names with product's own
credentials and explicit owner ID. Supply scoped `GITHUB_TOKEN`,
`LINEAR_API_KEY`, and `POSTHOG_API_KEY`. Optional `FIRECRAWL_API_KEY` configures
an existing supported web provider. These three MCP entries use API keys;
they do not require the Sentry/Railway OAuth flow from eng.

Run inside product's interactive Railway SSH session:

```sh
hermes mcp test github
hermes mcp test linear
hermes mcp test posthog
```

A test connection/tool list is not a successful domain query. Verify a real
read from each target account, an authorized Slack reply, rejection of a
non-owner, and public web search plus page extraction. If a capability is
unavailable, report it as an activation gap.

After a small calibration task, build knowledge over several bounded turns.
Start with the docs index and core vision; expand only on Saar's next request.
The eventual assignment is:

> Build your initial map of Taikan. Resolve source revisions, inventory the
> docs, read the core vision/personas/architecture and feature overviews in
> bounded batches, and record what you have actually read. Produce a short
> product brief with target segments, jobs, intended differentiation, current
> surfaces, proposed versus approved priorities, and major evidence gaps.
> Show documentation conflicts and the five questions that most affect our
> decisions. Do not publish changes or claim the whole corpus has been read
> before you finish it. Save progress so you can resume.

Saar reviews that brief before product treats newly inferred direction as
approved strategy. Continue reading and analysis without requiring approval
for each source. This authoring task neither ran the assignment nor populated
the deployed agent's memory.

## Useful assignments

- **Decision brief:** "Should we build X now?" Answer with the customer job,
  strongest evidence, recommendation, alternative/defer option, displaced
  work, largest risk, and smallest test.
- **PRD:** "Turn this decision into an eng-ready slice." Include outcomes,
  non-goals, journey and exceptions, roles/locales/clients, acceptance criteria,
  instrumentation, rollout/stop conditions, and open eng questions.
- **Competitor analysis:** "Why would a studio switch from X?" Compare real
  customer workflows and switching costs, cite current public sources, and
  identify the implication for Taikan rather than a feature shopping list.
- **Portfolio review:** "What should I do this week?" Ground a short ranked
  list in current constraints, evidence, dependencies, and opportunity cost;
  label estimates unconfirmed by eng.
- **Risk review:** "What could make this launch fail?" Give concrete scenarios,
  evidence/confidence, mitigation, owner, and release blockers versus risks
  worth accepting or testing.
- **Outcome review:** "Did this release work?" Compare the hypothesis to actual
  cohort/denominator/window evidence and recommend continue/iterate/stop.

Use normal Slack conversations first. A weekly review can later be scheduled
once useful output, timing, delivery, and tool costs are verified with Saar.
No schedule or agent-to-agent messaging is created by this scaffold.

## Verification

Static checks validate the YAML/soul pair and the generic gateway startup.
They cannot test product judgment or prove external access. Use
[PRODUCT-EVALS.md](PRODUCT-EVALS.md) for behavioral acceptance before relying
on the agent's recommendations. Record the actual responses and source
revisions; an unrun scenario remains unverified.
