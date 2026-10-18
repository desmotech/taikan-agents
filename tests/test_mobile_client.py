import contextlib
import importlib.util
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("mobile_client", ROOT / "scripts/mobile-client.py")
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)

BUILD_RUNS = "/workflows/eas-build.yml/runs?event=workflow_dispatch&per_page=20"
OTA_RUNS = "/workflows/eas-update.yml/runs?event=workflow_dispatch&per_page=20"
DISPATCHED = {"workflow_run_id": 42, "run_url": "https://api.github.invalid/42", "html_url": "https://github.invalid/42"}


class FakeGitHub:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def urlopen(self, call, timeout):
        path = call.full_url.removeprefix(client.API)
        body = json.loads(call.data) if call.data else None
        self.calls.append((call.get_method(), path, body))
        response = self.responses[(call.get_method(), path)]
        return io.BytesIO(b"" if response is None else json.dumps(response).encode())

    def posts(self):
        return [(path, body) for method, path, body in self.calls if method == "POST"]


class FakeFastlane:
    """Stands in for subprocess.run; records each lane invocation."""

    def __init__(self, returncode=0, stdout="", stderr="", raises=None):
        self.returncode, self.stdout, self.stderr, self.raises = returncode, stdout, stderr, raises
        self.calls = []

    def run(self, argv, cwd, env, timeout, **kwargs):
        self.calls.append({"argv": argv, "env": env})
        if self.raises:
            raise self.raises
        return client.subprocess.CompletedProcess(argv, self.returncode, self.stdout, self.stderr)


def run_client(fake, *argv, fastlane=None):
    fastlane = fastlane or FakeFastlane()
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(client.urllib.request, "urlopen", fake.urlopen), \
            mock.patch.object(client.subprocess, "run", fastlane.run), \
            mock.patch.dict(os.environ, {"TAIKAN_MOBILE_GITHUB_TOKEN": "fake-token"}), \
            mock.patch.object(sys, "argv", ["mobile-client.py", *argv]), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            client.main()
            code = 0
        except SystemExit as exit:
            code = exit.code
        except RuntimeError as error:
            print(error, file=sys.stderr)
            code = 1
    return code, out.getvalue(), err.getvalue()


