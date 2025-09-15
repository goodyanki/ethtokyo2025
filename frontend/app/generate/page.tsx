"use client";

import { useEffect, useState } from "react";
import { QRCodeCanvas } from "qrcode.react";
import { BrowserProvider } from "ethers";
import {
  encodeReceiveCode,
  derivePubkeysFromAddress,
  generateNonce16,
} from "@/lib/receiveCode.js";
import {
  Wallet,
  QrCode,
  Loader2,
  Copy,
  CheckCircle2,
  AlertCircle,
  ChevronDown,
  KeyRound,
} from "lucide-react";

export default function GeneratePage() {
  const [provider, setProvider] = useState<BrowserProvider | null>(null);
  const [accounts, setAccounts] = useState<string[]>([]);
  const [account, setAccount] = useState<string>("");
  const [chainId, setChainId] = useState<string>("");
  const [receiveCode, setReceiveCode] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState<null | "connect" | "generate">(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [derived, setDerived] = useState<{ spend?: string; view?: string }>({});

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
      setBusy("connect");
      const eth = (window as any).ethereum;
      if (!eth) {
        setStatus("No wallet detected (window.ethereum)");
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
      setStatus(`✅ Connected · chainId=${net.chainId.toString()}`);
    } catch (e: any) {
      setStatus(`Connection failed: ${e?.message || String(e)}`);
    } finally {
      setBusy(null);
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
      setStatus(`Re-selection failed: ${e?.message || String(e)}`);
    }
  };

  const handleGenerate = async () => {
    try {
      setBusy("generate");
      setStatus("");
      setReceiveCode("");
      setDerived({});
      if (!account) {
        await connect();
        if (!account) return;
      }
      // 从所选地址派生“收款码用的公钥”（65B spend / 33B view）
      const { spend, view } = derivePubkeysFromAddress(account);
      const nonce = generateNonce16();
      const code = await encodeReceiveCode(spend, view, nonce);
      setReceiveCode(code);
      setDerived({ spend, view });
      setStatus("🎉 Receive code generated!");
    } catch (e: any) {
      setStatus(`Generation failed: ${e?.message || String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const copy = async (txt: string) => {
    try {
      await navigator.clipboard.writeText(txt);
      setStatus("Copied to clipboard");
    } catch {}
  };

  const Pill = ({ ok, label }: { ok: boolean; label: string }) => (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] transition-colors
      ${ok ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-white text-slate-600"}`}
    >
      {ok ? <CheckCircle2 className="h-3.5 w-3.5" /> : <AlertCircle className="h-3.5 w-3.5" />}
      {label}
    </span>
  );

  const short = (addr: string) => (addr ? `${addr.slice(0, 6)}…${addr.slice(-4)}` : "");

  return (
    <main className="relative min-h-screen bg-gradient-to-b from-white to-[#f7f9fc] text-[#0f172a]">
      {/* 背景点缀 */}
      <div className="pointer-events-none absolute -top-28 left-1/2 h-[460px] w-[680px] -translate-x-1/2 rounded-full bg-gradient-to-r from-indigo-400 via-sky-400 to-emerald-400 opacity-20 blur-3xl" />
      <div className="pointer-events-none absolute bottom-0 -right-24 h-[320px] w-[460px] rounded-full bg-gradient-to-tr from-fuchsia-400 via-pink-400 to-amber-300 opacity-20 blur-3xl" />

      <div className="relative mx-auto max-w-6xl px-6 py-12">
        {/* 顶部 */}
        <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Receive · Generate Receive Code</h1>
            <p className="mt-1 text-sm text-[#64748b]">
              Connect wallet → select account → one-click generate receive code (includes spend/view pubkeys & checksum)
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Pill ok={!!provider} label={provider ? "Wallet connected" : "Not connected"} />
            <Pill ok={!!account} label={account ? short(account) : "No account"} />
            <Pill ok={!!chainId} label={chainId ? `chainId=${chainId}` : "Network unknown"} />
          </div>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-start">
          {/* 左侧：连接 & 账户 */}
          <section className="rounded-2xl border border-slate-200 bg-white/90 shadow-lg overflow-hidden">
            <div className="relative p-5 flex items-center justify-between">
              <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-600 shadow-sm">
                <Wallet className="h-3.5 w-3.5 text-slate-800" />
                {provider ? "Wallet connected" : "Not connected"}
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={connect}
                  disabled={busy === "connect"}
                  className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-sky-500 to-sky-600 px-4 py-2 text-sm text-white shadow hover:from-sky-600 hover:to-sky-700"
                >
                  {busy === "connect" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wallet className="h-4 w-4" />}
                  {provider ? "Reconnect" : "Connect Wallet"}
                </button>
                <button
                  onClick={reselectAccounts}
                  className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm hover:bg-slate-50"
                >
                  Change accounts…
                </button>
              </div>
            </div>

            <div className="border-t border-slate-200/70 p-5">
              {accounts.length > 0 ? (
                <label className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm focus-within:ring-2 focus-within:ring-sky-500">
                  <span className="text-slate-600 w-20">Account</span>
                  <select
                    value={account}
                    onChange={(e) => setAccount(e.target.value)}
                    className="w-full outline-none text-slate-900 bg-transparent"
                  >
                    {accounts.map((a) => (
                      <option key={a} value={a}>
                        {a}
                      </option>
                    ))}
                  </select>
                </label>
              ) : (
                <div className="text-sm text-slate-500">
                  Account access not granted yet. Click "Connect Wallet" above.
                </div>
              )}
            </div>
          </section>

          {/* 右侧：生成收款码 & 结果 */}
          <section className="space-y-6">
            <div className="rounded-2xl border border-slate-200 bg-white/90 p-5 shadow-lg">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="grid h-10 w-10 place-items-center rounded-xl border border-slate-200 bg-white shadow">
                    <KeyRound className="h-5 w-5 text-slate-800" />
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-slate-900">Generate Receive Code</div>
                    <div className="text-xs text-slate-500">
                      Derive spend/view pubkeys from the selected address and package into a Base58 receive code
                    </div>
                  </div>
                </div>
                <button
                  onClick={handleGenerate}
                  disabled={!account || busy === "generate"}
                  className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm text-white transition-all ${
                    !account
                      ? "bg-slate-400 cursor-not-allowed"
                      : "bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-700 hover:to-indigo-800 shadow"
                  }`}
                >
                  {busy === "generate" ? <Loader2 className="h-4 w-4 animate-spin" /> : <QrCode className="h-4 w-4" />}
                  Generate
                </button>
              </div>

              {receiveCode && (
                <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-5 items-start">
                  <div className="rounded-xl border border-slate-200 bg-white p-3">
                    <div className="text-xs font-medium text-slate-700 mb-2">Receive Code (Base58)</div>
                    <div className="relative">
                      <p className="text-xs break-all font-mono bg-slate-50 p-2 rounded border border-slate-200/70">
                        {receiveCode}
                      </p>
                      <button
                        onClick={() => copy(receiveCode)}
                        className="absolute -top-3 -right-3 inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-700 hover:bg-slate-50"
                        title="Copy receive code"
                      >
                        <Copy className="h-3.5 w-3.5" /> copy
                      </button>
                    </div>
                  </div>

                  <div className="grid place-items-center rounded-xl border border-slate-200 bg-white p-4">
                    <QRCodeCanvas value={receiveCode} size={220} />
                  </div>
                </div>
              )}
            </div>

            {/* 高级信息（可折叠） */}
            <div className="rounded-2xl border border-slate-200 bg-white/90 p-5 shadow-sm">
              <button
                onClick={() => setShowAdvanced((s) => !s)}
                className="inline-flex items-center gap-1 text-sm text-slate-700 hover:text-slate-900"
              >
                <ChevronDown
                  className={`h-4 w-4 transition-transform ${showAdvanced ? "rotate-180" : ""}`}
                />
                Advanced · View derived pubkeys (65B/33B)
              </button>

              {showAdvanced && (
                <div className="mt-4 space-y-3 text-xs">
                  <Row
                    label="spend (65B uncompressed)"
                    value={derived.spend || ""}
                    onCopy={() => derived.spend && copy(derived.spend)}
                  />
                  <Row
                    label="view (33B compressed)"
                    value={derived.view || ""}
                    onCopy={() => derived.view && copy(derived.view)}
                  />
                </div>
              )}
            </div>

            {/* 状态栏 */}
            {status && (
              <div className="rounded-xl border border-slate-200 bg-white/90 p-3 text-sm text-slate-700">
                {status}
              </div>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}

/* ---------------- components ---------------- */

function Row({ label, value, onCopy }: { label: string; value: string; onCopy?: () => void }) {
  if (!value) return null;
  return (
    <div className="flex items-center gap-2">
      <span className="w-52 shrink-0 text-slate-600">{label}</span>
      <span className="grow break-all font-mono">{value}</span>
      {onCopy && (
        <button
          onClick={onCopy}
          className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-700 hover:bg-slate-50"
          title="Copy"
        >
          <Copy className="h-3.5 w-3.5" /> copy
        </button>
      )}
    </div>
  );
}
