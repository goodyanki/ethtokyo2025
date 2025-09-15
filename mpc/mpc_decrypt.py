import requests
import hashlib
from web3 import Web3
from coincurve import PublicKey
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

def mpc_ecies_decrypt(eph_pub_hex: str, iv_hex: str, ct_hex: str) -> bytes:
    """使用MPC节点协作进行ECIES解密"""
    
    # 第1步：收集ECDH分片（复用扫描器的网络逻辑）
    from .scanner import collect_scan_shares, MPC_THRESHOLD, _as_bytes
    
    R_bytes = _as_bytes(eph_pub_hex)
    shares = collect_scan_shares(R_bytes, need=MPC_THRESHOLD)
    
    if len(shares) < MPC_THRESHOLD:
        raise RuntimeError(f"Not enough shares for decryption: {len(shares)}/{MPC_THRESHOLD}")
    
    # 第2步：拉格朗日插值（复用扫描器的数学逻辑）
    from .scanner import _lagrange_coeffs_at_zero, _point_mul, _point_add
    
    indices = [i for (i, _) in shares]
    lambdas = _lagrange_coeffs_at_zero(indices)
    
    # 聚合ECDH结果：S = Σ λᵢ * Yᵢ = v * R
    S = None
    for lam, (_, Yi_bytes) in zip(lambdas, shares):
        Yi = PublicKey(Yi_bytes)
        weighted = _point_mul(Yi, lam)
        S = _point_add(S, weighted)
    
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