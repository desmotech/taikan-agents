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
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from cost_guard import Gate, Handler, Ledger, LocalServer


class FakeUpstream:
    def __init__(self):
        self.requests = []
        self.input_tokens = 1000
        self.count_status = 200
        self.status = 200
        self.usage = {"input_tokens": 1000, "output_tokens": 100}
        self.complete = True

    @contextlib.contextmanager
    def request(self, path, body):
        self.requests.append((path, copy.deepcopy(body)))
        if path.endswith("count_tokens"):
            data = json.dumps({"input_tokens": self.input_tokens}).encode()
            status = self.count_status
        elif body.get("stream"):
            events = [
                {"type": "message_start", "message": {"id": "msg_test", "type": "message", "role": "assistant", "model": body["model"], "content": [], "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 1000, "output_tokens": 0}}},
                {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
                {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "test"}},
                {"type": "content_block_stop", "index": 0},
                {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": self.usage},
            ]
            if self.complete:
                events.append({"type": "message_stop"})
            data = b"".join(b"event: " + e["type"].encode() + b"\ndata: " + json.dumps(e).encode() + b"\n\n" for e in events)
            status = self.status
        else:
            data = json.dumps({"id": "msg_test", "type": "message", "role": "assistant", "model": body["model"], "stop_reason": "end_turn", "stop_sequence": None, "content": [{"type": "text", "text": "test"}], "usage": self.usage}).encode()
            status = self.status
        response = io.BytesIO(data)
        response.status = status
        yield response


class CostGuardDriver:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cost-guard-test-")
        self.ledger = Ledger(Path(self.temp.name) / "ledger.sqlite3")
        self.upstream = FakeUpstream()
        self.server = LocalServer(("127.0.0.1", 0), Handler)
        self.server.token = "local-test-token"
        self.server.gate = Gate(self.ledger, self.upstream)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def post(self, updates=None, *, token=None, path="/v1/messages"):
        body = {"model": "claude-sonnet-5", "max_tokens": 4096,
                "messages": [{"role": "user", "content": "hello"}]}
        body.update(updates or {})
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            conn.request("POST", path, json.dumps(body), {
                "Content-Type": "application/json", "x-api-key": token or self.server.token,
            })
            response = conn.getresponse()
            return response.status, response.read().decode()
        finally:
            conn.close()

    def generation_calls(self):
        return [b for p, b in self.upstream.requests if p == "/v1/messages"]

    def rows(self):
        with self.ledger.connect() as db:
            return db.execute("SELECT day,reserved,charged,complete FROM calls").fetchall()

    def spend(self, amount, day=None):
        call_id = self.ledger.reserve("claude-sonnet-5", amount, day=day)
        with self.ledger.connect() as db:
            db.execute("UPDATE calls SET complete=1 WHERE id=?", (call_id,))

    def restart_ledger(self):
        self.ledger = Ledger(self.ledger.path)
        self.server.gate.ledger = self.ledger
        self.ledger.check_startup()