class MobileClientTests(unittest.TestCase):
    def test_build_is_production_from_main_and_auto_submitted(self):
        fake = FakeGitHub({("GET", BUILD_RUNS): {"workflow_runs": []},
                           ("POST", "/workflows/eas-build.yml/dispatches"): DISPATCHED})
        code, out, _ = run_client(fake, "build", "--platform", "ios")
        self.assertEqual(code, 0)
        self.assertEqual(fake.posts(), [("/workflows/eas-build.yml/dispatches", {
            "ref": "main", "return_run_details": True,
            "inputs": {"profile": "production", "platform": "ios", "auto_submit": "true"},
        })])
        self.assertEqual(json.loads(out)["html_url"], "https://github.invalid/42")

    def test_active_dispatched_run_blocks_a_second_dispatch(self):
        busy = {"status": "in_progress", "html_url": "https://github.invalid/41"}
        fake = FakeGitHub({("GET", BUILD_RUNS): {"workflow_runs": [busy]}})
        code, _, err = run_client(fake, "build", "--platform", "all")
        self.assertEqual(code, 1)
        self.assertIn("https://github.invalid/41", err)
        self.assertEqual(fake.posts(), [])

    def test_ota_environment_always_matches_branch(self):
        for branch in ("production", "preview"):
            fake = FakeGitHub({("GET", OTA_RUNS): {"workflow_runs": [{"status": "completed"}]},
                               ("POST", "/workflows/eas-update.yml/dispatches"): DISPATCHED})
            with self.subTest(branch=branch):
                code, _, _ = run_client(fake, "ota", "--branch", branch, "--message", "Fix RTL flicker")
                self.assertEqual(code, 0)
                self.assertEqual(fake.posts()[0][1]["inputs"],
                                 {"branch": branch, "environment": branch, "message": "Fix RTL flicker"})

    def test_ota_without_message_lets_the_workflow_use_the_commit_subject(self):
        fake = FakeGitHub({("GET", OTA_RUNS): {"workflow_runs": []},
                           ("POST", "/workflows/eas-update.yml/dispatches"): DISPATCHED})
        run_client(fake, "ota", "--branch", "production")
        self.assertNotIn("message", fake.posts()[0][1]["inputs"])

    def test_multiline_or_oversized_message_is_rejected_before_any_request(self):
        for text in ("line one\nline two", "x" * 201, "   "):
            fake = FakeGitHub({})
            with self.subTest(text=text[:20]):
                code, _, _ = run_client(fake, "ota", "--branch", "production", "--message", text)
                self.assertEqual(code, 2)
                self.assertEqual(fake.calls, [])

    def test_run_detail_refuses_runs_from_other_workflows(self):
        fake = FakeGitHub({("GET", "/runs/7"): {"path": ".github/workflows/brand-build.yml"}})
        code, _, err = run_client(fake, "run", "7")
        self.assertEqual(code, 1)
        self.assertIn("does not belong", err)
        self.assertEqual(len(fake.calls), 1)

    def test_ios_release_sends_default_and_locale_notes_to_the_release_lane(self):
        fastlane = FakeFastlane(stdout='noise\nTAIKAN_STORE_RESULT {"submitted": true}\n')
        code, out, _ = run_client(FakeGitHub({}), "ios-release", "--version", "1.2.0", "--build", "18",
                                  "--notes", "Faster booking", "--locale-notes", "he=הזמנה מהירה יותר",
                                  fastlane=fastlane)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"submitted": True})
        call, = fastlane.calls
        self.assertEqual(call["argv"], ["fastlane", "ios", "release"])
        self.assertEqual(call["env"]["TAIKAN_STORE_VERSION"], "1.2.0")
        self.assertEqual(call["env"]["TAIKAN_STORE_BUILD"], "18")
        self.assertEqual(json.loads(call["env"]["TAIKAN_STORE_NOTES"]),
                         {"default": "Faster booking", "he": "הזמנה מהירה יותר"})

    def test_android_release_names_only_the_version_code(self):
        fastlane = FakeFastlane(stdout='TAIKAN_STORE_RESULT {"promoted": true}\n')
        code, _, _ = run_client(FakeGitHub({}), "android-release", "--version-code", "18", fastlane=fastlane)
        self.assertEqual(code, 0)
        self.assertEqual(fastlane.calls[0]["argv"], ["fastlane", "android", "release"])
        self.assertEqual(fastlane.calls[0]["env"]["TAIKAN_STORE_VERSION_CODE"], "18")

    def test_lane_failure_reports_fastlane_errors_not_a_result(self):
        fastlane = FakeFastlane(returncode=1, stdout="step\n[!] Version 1.1.0 is already in review\n")
        code, out, err = run_client(FakeGitHub({}), "store-status", "--platform", "ios", fastlane=fastlane)
        self.assertEqual((code, out), (1, ""))
        self.assertIn("Version 1.1.0 is already in review", err)

    def test_lane_timeout_is_reported_as_unknown_effect(self):
        fastlane = FakeFastlane(raises=client.subprocess.TimeoutExpired("fastlane", 280))
        code, _, err = run_client(FakeGitHub({}), "android-release", "--version-code", "18", fastlane=fastlane)
        self.assertEqual(code, 1)
        self.assertIn("effect is unknown", err)

    def test_invalid_release_inputs_never_reach_fastlane(self):
        cases = [
            ("ios-release", "--version", "1.2", "--build", "18", "--notes", "x"),
            ("ios-release", "--version", "1.2.0", "--build", "0", "--notes", "x"),
            ("ios-release", "--version", "1.2.0", "--build", "18", "--notes", "x", "--locale-notes", "Hebrew=x"),
            ("ios-release", "--version", "1.2.0", "--build", "18", "--notes", "x" * 4001),
            ("android-release", "--version-code", "-3"),
        ]
        for argv in cases:
            fastlane = FakeFastlane()
            with self.subTest(argv=argv[:6]):
                code, _, _ = run_client(FakeGitHub({}), *argv, fastlane=fastlane)
                self.assertEqual(code, 2)
                self.assertEqual(fastlane.calls, [])

    def test_204_dispatch_reports_success_without_a_run_link(self):
        fake = FakeGitHub({("GET", OTA_RUNS): {"workflow_runs": []},
                           ("POST", "/workflows/eas-update.yml/dispatches"): None})
        code, out, _ = run_client(fake, "ota", "--branch", "production")
        self.assertEqual(code, 0)
        self.assertIsNone(json.loads(out)["run_id"])
        self.assertEqual(len(fake.posts()), 1)


if __name__ == "__main__":
    unittest.main()
