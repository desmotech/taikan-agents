import unittest

from entrypoint_driver import EntrypointDriver


class EntrypointTests(unittest.TestCase):
    def setUp(self):
        self.driver = EntrypointDriver()
        self.addCleanup(self.driver.close)

    def test_slack_starts_and_loads_git_assets(self):
        result = self.driver.run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.driver.launched())
        self.assertEqual(self.driver.read_state("SOUL.md"), self.driver.source_asset("souls/eng.md"))
        self.assertEqual(self.driver.read_state("config.yaml"), self.driver.source_asset("config/eng.yaml"))
        for secret in ("fake-provider", "fake-slack-bot", "fake-slack-app"):
            self.assertNotIn(secret, result.stdout + result.stderr)

    def test_legacy_credentials_cannot_enable_other_platforms(self):
        self.driver.given_state(".env", "TELEGRAM_BOT_TOKEN=fake-old-token\n")
        result = self.driver.run(
            TELEGRAM_BOT_TOKEN="fake-old-token",
            DISCORD_BOT_TOKEN="fake-discord",
            WHATSAPP_ENABLED="true",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in self.driver.environment_names():
            self.assertFalse(name.startswith(("TELEGRAM_", "DISCORD_", "WHATSAPP_")))
        for prefix in ("TELEGRAM_", "DISCORD_", "WHATSAPP_"):
            self.assertNotIn(prefix, self.driver.read_state(".env"))
        self.assertIn("SLACK_BOT_TOKEN", self.driver.environment_names())

    def test_restart_preserves_agent_state_but_refreshes_identity(self):
        persisted = {
            "memories/MEMORY.md": "remember this",
            "sessions/session.json": "existing session",
            "cron/jobs.json": "existing schedules",
            "state.db": "existing state",
            "auth.json": "existing auth",
            "mcp-tokens/railway.json": "existing Railway OAuth",
            "mcp-tokens/sentry.json": "existing Sentry OAuth",
            ".initialized": "original initialization",
        }
        for path, content in persisted.items():
            self.driver.given_state(path, content)
        self.driver.given_state("SOUL.md", "stale identity")
        self.driver.given_state("config.yaml", "stale config")
        result = self.driver.run()
        self.assertEqual(result.returncode, 0, result.stderr)
        for path, content in persisted.items():
            self.assertEqual(self.driver.read_state(path), content)
        self.assertEqual(self.driver.read_state("SOUL.md"), self.driver.source_asset("souls/eng.md"))

    def test_railway_without_data_volume_refuses_to_start(self):
        for mount in (None, "/wrong-path"):
            with self.subTest(mount=mount):
                result = self.driver.run(
                    RAILWAY_ENVIRONMENT_ID="test-environment",
                    RAILWAY_VOLUME_MOUNT_PATH=mount,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("persistent Railway volume at /data", result.stderr)
                self.assertFalse(self.driver.launched())
                self.assertFalse(self.driver.state_exists(".initialized"))

    def test_railway_with_data_volume_starts(self):
        result = self.driver.run(
            RAILWAY_ENVIRONMENT_ID="test-environment",
            RAILWAY_VOLUME_MOUNT_PATH="/data",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.driver.launched())

    def test_incomplete_slack_setup_is_rejected_without_fallback(self):
        cases = [
            {"SLACK_BOT_TOKEN": None},
            {"SLACK_APP_TOKEN": None},
            {"SLACK_BOT_TOKEN": None, "SLACK_APP_TOKEN": None, "TELEGRAM_BOT_TOKEN": "fake-old-token"},
        ]
        for settings in cases:
            with self.subTest(settings=settings):
                result = self.driver.run(**settings)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Slack requires both", result.stderr)
                self.assertFalse(self.driver.launched())

    def test_missing_or_empty_owner_allowlist_is_rejected(self):
        for value in (None, "", " , "):
            with self.subTest(value=value):
                result = self.driver.run(SLACK_ALLOWED_USERS=value)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Set SLACK_ALLOWED_USERS", result.stderr)
                self.assertFalse(self.driver.launched())

    def test_allow_all_cannot_override_owner_restriction(self):
        for name in ("GATEWAY_ALLOW_ALL_USERS", "SLACK_ALLOW_ALL_USERS"):
            with self.subTest(name=name):
                result = self.driver.run(**{name: "true"})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("allow-all must be disabled", result.stderr)
                self.assertFalse(self.driver.launched())

    def test_release_bot_keeps_its_credential_boundary(self):
        result = self.driver.run(
            BOT="release", TAIKAN_RELEASE_API_URL="https://example.invalid",
            TAIKAN_RELEASE_ASSISTANT_TOKEN="fake-release", GITHUB_TOKEN="fake-github",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("release bot refuses unexpected privileged variable GITHUB_TOKEN", result.stderr)
        self.assertFalse(self.driver.launched())
        self.assertNotIn("fake-github", result.stdout + result.stderr)
