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

    # 4) 真实 ECIES 解密金额 —— 这里代表“通过 MPC 协作拿到 view 私钥结果”
    #    实际生产：把下面解密替换成 MPC 协议（节点各自做 ECDH share，再组合得 key）
    amount_cipher = data["amountCipher"]  # {ephPub, iv, ct} (hex)
    eph_pub = _hex_to_bytes(amount_cipher["ephPub"])
    iv      = _hex_to_bytes(amount_cipher["iv"])
    ct      = _hex_to_bytes(amount_cipher["ct"])

    VIEW_SK_HEX = os.getenv("VIEW_SK_HEX", None)
    if not VIEW_SK_HEX:
        raise ValueError("VIEW_SK_HEX not set (demo uses env var to simulate MPC result)")

    pt_bytes = ecies_decrypt_secp256k1(VIEW_SK_HEX, eph_pub, iv, ct)
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
        R=eph_pub,         # 可以把一次性公钥 R 也塞进公告，便于恢复
        memo=ct            # 或者放一段加密 memo
    )

    return {
        "tag": onchain_tag_hex,
        "announceTx": receipt_announce.transactionHash.hex(),
        "decrypted_amount": decrypted_amount,
        "amount_commitment": shares,
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
