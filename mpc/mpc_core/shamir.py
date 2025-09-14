# mpc_core/shamir.py
import random

P = 2**127 - 1  # 大素数作为有限域

def _eval_poly(coeffs, x, p=P):
    """多项式求值"""
    return sum([c * pow(x, i, p) for i, c in enumerate(coeffs)]) % p

def shamir_split(secret: int, n: int = 3, t: int = 2, p: int = P):
    """Shamir 秘密分享，将 secret 拆成 n 份，阈值 t"""
    coeffs = [secret] + [random.randrange(0, p) for _ in range(t - 1)]
    shares = [(i, _eval_poly(coeffs, i, p)) for i in range(1, n + 1)]
    return shares

def shamir_reconstruct(shares, p=P):
    """Lagrange 插值重建秘密"""
    res = 0
    for j, (xj, yj) in enumerate(shares):
        lj = 1
        for m, (xm, _) in enumerate(shares):
            if m != j:
                lj = (lj * xm * pow(xm - xj, -1, p)) % p
        res = (res + yj * lj) % p
    return res
