# Unverified

> **Cost incident — 2026-09-22:** Eng is stopped and its key revoked.
> Agent startup now defaults off. Read [cost controls](COST-CONTROLS.md) before
> any activation. Automatic cron dispatch and background reviews are disabled;
> older scheduling instructions below do not enable them.


Things I could not confirm in the docs, the repo, or `--help`. Each has the
safe default I used. None is a silent guess.

1. **Paid calibration after cost controls.** The real Hermes config loader,
   automatic-review/scheduler hooks, and native Anthropic SDK (streaming and
   non-streaming) have passed offline checks against fake provider responses.
   The proxy permits only `claude-sonnet-5` and `claude-haiku-4-5`. No provider
   spending limit has been verified and no paid calibration task has been run.
   Reconcile the first bounded Slack task against actual provider accounting
   before unattended use. Alternate-provider fallbacks are deliberately blocked.

2. **Root gateway.** The official Hermes Docker page says the gateway refuses to
   run as root unless `HERMES_ALLOW_ROOT_GATEWAY=1`. The template image runs as
   root and its README implies it works, so that check may be specific to the
   official image's entrypoint. Default: set nothing. If the first deploy logs
   a root refusal, add `HERMES_ALLOW_ROOT_GATEWAY=1` as a Railway variable
   (documented var) and redeploy.

3. **Live authentication on the remote MCP servers.** Linear and PostHog now
   document API-key bearer authentication (sources in [ENG.md](ENG.md)); the
   actual credentials and scopes still need live verification. The configured
   GitHub connection also needs verification. **Updated 2026-09-22:** Sentry's
   hosted server documents OAuth-only access; eng now uses `auth: oauth`.
   Complete `hermes mcp login sentry` in an interactive Railway SSH shell;
   attach `/data` first so credentials survive deployment. On a headless box,
   complete the OAuth flow by pasting back the
   redirect URL (documented in Hermes' mcp guide). `eng` also has the `gh` CLI
   and `GITHUB_TOKEN` in the image, providing an alternative to test if that MCP
   fails; credentials and scopes still need verification.

4. **`railway service list --json` and `railway volume list --json` shapes.**
   Not shown in `--help`. `bootstrap.sh` greps for the service name and for
   `"/data"` as existence checks. A false positive skips creation (safe); a
   false negative would attempt a duplicate `railway add` or `volume add`, whose
   behaviour on an existing name is also undocumented. Run the script once and
   read its output; adjust the grep if the shape differs.

5. **Default replica region.** `railway scale` is per region and the default
   region of a new service is not in `--help`. Default: the script prints the
   dashboard step unless `RAILWAY_REGION` is set. Services start at 1 replica.

6. **Cron timezone when `timezone:` and container `TZ` differ.** Docs say the
   `timezone:` key affects cron scheduling and the troubleshooting page says
   jobs use "local timezone". Default: both set to `Asia/Jerusalem`, so there is
   no difference to resolve. Verify the first 07:30 digest arrives at 07:30.

7. **Preventing the agent from editing SOUL.md.** No config switch exists; File
   Write Safety's always-blocked list does not include SOUL.md. Default: the
   entrypoint overwrites SOUL.md from Git on every boot, and every soul says
   "never edit your own SOUL.md". Between deploys an edit could persist in the
   running session. If that matters, `HERMES_WRITE_SAFE_ROOT` is the documented
   knob, but its exact semantics on a root container were not verified.

8. **Process env vs `.env` precedence for the same key.** Only documented for
   the official Docker image (`-e` overrides `.env`). Here both hold the same
   values, written from the same Railway variables, so it cannot matter.

9. **Toolset names for `agent.disabled_toolsets`.** The reference page lists
   them but I did not verify each name, so no toolsets are disabled in any
   config. Restrictions are enforced by the souls and by which tokens each
   service has. If you want `marketing` to have no terminal, that key is where
   it goes, once the name is confirmed at
   https://hermes-agent.nousresearch.com/docs/reference/toolsets-reference.

10. **Railway GitHub App visibility of the fork.** `railway service source
    connect` help says to use `--branch` for repos "not visible through the
    Railway GitHub App". The script passes `--branch`. If the connect step still
    fails, install the Railway GitHub App on `desmotech/taikan-agents` from the
    dashboard and re-run.

11. **Fleet Slack activation.** Native Hermes Slack requires both bot and
    app-level Socket Mode tokens; the entrypoint validates both and an owner
    allowlist. The owner's tokens, scopes/events, destination, and actual replies
    have not been checked. Legacy platform variables are stripped before the
    gateway starts; existing Railway variables and persisted cron destinations
    still need cleanup during deployment. Follow [ENG.md](ENG.md).

12. **eng Railway MCP.** The remote endpoint and OAuth are documented; login,
    refresh, project access, and tool discovery on pinned Hermes remain
    unverified. Hosted Railway exposes an action-capable `railway-agent`; do
    not claim read-only log/metric coverage until a direct read path is verified.
    The soul requires approval before delegating to that tool. No Railway CLI
    or runtime upgrade is included in this change.

13. **product activation and judgment.** The CPO soul/config declares GitHub,
    Linear, PostHog, and public research workflows; product is not deployed.
    Dedicated read-scoped credentials, actual web search/extraction in the
    pinned image, the document inventory/reading pass, and notebook persistence
    need verification. No external customer-feedback repository is connected.
    Run [PRODUCT-EVALS.md](PRODUCT-EVALS.md) after activation; static validation
    is not proof of product judgment, source coverage, or live tool access.
