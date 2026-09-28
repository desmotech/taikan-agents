from pathlib import Path
import sys
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from runtime_policy import errors


def load(name):
    return yaml.safe_load((ROOT / "config" / f"{name}.yaml").read_text())


class RuntimePolicyTests(unittest.TestCase):
    def test_limits_above_eng_maxima_are_rejected(self):
        for path, value in ((("agent", "max_turns"), 41), (("model", "context_length"), 120_001),
                            (("model", "max_tokens"), 16_385), (("compression", "threshold_tokens"), 80_001),
                            (("agent", "run_budget_seconds"), 1801)):
            config = load("eng")
            config[path[0]][path[1]] = value
            with self.subTest(path=path):
                self.assertTrue(any(".".join(path) in p for p in errors(config)))

    def test_opus_side_calls_must_run_on_haiku(self):
        config = load("eng")
        del config["auxiliary"]["title_generation"]
        self.assertIn("auxiliary.title_generation must use provider anthropic, model claude-haiku-4-5",
                      errors(config))

    def test_background_review_cannot_be_enabled(self):
        config = load("eng")
        config["auxiliary"]["background_review"]["enabled"] = True
        self.assertIn("auxiliary.background_review.enabled must be False", errors(config))


if __name__ == "__main__":
    unittest.main()
