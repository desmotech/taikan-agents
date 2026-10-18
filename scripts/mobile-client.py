#!/usr/bin/env python3
"""Allowlisted client for taikan-mobile builds, OTA updates, and store releases.

Builds and OTAs dispatch taikan-mobile GitHub workflows; store status and
releases run the lanes in fastlane/Fastfile against App Store Connect and Play.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.github.com/repos/desmotech/taikan-mobile/actions"
REF = "main"
WORKFLOWS = {"build": "eas-build.yml", "ota": "eas-update.yml"}
MAX_MESSAGE = 200
MAX_NOTES = 4000  # App Store "What's New" limit
FASTFILE = Path(__file__).resolve().parents[1] / "fastlane" / "Fastfile"
RESULT_MARKER = "TAIKAN_STORE_RESULT "
FASTLANE_ENV = {
    "CI": "true", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "FASTLANE_DISABLE_COLORS": "1",
    "FASTLANE_SKIP_UPDATE_CHECK": "1", "FASTLANE_HIDE_CHANGELOG": "1", "FASTLANE_OPT_OUT_USAGE": "YES",
}
LANE_TIMEOUT = {"status": 120, "release": 280}  # under the agent's 300s terminal timeout


def request(method: str, path: str, body: dict | None = None) -> object:
    token = os.environ.get("TAIKAN_MOBILE_GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("TAIKAN_MOBILE_GITHUB_TOKEN is required")
    call = urllib.request.Request(
        f"{API}{path}",
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
        data=json.dumps(body).encode() if body is not None else None,
    )
    try:
        with urllib.request.urlopen(call, timeout=30) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"GitHub rejected the request with status {error.code}") from error
    return json.loads(raw) if raw else None


def active_run(workflow: str) -> dict | None:
    runs = request("GET", f"/workflows/{workflow}/runs?event=workflow_dispatch&per_page=20")
    return next((run for run in runs["workflow_runs"] if run["status"] != "completed"), None)


def dispatch(kind: str, inputs: dict) -> dict:
    workflow = WORKFLOWS[kind]
    busy = active_run(workflow)
    if busy:
        raise RuntimeError(f"A {kind} run is already {busy['status']}: {busy['html_url']}")
    result = request("POST", f"/workflows/{workflow}/dispatches",
                     {"ref": REF, "inputs": inputs, "return_run_details": True})
    dispatched = {"workflow": kind, "ref": REF, "inputs": inputs}
    if result is None:  # 204: dispatched, but GitHub returned no run details
        return dispatched | {"run_id": None, "html_url": None, "note": "dispatched; find the run with `runs`"}
    return dispatched | {"run_id": result["workflow_run_id"], "html_url": result["html_url"]}


def summary(run: dict) -> dict:
    return {
        "run_id": run["id"],
        "workflow": next(kind for kind, file in WORKFLOWS.items() if run["path"].endswith(f"/{file}")),
        "event": run["event"],
        "status": run["status"],
        "conclusion": run["conclusion"],
        "title": run["display_title"],
        "commit": run["head_sha"][:7],
        "created_at": run["created_at"],
        "html_url": run["html_url"],
    }


def recent(limit: int) -> list:
    runs = []
    for workflow in WORKFLOWS.values():
        runs += request("GET", f"/workflows/{workflow}/runs?per_page={limit}")["workflow_runs"]
    runs.sort(key=lambda run: run["created_at"], reverse=True)
    return [summary(run) for run in runs[:limit]]


def detail(run_id: int) -> dict:
    run = request("GET", f"/runs/{run_id}")
    if not any(run["path"].endswith(f"/{file}") for file in WORKFLOWS.values()):
        raise RuntimeError("That run does not belong to the build or OTA workflow")
    jobs = request("GET", f"/runs/{run_id}/jobs")["jobs"]
    return summary(run) | {"jobs": [
        {"name": job["name"], "status": job["status"], "conclusion": job["conclusion"],
         "failed_steps": [step["name"] for step in job.get("steps", []) if step["conclusion"] == "failure"]}
        for job in jobs
    ]}


def message(value: str) -> str:
    if not value.strip() or len(value) > MAX_MESSAGE or any(ord(c) < 32 for c in value):
        raise argparse.ArgumentTypeError(f"a single-line message of 1-{MAX_MESSAGE} characters is required")
    return value.strip()


def lane(platform: str, name: str, inputs: dict) -> dict:
    """Run one Fastfile lane in a scratch directory and return its JSON result."""
    with tempfile.TemporaryDirectory(prefix="taikan-store-") as scratch:
        (Path(scratch) / "fastlane").mkdir()
        shutil.copy(FASTFILE, Path(scratch) / "fastlane" / "Fastfile")
        try:
            done = subprocess.run(
                ["fastlane", platform, name], cwd=scratch, capture_output=True, text=True,
                env=os.environ | FASTLANE_ENV | inputs, timeout=LANE_TIMEOUT[name],
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"{platform} {name} timed out; its store effect is unknown, check store-status")
    lines = done.stdout.splitlines()
    result = next((line[len(RESULT_MARKER):] for line in lines if line.startswith(RESULT_MARKER)), None)
    if done.returncode == 0 and result:
        return json.loads(result)
    errors = [line.strip() for line in lines + done.stderr.splitlines() if "[!]" in line]
    raise RuntimeError(f"{platform} {name} failed: " + (" | ".join(errors[-3:]) or "\n".join(lines[-10:])))


def version(value: str) -> str:
    if not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise argparse.ArgumentTypeError("a version like 1.2.0 is required")
    return value


def positive(value: str) -> int:
    if not value.isdigit() or int(value) < 1:
        raise argparse.ArgumentTypeError("a positive integer is required")
    return int(value)


def notes(value: str) -> str:
    if not value.strip() or len(value) > MAX_NOTES or any(ord(c) < 32 and c != "\n" for c in value):
        raise argparse.ArgumentTypeError(f"release notes of 1-{MAX_NOTES} characters are required")
    return value.strip()


def locale_notes(value: str) -> tuple:
    locale, _, text = value.partition("=")
    if not re.fullmatch(r"[a-z]{2,3}(-[A-Za-z0-9]{2,4})?", locale):
        raise argparse.ArgumentTypeError("LOCALE=TEXT with an App Store locale such as he or en-US is required")
    return locale, notes(text)


def main() -> None:
    parser = argparse.ArgumentParser(description="Start or inspect taikan-mobile builds, OTA updates, and store releases")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="production EAS build from main, auto-submitted to the stores")
    build.add_argument("--platform", required=True, choices=["ios", "android", "all"])
    ota = sub.add_parser("ota", help="EAS update from main")
    ota.add_argument("--branch", required=True, choices=["production", "preview"])
    ota.add_argument("--message", type=message)
    runs = sub.add_parser("runs", help="recent build and OTA runs")
    runs.add_argument("--limit", type=int, choices=range(1, 21), default=5, metavar="1-20")
    show = sub.add_parser("run", help="one run with job results")
    show.add_argument("run_id", type=int)
    status = sub.add_parser("store-status", help="App Store or Play production state and recent builds")
    status.add_argument("--platform", required=True, choices=["ios", "android"])
    ios = sub.add_parser("ios-release", help="submit an uploaded build for App Review; released on approval")
    ios.add_argument("--version", required=True, type=version)
    ios.add_argument("--build", required=True, type=positive)
    ios.add_argument("--notes", required=True, type=notes, help="What's New for every locale without an override")
    ios.add_argument("--locale-notes", action="append", default=[], type=locale_notes, metavar="LOCALE=TEXT")
    android = sub.add_parser("android-release", help="promote an internal-track release to production at 100%%")
    android.add_argument("--version-code", required=True, type=positive)
    args = parser.parse_args()
    if args.command == "build":
        result = dispatch("build", {"profile": "production", "platform": args.platform, "auto_submit": "true"})
    elif args.command == "ota":
        inputs = {"branch": args.branch, "environment": args.branch}
        if args.message:
            inputs["message"] = args.message
        result = dispatch("ota", inputs)
    elif args.command == "runs":
        result = recent(args.limit)
    elif args.command == "run":
        result = detail(args.run_id)
    elif args.command == "store-status":
        result = lane(args.platform, "status", {})
    elif args.command == "ios-release":
        result = lane("ios", "release", {
            "TAIKAN_STORE_VERSION": args.version,
            "TAIKAN_STORE_BUILD": str(args.build),
            "TAIKAN_STORE_NOTES": json.dumps({"default": args.notes} | dict(args.locale_notes), ensure_ascii=False),
        })
    else:
        result = lane("android", "release", {"TAIKAN_STORE_VERSION_CODE": str(args.version_code)})
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
