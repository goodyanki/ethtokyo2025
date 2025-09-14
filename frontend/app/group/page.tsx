"use client";

import React, { useMemo, useState } from "react";
import { ethers } from "ethers";

// 下拉选择 node1..node10；连接钱包；输入 Vault 地址与金额；点击转账（锁款）
// 如需加密 note：把 note 改成 eciesEncryptToViewPub(...) 的结果并确保合约有 lockETHWithNote

const VAULT_ABI = [
  "event Locked(bytes32 indexed escrowId, address indexed payer, address indexed token, uint256 amount)",
  "event LockedWithNote(bytes32 indexed escrowId, address indexed payer, address indexed token, uint256 amount, bytes note)",
  "event Withdrawn(bytes32 indexed escrowId, address indexed to, uint256 amount, uint256 nullifierHash)",
  "function lockETH(bytes32 escrowId) payable",
  "function lockETHWithNote(bytes32 escrowId, bytes note) payable",
];

function cls(...s: Array<string | false | null | undefined>) {
  return s.filter(Boolean).join(" ");
}
function short(addr?: string | null) {
  return addr ? `${addr.slice(0, 6)}…${addr.slice(-4)}` : "";
}
function randBytes32(): string {
  const b = new Uint8Array(32);
  crypto.getRandomValues(b);
  return ethers.hexlify(b);
}

export default function GroupTransferPage() {
  const [selectedNode, setSelectedNode] = useState("node1");
  const [vaultAddress, setVaultAddress] = useState("");
  const [amountEth, setAmountEth] = useState("");
  const [connected, setConnected] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [txHash, setTxHash] = useState<string | null>(null);
  const [escrowId, setEscrowId] = useState<string>(randBytes32());

  const canSubmit = useMemo(() => {
    return !!connected && ethers.isAddress(vaultAddress) && !!amountEth && !busy;
  }, [connected, vaultAddress, amountEth, busy]);

  async function connectWallet() {
    try {
      // @ts-ignore
      if (!window.ethereum) {
        alert("请安装 MetaMask 或兼容钱包扩展");
        return;
      }
      // @ts-ignore
      const provider = new ethers.BrowserProvider(window.ethereum);
      await provider.send("eth_requestAccounts", []);
      const signer = await provider.getSigner();
      const addr = await signer.getAddress();
      setConnected(addr);
    } catch (e: any) {
      console.error(e);
      alert(e?.message || "连接钱包失败");
    }
  }

  async function handleTransfer() {
    setStatus(null);
    setTxHash(null);
    setBusy(true);
    try {
      // @ts-ignore
      const provider = new ethers.BrowserProvider(window.ethereum);
      const signer = await provider.getSigner();
      const vault = new ethers.Contract(vaultAddress, VAULT_ABI, signer);

      const value = ethers.parseEther(amountEth);
      const note = new Uint8Array(0); // MVP：无加密 note；后续替换为加密后的字节

      setStatus("发送交易中…");

      let tx;
      try {
        tx = await vault.lockETHWithNote(escrowId, note, { value });
      } catch {
        tx = await vault.lockETH(escrowId, { value });
      }

      setStatus("等待上链确认…");
      const receipt = await tx.wait();
      setTxHash(receipt?.hash ?? tx.hash);
      setStatus("✅ 转账/锁款成功！");

      // 下一次自动换新 escrowId
      setEscrowId(randBytes32());
    } catch (err: any) {
      console.error(err);
      setStatus(`❌ 失败：${err?.reason || err?.message || String(err)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen w-full bg-gray-50 flex items-center justify-center p-6">
      <div className="w-full max-w-xl bg-white rounded-2xl shadow-xl p-6 space-y-6">
        <h1 className="text-2xl font-semibold">匿名付款 · MVP</h1>
        <p className="text-sm text-gray-500">
          选择节点，连接钱包，输入金额，点击「转账（锁款）」。默认调用
          <code className="mx-1">lockETHWithNote</code>，若无则回退
          <code className="mx-1">lockETH</code>。
        </p>

        {/* Node selector */}
        <div className="space-y-2">
          <label className="text-sm font-medium">选择节点</label>
          <select
            value={selectedNode}
            onChange={(e) => setSelectedNode(e.target.value)}
            className="w-full rounded-xl border border-gray-300 bg-white p-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {Array.from({ length: 10 }, (_, i) => `node${i + 1}`).map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
          <p className="text-xs text-gray-400">（此选择项供你做节点路由用，MVP 仅展示）</p>
        </div>

        {/* Vault address */}
        <div className="space-y-2">
          <label className="text-sm font-medium">Vault 合约地址</label>
          <input
            placeholder="0x..."
            value={vaultAddress}
            onChange={(e) => setVaultAddress(e.target.value.trim())}
            className="w-full rounded-xl border border-gray-300 bg-white p-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>

        {/* Amount */}
        <div className="space-y-2">
          <label className="text-sm font-medium">金额（ETH）</label>
          <input
            type="number"
            min="0"
            step="0.0001"
            placeholder="0.01"
            value={amountEth}
            onChange={(e) => setAmountEth(e.target.value)}
            className="w-full rounded-xl border border-gray-300 bg-white p-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>

        {/* Escrow ID */}
        <div className="space-y-1">
          <label className="text-sm font-medium">Escrow ID（自动生成）</label>
          <div className="text-xs font-mono break-all bg-gray-50 border rounded-xl p-2">
            {escrowId}
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-3">
          <button
            onClick={connectWallet}
            className={cls(
              "px-4 py-2 rounded-xl border transition",
              connected
                ? "bg-green-50 border-green-200 text-green-700"
                : "bg-indigo-600 border-indigo-600 text-white hover:bg-indigo-700"
            )}
          >
            {connected ? `已连接 ${short(connected)}` : "连接钱包"}
          </button>
          <button
            disabled={!canSubmit}
            onClick={handleTransfer}
            className={cls(
              "px-4 py-2 rounded-xl transition",
              canSubmit
                ? "bg-black text-white hover:bg-gray-800"
                : "bg-gray-200 text-gray-500 cursor-not-allowed"
            )}
          >
            {busy ? "发送中…" : "转账（锁款）"}
          </button>
        </div>

        {/* Status */}
        {status && (
          <div className="text-sm text-gray-700 bg-gray-100 rounded-xl p-3">
            {status}
            {txHash && (
              <div className="mt-1 break-all font-mono text-xs">tx: {txHash}</div>
            )}
          </div>
        )}

        <div className="pt-2 border-t text-xs text-gray-400">
          如需加密 signal，请在调用前用收款方 <code>pub_view</code> 生成
          <code className="mx-1">note</code>，然后调用{" "}
          <code>lockETHWithNote(escrowId, note)</code>。
        </div>
      </div>
    </div>
  );
}
