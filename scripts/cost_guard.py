#!/usr/bin/env python3
"""Local Anthropic gateway: key isolation, model/feature allowlist, usage ledger.

Only the supervisor receives the real key. Hermes gets a loopback capability.
Spending is capped by the Anthropic workspace limit, not here: the ledger
records what each call cost so spend is visible per UTC day and model.
Amounts are integer microdollars.
"""

import contextlib
import datetime as dt
import hmac
import http.client
import json
import os
from pathlib import Path
import secrets
import signal
import socketserver
import sqlite3
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


# Reviewed standard API rates, USD / million tokens (2026-09-22).
# Cache writes are recorded at the 1-hour (2x input) rate, reads at 0.1x.
RATES = {"claude-opus-5": (5, 25), "claude-sonnet-5": (2, 10), "claude-haiku-4-5": (1, 5)}
MAX_OUTPUT = 16_384
MAX_BODY = 32_000_000
UPSTREAM_TIMEOUT = 600
ALLOWED_FIELDS = {
    "model", "messages", "system", "tools", "tool_choice", "max_tokens",
    "stream", "stop_sequences", "metadata", "thinking", "output_config",
    "temperature", "top_p", "top_k", "cache_control", "service_tier",
}
# Provider headers Hermes/the SDK use for retry decisions and diagnostics.
RELAYED_HEADERS = ("content-type", "retry-after", "x-should-retry", "request-id")


class Denied(Exception):
    pass


def integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def validate_request(body):
    if not isinstance(body, dict) or set(body) - ALLOWED_FIELDS:
        raise Denied("Unsupported request feature; cost review required.")
    if body.get("model") not in RATES:
        raise Denied("Model blocked by cost policy; use a reviewed Opus 5, Sonnet 5 or Haiku 4.5 model.")
    if not isinstance(body.get("messages"), list) or not body["messages"]:
        raise Denied("A Messages request needs at least one message.")
    output = body.get("max_tokens")
    if not integer(output) or output < 1:
        raise Denied("max_tokens must be a positive integer.")
    body["max_tokens"] = min(output, MAX_OUTPUT)
    if body.get("service_tier", "standard_only") not in ("auto", "standard_only"):
        raise Denied("Only standard pricing is allowed.")
    body["service_tier"] = "standard_only"
    tools = body.get("tools", [])
    if not isinstance(tools, list) or any(
        not isinstance(t, dict) or t.get("type", "custom") != "custom"
        for t in tools
    ):
        raise Denied("Provider-hosted paid tools are disabled; use local MCP tools.")
    def visit(item):
        if isinstance(item, dict):
            if item.get("type") in ("server_tool_use", "web_search_tool_result"):
                raise Denied("Provider-hosted paid tools are disabled; use local MCP tools.")
            for v in item.values():
                visit(v)
        elif isinstance(item, list):
            for v in item:
                visit(v)
    visit(body["messages"])
    if "output_config" in body and (not isinstance(body["output_config"], dict) or set(body["output_config"]) - {"effort"}):
        raise Denied("Unsupported output configuration.")


