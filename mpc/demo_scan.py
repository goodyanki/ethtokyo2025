from .mpc_core.scan import derive_tag, match_tag, decrypt_amount_mpc

# 模拟链上公告
nonce = "0x1385..."
pubkey_view = "0x557efbcdc149fe74..."
onchain_tag = derive_tag(pubkey_view, nonce)  # 发送方生成的tag

# 收款人轻钱包扫描
if match_tag(pubkey_view, nonce, onchain_tag):
    print("✅ Found a transaction for me!")
    # 金额部分交给 MPC 协作解密
    fake_cipher = 123456  # 模拟金额密文
    amount = decrypt_amount_mpc(fake_cipher, lambda x: x-1)  # 假装MPC解密
    print("Decrypted amount (via MPC):", amount)
else:
    print("❌ No transaction for me.")
