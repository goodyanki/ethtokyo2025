# payment.py
import os
import json
from web3 import Web3
from eth_account import Account

from mpc_core.shamir import shamir_split
from mpc_core.scan import derive_tag, match_tag
from mpc_core.crypto import ecies_decrypt_secp256k1

# ---------- Web3 connection & contract ----------
RPC_URL = os.getenv("RPC_URL", "http://127.0.0.1:8545")
w3 = Web3(Web3.HTTPProvider(RPC_URL))

PAYMENT_PROXY_ADDRESS = Web3.to_checksum_address(
    os.getenv("PAYMENT_PROXY_ADDRESS", "0xYourDeployedContract")
)
ABI_PATH = os.getenv(
    "PAYMENT_PROXY_ABI",
    "artifacts/contracts/src/PaymentProxy.sol/PaymentProxy.json"
)
with open(ABI_PATH) as f:
    contract_json = json.load(f)
    abi = contract_json["abi"]

payment_contract = w3.eth.contract(address=PAYMENT_PROXY_ADDRESS, abi=abi)

SENDER_ADDR = Web3.to_checksum_address(os.getenv("ETH_SENDER", "0xYourAccount"))
SENDER_PK   = os.getenv("ETH_PRIVATE_KEY", "0xYourPrivateKey")

# ---------- MPC decryption config ----------
USE_MPC_DECRYPT = os.getenv("USE_MPC_DECRYPT", "true").lower() in ("1", "true", "yes")
MPC_NODES = [x.strip() for x in os.getenv("MPC_NODES", "http://127.0.0.1:7001,http://127.0.0.1:7002,http://127.0.0.1:7003").split(",") if x.strip()]
MPC_THRESHOLD = int(os.getenv("MPC_THRESHOLD", "2"))
HTTP_TIMEOUT_S = float(os.getenv("HTTP_TIMEOUT_S", "1.5"))
STRICT_MPC = os.getenv("STRICT_MPC", "false").lower() in ("1", "true", "yes")

# Backup view private key for simulated decryption
VIEW_SK_HEX = os.getenv("VIEW_SK_HEX", None)

def _hex_to_bytes(x: str) -> bytes:
    return Web3.to_bytes(hexstr=x)

def _bytes32_align(b: bytes) -> bytes:
    return b.ljust(32, b"\x00")[:32]

def send_tx(tx):
    tx["nonce"] = w3.eth.get_transaction_count(SENDER_ADDR)
    tx.setdefault("gas", 2_000_000)
    tx.setdefault("gasPrice", w3.to_wei("10", "gwei"))
    signed = w3.eth.account.sign_transaction(tx, private_key=SENDER_PK)
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
    return w3.eth.wait_for_transaction_receipt(tx_hash)

def announce_onchain(tag_bytes32: bytes, R: bytes, memo: bytes):
    tx = payment_contract.functions.announcePayment(tag_bytes32, R, memo).build_transaction({
        "from": SENDER_ADDR
    })
    return send_tx(tx)

