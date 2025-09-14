# mpc/node_scan.py
# -*- coding: utf-8 -*-
"""
最小可跑的 MPC 扫描“节点”：
- 每个节点持有一个 view_sk 的分片 y_i（标量），以及自己的索引 i
- 提供接口 POST /scan_share { "R": "0x02/03..(33B)" }
- 返回 {"i": i, "Yi": "0x02/03..(33B)"}，其中 Yi = y_i * R（点乘）
- 供 scanner（协调端）收集并按拉格朗日系数聚合

运行依赖：
  pip install fastapi uvicorn coincurve

运行示例（三节点三端口）：
  # 节点1
  export NODE_INDEX=1
  export VIEW_SK_SHARE_HEX=0x1a2b3c...   # 32B 标量（1..n-1）
  uvicorn mpc.node_scan:app --host 127.0.0.1 --port 7001

  # 节点2
  export NODE_INDEX=2
  export VIEW_SK_SHARE_HEX=0x4d5e6f...
  uvicorn mpc.node_scan:app --host 127.0.0.1 --port 7002

  # 节点3
  export NODE_INDEX=3
  export VIEW_SK_SHARE_HEX=0x7a8b9c...
  uvicorn mpc.node_scan:app --host 127.0.0.1 --port 7003

scanner 环境变量：
  export USE_MPC=true
  export MPC_NODES="http://127.0.0.1:7001,http://127.0.0.1:7002,http://127.0.0.1:7003"
  export MPC_THRESHOLD=2
"""

import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from coincurve import PublicKey

SECP_N = int("0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141", 16)

# -----------------------------------------------------------------------------
# 环境变量：节点索引 & 分片（标量）
# -----------------------------------------------------------------------------
def _require_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"env {name} is required")
    return v

def _strip0x(s: str) -> str:
    return s[2:] if s.lower().startswith("0x") else s

def _h2b(h: str) -> bytes:
    return bytes.fromhex(_strip0x(h))

def _b2h(b: bytes) -> str:
    return "0x" + b.hex()

NODE_INDEX = int(_require_env("NODE_INDEX"))
VIEW_SK_SHARE_HEX = _require_env("VIEW_SK_SHARE_HEX")
try:
    _tmp = int(_strip0x(VIEW_SK_SHARE_HEX), 16)
    if not (1 <= _tmp < SECP_N):
        raise ValueError("share not in [1, n-1]")
except Exception as e:
    raise RuntimeError(f"VIEW_SK_SHARE_HEX invalid: {e}")

VIEW_SK_SHARE_INT = int(_strip0x(VIEW_SK_SHARE_HEX), 16)

# -----------------------------------------------------------------------------
# FastAPI
# -----------------------------------------------------------------------------
app = FastAPI(title=f"MPC Scan Node #{NODE_INDEX}")

# （可选）允许本地前端调试
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

class ScanShareReq(BaseModel):
    R: str  # 0x02/03.. (33B 压缩公钥)

class ScanShareResp(BaseModel):
    i: int
    Yi: str # 0x02/03.. (33B)

@app.get("/health")
def health():
    return {"ok": True, "index": NODE_INDEX}

@app.get("/whoami")
def whoami():
    # 仅用于调试，不泄露分片！
    return {"index": NODE_INDEX}

@app.post("/scan_share", response_model=ScanShareResp)
def scan_share(req: ScanShareReq):
    # 校验 R
    try:
        Rb = _h2b(req.R.strip())
    except Exception:
        raise HTTPException(status_code=400, detail="invalid hex for R")
    if len(Rb) != 33 or Rb[0] not in (2, 3):
        raise HTTPException(status_code=400, detail="R must be a 33-byte compressed pubkey (0x02/0x03...)")

    # 计算 Yi = y_i * R（点乘），输出压缩形式 33B
    try:
        R = PublicKey(Rb)
        # coincurve PublicKey.multiply 接受 32-byte big-endian 标量
        k_bytes = VIEW_SK_SHARE_INT.to_bytes(32, "big")
        Yi = R.multiply(k_bytes)                     # PublicKey
        Yi_comp = Yi.format(compressed=True)         # bytes(33)
        return ScanShareResp(i=NODE_INDEX, Yi=_b2h(Yi_comp))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"point multiply failed: {e}")