def usage_cost(model, usage):
    """Microdollars for a usage block, or None if it lacks integer token counts."""
    if not isinstance(usage, dict) or not all(integer(usage.get(k)) for k in ("input_tokens", "output_tokens")):
        return None
    writes = usage.get("cache_creation_input_tokens") or 0
    reads = usage.get("cache_read_input_tokens") or 0
    if not integer(writes) or not integer(reads):
        return None
    ip, op = RATES[model]
    return (usage["input_tokens"] * ip + usage["output_tokens"] * op
            + writes * ip * 2 + (reads * ip + 9) // 10)


class Ledger:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS calls (
                    id INTEGER PRIMARY KEY, day TEXT NOT NULL, model TEXT NOT NULL,
                    usd_micro INTEGER NOT NULL, usage TEXT NOT NULL
                )
            """)

    @contextlib.contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def record(self, model, usage, day=None):
        """Store one call; returns (call cost, UTC day total) or None if usage is unusable."""
        cost = usage_cost(model, usage)
        if cost is None:
            return None
        day = day or dt.datetime.now(dt.timezone.utc).date().isoformat()
        with self.connect() as db:
            db.execute("INSERT INTO calls(day,model,usd_micro,usage) VALUES(?,?,?,?)",
                       (day, model, cost, json.dumps(usage, sort_keys=True)))
            today = db.execute("SELECT SUM(usd_micro) FROM calls WHERE day=?", (day,)).fetchone()[0]
        return cost, today


class AnthropicUpstream:
    def __init__(self, key):
        self.key = key

    @contextlib.contextmanager
    def request(self, path, body):
        # No inherited proxy, redirects, arbitrary upstream URL, beta features,
        # or user-supplied auth headers. Retries are left to Hermes.
        conn = http.client.HTTPSConnection("api.anthropic.com", timeout=UPSTREAM_TIMEOUT)
        try:
            conn.request("POST", path, json.dumps(body).encode(), {
                "x-api-key": self.key, "anthropic-version": "2023-06-01",
                "Content-Type": "application/json", "Accept-Encoding": "identity",
            })
            yield conn.getresponse()
        finally:
            conn.close()


class Gate:
    def __init__(self, ledger, upstream):
        self.ledger = ledger
        self.upstream = upstream

    def account(self, model, usage):
        try:
            result = self.ledger.record(model, usage)
        except sqlite3.Error as exc:
            print(f"[cost-guard] ledger write failed ({exc}); model={model} usage={json.dumps(usage)}", flush=True)
            return
        if result is None:
            print(f"[cost-guard] unaccounted call: incomplete usage model={model}", flush=True)
        else:
            cost, today = result
            print(f"[cost-guard] usd={cost / 1e6:.4f} today_usd={today / 1e6:.2f} model={model}", flush=True)


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def server_bind(self):
        # HTTPServer performs a reverse-DNS lookup even for 127.0.0.1.
        # No hostname is needed for this private listener.
        socketserver.TCPServer.server_bind(self)
        self.server_name = "localhost"
        self.server_port = self.server_address[1]


class Handler(BaseHTTPRequestHandler):
    # HTTP/1.0 closes each response, allowing streaming without buffering the
    # completion or implementing a second chunked transfer encoder.
    def log_message(self, *_):
        pass  # Never log request bodies, keys, completions, or arbitrary URLs.

    def fail(self, status, kind, message):
        data = json.dumps({"type": "error", "error": {
            "type": kind, "message": "Taikan cost guard: " + message,
        }}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        gate = self.server.gate
        started = False
        usage = None
        model = None
        try:
            if not hmac.compare_digest(self.headers.get("x-api-key", ""), self.server.token):
                raise Denied("Invalid local gateway credential.")
            if self.path not in ("/v1/messages", "/v1/messages?beta=true"):
                raise Denied("Only Messages calls are supported.")
            size = int(self.headers.get("Content-Length", "0"))
            if self.headers.get("Transfer-Encoding") or not 0 < size <= MAX_BODY:
                raise Denied("Request body exceeds the gateway limit.")
            self.connection.settimeout(100)
            body = json.loads(self.rfile.read(size))
            validate_request(body)
            model = body["model"]
            with gate.upstream.request("/v1/messages", body) as response:
                self.send_response(response.status)
                for name, value in response.getheaders():
                    if name.lower() in RELAYED_HEADERS or name.lower().startswith("anthropic-ratelimit-"):
                        self.send_header(name, value)
                self.end_headers()
                started = True
                if response.status != 200:
                    # Unbilled provider error: relay as-is so Hermes applies its retry policy.
                    self.wfile.write(response.read())
                    return
                if body.get("stream"):
                    while True:
                        line = response.readline()
                        if not line:
                            break
                        self.wfile.write(line)
                        self.wfile.flush()
                        if line.startswith(b"data: "):
                            event = json.loads(line[6:])
                            kind = event.get("type")
                            if kind == "message_start":
                                usage = dict(event["message"].get("usage") or {})
                            elif kind == "message_delta" and usage is not None:
                                usage.update(event.get("usage") or {})
                else:
                    data = response.read()
                    self.wfile.write(data)
                    usage = json.loads(data).get("usage")
        except Denied as exc:
            print("[cost-guard] refused: " + str(exc), flush=True)
            if not started:
                with contextlib.suppress(OSError):
                    self.fail(400, "invalid_request_error", str(exc))
        except Exception as exc:
            print(f"[cost-guard] request failed: {type(exc).__name__}", flush=True)
            if not started:
                with contextlib.suppress(OSError):
                    # Transport failure before any provider response: retryable for Hermes.
                    self.fail(502, "api_error", "Provider connection failed; retry.")
        finally:
            # Best-known usage is recorded even for interrupted streams.
            if model is not None and usage is not None:
                gate.account(model, usage)


def child_environment(env, token, port):
    result = dict(env)
    # Other provider keys would allow alternate model routes around the gate.
    forbidden = ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_TOKEN",
                 "GOOGLE_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY", "DEEPSEEK_API_KEY",
                 "DASHSCOPE_API_KEY", "KIMI_API_KEY", "GLM_API_KEY", "HF_TOKEN",
                 "AI_GATEWAY_API_KEY", "MINIMAX_API_KEY", "COPILOT_GITHUB_TOKEN", "NOUS_API_KEY")
    if any(result.get(k) for k in forbidden):
        raise Denied("Remove alternate inference credentials before enabling this agent.")
    result["ANTHROPIC_API_KEY"] = token
    result["ANTHROPIC_BASE_URL"] = f"http://127.0.0.1:{port}"
    result["HERMES_INFERENCE_PROVIDER"] = "anthropic"
    # config.yaml agent.max_turns is authoritative; drop inherited overrides.
    for k in ("LLM_MODEL", "OPENAI_BASE_URL", "HERMES_DUMP_REQUESTS", "HERMES_MAX_ITERATIONS",
              "CONTEXT_COMPRESSION_ENABLED", "CONTEXT_COMPRESSION_THRESHOLD", "CONTEXT_COMPRESSION_MODEL"):
        result.pop(k, None)
    return result


def main():
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise Denied("ANTHROPIC_API_KEY is required; alternate providers are disabled.")
    home = Path(os.environ.get("HERMES_HOME", "/data/.hermes"))
    ledger = Ledger(home / "cost-guard" / "usage.sqlite3")
    server = LocalServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    server.token = "taikan-local-" + secrets.token_hex(32)
    server.gate = Gate(ledger, AnthropicUpstream(key))
    env = child_environment(os.environ, server.token, server.server_port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    child = subprocess.Popen(["/bin/bash", sys.argv[1], "--guarded"], env=env, start_new_session=True)
    def stop(signum, _frame):
        with contextlib.suppress(ProcessLookupError):
            os.killpg(child.pid, signum)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        return child.wait()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Denied as exc:
        print("[cost-guard] Startup refused: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
    except sqlite3.Error:
        print("[cost-guard] Startup refused; usage ledger is unavailable.", file=sys.stderr)
        raise SystemExit(1)
