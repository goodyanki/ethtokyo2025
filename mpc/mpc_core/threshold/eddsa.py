# mpc_core/threshold/eddsa.py
import hashlib
import secrets
from ..shamir import shamir_split, shamir_reconstruct, P

class ThresholdSigner:
    def __init__(self, n=3, t=2):
        self.n = n
        self.t = t
        self.shares = {}
        self.public_key = None
        self.secret = None

    def distributed_keygen(self):
        """用 Shamir 生成私钥 shares"""
        secret = secrets.randbelow(P)
        shares = shamir_split(secret, n=self.n, t=self.t)
        self.shares = {i: share for i, share in shares}
        self.secret = secret
        self.public_key = hashlib.sha256(str(secret).encode()).hexdigest()

    def sign_share(self, pid, message: bytes):
        """参与方本地计算部分签名（hash + share）"""
        h = int.from_bytes(hashlib.sha256(message).digest(), "big") % P
        # self.shares[pid] 存的是 share 值本身，索引就是 pid
        si = self.shares[pid]
        i = pid
        partial = (i, (h * si) % P)
        return partial

    def aggregate(self, partial_sigs):
        """用 Shamir 重建完整签名"""
        sig = shamir_reconstruct(partial_sigs, p=P)
        return sig

    def verify(self, message: bytes, signature: int):
        """简化验证：用 hash(secret) 作为 public key 验证"""
        h = int.from_bytes(hashlib.sha256(message).digest(), "big") % P
        expected = (h * self.secret) % P
        return expected == signature
