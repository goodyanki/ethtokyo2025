// frontend/app/claim/page.tsx
"use client";

import { useState } from "react";
import { deriveOneTimePrivKey, sweepNative, sweepERC20 } from "@/lib/sweep";

const RPC_URL = process.env.NEXT_PUBLIC_RPC_URL || "http://127.0.0.1:8545";

export default function ClaimPage() {
  const [baseAddr, setBaseAddr] = useState("0x70997970C51812dc3A010C7d01b50e0d17dc79C8"); // demo 默认
  const [R, setR] = useState("");            // 0x02/03.. 压缩公钥(33B)
  const [to, setTo] = useState("");          // 你的主钱包地址
  const [token, setToken] = useState("");    // 为空则转 ETH，填合约地址则转 Token
  const [pHex, setPHex] = useState("");
  const [addrP, setAddrP] = useState("");
  const [status, setStatus] = useState("");

  async function onDerive() {
    try {
      setStatus("Deriving one-time private key...");
      const p = await deriveOneTimePrivKey(R.trim(), baseAddr.trim());
      setPHex(p);

      // 计算一次性地址（可选：给用户信心）
      const { ethers } = await import("ethers");
      const wallet = new ethers.Wallet(p);
      setAddrP(await wallet.getAddress());
      setStatus("Derived.");
    } catch (e: any) {
      console.error(e);
      setStatus("Derive failed: " + e.message);
    }
  }

  async function onSweep() {
    try {
      if (!pHex) throw new Error("please derive p first");
      setStatus("Sweeping...");
      if (token.trim()) {
        const receipt = await sweepERC20({ rpcUrl: RPC_URL, tokenAddress: token.trim(), fromPrivHex: pHex, toAddress: to.trim() });
        setStatus("Token swept. Tx: " + receipt?.hash);
      } else {
        const receipt = await sweepNative({ rpcUrl: RPC_URL, fromPrivHex: pHex, toAddress: to.trim() });
        setStatus("ETH swept. Tx: " + receipt?.hash);
      }
    } catch (e: any) {
      console.error(e);
      setStatus("Sweep failed: " + e.message);
    }
  }

  return (
    <main className="mx-auto max-w-2xl p-6 space-y-4">
      <h1 className="text-2xl font-semibold">领取 / 转出（Sweep）</h1>

      <label className="block">
        <div className="text-sm text-gray-600">基础地址（生成收款码用的地址）</div>
        <input value={baseAddr} onChange={e=>setBaseAddr(e.target.value)} className="w-full border rounded p-2" />
      </label>

      <label className="block">
        <div className="text-sm text-gray-600">R（33B 压缩公钥，0x02/03 开头）</div>
        <input value={R} onChange={e=>setR(e.target.value)} className="w-full border rounded p-2" placeholder="0x02..." />
      </label>

      <label className="block">
        <div className="text-sm text-gray-600">目标主钱包地址（接收最终资金）</div>
        <input value={to} onChange={e=>setTo(e.target.value)} className="w-full border rounded p-2" placeholder="0x..." />
      </label>

      <label className="block">
        <div className="text-sm text-gray-600">（可选）ERC-20 合约地址（留空则转 ETH）</div>
        <input value={token} onChange={e=>setToken(e.target.value)} className="w-full border rounded p-2" placeholder="0xToken…" />
      </label>

      <div className="flex gap-3">
        <button onClick={onDerive} className="px-4 py-2 rounded bg-indigo-600 text-white">1) 计算一次性私钥</button>
        <button onClick={onSweep} className="px-4 py-2 rounded bg-emerald-600 text-white">2) 转出</button>
      </div>

      {pHex && (
        <div className="mt-3 text-sm">
          <div>一次性私钥 p：<code className="break-all">{pHex}</code></div>
          <div>一次性地址 P：<code className="break-all">{addrP}</code></div>
        </div>
      )}

      <div className="text-sm text-gray-700">{status}</div>

      <p className="text-xs text-gray-500">
        提示：如果转 ERC-20，需要一次性地址里有少量 ETH 支付 gas。此页面所有计算与签名都在浏览器本地完成，私钥不会上传。
      </p>
    </main>
  );
}
