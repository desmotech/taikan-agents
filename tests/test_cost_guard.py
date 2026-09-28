import concurrent.futures
import time
import unittest
from pathlib import Path

from cost_guard_driver import CostGuardDriver
from cost_guard import Denied, child_environment


class CostGuardTests(unittest.TestCase):
    def setUp(self):
        self.driver = CostGuardDriver()
        self.addCleanup(self.driver.close)

    def test_completed_call_is_relayed_and_accounted(self):
        status, body, _ = self.driver.post()
        self.assertEqual(status, 200)
        self.assertIn('"text": "test"', body)
        self.assertEqual(self.driver.rows(), [("claude-sonnet-5", 3000)])

    def test_stream_usage_is_accounted(self):
        status, body, headers = self.driver.post({"stream": True})
        self.assertEqual(status, 200)
        self.assertIn("message_stop", body)
        self.assertEqual(headers["content-type"], "text/event-stream")
        self.assertEqual(self.driver.rows(), [("claude-sonnet-5", 3000)])

    def test_opus_uses_reviewed_rates_including_cache(self):
        self.driver.upstream.usage.update(cache_creation_input_tokens=1000, cache_read_input_tokens=10001)
        self.assertEqual(self.driver.post({"model": "claude-opus-5"})[0], 200)
        # 1000*5 input + 100*25 output + 1000*5*2 cache write + ceil(10001*5/10) cache read
        self.assertEqual(self.driver.rows(), [("claude-opus-5", 22501)])

    def test_output_is_clamped_and_standard_tier_forced(self):
        self.assertEqual(self.driver.post({"max_tokens": 100000})[0], 200)
        self.assertEqual(self.driver.generation_calls()[0]["max_tokens"], 16384)
        self.assertEqual(self.driver.generation_calls()[0]["service_tier"], "standard_only")

    def test_unknown_model_paid_tools_and_api_routes_are_blocked(self):
        for updates in ({"model": "unreviewed-model"}, {"speed": "fast"},
                        {"tools": [{"type": "web_search_20250305", "name": "web_search"}]},
                        {"service_tier": "priority"}, {"max_tokens": -1}):
            with self.subTest(updates=updates):
                self.assertEqual(self.driver.post(updates)[0], 400)
        self.assertEqual(self.driver.post(path="/v1/messages/batches")[0], 400)
        self.assertEqual(self.driver.post(token="wrong")[0], 400)
        self.assertEqual(self.driver.generation_calls(), [])

    def test_provider_overload_is_relayed_for_retry_and_does_not_block_later_calls(self):
        self.driver.upstream.status = 529
        self.driver.upstream.headers = [("content-type", "application/json"), ("retry-after", "3"),
                                        ("x-should-retry", "true")]
        status, body, headers = self.driver.post()
        self.assertEqual(status, 529)
        self.assertIn("overloaded_error", body)
        self.assertEqual((headers["retry-after"], headers["x-should-retry"]), ("3", "true"))
        self.assertEqual(self.driver.rows(), [])
        self.driver.upstream.status = 200
        self.assertEqual(self.driver.post()[0], 200)
        self.assertEqual(self.driver.rows(), [("claude-sonnet-5", 3000)])

    def test_transport_failure_is_retryable_and_does_not_block_later_calls(self):
        self.driver.upstream.error = ConnectionResetError()
        status, body, _ = self.driver.post()
        self.assertEqual(status, 502)
        self.assertIn("api_error", body)
        self.driver.upstream.error = None
        self.assertEqual(self.driver.post()[0], 200)

    def test_interrupted_stream_records_best_known_usage_and_keeps_serving(self):
        self.driver.upstream.complete = False
        self.assertEqual(self.driver.post({"stream": True})[0], 200)
        # message_start usage only: 1000 input + 1 output on Sonnet 5.
        self.assertEqual(self.driver.rows(), [("claude-sonnet-5", 2010)])
        self.driver.upstream.complete = True
        self.assertEqual(self.driver.post()[0], 200)

    def test_concurrent_calls_are_all_served(self):
        self.driver.upstream.hold = True
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(self.driver.post) for _ in range(3)]
            deadline = time.monotonic() + 5
            while len(self.driver.generation_calls()) < 3 and time.monotonic() < deadline:
                time.sleep(0.01)
            in_flight = len(self.driver.generation_calls())
            self.driver.upstream.release.set()
            statuses = [f.result()[0] for f in futures]
        self.assertEqual(in_flight, 3)
        self.assertEqual(statuses, [200, 200, 200])
        self.assertEqual(len(self.driver.rows()), 3)

    def test_images_are_forwarded(self):
        status, _, _ = self.driver.post({"messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "iVBORw0KGgo="}}
        ]}]})
        self.assertEqual(status, 200)
        self.assertEqual(len(self.driver.generation_calls()), 1)

    def test_broken_ledger_does_not_stop_the_agent(self):
        Path(self.driver.ledger.path).write_bytes(b"invalid sqlite file")
        self.assertEqual(self.driver.post()[0], 200)

    def test_real_key_and_overrides_are_not_inherited_by_hermes(self):
        env = child_environment({"ANTHROPIC_API_KEY": "real-secret", "LLM_MODEL": "claude-opus-5",
                                 "HERMES_MAX_ITERATIONS": "9999"}, "local-token", 12345)
        self.assertNotIn("real-secret", str(env))
        self.assertNotIn("HERMES_MAX_ITERATIONS", env)
        self.assertEqual(env["ANTHROPIC_BASE_URL"], "http://127.0.0.1:12345")
        self.assertNotIn("LLM_MODEL", env)
        with self.assertRaises(Denied):
            child_environment({"OPENROUTER_API_KEY": "alternate-secret"}, "local-token", 12345)


if __name__ == "__main__":
    unittest.main()
