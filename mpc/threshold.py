# demo_threshold_sig.py
from .mpc_core.threshold.eddsa import ThresholdSigner

message = b"authorize payment of 100 tokens"

# 初始化3方，阈值2
signer = ThresholdSigner(n=3, t=2)
signer.distributed_keygen()

# Party1和Party3 参与签名
sig1 = signer.sign_share(1, message)
sig3 = signer.sign_share(3, message)

# 聚合
signature = signer.aggregate([sig1, sig3])

# 验证
ok = signer.verify(message, signature)
print("Threshold signature valid?", ok)
