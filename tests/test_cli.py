"""Unit and CLI integration tests for main.py."""

import os
import unittest
from pathlib import Path
from click.testing import CliRunner

from main import cli


class TestMainCLI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = CliRunner()
        cls.portrait_path = "data/test_images/portrait.png"
        cls.blank_path = "data/test_images/blank.png"
        cls.nonexistent_path = "data/test_images/does_not_exist.png"

    def test_cli_help(self):
        result = self.runner.invoke(cli, ["--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Decentralized Facial Identity", result.output)
        self.assertIn("run", result.output)
        self.assertIn("verify", result.output)

    def test_run_missing_image_file(self):
        result = self.runner.invoke(cli, ["run", "--image", self.nonexistent_path])
        self.assertEqual(result.exit_code, 1)
        self.assertIn("ALERT: INVALID IMAGE INPUT", result.output)

    def test_run_no_face_detected(self):
        result = self.runner.invoke(cli, ["run", "--image", self.blank_path])
        self.assertEqual(result.exit_code, 1)
        self.assertIn("ALERT: NO FACE DETECTED", result.output)

    def test_run_missing_api_key_alert(self):
        # Ensure no mock or live key is set
        old_mock = os.environ.pop("SERPAPI_MOCK", None)
        old_key = os.environ.pop("SERPAPI_KEY", None)
        try:
            result = self.runner.invoke(cli, ["run", "--image", self.portrait_path])
            self.assertEqual(result.exit_code, 1)
            self.assertIn("ALERT: AUTHENTICATION ERROR", result.output)
        finally:
            if old_mock:
                os.environ["SERPAPI_MOCK"] = old_mock
            if old_key:
                os.environ["SERPAPI_KEY"] = old_key

    def test_run_and_verify_lifecycle(self):
        # 1. Run pipeline in mock mode
        os.environ["SERPAPI_MOCK"] = "1"
        try:
            run_res = self.runner.invoke(cli, ["run", "--image", self.portrait_path])
            self.assertEqual(run_res.exit_code, 0)
            self.assertIn("PIPELINE INITIATION", run_res.output)
            self.assertIn("Biometric Face Detection", run_res.output)
            self.assertIn("Discovered Social Post Details", run_res.output)
            self.assertIn("32-BYTE KECCAK-256 FINGERPRINT", run_res.output)
            self.assertIn("NOTARIZATION SUCCESSFUL", run_res.output)

            # 2. Verify with correct parameters -> INTEGRITY VERIFIED
            verify_valid = self.runner.invoke(
                cli,
                [
                    "verify",
                    "--image",
                    self.portrait_path,
                    "--post-url",
                    "https://x.com/vitalikbuterin/status/1789402948201",
                    "--platform",
                    "X/Twitter",
                ],
            )
            self.assertEqual(verify_valid.exit_code, 0)
            self.assertIn("INTEGRITY VERIFIED", verify_valid.output)

            # 3. Verify with tampered parameters -> TAMPER ALERT
            verify_invalid = self.runner.invoke(
                cli,
                [
                    "verify",
                    "--image",
                    self.portrait_path,
                    "--post-url",
                    "https://x.com/fake_attacker/status/11111",
                    "--platform",
                    "X/Twitter",
                ],
            )
            self.assertEqual(verify_invalid.exit_code, 0)
            self.assertIn("TAMPER ALERT / RECORD NOT FOUND", verify_invalid.output)
        finally:
            os.environ.pop("SERPAPI_MOCK", None)


if __name__ == "__main__":
    unittest.main()
