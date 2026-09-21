#!/usr/bin/env python3
"""Allowlisted client for the four branded-app assistant endpoints."""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.I)


def request(method: str, path: str) -> object:
    base = os.environ.get("TAIKAN_RELEASE_API_URL", "").rstrip("/")
    token = os.environ.get("TAIKAN_RELEASE_ASSISTANT_TOKEN", "")
    if not base.startswith("https://") or not token:
        raise RuntimeError("TAIKAN_RELEASE_API_URL and TAIKAN_RELEASE_ASSISTANT_TOKEN are required")
    call = urllib.request.Request(
        f"{base}{path}",
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        data=b"{}" if method == "POST" else None,
    )
    try:
        with urllib.request.urlopen(call, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Release API rejected the request with status {error.code}") from error
    return payload.get("data")


def identifier(value: str) -> str:
    if not UUID.fullmatch(value):
        raise argparse.ArgumentTypeError("an operation or release UUID is required")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Read or nudge owner-approved branded-app releases")
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list")
    listing.add_argument("--cursor")
    show = sub.add_parser("get")
    show.add_argument("release_id", type=identifier)
    preflight = sub.add_parser("preflight")
    preflight.add_argument("operation_id", type=identifier)
    execute = sub.add_parser("execute-approved")
    execute.add_argument("operation_id", type=identifier)
    args = parser.parse_args()
    if args.command == "list":
        suffix = f"?cursor={urllib.parse.quote(args.cursor)}" if args.cursor else ""
        result = request("GET", f"/internal/branded-app-assistant/releases{suffix}")
    elif args.command == "get":
        result = request("GET", f"/internal/branded-app-assistant/releases/{args.release_id}")
    elif args.command == "preflight":
        result = request("POST", f"/internal/branded-app-assistant/operations/{args.operation_id}/preflight")
    else:
        result = request("POST", f"/internal/branded-app-assistant/operations/{args.operation_id}/execute-approved")
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
