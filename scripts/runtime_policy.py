"""Validated fleet defaults and the supported Hermes runtime safety hooks."""

import os
from pathlib import Path
import runpy
import shutil
import sys

import yaml


def errors(config):
    required = {
        ("agent", "max_turns"): 12,
        ("agent", "run_budget_seconds"): 180,
        ("model", "provider"): "anthropic",
        ("model", "context_length"): 40000,
        ("model", "max_tokens"): 4096,
        ("compression", "enabled"): True,
        ("compression", "threshold_tokens"): 24000,
        ("auxiliary", "background_review", "enabled"): False,
        ("curator", "enabled"): False,
        ("memory", "nudge_interval"): 0,
        ("tool_loop_guardrails", "hard_stop_enabled"): True,
    }
    problems = []
    for path, expected in required.items():
        actual = config
        for part in path:
            actual = actual.get(part) if isinstance(actual, dict) else None
        if actual != expected or type(actual) is not type(expected):
            problems.append(".".join(path) + f" must be {expected!r}")
    if config.get("model", {}).get("default") not in ("claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"):
        problems.append("Only cost-reviewed Opus 5, Sonnet 5 and Haiku 4.5 models are permitted")
    if not {"delegation", "cronjob"}.issubset(config.get("agent", {}).get("disabled_toolsets", [])):
        problems.append("Delegation and cronjob toolsets must be disabled")
    return problems


def prepare(path):
    config = yaml.safe_load(Path(path).read_text())
    problems = errors(config)
    if problems:
        raise ValueError("; ".join(problems))
    base = os.environ.get("ANTHROPIC_BASE_URL", "")
    if not base.startswith("http://127.0.0.1:") or not os.environ.get("ANTHROPIC_API_KEY", "").startswith("taikan-local-"):
        raise ValueError("Gateway must run under the cost supervisor")
    config["model"]["base_url"] = base
    for task in config.get("auxiliary", {}).values():
        if isinstance(task, dict) and task.get("provider") == "anthropic":
            task["base_url"] = base
    Path(path).write_text(yaml.safe_dump(config, sort_keys=False))


def install_hooks():
    # Hermes has no supported cron off switch: unknown providers silently fall
    # back to the built-in ticker. Disable dispatch at its verified boundary.
    # Leave jobs.json untouched so existing schedules remain inspectable.
    import cron.scheduler_provider as scheduler
    import agent.background_review as review

    if not callable(getattr(scheduler.InProcessCronScheduler, "start", None)):
        raise RuntimeError("Unsupported Hermes scheduler; refusing startup")
    if not callable(getattr(review, "load_background_review_settings", None)):
        raise RuntimeError("Unsupported Hermes background review; refusing startup")

    def wait_without_dispatch(stop_event, **_kwargs):
        stop_event.wait()

    scheduler.InProcessCronScheduler.start = staticmethod(wait_without_dispatch)
    # Force the built-in disabled scheduler, including if persisted config names
    # an external provider. Manual cron via terminal is still owner-controlled.
    scheduler.resolve_cron_scheduler = scheduler.InProcessCronScheduler
    review.load_background_review_settings = lambda: (False, {"enabled": False})
    print("[cost-guard] Automatic cron dispatch and background reviews disabled.", flush=True)


def gateway():
    install_hooks()
    sys.argv = ["hermes", "gateway"]
    runpy.run_path(shutil.which("hermes"), run_name="__main__")


if __name__ == "__main__":
    if sys.argv[1] == "prepare":
        prepare(sys.argv[2])
    elif sys.argv[1] == "gateway":
        gateway()
    else:
        raise SystemExit("Unknown runtime policy command")
