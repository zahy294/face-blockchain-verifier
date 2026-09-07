import json
import logging
import os
import urllib.parse
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional, Union

import requests
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from web3 import Web3

# Setup logger
logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------
class RateLimitError(Exception):
    """Raised when SerpApi returns HTTP 429 Too Many Requests."""
    pass


class SerpApiError(Exception):
    """Raised when SerpApi returns an unexpected error response."""
    pass


# ---------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------
class SocialMatch(BaseModel):
    """Represents a matching social media post."""
    platform: str
    post_url: str
    title: str
    source_image_url: Optional[str] = None


class SearchResult(BaseModel):
    """Encapsulates the result of a social media image search."""
    success: bool
    message: str
    matches: List[SocialMatch] = Field(default_factory=list)


# ---------------------------------------------------------
# Standalone Helper: compute_canonical_hash
# ---------------------------------------------------------
def compute_canonical_hash(face_hash: str, post_url: str, platform: str) -> bytes:
    """
    Builds a deterministic JSON object (alphabetically sorted keys, no whitespace),
    computes its Keccak-256 hash using web3.Web3.keccak(text=...), and returns raw 32 bytes.

    :param face_hash: Fingerprint/hash of the detected face.
    :param post_url: Canonical URL of the social media post.
    :param platform: Name of the identified social media platform.
    :return: Raw 32 bytes representing the Keccak-256 digest.
    """
    payload = {
        "face_hash": str(face_hash),
        "platform": str(platform),
        "post_url": str(post_url),
    }
    # Deterministic JSON representation: keys sorted alphabetically, no extra whitespace
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    keccak_hexbytes = Web3.keccak(text=canonical_json)
    return bytes(keccak_hexbytes)


