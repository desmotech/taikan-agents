"""Exercise the actual HTTP boundary with a fake provider; never uses a key."""

import contextlib
import copy
import http.client
import io
import json
from pathlib import Path
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from cost_guard import Gate, Handler, Ledger, LocalServer


class FakeUpstream:
    def __init__(self):
        self.requests = []
        self.status = 200
        self.headers = [("content-type", "application/json")]
        self.usage = {"input_tokens": 1000, "output_tokens": 100}
        self.complete = True
        self.error = None
        # When set, each request waits for release so tests can hold calls in flight.
        self.hold = False
        self.release = threading.Event()
        self.lock = threading.Lock()

    @contextlib.contextmanager
    def request(self, path, body):
        with self.lock:
            self.requests.append((path, copy.deepcopy(body)))
        if self.error:
            raise self.error
        if self.hold:
            self.release.wait(5)
        headers = list(self.headers)
        if self.status != 200:
            data = json.dumps({"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}).encode()
        elif body.get("stream"):
            events = [
                {"type": "message_start", "message": {"id": "msg_test", "type": "message", "role": "assistant", "model": body["model"], "content": [], "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 1000, "output_tokens": 1}}},
                {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
                {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "test"}},
                {"type": "content_block_stop", "index": 0},
            ]
            if self.complete:
                events += [{"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": self.usage},
                           {"type": "message_stop"}]
            data = b"".join(b"event: " + e["type"].encode() + b"\ndata: " + json.dumps(e).encode() + b"\n\n" for e in events)
            headers = [("content-type", "text/event-stream")]
        else:
            data = json.dumps({"id": "msg_test", "type": "message", "role": "assistant", "model": body["model"], "stop_reason": "end_turn", "stop_sequence": None, "content": [{"type": "text", "text": "test"}], "usage": self.usage}).encode()
        response = io.BytesIO(data)
        response.status = self.status
        response.getheaders = lambda: headers
        yield response


class CostGuardDriver:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cost-guard-test-")
        self.ledger = Ledger(Path(self.temp.name) / "usage.sqlite3")
        self.upstream = FakeUpstream()
        self.server = LocalServer(("127.0.0.1", 0), Handler)
        self.server.token = "local-test-token"
        self.server.gate = Gate(self.ledger, self.upstream)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.upstream.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def post(self, updates=None, *, token=None, path="/v1/messages"):
        """Returns (status, body text, headers dict)."""
        body = {"model": "claude-sonnet-5", "max_tokens": 4096,
                "messages": [{"role": "user", "content": "hello"}]}
        body.update(updates or {})
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        try:
            conn.request("POST", path, json.dumps(body), {
                "Content-Type": "application/json", "x-api-key": token or self.server.token,
            })
            response = conn.getresponse()
            return response.status, response.read().decode(), {k.lower(): v for k, v in response.getheaders()}
        finally:
            conn.close()

    def generation_calls(self):
        return [b for p, b in self.upstream.requests if p == "/v1/messages"]

    def get(self, path="/v1/models", *, token=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        try:
            conn.request("GET", path, headers={"x-api-key": self.server.token if token is None else token})
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def rows(self):
        with self.ledger.connect() as db:
            return db.execute("SELECT model, usd_micro FROM calls ORDER BY id").fetchall()
