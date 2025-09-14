# 方案1: 修改后端直接调用合约
# mpc/server.py 的 sender_announce 函数

import os
from web3 import Web3
import json

# 在文件顶部添加
RPC_URL = os.getenv("RPC_URL", "http://127.0.0.1:8545")
REGISTRY_ADDRESS = os.getenv("REGISTRY_V2")  # StealthRegistry 合约地址
PRIVATE_KEY = os.getenv("SENDER_PRIVATE_KEY")  # 发送交易的私钥

w3 = Web3(Web3.HTTPProvider(RPC_URL))

# 加载 StealthRegistry ABI
with open("../contracts/out/StealthRegistry.sol/StealthRegistryV2.json") as f:
    registry_abi = json.load(f)["abi"]

@app.post("/sender/announce")
def sender_announce(request: AnnounceRequest):
    """
    接收发送方的公告请求，真实发布到链上
    """
    try:
        if not REGISTRY_ADDRESS:
            return {"ok": False, "error": "合约地址未配置"}
            
        # 创建合约实例
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(REGISTRY_ADDRESS), 
            abi=registry_abi
        )
        
        # 准备参数
        R_bytes = bytes.fromhex(request.R[2:] if request.R.startswith('0x') else request.R)
        tag_bytes32 = bytes.fromhex(request.tag[2:] if request.tag.startswith('0x') else request.tag)
        commitment_bytes32 = bytes.fromhex(request.commitment[2:] if request.commitment.startswith('0x') else request.commitment)
        memo_bytes = b""  # 暂时为空
        
        # 构建交易
        account = w3.eth.account.from_key(PRIVATE_KEY)
        
        # 调用 publish 方法
        tx = contract.functions.publish(
            R_bytes,
            memo_bytes, 
            commitment_bytes32,
            tag_bytes32
        ).build_transaction({
            'from': account.address,
            'nonce': w3.eth.get_transaction_count(account.address),
            'gas': 200000,
            'gasPrice': w3.to_wei('10', 'gwei')
        })
        
        # 签名并发送
        signed_tx = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        return {
            "ok": True,
            "message": "公告已上链",
            "txHash": receipt.transactionHash.hex(),
            "blockNumber": receipt.blockNumber
        }
        
    except Exception as e:
        print(f"上链失败: {e}")
        return {"ok": False, "error": str(e)}