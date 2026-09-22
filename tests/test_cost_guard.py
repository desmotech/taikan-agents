import concurrent.futures
import unittest

from cost_guard_driver import CostGuardDriver
from cost_guard import Denied, child_environment


class CostGuardTests(unittest.TestCase):
    def setUp(self):
        self.driver = CostGuardDriver()
        self.addCleanup(self.driver.close)

    def test_success_reserves_then_settles_and_survives_restart(self):
        status, _ = self.driver.post()
        self.assertEqual(status, 200)
        row = self.driver.rows()[0]
        self.assertGreater(row[1], row[2])
        self.assertEqual(row[2:], (3000, 1))
        self.driver.restart_ledger()
        self.assertEqual(self.driver.rows()[0], row)

    def test_stream_usage_is_accounted(self):
        self.assertEqual(self.driver.post({"stream": True})[0], 200)
        self.assertEqual(self.driver.rows()[0][2:], (3000, 1))

    def test_cache_reads_and_writes_are_counted_conservatively(self):
        self.driver.upstream.usage.update(cache_creation_input_tokens=1000, cache_read_input_tokens=10001)
        self.driver.post()
        self.assertEqual(self.driver.rows()[0][2], 9001)

    def test_output_cap_is_enforced_at_network_boundary(self):
        self.assertEqual(self.driver.post({"max_tokens": 100000})[0], 200)
        self.assertEqual(self.driver.generation_calls()[0]["max_tokens"], 4096)
        self.assertEqual(self.driver.generation_calls()[0]["service_tier"], "standard_only")

    def test_oversized_context_is_rejected_before_generation(self):
        self.driver.upstream.input_tokens = 40001
        self.assertEqual(self.driver.post()[0], 400)
        self.assertEqual(self.driver.generation_calls(), [])

    def test_failed_token_counting_never_generates(self):
        self.driver.upstream.count_status = 429
        self.assertEqual(self.driver.post()[0], 400)
        self.assertEqual(self.driver.generation_calls(), [])

    def test_unknown_model_paid_tools_and_api_routes_are_blocked(self):
        for updates in ({"model": "claude-opus-5"}, {"speed": "fast"},
                        {"tools": [{"type": "web_search_20250305", "name": "web_search"}]},
                        {"service_tier": "priority"}, {"max_tokens": -1}):
            with self.subTest(updates=updates):
                self.assertEqual(self.driver.post(updates)[0], 400)
        self.assertEqual(self.driver.post(path="/v1/messages/batches")[0], 400)
        self.assertEqual(self.driver.post(token="wrong")[0], 400)
        self.assertEqual(self.driver.generation_calls(), [])

    def test_daily_cap_blocks_before_provider_generation(self):
        self.driver.spend(2_000_000)
        self.assertEqual(self.driver.post()[0], 400)
        self.assertEqual(self.driver.generation_calls(), [])
        self.driver.restart_ledger()
        self.assertEqual(self.driver.post()[0], 400)

    def test_total_cap_does_not_reset_on_day_change(self):
        for day in range(1, 6):
            self.driver.spend(2_000_000, day=f"2000-01-{day:02d}")
        self.assertEqual(self.driver.post()[0], 400)
        self.assertEqual(self.driver.generation_calls(), [])

    def test_parallel_reservations_cannot_overspend(self):
        def reserve(_):
            try:
                return self.driver.ledger.reserve("claude-sonnet-5", 1_000_000)
            except Denied:
                return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            accepted = [r for r in pool.map(reserve, range(8)) if r]
        self.assertEqual(len(accepted), 2)

    def test_simultaneous_generation_is_rejected(self):
        self.driver.server.gate.active.acquire()
        try:
            self.assertEqual(self.driver.post()[0], 400)
        finally:
            self.driver.server.gate.active.release()
        self.assertEqual(self.driver.generation_calls(), [])

    def test_incomplete_stream_latches_off_and_keeps_reservation(self):
        self.driver.upstream.complete = False
        self.driver.post({"stream": True})
        self.assertEqual(self.driver.rows()[0][1], self.driver.rows()[0][2])
        self.assertEqual(self.driver.post()[0], 400)
        self.assertEqual(len(self.driver.generation_calls()), 1)
        with self.assertRaises(Denied):
            self.driver.restart_ledger()

    def test_provider_error_or_missing_usage_cannot_trigger_paid_retries(self):
        self.driver.upstream.status = 400
        self.assertEqual(self.driver.post()[0], 400)
        self.assertEqual(self.driver.post()[0], 400)
        self.assertEqual(len(self.driver.generation_calls()), 1)

    def test_missing_usage_keeps_reservation_and_blocks_future_work(self):
        self.driver.upstream.usage = {}
        self.driver.post()
        self.assertEqual(self.driver.post()[0], 400)
        self.assertEqual(len(self.driver.generation_calls()), 1)

    def test_usage_exceeding_reservation_latches_off(self):
        self.driver.upstream.usage["input_tokens"] = 100000
        self.driver.post()
        self.assertEqual(self.driver.post()[0], 400)
        self.assertEqual(len(self.driver.generation_calls()), 1)

    def test_real_key_and_overrides_are_not_inherited_by_hermes(self):
        env = child_environment({"ANTHROPIC_API_KEY": "real-secret", "LLM_MODEL": "claude-opus-5",
                                 "HERMES_MAX_ITERATIONS": "9999"}, "local-token", 12345)
        self.assertNotIn("real-secret", str(env))
        self.assertEqual(env["HERMES_MAX_ITERATIONS"], "12")
        self.assertEqual(env["ANTHROPIC_BASE_URL"], "http://127.0.0.1:12345")
        self.assertNotIn("LLM_MODEL", env)
        with self.assertRaises(Denied):
            child_environment({"OPENROUTER_API_KEY": "alternate-secret"}, "local-token", 12345)

    def test_stream_without_final_output_usage_is_not_refunded(self):
        self.driver.upstream.usage = {"input_tokens": 1000}
        self.driver.post({"stream": True})
        self.assertEqual(self.driver.rows()[0][1], self.driver.rows()[0][2])
        self.assertEqual(self.driver.rows()[0][3], 0)
        self.assertEqual(self.driver.post()[0], 400)

    def test_corrupt_ledger_never_sends_a_generation(self):
        from pathlib import Path
        Path(self.driver.ledger.path).write_bytes(b"invalid sqlite file")
        self.assertEqual(self.driver.post()[0], 400)
        self.assertEqual(self.driver.generation_calls(), [])

    def test_media_is_rejected_before_generation(self):
        status, _ = self.driver.post({"messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "data": "invalid"}}
        ]}]})
        self.assertEqual(status, 400)
        self.assertEqual(self.driver.generation_calls(), [])
