# payment.py
import os
import json
from web3 import Web3
from eth_account import Account

from mpc_core.shamir import shamir_split
from mpc_core.scan import derive_tag, match_tag
from mpc_core.crypto import ecies_decrypt_secp256k1

# ---------- Web3 连接 & 合约 ----------
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

# ---------- MPC 解密配置 ----------
USE_MPC_DECRYPT = os.getenv("USE_MPC_DECRYPT", "true").lower() in ("1", "true", "yes")
MPC_NODES = [x.strip() for x in os.getenv("MPC_NODES", "http://127.0.0.1:7001,http://127.0.0.1:7002,http://127.0.0.1:7003").split(",") if x.strip()]
MPC_THRESHOLD = int(os.getenv("MPC_THRESHOLD", "2"))
HTTP_TIMEOUT_S = float(os.getenv("HTTP_TIMEOUT_S", "1.5"))
STRICT_MPC = os.getenv("STRICT_MPC", "false").lower() in ("1", "true", "yes")

# 模拟解密的备用私钥
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

# -------------------- MPC 解密实现 --------------------
def mpc_ecies_decrypt(eph_pub_hex: str, iv_hex: str, ct_hex: str) -> bytes:
    """使用MPC节点协作进行ECIES解密"""
    import requests
    import hashlib
    from coincurve import PublicKey
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    
    # 第1步：收集ECDH分片
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
            # 直接复用 /scan_share 端点，因为计算的是同一个 yi * R
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
                
            PublicKey(Yi)  # 验证点在曲线上
            shares.append((i, Yi))
            seen.add(i)
            
            if len(shares) >= MPC_THRESHOLD:
                break
                
        except Exception as e:
            print(f"⚠️ ECDH share from {url} failed: {e}")
            continue
    
    if len(shares) < MPC_THRESHOLD:
        raise RuntimeError(f"Not enough ECDH shares: {len(shares)}/{MPC_THRESHOLD}")
    
    # 第2步：拉格朗日插值聚合
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
        k_bytes = (k % SECP_N).to_bytes(32, "big")
        return pub.multiply(k_bytes)
    
    def _point_add(p, q):
        if p is None:
            return q
        return PublicKey.combine_keys([p, q])
    
    indices = [i for (i, _) in shares]
    lambdas = _lagrange_coeffs_at_zero(indices)
    
    # 聚合 S = Σ λᵢ * Yᵢ = v * R
    S = None
    for lam, (_, Yi_bytes) in zip(lambdas, shares):
        Yi = PublicKey(Yi_bytes)
        weighted = _point_mul(Yi, lam)
        S = _point_add(S, weighted)
    
    if S is None:
        raise RuntimeError("Failed to aggregate ECDH result")
    
    # 第3步：提取共享密钥（X坐标32字节）
    shared_secret = S.format(compressed=False)[1:33]  # 取X坐标
    
    # 第4步：HKDF派生AES密钥
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"ecies-secp256k1-key"
    )
    aes_key = hkdf.derive(shared_secret)
    
    # 第5步：AES-CTR解密
    iv_bytes = _as_bytes(iv_hex)
    ct_bytes = _as_bytes(ct_hex)
    
    cipher = Cipher(algorithms.AES(aes_key), modes.CTR(iv_bytes))
    decryptor = cipher.decryptor()
    plaintext = decryptor.update(ct_bytes) + decryptor.finalize()
    
    return plaintext

# -------------------- 主入口 --------------------
def process_payment_request(req_json: str):
    data = json.loads(req_json)

    pubkey_spend = data["pubkeySpend"]
    pubkey_view  = data["pubkeyView"]
    nonce        = data["nonce"]
    checksum     = data["checksum"]
    to_addr      = Web3.to_checksum_address(data.get("to", SENDER_ADDR))

    # 1) checksum 简检
    if not str(checksum).startswith("0x"):
        raise ValueError("Invalid checksum")

    # 2) 生成选择性披露 tag（链上公告字段）
    onchain_tag_hex = derive_tag(pubkey_view, nonce)  # sha256 hex
    onchain_tag_bytes = _bytes32_align(_hex_to_bytes(onchain_tag_hex))

    # 3) 轻钱包/本地匹配（demo必为真）
    if not match_tag(pubkey_view, nonce, onchain_tag_hex):
        return {"status": "no_match", "message": "No transaction for this address"}

    # 4) ECIES 解密金额 - MPC 或模拟
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
        
        # 回退机制（如果不是严格MPC模式）
        if USE_MPC_DECRYPT and not STRICT_MPC and VIEW_SK_HEX:
            print("🔄 Falling back to simulated decryption...")
            try:
                pt_bytes = ecies_decrypt_secp256k1(VIEW_SK_HEX, _hex_to_bytes(eph_pub), _hex_to_bytes(iv), _hex_to_bytes(ct))
                print("✅ Fallback decryption successful")
            except Exception as fallback_err:
                raise ValueError(f"Both MPC and fallback decryption failed: {decrypt_err}, {fallback_err}")
        else:
            raise ValueError(f"Decryption failed: {decrypt_err}")

    # 解析解密结果
    try:
        decrypted_amount = int(pt_bytes.decode())
    except Exception:
        # 也支持直接把明文当大端整数编码
        decrypted_amount = int.from_bytes(pt_bytes, "big")

    # 5) Shamir 分片（3方，阈值2）
    shares = shamir_split(decrypted_amount, n=3, t=2)

    # 6) 生成 secp256k1 ECDSA 签名（供合约 ecrecover）
    MPC_ECDSA_PK = os.getenv("MPC_ECDSA_PK", SENDER_PK)  # demo：用本地私钥模拟 TSS 聚合签名者
    mpc_account  = Account.from_key(MPC_ECDSA_PK)

    # 防重放：paymentId 绑定 tag + to + amount
    payment_id = Web3.keccak(text=f"{onchain_tag_hex}:{to_addr}:{decrypted_amount}")  # bytes32
    digest = Web3.solidity_keccak(
        ["bytes32", "address", "uint256", "bytes32"],
        [payment_id, to_addr, decrypted_amount, onchain_tag_bytes]
    )
    signed = Account.sign_hash(digest, private_key=MPC_ECDSA_PK)
    v, r, s = int(signed.v), Web3.to_hex(signed.r), Web3.to_hex(signed.s)

    # 7) 上链公告（事件可供钱包离线后回放）
    receipt_announce = announce_onchain(
        tag_bytes32=onchain_tag_bytes,
        R=_hex_to_bytes(eph_pub),         # 可以把一次性公钥 R 也塞进公告，便于恢复
        memo=_hex_to_bytes(ct)            # 或者放一段加密 memo
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