# Unverified

Things I could not confirm in the docs, the repo, or `--help`. Each has the
safe default I used. None is a silent guess.

1. **Claude 5 model ids inside Hermes.** Hermes docs only show `claude-sonnet-4-6`
   for native Anthropic and list no Claude 5 or Haiku id in the model catalog.
   Default: `claude-opus-5` / `claude-sonnet-5` / `claude-haiku-4-5`, the exact
   Anthropic API ids. **Half-closed 2026-08-29:** the ids are confirmed correct
   on the Anthropic side - `claude-opus-5` ($5/$25 per MTok), `claude-sonnet-5`
   ($2/$10), `claude-haiku-4-5` ($1/$5), no date suffixes. What remains open is
   only whether Hermes passes them through or validates against its own catalog.
   Check on first boot: `railway ssh --service eng -- hermes model`.
   If Hermes validates against a catalog and rejects them, the fallback is
   `model.provider: openrouter` with `anthropic/claude-opus-5`, which needs an
   OpenRouter key.

2. **Root gateway.** The official Hermes Docker page says the gateway refuses to
   run as root unless `HERMES_ALLOW_ROOT_GATEWAY=1`. The template image runs as
   root and its README implies it works, so that check may be specific to the
   official image's entrypoint. Default: set nothing. If the first deploy logs
   a root refusal, add `HERMES_ALLOW_ROOT_GATEWAY=1` as a Railway variable
   (documented var) and redeploy.

3. **Live authentication on the remote MCP servers.** Linear and PostHog now
   document API-key bearer authentication (sources in [ENG.md](ENG.md)); the
   actual credentials and scopes still need live verification. Sentry bearer
   compatibility remains unverified, as does the configured GitHub connection.
   Current default: bearer header for these four. If one rejects it,
   change that entry to `auth: oauth` and run `hermes mcp login <name>` over
   Railway SSH; the OAuth flow on a headless box needs the paste-back of the
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
