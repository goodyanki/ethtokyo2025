# mpc_core/beaver.py
import random
from .shamir import shamir_split, shamir_reconstruct, P

def beaver_triple(n=3, t=2, p=P):
    """生成 Beaver 三元组 (a, b, c=a*b) 的 shares"""
    a = random.randrange(0, p)
    b = random.randrange(0, p)
    c = (a * b) % p
    a_shares = shamir_split(a, n, t, p)
    b_shares = shamir_split(b, n, t, p)
    c_shares = shamir_split(c, n, t, p)
    return a_shares, b_shares, c_shares

def mpc_multiply(x_shares, y_shares, triple, p=P):
    """
    使用 Beaver 三元组做安全乘法
    x_shares, y_shares: 每个参与方的输入 shares
    triple: (a_shares, b_shares, c_shares)
    """
    a_shares, b_shares, c_shares = triple

    # 每方持有 (xi, yi, ai, bi, ci)
    z_shares = []
    for ((idx, xi), (_, yi), (_, ai), (_, bi), (_, ci)) in zip(x_shares, y_shares, a_shares, b_shares, c_shares):
        dx = (xi - ai) % p
        dy = (yi - bi) % p
        zi = (ci + dx * bi + dy * ai + dx * dy) % p
        z_shares.append((idx, zi))
    return z_shares
