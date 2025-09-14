# mpc_core/crypto.py
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.exceptions import InvalidKey
import os

# ---- secp256k1 ECIES（ECDH + HKDF + AES-CTR） ----

def _kdf(shared_secret: bytes, info: bytes = b"ecies-secp256k1", length: int = 32) -> bytes:
    hkdf = HKDF(algorithm=hashes.SHA256(), length=length, salt=None, info=info)
    return hkdf.derive(shared_secret)

def ecies_encrypt_secp256k1(pubkey_bytes_compressed: bytes, plaintext: bytes):
    """
    输入: 收款人 view 公钥(压缩 secp256k1 33字节), 明文
    输出: (eph_pub_compressed, iv16, ciphertext)
    """
    # 载入对方公钥
    pubkey = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256K1(), pubkey_bytes_compressed)

    # 生成临时密钥对
    eph_priv = ec.generate_private_key(ec.SECP256K1())
    eph_pub = eph_priv.public_key()

    # ECDH -> HKDF -> 对称密钥
    shared = eph_priv.exchange(ec.ECDH(), pubkey)
    key = _kdf(shared, info=b"ecies-secp256k1-key", length=32)

    iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(key), modes.CTR(iv))
    enc = cipher.encryptor()
    ct = enc.update(plaintext) + enc.finalize()

    eph_pub_bytes = eph_pub.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.CompressedPoint
    )
    return eph_pub_bytes, iv, ct

def ecies_decrypt_secp256k1(privkey_hex: str, eph_pub_bytes_compressed: bytes, iv: bytes, ciphertext: bytes) -> bytes:
    """
    输入: 自己的 view 私钥(十六进制), 发送方临时公钥(压缩), iv, 密文
    输出: 明文
    """
    try:
        sk_int = int(privkey_hex, 16)
    except Exception as e:
        raise InvalidKey(f"Invalid secp256k1 private key hex: {e}")

    priv = ec.derive_private_key(sk_int, ec.SECP256K1())
    eph_pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256K1(), eph_pub_bytes_compressed)

    shared = priv.exchange(ec.ECDH(), eph_pub)
    key = _kdf(shared, info=b"ecies-secp256k1-key", length=32)

    cipher = Cipher(algorithms.AES(key), modes.CTR(iv))
    dec = cipher.decryptor()
    pt = dec.update(ciphertext) + dec.finalize()
    return pt
