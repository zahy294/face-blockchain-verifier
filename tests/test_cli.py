"""Unit and CLI integration tests for main.py."""

import os
import unittest
from unittest.mock import patch
from pathlib import Path
from click.testing import CliRunner

from main import cli
from src.social_searcher import SearchResult, SocialMatch


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
        # Ensure no key is set in env
        with patch.dict(os.environ, {"SERPAPI_KEY": ""}):
            with patch("src.social_searcher.load_dotenv"):
                result = self.runner.invoke(cli, ["run", "--image", self.portrait_path])
                self.assertEqual(result.exit_code, 1)
                self.assertIn("ALERT: AUTHENTICATION ERROR", result.output)

    def test_run_and_verify_lifecycle(self):
        import time
        unique_id = int(time.time() * 1000)
        sample_post_url = f"https://x.com/verified_author/status/{unique_id}"
        sample_platform = "X/Twitter"
        sample_match = SocialMatch(
            platform=sample_platform,
            post_url=sample_post_url,
            title="Official Verified Portrait",
            source_image_url="https://pbs.twimg.com/media/sample.jpg",
        )
        mocked_search_result = SearchResult(
            success=True,
            message="Search completed successfully. Found 1 match.",
            matches=[sample_match],
        )

        with patch("main.SocialImageSearcher.search", return_value=mocked_search_result):
            # 1. Run pipeline
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
                    sample_post_url,
                    "--platform",
                    sample_platform,
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
                    sample_platform,
                ],
            )
            self.assertEqual(verify_invalid.exit_code, 0)
            self.assertIn("TAMPER ALERT / RECORD NOT FOUND", verify_invalid.output)


if __name__ == "__main__":
    unittest.main()
