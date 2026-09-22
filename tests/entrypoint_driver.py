"""Run the real entrypoint with isolated state and a recording gateway stub."""

import os
import subprocess
import tempfile
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
            '#!/bin/sh\n[ "$1" = gateway ] || exit 91\n'
            'env | cut -d= -f1 > "$HERMES_HOME/launched-env-names"\n'
        )
        stub.chmod(0o755)
        self.env = {
            "PATH": str(self.bin) + ":" + os.defpath,
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

    def read_state(self, relative):
        return (self.state / relative).read_text()

    def source_asset(self, relative):
        return (ROOT / relative).read_text()
