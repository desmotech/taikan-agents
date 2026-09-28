#!/usr/bin/env python3
"""Validate the deployable asset set without contacting external services."""

import re
import tomllib
from pathlib import Path

import yaml

from runtime_policy import errors as cost_errors


ROOT = Path(__file__).resolve().parents[1]


def main():
    souls = {p.stem: p for p in (ROOT / "souls").glob("*.md")}
    configs = {p.stem: p for p in (ROOT / "config").glob("*.yaml")}
    errors = []

    if not souls or souls.keys() != configs.keys():
        errors.append("Every soul must have exactly one matching YAML config")

    for name, path in souls.items():
        text = path.read_text()
        if not text.strip() or len(text) > 20_000:
            errors.append(f"{path.relative_to(ROOT)} must contain 1–20,000 characters")

    for name, path in configs.items():
        config = yaml.safe_load(path.read_text())
        if not isinstance(config, dict):
            errors.append(f"{path.relative_to(ROOT)} must be a YAML mapping")
            continue
        if config.get("timezone") != "Asia/Jerusalem":
            errors.append(f"{name}: missing fleet timezone")
        errors.extend(f"{name}: {error}" for error in cost_errors(config))
        model = config.get("model", {})
        if not model.get("provider") or not model.get("default"):
            errors.append(f"{name}: model provider and default are required")
        for server, settings in config.get("mcp_servers", {}).items():
            if not isinstance(settings, dict):
                errors.append(f"{name}/{server}: MCP settings must be a mapping")
                continue
            if bool(settings.get("url")) == bool(settings.get("command")):
                errors.append(f"{name}/{server}: choose exactly one MCP transport")
            for header, value in settings.get("headers", {}).items():
                if header.lower() == "authorization" and not re.search(r"\$\{[A-Z_][A-Z0-9_]*\}", str(value)):
                    errors.append(f"{name}/{server}: authorization must reference an environment variable")

    railway = tomllib.loads((ROOT / "railway.toml").read_text())
    if railway.get("build", {}).get("builder") != "dockerfile":
        errors.append("Railway must build the CI-validated Dockerfile")
    if railway.get("deploy", {}).get("requiredMountPath") != "/data":
        errors.append("Railway must require the persistent /data volume")

    dockerfile = (ROOT / "Dockerfile").read_text()
    if 'rev-parse HEAD)" = "5fc308a70719a83cccdbba4c0e39c23f5a8239d5"' not in dockerfile:
        errors.append("Dockerfile must verify the cost-reviewed Hermes commit")
    match = re.search(r"^ARG HERMES_GIT_REF=(\S+)$", dockerfile, re.MULTILINE)
    if not match or not re.fullmatch(r"v\d{4}\.\d+\.\d+|[a-f0-9]{40}", match[1]):
        errors.append("Dockerfile must supply a pinned Hermes ref for CI and Railway")
    elif match[1] not in (ROOT / "scripts/bootstrap.sh").read_text() or not re.search(
        rf"^HERMES_GIT_REF={re.escape(match[1])}(?:\s|$)",
        (ROOT / ".env.example").read_text(), re.MULTILINE,
    ):
        errors.append("Hermes defaults differ between Dockerfile, bootstrap, and .env.example")

    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Validated {len(souls)} agent asset pairs and Railway build configuration.")


if __name__ == "__main__":
    main()