# ---------------------------------------------------------
# Social Image Searcher
# ---------------------------------------------------------
class SocialImageSearcher:
    """
    Uploads cropped facial images to SerpApi's Google Lens endpoint and isolates
    matching public social media posts across configured platforms.
    """

    SERPAPI_IMAGE_URL = "https://serpapi.com/image"
    SERPAPI_SEARCH_URL = "https://serpapi.com/search"

    DEFAULT_PLATFORMS: Dict[str, str] = {
        "x.com": "X/Twitter",
        "twitter.com": "X/Twitter",
        "instagram.com": "Instagram",
        "linkedin.com": "LinkedIn",
        "reddit.com": "Reddit",
        "facebook.com": "Facebook",
        "youtube.com": "YouTube",
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        platform_mappings: Optional[Dict[str, str]] = None,
        timeout: int = 30,
    ) -> None:
        self.api_key = api_key or os.getenv("SERPAPI_KEY")
        self.platform_mappings = platform_mappings or self.DEFAULT_PLATFORMS
        self.timeout = timeout
        self.session = requests.Session()

    def _get_api_key(self) -> str:
        key = self.api_key or os.getenv("SERPAPI_KEY")
        if not key:
            raise ValueError(
                "SERPAPI_KEY is not configured. Set SERPAPI_KEY in .env or provide it to SocialImageSearcher."
            )
        return key

    def _match_platform(self, url: str) -> Optional[str]:
        """
        Extracts host/domain from post URL and matches it against configured target platforms.
        """
        if not url:
            return None
        try:
            parsed = urllib.parse.urlparse(url)
            netloc = parsed.netloc.lower()
            if ":" in netloc:
                netloc = netloc.split(":")[0]

            for domain, platform_name in self.platform_mappings.items():
                if netloc == domain or netloc.endswith("." + domain):
                    return platform_name
        except Exception as e:
            logger.debug(f"Failed to parse URL netloc for {url}: {e}")
        return None

    @retry(
        retry=retry_if_exception_type(RateLimitError),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def upload_image(self, image_input: Union[str, Path, bytes, BinaryIO]) -> str:
        """
        Uploads local cropped image to SerpApi's /image endpoint to obtain an image_id.
        Applies exponential backoff on HTTP 429 rate limits using tenacity.

        :param image_input: Local file path, raw image bytes, or binary stream.
        :return: Extracted image_id string.
        """
        api_key = self._get_api_key()

        if isinstance(image_input, (str, Path)):
            path = Path(image_input)
            if not path.is_file():
                raise FileNotFoundError(f"Image file not found: {path}")
            with open(path, "rb") as f:
                image_bytes = f.read()
            filename = path.name
        elif isinstance(image_input, bytes):
            image_bytes = image_input
            filename = "cropped_face.jpg"
        elif hasattr(image_input, "read"):
            image_bytes = image_input.read()
            filename = getattr(image_input, "name", "cropped_face.jpg")
        else:
            raise TypeError("image_input must be a file path, bytes, or file-like binary stream.")

        files = {"image": (filename, image_bytes, "image/jpeg")}
        data = {"api_key": api_key}

        response = self.session.post(
            self.SERPAPI_IMAGE_URL,
            data=data,
            files=files,
            timeout=self.timeout,
        )

        if response.status_code == 429:
            logger.warning("SerpApi /image returned HTTP 429 Too Many Requests. Retrying with exponential backoff...")
            raise RateLimitError("SerpApi /image rate limit reached (HTTP 429).")

        if not response.ok:
            raise SerpApiError(
                f"SerpApi image upload failed with status {response.status_code}: {response.text}"
            )

        resp_json = response.json()
        image_id = resp_json.get("image_id") or resp_json.get("id")
        if not image_id:
            raise SerpApiError(f"No image_id returned in SerpApi upload response: {resp_json}")

        return str(image_id)

    @retry(
        retry=retry_if_exception_type(RateLimitError),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def query_google_lens(self, image_id: str) -> Dict[str, Any]:
        """
        Queries SerpApi's Google Lens endpoint using the provided image_id.
        Applies exponential backoff on HTTP 429 rate limits using tenacity.

        :param image_id: The image_id obtained from the SerpApi /image endpoint.
        :return: Raw JSON response dictionary from SerpApi.
        """
        api_key = self._get_api_key()
        params = {
            "engine": "google_lens",
            "image_id": image_id,
            "api_key": api_key,
        }

        response = self.session.get(
            self.SERPAPI_SEARCH_URL,
            params=params,
            timeout=self.timeout,
        )

        if response.status_code == 429:
            logger.warning("SerpApi /search returned HTTP 429 Too Many Requests. Retrying with exponential backoff...")
            raise RateLimitError("SerpApi /search rate limit reached (HTTP 429).")

        if not response.ok:
            raise SerpApiError(
                f"SerpApi Google Lens query failed with status {response.status_code}: {response.text}"
            )

        return response.json()

    def parse_visual_matches(self, lens_data: Dict[str, Any]) -> List[SocialMatch]:
        """
        Parses visual_matches from Google Lens response, filters out non-matching domains,
        and maps matching items to their corresponding social network names.

        :param lens_data: JSON response dict from Google Lens search.
        :return: List of filtered SocialMatch instances.
        """
        visual_matches = lens_data.get("visual_matches", [])
        if not isinstance(visual_matches, list):
            return []

        social_matches: List[SocialMatch] = []
        for item in visual_matches:
            if not isinstance(item, dict):
                continue

            post_url = item.get("link") or item.get("url") or ""
            if not post_url:
                continue

            platform = self._match_platform(post_url)
            if not platform:
                # Discard non-matching domain
                continue

            title = item.get("title") or item.get("source") or platform
            source_image_url = (
                item.get("thumbnail")
                or item.get("original")
                or item.get("image")
                or item.get("source_icon")
            )

            social_matches.append(
                SocialMatch(
                    platform=platform,
                    post_url=post_url,
                    title=str(title).strip(),
                    source_image_url=source_image_url,
                )
            )

        return social_matches

    def search(self, image_input: Union[str, Path, bytes, BinaryIO]) -> SearchResult:
        """
        Uploads image, queries Google Lens, parses matches, and isolates social media posts.
        Gracefully handles scenarios with zero matches or failures without crashing.

        :param image_input: Cropped image file path, raw bytes, or binary stream.
        :return: SearchResult model.
        """
        if os.getenv("SERPAPI_MOCK") == "1" or os.getenv("MOCK_SEARCH") == "1":
            return SearchResult(
                success=True,
                message="Mock search completed successfully. Found 1 social media match.",
                matches=[
                    SocialMatch(
                        platform="X/Twitter",
                        post_url="https://x.com/vitalikbuterin/status/1789402948201",
                        title="Keynote Announcement & Verified Profile Portrait",
                        source_image_url="https://pbs.twimg.com/media/profile_img.jpg",
                    )
                ],
            )

        try:
            image_id = self.upload_image(image_input)
            lens_data = self.query_google_lens(image_id)
            matches = self.parse_visual_matches(lens_data)

            if not matches:
                return SearchResult(
                    success=True,
                    message="Search completed successfully. Zero social media matches found.",
                    matches=[],
                )

            return SearchResult(
                success=True,
                message=f"Search completed successfully. Found {len(matches)} social media match(es).",
                matches=matches,
            )

        except Exception as e:
            logger.debug(f"Error executing social image search: {e}")
            return SearchResult(
                success=False,
                message=f"Social search failed: {str(e)}",
                matches=[],
            )


# ---------------------------------------------------------
# Standalone CLI / Verification Test Block
# ---------------------------------------------------------
if __name__ == "__main__":
    import sys

    load_dotenv()
    api_key = os.getenv("SERPAPI_KEY")

    print("=" * 60)
    print("Social Image Searcher - Standalone Verification")
    print("=" * 60)

    # 1. Verify compute_canonical_hash
    sample_face_hash = "0x4a7269b61d36d895b6c29b9f3f98276f7a637d7c6b9868e8b839352e8d35f470"
    sample_post_url = "https://twitter.com/user/status/1234567890"
    sample_platform = "X/Twitter"

    canonical_hash = compute_canonical_hash(
        face_hash=sample_face_hash,
        post_url=sample_post_url,
        platform=sample_platform,
    )

    print("\n[Canonical Hash Verification]")
    print(f"  Face Hash:            {sample_face_hash}")
    print(f"  Platform:             {sample_platform}")
    print(f"  Post URL:             {sample_post_url}")
    print(f"  Keccak-256 (32B raw): {canonical_hash.hex()}")
    print(f"  Byte Length:          {len(canonical_hash)} bytes")
    assert len(canonical_hash) == 32, "Canonical hash must be exactly 32 bytes"

    # 2. Verify platform domain mapping
    searcher = SocialImageSearcher(api_key=api_key)
    test_domains = [
        ("https://x.com/username/status/100", "X/Twitter"),
        ("https://twitter.com/username/status/200", "X/Twitter"),
        ("https://www.instagram.com/p/ABC123xyz/", "Instagram"),
        ("https://linkedin.com/in/johndoe", "LinkedIn"),
        ("https://www.reddit.com/r/technology/comments/abc", "Reddit"),
        ("https://facebook.com/user/posts/1", "Facebook"),
        ("https://m.facebook.com/story.php?id=99", "Facebook"),
        ("https://youtube.com/watch?v=dQw4w9WgXcQ", "YouTube"),
        ("https://github.com/google/gemini", None),
        ("https://nytimes.com/world/article.html", None),
    ]

    print("\n[Platform Domain Matching Verification]")
    for url, expected in test_domains:
        matched = searcher._match_platform(url)
        status = "PASS" if matched == expected else "FAIL"
        print(f"  [{status}] {url} -> {matched} (expected: {expected})")
        assert matched == expected, f"Domain mapping assertion failed for {url}"

    # 3. Verify parser with mock Google Lens response
    mock_lens_response = {
        "visual_matches": [
            {
                "position": 1,
                "title": "Alice on X: 'Excited about the conference!'",
                "link": "https://twitter.com/alice/status/12345",
                "thumbnail": "https://serpapi.com/mock_thumb1.jpg",
                "source": "Twitter",
            },
            {
                "position": 2,
                "title": "Random Blog Post",
                "link": "https://randomblog.com/post/999",
                "thumbnail": "https://serpapi.com/mock_thumb2.jpg",
                "source": "RandomBlog",
            },
            {
                "position": 3,
                "title": "Bob's Instagram Post",
                "link": "https://www.instagram.com/p/Cz98765/",
                "thumbnail": "https://serpapi.com/mock_thumb3.jpg",
                "source": "Instagram",
            },
            {
                "position": 4,
                "title": "Reddit Thread Discussion",
                "link": "https://old.reddit.com/r/web3/comments/xyz123",
                "thumbnail": "https://serpapi.com/mock_thumb4.jpg",
                "source": "Reddit",
            },
        ]
    }

    parsed_matches = searcher.parse_visual_matches(mock_lens_response)
    print("\n[Mock Visual Matches Parsing Verification]")
    print(f"  Input matches count:   {len(mock_lens_response['visual_matches'])}")
    print(f"  Filtered social count: {len(parsed_matches)}")
    for idx, match in enumerate(parsed_matches, 1):
        print(f"    Match #{idx}: Platform={match.platform}, Title={match.title}, URL={match.post_url}")
    assert len(parsed_matches) == 3, f"Expected 3 social media matches, got {len(parsed_matches)}"

    # 4. Check API Key configuration for live tests
    print("\n[SerpApi Live Integration Status]")
    if not api_key:
        print("  SERPAPI_KEY is not set in .env. Live network calls skipped.")
        print("  Set SERPAPI_KEY in .env to perform live Google Lens image searches.")
    else:
        masked_key = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "***"
        print(f"  SERPAPI_KEY detected: {masked_key}")
        if len(sys.argv) > 1:
            img_path = sys.argv[1]
            print(f"  Searching image: {img_path}")
            result = searcher.search(img_path)
            print(f"  Result Success: {result.success}")
            print(f"  Result Message: {result.message}")
            print(f"  Matches Found:  {len(result.matches)}")
            for m in result.matches:
                print(f"    - [{m.platform}] {m.title}: {m.post_url}")

    print("\nAll standalone module checks passed successfully!")
