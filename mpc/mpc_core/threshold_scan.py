# mpc_core/threshold_scan.py
from typing import List, Tuple
from web3 import Web3
import hashlib, json
from coincurve import PublicKey

# secp256k1 曲线阶
N = int("0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141", 16)

def _mod_inv(x: int) -> int:
    return pow(x % N, N - 2, N)

def _lagrange_at_zero(indices: List[int]) -> List[int]:
    """
    计算在 x=0 的拉格朗日系数 λ_i（模 n），indices 是参与的 x 坐标（从 1 开始的正整数）。
    """
    lambdas: List[int] = []
    for i, xi in enumerate(indices):
        num, den = 1, 1
        for j, xj in enumerate(indices):
            if j == i:
                continue
            num = (num * (-xj % N)) % N        # (0 - xj)
            den = (den * ((xi - xj) % N)) % N  # (xi - xj)
        lambdas.append((num * _mod_inv(den)) % N)
    return lambdas

def _point_add(points: List[PublicKey]) -> PublicKey:
    # coincurve 提供 PublicKey.combine 合并多个公钥（椭圆曲线点相加）
    return PublicKey.combine(points)

def _point_mul(point: PublicKey, k: int) -> PublicKey:
    # 对给定点做标量乘法
    return point.multiply(k.to_bytes(32, "big"))

def derive_tag_tofn(
    R_compressed: bytes,
    shares: List[Tuple[int, int]],
) -> bytes:
    """
    用 t-of-n 分片在“点上插值”计算 S = s_view * R（不重建明文私钥），
    再 tag = keccak256( sha256( S_compressed ) )

    入参:
      - R_compressed: 33字节压缩一次性公钥 r·G（secp256k1）
      - shares: [(i, y_i), ...] 任意 t 份 Shamir 分片（i 从 1 起；y_i < n）

    返回:
      - 32 字节 tag（bytes）
    """
    if len(shares) < 2:
        raise ValueError("need at least 2 shares for threshold scan demo")

    indices = [i for (i, _) in shares]
    lambdas = _lagrange_at_zero(indices)
    R = PublicKey(R_compressed)

    weighted_points: List[PublicKey] = []
    for (i, yi), li in zip(shares, lambdas):
        # 局部点：yi * R
        Pi = R.multiply(yi.to_bytes(32, "big"))
        # 加权：λ_i * (yi * R)
        Qi = _point_mul(Pi, li)
        weighted_points.append(Qi)

    S_point = _point_add(weighted_points)              # S = s_view * R
    S_bytes = S_point.format(compressed=True)          # 33B
    s_hash = hashlib.sha256(S_bytes).digest()          # 32B
    tag = Web3.keccak(s_hash)                          # 32B
    return tag

def parse_shares_json(shares_json: str) -> List[Tuple[int, int]]:
    """
    解析形如 '[["1","0xabc..."],["3","0xdef..."]]' 的 JSON，返回 [(1, int_y1), (3, int_y3)]
    """
    raw = json.loads(shares_json)
    out: List[Tuple[int, int]] = []
    for idx_str, y_hex in raw:
        out.append((int(idx_str), int(y_hex, 16)))
    return out
