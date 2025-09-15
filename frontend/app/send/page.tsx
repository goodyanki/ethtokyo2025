"use client";

import { useEffect, useRef, useState, type ReactNode, type MouseEvent } from "react";
import jsQR from "jsqr";
import { decodeReceiveCode } from "@/lib/receiveCode";
import { BrowserProvider, parseEther } from "ethers";
import { senderAssembleAnnouncement } from "@/lib/crypto.js";
import {
  Camera,
  QrCode,
  KeyRound,
  Wallet,
  Megaphone,
  Loader2,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  Copy,
} from "lucide-react";

type Decoded = {
  version: number;
  pubkeySpend: string; // 0x04... 65B
  pubkeyView: string;  // 0x02/0x03... 33B
  nonce: string;
  checksum: string;
};

type PostMode = "signal" | "announce";

export default function SendScanPage() {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const rafRef = useRef<number | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const [scanning, setScanning] = useState(false);
  const [rawCode, setRawCode] = useState<string>("");
  const [decoded, setDecoded] = useState<Decoded | null>(null);
  const [status, setStatus] = useState<string>("");

  // sending state
  const [amountEth, setAmountEth] = useState<string>("0.01");
  const [memo, setMemo] = useState<string>("");
  const [addr, setAddr] = useState<string>("");
  const [Rhex, setRhex] = useState<string>("");
  const [tagHex, setTagHex] = useState<string>("");
  const [txHash, setTxHash] = useState<string>("");

  // post channel: signal or announce
  const [postMode, setPostMode] = useState<PostMode>("announce");
  const [busy, setBusy] = useState<null | "scan" | "derive" | "send" | "announce">(null);

  const stopScan = () => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    setScanning(false);
  };

  useEffect(() => {
    return () => stopScan();
  }, []);

  const tick = () => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const w = video.videoWidth;
    const h = video.videoHeight;
    if (w && h) {
      canvas.width = w;
      canvas.height = h;
      ctx.drawImage(video, 0, 0, w, h);
      const imageData = ctx.getImageData(0, 0, w, h);
      const qr = jsQR(imageData.data, w, h);
      if (qr && qr.data) {
        stopScan();
        setRawCode(qr.data);
        decodeReceiveCode(qr.data)
          .then((d) => setDecoded(d as Decoded))
          .catch((e) => setStatus(`Decode failed: ${e?.message || String(e)}`));
        return;
      }
    }
    rafRef.current = requestAnimationFrame(tick);
  };

  const startScan = async () => {
    try {
      setBusy("scan");
      setStatus("");
      setRawCode("");
      setDecoded(null);
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" } },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setScanning(true);
      rafRef.current = requestAnimationFrame(tick);
    } catch (e: any) {
      setStatus(`Camera access failed: ${e?.message || String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  // Step 1: derive one-time address and announcement params
  const deriveOnce = async () => {
    try {
      setBusy("derive");
      setStatus("");
      setAddr(""); setRhex(""); setTagHex(""); setTxHash("");
      if (!decoded) {
        setStatus("Please scan a Receive Code first.");
        return;
      }
      const spend = decoded.pubkeySpend;
      const view  = decoded.pubkeyView;

      if (!(spend?.startsWith("0x") && view?.startsWith("0x"))) {
        setStatus("Invalid public key format in Receive Code.");
        return;
      }
      if (spend.length !== 2 + 65 * 2 || view.length !== 2 + 33 * 2) {
        setStatus("Invalid key length (need 65B uncompressed spend + 33B compressed view).");
        return;
      }

      const memoBytes = memo ? new TextEncoder().encode(memo) : undefined;
      const out = await senderAssembleAnnouncement({
        spendPubUncompressed: spend,
        viewPubCompressed: view,
        memoPlaintext: memoBytes,
      });
      setAddr(out.addr);
      setRhex(out.R);
      setTagHex(out.tag);
      setStatus("Derived one-time address & announcement params.");
    } catch (e: any) {
      setStatus(`Derivation failed: ${e?.message || String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  // Step 2: send ETH
  const sendEth = async () => {
    try {
      setBusy("send");
      setStatus("");
      if (!addr) {
        setStatus("Please derive a one-time address first.");
        return;
      }
      if (!(window as any).ethereum) {
        setStatus("No wallet detected (window.ethereum).");
        return;
      }
      const provider = new BrowserProvider((window as any).ethereum);
      const accounts = await (window as any).ethereum.request({ method: "eth_requestAccounts" });
      if (!accounts || accounts.length === 0) {
        setStatus("Wallet not connected.");
        return;
      }
      const signer = await provider.getSigner();
      const tx = await signer.sendTransaction({
        to: addr,
        value: parseEther(amountEth || "0.01"),
      });
      const receipt = await tx.wait();
      setTxHash(receipt?.hash || tx.hash);
      setStatus(`Payment sent to one-time address ${addr}.`);
    } catch (e: any) {
      setStatus(`Send failed: ${e?.message || String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  // Step 3: post announcement (Signal or Registry)
  const postAnnounce = async () => {
    try {
      setBusy("announce");
      setStatus("");

      if (!Rhex || !tagHex) {
        setStatus("Missing announcement params. Please derive first.");
        return;
      }
      const commitment = "0x" + "00".repeat(32);

      if (postMode === "announce") {
        // Registry.Announce(bytes,bytes,bytes32,bytes32)
        const body = {
          R: Rhex,
          tag: tagHex,
          memoCipher: null as any,
          commitment,
          txHash: txHash || null,
        };
        const res = await fetch("http://127.0.0.1:8000/sender/announce", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body),
        });
        const j = await res.json();
        if (!res.ok || j?.ok === false) throw new Error(j?.error || `HTTP ${res.status}`);
        setStatus("✅ Posted to Registry · Announce.");
      } else {
        // SignalBoard.Signal(bytes32,bool,bytes32,bytes)
        const hex = Rhex.toLowerCase();
        if (!hex.startsWith("0x") || hex.length !== 2 + 33 * 2) {
          throw new Error("Invalid R length (need 33B compressed public key).");
        }
        const prefix = hex.slice(2, 4);
        const rx = "0x" + hex.slice(4);
        const yParity = prefix === "03";

        const body = {
          rx,                      // bytes32
          yParity,                 // bool
          tag: tagHex,             // bytes32
          memo: "0x",              // optional ciphertext
          txHash: txHash || null,
        };
        const res = await fetch("http://127.0.0.1:8000/sender/signal", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body),
        });
        const j = await res.json();
        if (!res.ok || j?.ok === false) throw new Error(j?.error || `HTTP ${res.status}`);
        setStatus("✅ Posted to SignalBoard · Signal.");
      }
    } catch (e: any) {
      setStatus(`Announcement failed: ${e?.message || String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const copy = async (txt: string) => {
    try { await navigator.clipboard.writeText(txt); setStatus("Copied to clipboard."); } catch {}
  };

  const Pill = ({ ok, label }: { ok: boolean; label: string }) => (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] transition-colors
      ${ok ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-white text-slate-600"}`}>
      {ok ? <CheckCircle2 className="h-3.5 w-3.5" /> : <AlertCircle className="h-3.5 w-3.5" />}
      {label}
    </span>
  );

  return (
    <main className="relative min-h-screen bg-gradient-to-b from-white to-[#f7f9fc] text-[#0f172a]">
      {/* background accents */}
      <div className="pointer-events-none absolute -top-24 left-1/2 h-[420px] w-[620px] -translate-x-1/2 rounded-full bg-gradient-to-r from-indigo-400 via-sky-400 to-emerald-400 opacity-20 blur-3xl" />
      <div className="pointer-events-none absolute bottom-0 -left-28 h-[300px] w-[420px] rounded-full bg-gradient-to-tr from-fuchsia-400 via-pink-400 to-amber-300 opacity-20 blur-3xl" />

      <div className="relative mx-auto max-w-6xl px-6 py-12">
        {/* header */}
        <header className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Send · Private Payment</h1>
            <p className="mt-1 text-sm text-[#64748b]">Scan Receive Code → derive one-time address → pay → post announcement</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Pill ok={!!rawCode} label={rawCode ? "Scanned" : "Not scanned"} />
            <Pill ok={!!addr} label={addr ? "Address ready" : "Not derived"} />
            <Pill ok={!!txHash} label={txHash ? "Paid" : "Not paid"} />
          </div>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-start">
          {/* left: camera & status */}
          <div className="relative rounded-2xl border border-slate-200 bg-white/90 shadow-lg overflow-hidden">
            <div className="absolute inset-0 pointer-events-none [mask-image:radial-gradient(120%_80%_at_50%_-10%,#000_55%,transparent_85%)]">
              <div className="absolute inset-x-0 -top-20 mx-auto h-80 w-[90%] rounded-full bg-gradient-to-r from-indigo-400/20 via-sky-400/20 to-emerald-400/20 blur-2xl" />
            </div>
            <div className="relative p-4 flex items-center justify-between">
              <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-600 shadow-sm">
                <Camera className="h-3.5 w-3.5 text-slate-800" />
                {scanning ? "Scanning…" : "Idle"}
              </div>
              <div className="flex items-center gap-2">
                {!scanning ? (
                  <button
                    onClick={startScan}
                    disabled={busy !== null}
                    className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-sky-500 to-sky-600 px-4 py-2 text-sm text-white shadow hover:from-sky-600 hover:to-sky-700"
                  >
                    {busy === "scan" ? <Loader2 className="h-4 w-4 animate-spin" /> : <QrCode className="h-4 w-4" />}
                    Start scan
                  </button>
                ) : (
                  <button
                    onClick={stopScan}
                    className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-rose-500 to-rose-600 px-4 py-2 text-sm text-white shadow hover:from-rose-600 hover:to-rose-700"
                  >
                    Stop
                  </button>
                )}
              </div>
            </div>
            <video ref={videoRef} className="w-full h-[360px] object-cover bg-black/5" muted playsInline />
            <canvas ref={canvasRef} className="hidden" />
            {status && (
              <div className="p-4 text-sm text-slate-600 border-t border-slate-200 bg-white/70">
                {status}
              </div>
            )}
          </div>

          {/* right: steps & form */}
          <div className="space-y-6">
            {/* scan result */}
            <div className="rounded-2xl border border-slate-200 bg-white/90 p-4 shadow-sm">
              <div className="mb-3 text-sm font-semibold text-slate-900">Scan result</div>
              {rawCode ? (
                <div className="space-y-3">
                  <div className="text-xs break-all bg-slate-50 p-2 rounded border border-slate-200/70">
                    {rawCode}
                  </div>
                  {decoded ? (
                    <ul className="text-xs grid grid-cols-1 gap-1">
                      <li>version: {decoded.version}</li>
                      <li>spend: <span className="break-all font-mono">{decoded.pubkeySpend}</span></li>
                      <li>view: <span className="break-all font-mono">{decoded.pubkeyView}</span></li>
                      <li>nonce: <span className="break-all font-mono">{decoded.nonce}</span></li>
                      <li>checksum: <span className="break-all font-mono">{decoded.checksum}</span></li>
                    </ul>
                  ) : (
                    <div className="text-sm text-[#64748b]">Decoding…</div>
                  )}
                </div>
              ) : (
                <div className="text-sm text-[#64748b]">No QR detected</div>
              )}
            </div>

            {/* form */}
            <div className="rounded-2xl border border-slate-200 bg-white/90 p-4 shadow-sm space-y-4">
              <div className="grid sm:grid-cols-2 gap-3">
                <label className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm focus-within:ring-2 focus-within:ring-sky-500">
                  <span className="text-slate-600 w-20">Amount (ETH)</span>
                  <input
                    value={amountEth}
                    onChange={(e) => setAmountEth(e.target.value)}
                    className="w-full outline-none text-slate-900 placeholder:text-slate-400"
                    placeholder="0.01"
                  />
                </label>
                <label className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm focus-within:ring-2 focus-within:ring-sky-500">
                  <span className="text-slate-600 w-20">Memo</span>
                  <input
                    value={memo}
                    onChange={(e) => setMemo(e.target.value)}
                    className="w-full outline-none text-slate-900 placeholder:text-slate-400"
                    placeholder="optional"
                  />
                </label>
              </div>

              {/* channel */}
              <div className="flex items-center gap-3">
                <span className="text-sm text-slate-600 w-20">Post to</span>
                <Segmented
                  value={postMode}
                  onChange={(v) => setPostMode(v)}
                  options={[
                    { value: "announce", label: "Registry (Announce)" },
                    { value: "signal", label: "SignalBoard (Signal)" },
                  ]}
                />
              </div>

              {/* steps */}
              <div className="space-y-3">
                <Step
                  n={1}
                  title="Derive one-time address"
                  desc="Compute (R, tag, addr) from Receive Code"
                  icon={<KeyRound className="h-5 w-5 text-slate-800" />}
                  loading={busy === "derive"}
                  disabled={!decoded}
                  onAction={deriveOnce}
                  actionLabel="Derive"
                />
                <Step
                  n={2}
                  title="Send to stealth address"
                  desc="Use browser wallet to send ETH"
                  icon={<Wallet className="h-5 w-5 text-slate-800" />}
                  loading={busy === "send"}
                  disabled={!addr}
                  onAction={sendEth}
                  actionLabel="Send"
                />
                <Step
                  n={3}
                  title="Post on-chain announcement"
                  desc={postMode === "announce" ? "Post R / tag / commitment to Registry" : "Post rx / yParity / tag to SignalBoard"}
                  icon={<Megaphone className="h-5 w-5 text-slate-800" />}
                  loading={busy === "announce"}
                  disabled={!Rhex || !tagHex}
                  onAction={postAnnounce}
                  actionLabel="Post"
                />
              </div>

              {/* result */}
              {addr && (
                <div className="mt-2 space-y-2 rounded-xl border border-slate-200 bg-gradient-to-br from-blue-50 to-purple-50 p-3 text-xs">
                  <Row label="one-time addr" value={addr} onCopy={() => copy(addr)} />
                  <Row label="R (33B)" value={Rhex} onCopy={() => copy(Rhex)} />
                  <Row label="tag (32B)" value={tagHex} onCopy={() => copy(tagHex)} />
                  {txHash && <Row label="txHash" value={txHash} onCopy={() => copy(txHash)} />}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}

/* ---------------- components ---------------- */

function Step({
  n, title, desc, icon, onAction, actionLabel, disabled, loading,
}: {
  n: number;
  title: string;
  desc: string;
  icon: ReactNode;
  onAction: (e: MouseEvent<HTMLButtonElement>) => void;
  actionLabel: ReactNode;
  disabled?: boolean;
  loading?: boolean;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white/90 p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-xl border border-slate-200 bg-white shadow">
            {icon}
          </div>
          <div>
            <div className="text-sm font-semibold text-slate-900">{n}️⃣ {title}</div>
            <div className="text-xs text-slate-500">{desc}</div>
          </div>
        </div>
        <div className="min-w-[120px]">
          <button
            className={`inline-flex items-center justify-center gap-2 rounded-xl px-3 py-2 text-sm text-white transition-all
              ${disabled ? "opacity-60 cursor-not-allowed bg-slate-400"
                         : "bg-gradient-to-r from-slate-700 to-slate-900 hover:from-slate-800 hover:to-black shadow"}`}
            disabled={!!disabled || !!loading}
            onClick={onAction}
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
            <span>{actionLabel}</span>
          </button>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value, onCopy }: { label: string; value: string; onCopy?: () => void }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-28 shrink-0 text-slate-600">{label}</span>
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

function Segmented<T extends string>({
  value, onChange, options,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string }[];
}) {
  return (
    <div className="inline-flex items-center rounded-xl border border-slate-200 bg-white p-1 shadow-sm">
      {options.map((op) => {
        const active = op.value === value;
        return (
          <button
            key={op.value}
            onClick={() => onChange(op.value)}
            type="button"
            className={`mx-0.5 rounded-lg px-3 py-1.5 text-[12.5px] transition-colors ${
              active
                ? "bg-slate-900 text-white"
                : "text-slate-700 hover:bg-slate-100"
            }`}
          >
            {op.label}
          </button>
        );
      })}
    </div>
  );
}
