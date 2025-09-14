"use client";

import { useEffect, useState } from "react";
import { QRCodeCanvas } from "qrcode.react";
import { BrowserProvider } from "ethers";
import {
  encodeReceiveCode,
  derivePubkeysFromAddress,
  generateNonce16,
} from "@/lib/receiveCode.js";

export default function GeneratePage() {
  const [provider, setProvider] = useState<BrowserProvider | null>(null);
  const [accounts, setAccounts] = useState<string[]>([]);
  const [account, setAccount] = useState<string>("");
  const [chainId, setChainId] = useState<string>("");
  const [receiveCode, setReceiveCode] = useState("");
  const [status, setStatus] = useState("");

  // 监听 metamask 账户/网络切换
  useEffect(() => {
    const eth = (window as any).ethereum;
    if (!eth) return;

    const onAcc = (accs: string[]) => {
      setAccounts(accs || []);
      if (accs?.length) setAccount((prev) => (accs.includes(prev) ? prev : accs[0]));
    };
    const onChain = (cid: string) => setChainId(parseInt(cid, 16).toString());

    eth.on?.("accountsChanged", onAcc);
    eth.on?.("chainChanged", onChain);
    return () => {
      eth.removeListener?.("accountsChanged", onAcc);
      eth.removeListener?.("chainChanged", onChain);
    };
  }, []);

  const connect = async () => {
    try {
      const eth = (window as any).ethereum;
      if (!eth) {
        setStatus("未检测到钱包 (window.ethereum)");
        return;
      }
      const prov = new BrowserProvider(eth);
      setProvider(prov);

      // 打开账户选择器（可多选）
      const accs: string[] = await eth.request({ method: "eth_requestAccounts" });
      setAccounts(accs || []);
      setAccount(accs?.[0] || "");

      const net = await prov.getNetwork();
      setChainId(net.chainId.toString());
      setStatus(`Connected. chainId=${net.chainId.toString()}`);
    } catch (e: any) {
      setStatus(`连接失败: ${e?.message || String(e)}`);
    }
  };

  // 重新弹出 MetaMask 账户权限选择器（可更换勾选的地址）
  const reselectAccounts = async () => {
    try {
      const eth = (window as any).ethereum;
      if (!eth) return;
      await eth.request({
        method: "wallet_requestPermissions",
        params: [{ eth_accounts: {} }],
      });
      // 重新取一次选中的账户
      const accs: string[] = await eth.request({ method: "eth_requestAccounts" });
      setAccounts(accs || []);
      setAccount(accs?.[0] || "");
    } catch (e: any) {
      setStatus(`重新选择失败: ${e?.message || String(e)}`);
    }
  };

  const handleGenerate = async () => {
    try {
      setStatus("");
      if (!account) {
        await connect();
        if (!account) return;
      }
      // 从所选地址派生“收款码用的公钥”（你的 receiveCode.js 里已改为 secp 公钥 65B/33B）
      const { spend, view } = derivePubkeysFromAddress(account);
      const nonce = generateNonce16();
      const code = await encodeReceiveCode(spend, view, nonce);
      setReceiveCode(code);
      setStatus("收款码已生成");
    } catch (e: any) {
      setStatus(`生成失败: ${e?.message || String(e)}`);
    }
  };

  return (
    <div className="flex flex-col items-center gap-6 p-10">
      <h1 className="text-2xl font-bold">Generate OTP</h1>

      <div className="flex flex-col gap-3 items-start w-full max-w-3xl">
        <div className="flex items-center gap-3">
          <button onClick={connect} className="rounded bg-gray-200 px-3 py-2">
            Connect
          </button>

          <button onClick={reselectAccounts} className="rounded bg-gray-200 px-3 py-2">
            选择账户…
          </button>

          <span className="text-sm">
            {account ? `connected: ${account}` : "disconnected"}
            {chainId && ` · chainId=${chainId}`}
          </span>
        </div>

        {accounts.length > 0 && (
          <div className="flex items-center gap-2">
            <label className="text-sm">使用账户</label>
            <select
              value={account}
              onChange={(e) => setAccount(e.target.value)}
              className="rounded border px-2 py-1 text-sm min-w-[360px]"
            >
              {accounts.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </div>
        )}
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
