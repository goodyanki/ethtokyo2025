# coordinator.py
import asyncio
from .mpc_core.shamir import shamir_split, shamir_reconstruct
from .mpc_core.beaver import beaver_triple, mpc_multiply
from .mpc_core.threshold.eddsa import ThresholdSigner

async def run_demo():
    print("=== DEMO: Secure SUM ===")
    secrets = {1: 5, 2: 7, 3: 9}
    shares = {pid: shamir_split(secrets[pid], n=3, t=2) for pid in secrets}
    local_sums = {
        pid: sum(v for (_, v) in [shares[1][pid-1], shares[2][pid-1], shares[3][pid-1]])
        for pid in secrets
    }
    collected = [(pid, local_sums[pid]) for pid in secrets]
    total = shamir_reconstruct(collected)
    print(f"Final SUM = {total}")

    print("\n=== DEMO: Secure MULTIPLY ===")
    triple = beaver_triple()
    x_shares = shamir_split(5)
    y_shares = shamir_split(7)
    z_shares = mpc_multiply(x_shares, y_shares, triple)
    product = shamir_reconstruct(z_shares)
    print(f"Final PRODUCT = {product}")

    print("\n=== DEMO: Threshold Signature (2-of-3) ===")
    message = b"pay 100 tokens to Bob"
    signer = ThresholdSigner(n=3, t=2)
    # 分布式密钥生成
    signer.distributed_keygen()
    # 选择2个参与方签名
    sig1 = signer.sign_share(1, message)
    sig2 = signer.sign_share(2, message)
    signature = signer.aggregate([sig1, sig2])
    ok = signer.verify(message, signature)
    print(f"Threshold Signature Verified? {ok}")

if __name__ == "__main__":
    asyncio.run(run_demo())
