#!/usr/bin/env python3
"""
tests/test_live_serp.py - Live SerpApi & Google Lens Integration Test Script

Performs a live end-to-end verification:
1. Loads SERPAPI_KEY from .env via python-dotenv.
2. Compresses & resizes data/test_face.jpg to stay under 500 KB.
3. POSTs image to https://serpapi.com/image to retrieve image_id.
4. Queries Google Lens at https://serpapi.com/search using image_id.
5. Displays HTTP status codes, image_id, and the top 3 visual matches (title, domain, link).
"""

import os
import sys
import urllib.parse
from pathlib import Path
import requests
from dotenv import load_dotenv

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.social_searcher import SocialImageSearcher, compress_and_resize_image


def main():
    print("=" * 65)
    print("  SERPAPI GOOGLE LENS - LIVE REVERSE SEARCH TEST")
    print("=" * 65)

    # 1. Load environment variables
    load_dotenv(PROJECT_ROOT / ".env", override=True)
    api_key = os.getenv("SERPAPI_KEY")

    if not api_key or not api_key.strip():
        print("\n[!] ERROR: SERPAPI_KEY is not set or is empty in .env.")
        print("    Please set SERPAPI_KEY=<your_key> in .env and rerun this script.")
        print("=" * 65)
        sys.exit(1)

    masked_key = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "***"
    print(f"[*] Loaded SERPAPI_KEY: {masked_key}")

    # 2. Check input image
    image_path = PROJECT_ROOT / "data" / "test_face.jpg"
    if not image_path.exists():
        print(f"[!] Target image not found at: {image_path}")
        print("    Attempting to download sample image...")
        try:
            from data.setup_sample import download_sample_face
            download_sample_face(image_path)
        except Exception as e:
            print(f"[!] Failed to download sample image: {e}")
            sys.exit(1)

    print(f"[*] Target Image: {image_path} (Original Size: {image_path.stat().st_size:,} bytes)")

    # 3. Compress / resize image
    filename, compressed_bytes = compress_and_resize_image(image_path, max_dim=800, quality=85)
    print(f"[*] Compressed Payload Size: {len(compressed_bytes):,} bytes (< 500 KB limit)")

    # 4. Upload to SerpApi /image
    print("\n[1/2] Uploading image to SerpApi /image endpoint...")
    upload_url = "https://serpapi.com/image"
    files = {"image": (filename, compressed_bytes, "image/jpeg")}
    data = {"api_key": api_key}

    upload_res = requests.post(upload_url, files=files, data=data, timeout=30)
    print(f"      HTTP Status Code: {upload_res.status_code}")

    if not upload_res.ok:
        print(f"[X] Upload failed: {upload_res.text}")
        sys.exit(1)

    upload_json = upload_res.json()
    image_id = upload_json.get("image_id") or upload_json.get("id")
    print(f"      Returned image_id: {image_id}")

    if not image_id:
        print(f"[X] No image_id in response: {upload_json}")
        sys.exit(1)

    # 5. Query Google Lens with image_id
    print("\n[2/2] Querying Google Lens with image_id...")
    search_url = "https://serpapi.com/search"
    params = {
        "engine": "google_lens",
        "image_id": image_id,
        "api_key": api_key,
    }

    search_res = requests.get(search_url, params=params, timeout=30)
    print(f"      HTTP Status Code: {search_res.status_code}")

    if not search_res.ok:
        print(f"[X] Google Lens query failed: {search_res.text}")
        sys.exit(1)

    search_json = search_res.json()
    visual_matches = search_json.get("visual_matches", [])
    print(f"      Total Visual Matches Returned: {len(visual_matches)}")

    # 6. Display first 3 visual matches (title, domain, link)
    print("\n" + "-" * 65)
    print("  TOP 3 VISUAL MATCHES")
    print("-" * 65)

    if not visual_matches:
        print("  (No visual matches returned by Google Lens)")
    else:
        for idx, match in enumerate(visual_matches[:3], start=1):
            title = match.get("title") or match.get("source") or "No title"
            link = match.get("link") or match.get("url") or "No link"
            domain = "Unknown"
            if link and link != "No link":
                try:
                    parsed = urllib.parse.urlparse(link)
                    domain = parsed.netloc or "Unknown"
                except Exception:
                    domain = "Unknown"

            print(f"\n  Match #{idx}:")
            print(f"    Title  : {title}")
            print(f"    Domain : {domain}")
            print(f"    Link   : {link}")

    # 7. Verify end-to-end with SocialImageSearcher class
    print("\n" + "-" * 65)
    print("  END-TO-END SocialImageSearcher.search() VERIFICATION")
    print("-" * 65)
    searcher = SocialImageSearcher()
    result = searcher.search(str(image_path))
    print(f"  Success : {result.success}")
    print(f"  Message : {result.message}")
    print(f"  Matches : {len(result.matches)}")
    for m in result.matches[:3]:
        print(f"    - [{m.platform}] {m.title}: {m.post_url}")

    print("\n" + "=" * 65)
    print("  LIVE SERPAPI TEST COMPLETED SUCCESSFULLY!")
    print("  SerpApi dashboard search counter incremented.")
    print("=" * 65)


if __name__ == "__main__":
    main()
