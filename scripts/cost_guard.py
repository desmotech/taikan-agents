#!/usr/bin/env python3
"""Local Anthropic admission gate and persistent, conservative spending ledger.

Only the supervisor receives the real key. Hermes gets a loopback capability.
This limits accidental runaway work, not a hostile process with shell/root access.
All amounts are integer microdollars; reservations survive crashes and restarts.
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

import yaml


# Reviewed standard API rates, USD / million tokens (2026-09-22).
# A cache write is conservatively charged at the 1-hour (2x input) rate.
# Unknown models, paid server tools, fast mode, and unknown API features fail closed.
RATES = {"claude-sonnet-5": (2, 10), "claude-haiku-4-5": (1, 5)}
DAILY_USD_MICRO = 2_000_000
TOTAL_USD_MICRO = 10_000_000
MAX_INPUT = 40_000
MAX_OUTPUT = 4096
MAX_BODY = 1_000_000
MAX_RESPONSE = 2_000_000
ALLOWED_FIELDS = {
    "model", "messages", "system", "tools", "tool_choice", "max_tokens",
    "stream", "stop_sequences", "metadata", "thinking", "output_config",
    "temperature", "top_p", "top_k", "cache_control", "service_tier",
}
COUNT_FIELDS = {"model", "messages", "system", "tools", "tool_choice", "thinking"}


class Denied(Exception):
    pass


def integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def validate_request(body):
    if not isinstance(body, dict) or set(body) - ALLOWED_FIELDS:
        raise Denied("Unsupported request feature; cost review required.")
    if body.get("model") not in RATES:
        raise Denied("Model blocked by cost policy; use Sonnet 5 or Haiku 4.5.")
    if not isinstance(body.get("messages"), list) or not body["messages"]:
        raise Denied("A bounded Messages request is required.")
    output = body.get("max_tokens")
    if not integer(output) or output < 1:
        raise Denied("Output limit exceeds 4096 tokens; start a smaller task.")
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
    # Client tools have no separate Anthropic tool fee. Reject features whose
    # billing or count_tokens semantics this gateway has not reviewed.
    def visit(item):
        if isinstance(item, dict):
            if item.get("type") in ("image", "document", "server_tool_use", "web_search_tool_result"):
                raise Denied("This text-only cost policy does not permit media or server tools.")
            for v in item.values():
                visit(v)
        elif isinstance(item, list):
            for v in item:
                visit(v)
    visit(body["messages"])
    if "output_config" in body and (not isinstance(body["output_config"], dict) or set(body["output_config"]) - {"effort"}):
        raise Denied("Unsupported output configuration.")


class Ledger:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS calls (
                    id TEXT PRIMARY KEY, day TEXT NOT NULL, model TEXT NOT NULL,
                    reserved INTEGER NOT NULL, charged INTEGER NOT NULL,
                    complete INTEGER NOT NULL DEFAULT 0, usage TEXT
                );
                CREATE TABLE IF NOT EXISTS stop (reason TEXT NOT NULL);
            """)

    @contextlib.contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def reserve(self, model, amount, day=None):
        day = day or dt.datetime.now(dt.timezone.utc).date().isoformat()
        call_id = secrets.token_hex(16)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM stop LIMIT 1").fetchone():
                raise Denied("Cost gate is latched off; owner must review the ledger before restarting.")
            total, today = db.execute(
                "SELECT COALESCE(SUM(charged),0), COALESCE(SUM(CASE WHEN day=? THEN charged ELSE 0 END),0) FROM calls",
                (day,),
            ).fetchone()
            if total + amount > TOTAL_USD_MICRO or today + amount > DAILY_USD_MICRO:
                raise Denied("Agent budget exhausted ($2/UTC day, $10 total); no request sent. Owner review required.")
            db.execute("INSERT INTO calls(id,day,model,reserved,charged) VALUES(?,?,?,?,?)",
                       (call_id, day, model, amount, amount))
        return call_id

    def latch(self, reason):
        with self.connect() as db:
            db.execute("INSERT INTO stop(reason) VALUES(?)", (reason,))

    def check_startup(self):
        # An interrupted request's reservation is never refunded on restart.
        with self.connect() as db:
            if db.execute("SELECT 1 FROM calls WHERE complete=0 LIMIT 1").fetchone():
                raise Denied("Unfinished billed request in ledger; owner review required. Reservation preserved.")
            if db.execute("SELECT 1 FROM stop LIMIT 1").fetchone():
                raise Denied("Cost gate is latched off; owner review required.")

    def settle(self, call_id, usage):
        if not isinstance(usage, dict) or not all(integer(usage.get(k)) for k in ("input_tokens", "output_tokens")):
            raise Denied("Missing usage accounting; reservation preserved.")
        for k in ("cache_creation_input_tokens", "cache_read_input_tokens"):
            if not integer(usage.get(k, 0)):
                raise Denied("Invalid cache accounting; reservation preserved.")
        # Reject any provider-hosted tool usage even if a future API accepts it.
        if usage.get("server_tool_use") or usage.get("service_tier", "standard") != "standard":
            raise Denied("Unpriced usage; reservation preserved.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            model, reserved, complete = db.execute(
                "SELECT model,reserved,complete FROM calls WHERE id=?", (call_id,)
            ).fetchone()
            if complete:
                raise Denied("Duplicate accounting settlement.")
            ip, op = RATES[model]
            # Cache reads rounded UP to whole microdollars. 1-hour write rate
            # deliberately also applied to 5-minute writes (conservative).
            charge = (usage["input_tokens"] * ip + usage["output_tokens"] * op
                      + usage.get("cache_creation_input_tokens", 0) * ip * 2
                      + (usage.get("cache_read_input_tokens", 0) * ip + 9) // 10)
            if charge > reserved:
                db.execute("INSERT INTO stop(reason) VALUES('usage exceeded reservation')")
            db.execute("UPDATE calls SET charged=?,complete=1,usage=? WHERE id=?",
                       (charge, json.dumps(usage, sort_keys=True), call_id))
        return charge


class AnthropicUpstream:
    def __init__(self, key):
        self.key = key

    @contextlib.contextmanager
    def request(self, path, body):
        # No inherited proxy, redirects, arbitrary upstream URL, beta features,
        # automatic retry, or user-supplied auth headers.
        conn = http.client.HTTPSConnection("api.anthropic.com", timeout=90)
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
        self.active = threading.BoundedSemaphore(1)

    def admit(self, body):
        validate_request(body)
        with self.upstream.request("/v1/messages/count_tokens", {
            k: v for k, v in body.items() if k in COUNT_FIELDS
        }) as response:
            if response.status != 200:
                raise Denied("Token counting failed; no generation request sent.")
            count = json.loads(response.read(MAX_RESPONSE)).get("input_tokens")
        if not integer(count) or count > MAX_INPUT:
            raise Denied("Input exceeds 40,000 tokens; use a new, focused thread or smaller tool results.")
        # Count API is an estimate. Reserve generous headroom and the most
        # expensive supported cache-write rate, plus the entire output cap.
        ip, op = RATES[body["model"]]
        reserved = (count + max(4096, count // 4)) * ip * 2 + body["max_tokens"] * op
        return self.ledger.reserve(body["model"], reserved)


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

    def fail(self, message):
        data = json.dumps({"type": "error", "error": {
            "type": "invalid_request_error", "message": "Taikan cost guard: " + message,
        }}).encode()
        self.send_response(400)  # non-retryable in Anthropic SDK/Hermes
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        gate = self.server.gate
        acquired = False
        call_id = None
        started = False
        try:
            if not hmac.compare_digest(self.headers.get("x-api-key", ""), self.server.token):
                raise Denied("Invalid local gateway credential.")
            if self.path not in ("/v1/messages", "/v1/messages?beta=true"):
                raise Denied("Only bounded Messages calls are supported.")
            size = int(self.headers.get("Content-Length", "0"))
            if self.headers.get("Transfer-Encoding") or not 0 < size <= MAX_BODY:
                raise Denied("Request body exceeds the cost policy limit.")
            self.connection.settimeout(100)
            body = json.loads(self.rfile.read(size))
            acquired = gate.active.acquire(blocking=False)
            if not acquired:
                raise Denied("One model request is already running; no parallel spending allowed.")
            call_id = gate.admit(body)
            with gate.upstream.request("/v1/messages", body) as response:
                if response.status != 200:
                    raise Denied("Provider rejected the request; reservation kept and gate stopped for review.")
                usage = None
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream" if body.get("stream") else "application/json")
                self.end_headers()
                started = True
                if body.get("stream"):
                    finished = False
                    final_usage = False
                    read_size = 0
                    while True:
                        line = response.readline(MAX_RESPONSE + 1)
                        if not line:
                            break
                        read_size += len(line)
                        if read_size > MAX_RESPONSE:
                            raise Denied("Stream exceeded policy limit.")
                        self.wfile.write(line)
                        self.wfile.flush()
                        if line.startswith(b"data: "):
                            event = json.loads(line[6:])
                            kind = event.get("type")
                            if kind == "message_start":
                                usage = dict(event["message"].get("usage", {}))
                            elif kind == "message_delta" and usage is not None:
                                usage.update(event.get("usage", {}))
                                final_usage = integer(event.get("usage", {}).get("output_tokens"))
                            elif kind == "message_stop":
                                finished = True
                            elif kind == "error":
                                raise Denied("Provider stream failed; reservation preserved.")
                    if not finished or not final_usage:
                        raise Denied("Incomplete provider stream; reservation preserved.")
                else:
                    data = response.read(MAX_RESPONSE + 1)
                    if len(data) > MAX_RESPONSE:
                        raise Denied("Response exceeded policy limit.")
                    usage = json.loads(data).get("usage")
                    self.wfile.write(data)
                charged = gate.ledger.settle(call_id, usage)
                print(f"[cost-guard] accounted_usd={charged / 1_000_000:.6f} model={body['model']}", flush=True)
        except Exception as exc:
            if call_id:
                gate.ledger.latch("request incomplete or accounting unavailable")
            message = str(exc) if isinstance(exc, Denied) else "Request/accounting failure; no automatic retry."
            print("[cost-guard] blocked: " + message, flush=True)
            if not started:
                with contextlib.suppress(OSError):
                    self.fail(message)
        finally:
            if acquired:
                gate.active.release()


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
    result["HERMES_MAX_ITERATIONS"] = "12"
    result["HERMES_INFERENCE_PROVIDER"] = "anthropic"
    for k in ("LLM_MODEL", "OPENAI_BASE_URL", "HERMES_DUMP_REQUESTS",
              "CONTEXT_COMPRESSION_ENABLED", "CONTEXT_COMPRESSION_THRESHOLD", "CONTEXT_COMPRESSION_MODEL"):
        result.pop(k, None)
    return result


def main():
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise Denied("ANTHROPIC_API_KEY is required; alternate providers are disabled.")
    home = Path(os.environ.get("HERMES_HOME", "/data/.hermes"))
    ledger = Ledger(home / "cost-guard" / "ledger.sqlite3")
    ledger.check_startup()
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
        print("[cost-guard] Startup refused; persistent cost ledger is unavailable.", file=sys.stderr)
        raise SystemExit(1)
