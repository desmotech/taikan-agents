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
        assert cfg["model"]["default"] == "claude-opus-5"
        assert cfg["agent"]["max_turns"] == 40
        assert cfg["model"]["max_tokens"] == 16384
        assert cfg["model"]["context_length"] == 120000
        assert cfg["compression"]["threshold_tokens"] == 80000
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

        # Production routing: main loop and every side-call reach the loopback guard;
        # side-calls run on Haiku instead of inheriting Opus.
        from hermes_cli.runtime_provider import resolve_runtime_provider
        from agent.auxiliary_client import get_text_auxiliary_client
        from runtime_policy import OPUS_AUXILIARY_TASKS
        runtime = resolve_runtime_provider(requested="anthropic")
        assert runtime["base_url"].startswith("http://127.0.0.1:"), runtime["base_url"]
        for task in OPUS_AUXILIARY_TASKS:
            client, model = get_text_auxiliary_client(task, main_runtime=runtime)
            assert model == "claude-haiku-4-5", (task, model)
            assert str(client.base_url).startswith("http://127.0.0.1:"), (task, client.base_url)

        from agent.anthropic_adapter import build_anthropic_client
        import anthropic
        driver = CostGuardDriver()
        try:
            base = f"http://127.0.0.1:{driver.server.server_port}"
            client = build_anthropic_client(driver.server.token, base, timeout=5)
            result = client.messages.create(model="claude-opus-5", max_tokens=16384,
                                            messages=[{"role": "user", "content": "hello"}])
            assert result.content[0].text == "test"
            assert driver.rows() == [("claude-opus-5", 7500)]
            with client.messages.stream(model="claude-opus-5", max_tokens=16384,
                                        messages=[{"role": "user", "content": "hello"}]) as stream:
                assert "".join(stream.text_stream) == "test"
                assert stream.get_final_message().usage.output_tokens == 100
            assert sum(row[1] for row in driver.rows()) == 15000
            # The real SDK must see provider overload as retryable, not a terminal 400.
            driver.upstream.status = 529
            try:
                client.with_options(max_retries=0).messages.create(
                    model="claude-opus-5", max_tokens=16384,
                    messages=[{"role": "user", "content": "overloaded"}])
            except anthropic.APIStatusError as exc:
                assert exc.status_code == 529 and not isinstance(exc, anthropic.BadRequestError)
            else:
                raise AssertionError("Provider overload was not relayed")
            driver.upstream.status = 200
            client.messages.create(model="claude-opus-5", max_tokens=16384,
                                   messages=[{"role": "user", "content": "recovered"}])
            assert len(driver.rows()) == 3
            client.close()
        finally:
            driver.close()
    print("Real Hermes config, runtime hooks, native Anthropic adapter and error relay verified offline.")


if __name__ == "__main__":
    main()
