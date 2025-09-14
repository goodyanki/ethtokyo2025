"use client";

import { useState } from "react";
import { QRCodeCanvas } from "qrcode.react";
import { BrowserProvider } from "ethers";
import { encodeReceiveCode, derivePubkeysFromAddress, generateNonce16 } from "@/lib/receiveCode";

export default function GeneratePage() {
  const [receiveCode, setReceiveCode] = useState("");
  const [account, setAccount] = useState<string>("");
  const [status, setStatus] = useState<string>("");

  const connect = async () => {
    try {
      if (!(window as any).ethereum) {
        setStatus("未检测到钱包 (window.ethereum)");
        return;
      }
      const provider = new BrowserProvider((window as any).ethereum);
      const accounts = await (window as any).ethereum.request({ method: "eth_requestAccounts" });
      setAccount(accounts?.[0] || "");
      const net = await provider.getNetwork();
      setStatus(`Connected. chainId=${net.chainId.toString()}`);
    } catch (e: any) {
      setStatus(`连接失败: ${e?.message || String(e)}`);
    }
  };

  const handleGenerate = async () => {
    try {
      setStatus("");
      if (!account) {
        await connect();
        if (!account) return;
      }
      // 基于钱包地址本地派生两个32B“公钥”标识（示例用途，生产建议使用真正的加密公钥或 EIP-5630 等标准）
      const { spend, view } = derivePubkeysFromAddress(account);
      const nonce = generateNonce16(); // Web Crypto RNG
      const code = await encodeReceiveCode(spend, view, nonce);
      setReceiveCode(code);
    } catch (e: any) {
      setStatus(`生成失败: ${e?.message || String(e)}`);
    }
  };

  return (
    <div className="flex flex-col items-center gap-6 p-10">
      <h1 className="text-2xl font-bold">Generate OTP</h1>

      <div className="flex items-center gap-3">
        <button onClick={connect} className="rounded bg-gray-200 px-3 py-2">Connect to Wallet</button>
        <span className="text-sm">{account ? `connected: ${account}` : "disconnected"}</span>
      </div>

      <button
        onClick={handleGenerate}
        className="rounded-lg bg-blue-600 text-white px-4 py-2 hover:bg-blue-700 transition-colors"
      >
        Generate
      </button>

      {receiveCode && (
        <div className="flex flex-col items-center gap-4">
          <p className="break-all text-sm font-mono bg-gray-100 p-2 rounded">
            {receiveCode}
          </p>
          <QRCodeCanvas value={receiveCode} size={256} />
        </div>
      )}

      {status && <p className="text-sm text-gray-600">{status}</p>}
    </div>
  );
}
