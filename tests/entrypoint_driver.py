"""Run the real entrypoint with isolated state and a recording gateway stub."""

import os
import subprocess
import tempfile
import sys

import yaml
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class EntrypointDriver:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory(prefix="taikan-entrypoint-")
        self.root = Path(self.temp.name)
        self.state = self.root / "state"
        self.state.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        stub = self.bin / "hermes"
        stub.write_text(
            'import os\nfrom pathlib import Path\n'
            'Path(os.environ["HERMES_HOME"], "launched-env-names").write_text("\\n".join(os.environ))\n'
        )
        stub.chmod(0o755)
        for package, module, code in (
            ("cron", "scheduler_provider", "class InProcessCronScheduler:\n    def start(self, *a, **k): pass\n"),
            ("agent", "background_review", "def load_background_review_settings(): return True, {}\n"),
        ):
            target = self.root / package
            target.mkdir()
            (target / "__init__.py").write_text("")
            (target / (module + ".py")).write_text(code)
        self.env = {
            "PATH": str(self.bin) + ":" + str(Path(sys.executable).parent) + ":" + os.defpath,
            "PYTHONPATH": str(self.root),
            "TAIKAN_AGENT_ENABLED": "true",
            "ANTHROPIC_API_KEY": "fake-provider",
            "BOT": "eng",
            "BOT_ASSETS_DIR": str(ROOT),
            "HERMES_HOME": str(self.state),
            "TERMINAL_CWD": str(self.root / "workspace"),
            "SLACK_BOT_TOKEN": "fake-slack-bot",
            "SLACK_APP_TOKEN": "fake-slack-app",
            "SLACK_ALLOWED_USERS": "U_OWNER",
        }

    def close(self):
        self.temp.cleanup()

    def given_state(self, relative, text):
        path = self.state / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def run(self, **overrides):
        env = dict(self.env)
        for key, value in overrides.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        return subprocess.run(
            ["/bin/bash", str(ROOT / "scripts/entrypoint.sh")],
            env=env, capture_output=True, text=True, timeout=10,
        )

    def launched(self):
        return (self.state / "launched-env-names").exists()

    def environment_names(self):
        return self.read_state("launched-env-names").splitlines()

    def state_exists(self, relative):
        return (self.state / relative).exists()

    def read_state(self, relative):
        return (self.state / relative).read_text()

    def source_asset(self, relative):
        return (ROOT / relative).read_text()

    def config_matches_asset(self):
        actual = yaml.safe_load(self.read_state("config.yaml"))
        expected = yaml.safe_load(self.source_asset("config/eng.yaml"))
        actual["model"].pop("base_url")
        for task in actual["auxiliary"].values():
            if isinstance(task, dict):
                task.pop("base_url", None)
        return actual == expected