# -------------------- MPC decryption implementation --------------------
def mpc_ecies_decrypt(eph_pub_hex: str, iv_hex: str, ct_hex: str) -> bytes:
    """ECIES decryption using MPC nodes"""
    import requests
    import hashlib
    from coincurve import PublicKey
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    
    # Step 1: collect ECDH shares
    # Reuse /scan_share endpoint since it computes Yi = share_i * R
    def _as_bytes(x) -> bytes:
        if isinstance(x, str):
            s = x.strip()
            if s.lower().startswith("0x"):
                s = s[2:]
            return bytes.fromhex(s)
        return bytes(x)
    
    def _b2h(b: bytes) -> str:
        return "0x" + b.hex()
    
    R_bytes = _as_bytes(eph_pub_hex)
    shares = []
    seen = set()
    
    payload = {"R": _b2h(R_bytes)}
    
    for url in MPC_NODES:
        try:
            resp = requests.post(f"{url.rstrip('/')}/scan_share", json=payload, timeout=HTTP_TIMEOUT_S)
            resp.raise_for_status()
            data = resp.json()
            
            i = int(data["i"])
            if i in seen:
                continue
            Yi = _as_bytes(data["Yi"])
            
            if len(Yi) != 33 or Yi[0] not in (2, 3):
                print(f"⚠️ bad Yi from {url}: len={len(Yi)}")
                continue
                
            PublicKey(Yi)  # sanity check: point must be on curve
            shares.append((i, Yi))
            seen.add(i)
            
            if len(shares) >= MPC_THRESHOLD:
                break
                
        except Exception as e:
            print(f"⚠️ ECDH share from {url} failed: {e}")
            continue
    
    if len(shares) < MPC_THRESHOLD:
        raise RuntimeError(f"Not enough ECDH shares: {len(shares)}/{MPC_THRESHOLD}")
    
    # Step 2: aggregate via Lagrange interpolation at x=0
    SECP_N = int("0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141", 16)
    
    def _lagrange_coeffs_at_zero(indices):
        lambdas = []
        for i in indices:
            num = 1
            den = 1
            for j in indices:
                if j == i:
                    continue
                num = (num * (-j % SECP_N)) % SECP_N
                den = (den * ((i - j) % SECP_N)) % SECP_N
            den_inv = pow(den, SECP_N - 2, SECP_N)
            lambdas.append((num * den_inv) % SECP_N)
        return lambdas
    
    def _point_mul(pub, k):
        # coincurve expects 32-byte big-endian scalar
        k_bytes = (k % SECP_N).to_bytes(32, "big")
        return pub.multiply(k_bytes)
    
    def _point_add(p, q):
        if p is None:
            return q
        return PublicKey.combine_keys([p, q])
    
    indices = [i for (i, _) in shares]
    lambdas = _lagrange_coeffs_at_zero(indices)
    
    # Aggregate S = Σ λᵢ * Yᵢ = v * R
    S = None
    for lam, (_, Yi_bytes) in zip(lambdas, shares):
        Yi = PublicKey(Yi_bytes)
        weighted = _point_mul(Yi, lam)
        S = _point_add(S, weighted)
    
    if S is None:
        raise RuntimeError("Failed to aggregate ECDH result")
    
    # Step 3: extract shared key = X coordinate (32 bytes)
    shared_secret = S.format(compressed=False)[1:33]
    
    # Step 4: derive AES key via HKDF-SHA256
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"ecies-secp256k1-key"
    )
    aes_key = hkdf.derive(shared_secret)
    
    # Step 5: AES-CTR decrypt
    iv_bytes = _as_bytes(iv_hex)
    ct_bytes = _as_bytes(ct_hex)
    
    cipher = Cipher(algorithms.AES(aes_key), modes.CTR(iv_bytes))
    decryptor = cipher.decryptor()
    plaintext = decryptor.update(ct_bytes) + decryptor.finalize()
    
    return plaintext

