# make_shares.py  —— 2-of-3 Shamir for secp256k1
import secrets

N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141

def shamir_split(secret: int, t: int, n: int):
    # f(x) = secret + a1*x (t=2)
    a1 = secrets.randbelow(N-1) + 1
    shares = []
    for i in range(1, n+1):
        y = (secret + a1 * i) % N
        shares.append((i, y))
    return shares

view_sk_hex = "0x" + "37aaf720da558828d27fdc80cdda83dc4e268e818e4fe562f5f8fed2fdf8ec5f"[0:]  # 你的
s = int(view_sk_hex, 16)
shares = shamir_split(s, t=2, n=3)
for i, y in shares:
    print(f"NODE_INDEX={i}  VIEW_SK_SHARE_HEX=0x{y:064x}")
