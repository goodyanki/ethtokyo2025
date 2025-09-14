# mpc_core/scan.py
from typing import Callable
from hashlib import sha256

def _clean_hex(h: str) -> bytes:
    s = h.lower().replace("0x", "")
    if len(s) % 2 != 0:
        s = "0" + s
    return bytes.fromhex(s)

def derive_tag(pubkey_view: str, nonce: str) -> str:
    """Derive a lightweight scan tag from view key and nonce.
    This is a demo: tag = sha256(view || nonce)[0:16] as hex.
    """
    data = _clean_hex(pubkey_view) + _clean_hex(nonce)
    # Use full 32-byte SHA-256 for onchain bytes32 compatibility
    tag = sha256(data).digest()
    return "0x" + tag.hex()

def match_tag(pubkey_view: str, nonce: str, onchain_tag: str) -> bool:
    return derive_tag(pubkey_view, nonce).lower() == onchain_tag.lower()

def decrypt_amount_mpc(cipher_amount: int, mpc_oracle: Callable[[int], int]) -> int:
    """Demo MPC decrypt shim: delegate to provided oracle/closure.
    In real system this would dispatch an MPC round and return plaintext.
    """
    return mpc_oracle(cipher_amount)
