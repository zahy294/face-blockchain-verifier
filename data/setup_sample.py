#!/usr/bin/env python3
"""
setup_sample.py - Automated Sample Dataset Provisioner

Downloads a verified, publicly indexed portrait image to `data/test_face.jpg`
so the pipeline can be tested immediately without manual image sourcing.
"""

import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

# Target destination
DATA_DIR = Path(__file__).resolve().parent
TARGET_FILE = DATA_DIR / "test_face.jpg"

# Curated list of verified, publicly indexed high-resolution portraits (with fallback mirrors)
SAMPLE_URLS = [
    # Wikimedia Commons: Public domain photograph portrait of Alan Turing
    "https://upload.wikimedia.org/wikipedia/commons/a/a1/Alan_Turing_Aged_16.jpg",
    # Wikimedia Commons: Public domain official portrait of Barack Obama (widely indexed across web/search engines)
    "https://upload.wikimedia.org/wikipedia/commons/8/8d/President_Barack_Obama.jpg",
    # GitHub raw fallback mirror for deterministic CI/CD environments
    "https://raw.githubusercontent.com/opencv/opencv/master/samples/data/lena.jpg",
]

HEADERS = {
    "User-Agent": "FaceBlockchainVerifier/1.0 (QA Automated Dataset Provisioner; Python/urllib)"
}


def download_sample_face(target_path: Path = TARGET_FILE) -> Path:
    """
    Downloads a sample portrait image and writes it to target_path.
    Tries multiple candidate URLs with proper headers and validates file integrity.
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("  Face Blockchain Verifier - Sample Data Setup")
    print("=" * 60)
    print(f"[*] Target path: {target_path}")

    last_error = None
    for url in SAMPLE_URLS:
        print(f"[*] Attempting download from: {url} ...")
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as response:
                if response.status != 200:
                    print(f"    [!] Received HTTP status {response.status}, trying next mirror...")
                    continue
                data = response.read()

                # Basic validation: ensure data is non-empty and at least 5 KB
                if len(data) < 5000:
                    print(f"    [!] Downloaded payload too small ({len(data)} bytes), skipping...")
                    continue

                # Validate JPEG/PNG magic bytes
                if not (data.startswith(b"\xff\xd8\xff") or data.startswith(b"\x89PNG")):
                    print("    [!] Data does not match JPEG/PNG magic bytes, skipping...")
                    continue

                with open(target_path, "wb") as f:
                    f.write(data)

                print(f"[+] Successfully downloaded sample portrait ({len(data):,} bytes).")
                print(f"[+] Saved to: {target_path}")
                print("=" * 60)
                return target_path

        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, Exception) as e:
            print(f"    [!] Error downloading from {url}: {e}")
            last_error = e
            continue

    print(f"[X] Failed to download sample image from all mirrors. Last error: {last_error}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    download_sample_face()
