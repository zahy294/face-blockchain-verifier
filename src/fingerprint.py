"""Canonical Keccak-256 fingerprint generator linking face hash, platform, and post URL."""

import json
from web3 import Web3
from eth_utils import to_hex


def compute_canonical_fingerprint(face_hash: str, platform: str, post_url: str) -> str:
    """
    Computes a canonical 32-byte Keccak-256 hash linking:
    - face SHA-256 hash
    - social platform identifier
    - canonical post URL
    
    Returns:
        Hex-encoded 32-byte hash starting with '0x' (66 characters total).
    """
    payload = {
        "face_hash": str(face_hash).strip().lower(),
        "platform": str(platform).strip(),
        "post_url": str(post_url).strip(),
    }
    # Deterministic JSON representation: keys sorted alphabetically, no extra whitespace
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    keccak_hexbytes = Web3.keccak(text=canonical_json)
    return to_hex(keccak_hexbytes)
