#!/usr/bin/env python3
"""Run inside the built image with --network none; no real keys or providers."""

import os
from pathlib import Path
import sys
import tempfile
import threading

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from cost_guard_driver import CostGuardDriver
from runtime_policy import prepare, install_hooks


def main():
    with tempfile.TemporaryDirectory() as home:
        os.environ["HERMES_HOME"] = home
        os.environ["ANTHROPIC_API_KEY"] = "taikan-local-test"
        os.environ["ANTHROPIC_BASE_URL"] = "http://127.0.0.1:12345"
        config_path = Path(home) / "config.yaml"
        config_path.write_text((ROOT / "config/eng.yaml").read_text())
        prepare(config_path)

        from hermes_cli.config import load_config
        cfg = load_config()
        assert cfg["agent"]["max_turns"] == 12
        assert cfg["model"]["max_tokens"] == 4096
        assert cfg["model"]["context_length"] == 40000
        assert cfg["compression"]["threshold_tokens"] == 24000
        assert cfg["auxiliary"]["background_review"]["enabled"] is False
        assert cfg["curator"]["enabled"] is False

        install_hooks()
        from agent.background_review import load_background_review_settings
        from cron.scheduler_provider import resolve_cron_scheduler
        assert load_background_review_settings()[0] is False
        stopped = threading.Event()
        stopped.set()
        # A stopped scheduler returns without ever reading/running stored jobs.
        resolve_cron_scheduler().start(stopped)

        from agent.anthropic_adapter import build_anthropic_client
        driver = CostGuardDriver()
        try:
            base = f"http://127.0.0.1:{driver.server.server_port}"
            client = build_anthropic_client(driver.server.token, base, timeout=5)
            result = client.messages.create(model="claude-sonnet-5", max_tokens=4096,
                                            messages=[{"role": "user", "content": "hello"}])
            assert result.content[0].text == "test"
            assert len(driver.generation_calls()) == 1
            assert driver.rows()[0][2:] == (3000, 1)
            with client.messages.stream(model="claude-sonnet-5", max_tokens=4096,
                                        messages=[{"role": "user", "content": "hello"}]) as stream:
                assert "".join(stream.text_stream) == "test"
                assert stream.get_final_message().usage.output_tokens == 100
            assert len(driver.generation_calls()) == 2
            assert sum(row[2] for row in driver.rows()) == 6000
            driver.spend(1_994_000)
            import anthropic
            try:
                client.messages.create(model="claude-sonnet-5", max_tokens=4096,
                                       messages=[{"role": "user", "content": "over budget"}])
            except anthropic.BadRequestError:
                pass
            else:
                raise AssertionError("Real SDK bypassed the budget denial")
            assert len(driver.generation_calls()) == 2
            client.close()
        finally:
            driver.close()
    print("Real Hermes config, runtime hooks, native Anthropic adapter and budget denial verified offline.")


if __name__ == "__main__":
    main()