# -------------------- Main entry --------------------
def process_payment_request(req_json: str):
    data = json.loads(req_json)

    pubkey_spend = data["pubkeySpend"]
    pubkey_view  = data["pubkeyView"]
    nonce        = data["nonce"]
    checksum     = data["checksum"]
    to_addr      = Web3.to_checksum_address(data.get("to", SENDER_ADDR))

    # 1) checksum sanity check
    if not str(checksum).startswith("0x"):
        raise ValueError("Invalid checksum")

    # 2) generate linkability tag (on-chain announcement field)
    onchain_tag_hex = derive_tag(pubkey_view, nonce)  # sha256 hex
    onchain_tag_bytes = _bytes32_align(_hex_to_bytes(onchain_tag_hex))

    # 3) local/light-wallet matching (always true in demo)
    if not match_tag(pubkey_view, nonce, onchain_tag_hex):
        return {"status": "no_match", "message": "No transaction for this address"}

    # 4) ECIES decryption of amount — MPC or simulated
    amount_cipher = data["amountCipher"]  # {ephPub, iv, ct} (hex)
    eph_pub = amount_cipher["ephPub"]
    iv      = amount_cipher["iv"]
    ct      = amount_cipher["ct"]

    try:
        if USE_MPC_DECRYPT:
            print("🔄 Using MPC decryption...")
            pt_bytes = mpc_ecies_decrypt(eph_pub, iv, ct)
            print("✅ MPC decryption successful")
        else:
            print("🔄 Using simulated decryption...")
            if not VIEW_SK_HEX:
                raise ValueError("VIEW_SK_HEX not set for simulated decryption")
            pt_bytes = ecies_decrypt_secp256k1(VIEW_SK_HEX, _hex_to_bytes(eph_pub), _hex_to_bytes(iv), _hex_to_bytes(ct))
            print("✅ Simulated decryption successful")
            
    except Exception as decrypt_err:
        print(f"❌ Decryption failed: {decrypt_err}")
        
        # Fallback (if not strict-MPC mode)
        if USE_MPC_DECRYPT and not STRICT_MPC and VIEW_SK_HEX:
            print("🔄 Falling back to simulated decryption...")
            try:
                pt_bytes = ecies_decrypt_secp256k1(VIEW_SK_HEX, _hex_to_bytes(eph_pub), _hex_to_bytes(iv), _hex_to_bytes(ct))
                print("✅ Fallback decryption successful")
            except Exception as fallback_err:
                raise ValueError(f"Both MPC and fallback decryption failed: {decrypt_err}, {fallback_err}")
        else:
            raise ValueError(f"Decryption failed: {decrypt_err}")

    # Parse decrypted result
    try:
        decrypted_amount = int(pt_bytes.decode())
    except Exception:
        # Also support interpreting plaintext as big-endian integer
        decrypted_amount = int.from_bytes(pt_bytes, "big")

    # 5) Shamir secret sharing (3 parties, threshold 2)
    shares = shamir_split(decrypted_amount, n=3, t=2)

    # 6) Generate secp256k1 ECDSA signature (verified by contract via ecrecover)
    MPC_ECDSA_PK = os.getenv("MPC_ECDSA_PK", SENDER_PK)  # demo: simulate TSS aggregator with local key
    mpc_account  = Account.from_key(MPC_ECDSA_PK)

    # Anti-replay: bind paymentId to (tag + to + amount)
    payment_id = Web3.keccak(text=f"{onchain_tag_hex}:{to_addr}:{decrypted_amount}")  # bytes32
    digest = Web3.solidity_keccak(
        ["bytes32", "address", "uint256", "bytes32"],
        [payment_id, to_addr, decrypted_amount, onchain_tag_bytes]
    )
    signed = Account.sign_hash(digest, private_key=MPC_ECDSA_PK)
    v, r, s = int(signed.v), Web3.to_hex(signed.r), Web3.to_hex(signed.s)

    # 7) On-chain announcement (event can be replayed by wallets later)
    receipt_announce = announce_onchain(
        tag_bytes32=onchain_tag_bytes,
        R=_hex_to_bytes(eph_pub),         # optionally include ephemeral R for recovery
        memo=_hex_to_bytes(ct)            # or put an encrypted memo
    )

    return {
        "tag": onchain_tag_hex,
        "announceTx": receipt_announce.transactionHash.hex(),
        "decrypted_amount": decrypted_amount,
        "amount_commitment": shares,
        "decryption_method": "mpc" if USE_MPC_DECRYPT else "simulated",
        "ecdsa": {
            "paymentId": Web3.to_hex(payment_id),
            "to": to_addr,
            "digest": Web3.to_hex(digest),
            "v": v,
            "r": r,
            "s": s,
            "signer": mpc_account.address
        }
    }
