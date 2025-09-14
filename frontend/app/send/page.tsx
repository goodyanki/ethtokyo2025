"use client";

import { useEffect, useRef, useState } from "react";
import jsQR from "jsqr";
import { decodeReceiveCode } from "@/lib/receiveCode";
import { BrowserProvider, parseEther } from "ethers";
import { senderAssembleAnnouncement } from "@/lib/crypto.js";

type Decoded = {
  version: number;
  pubkeySpend: string; // 0x04... 65B
  pubkeyView: string;  // 0x02/0x03... 33B
  nonce: string;
  checksum: string;
};

export default function SendScanPage() {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const rafRef = useRef<number | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const [scanning, setScanning] = useState(false);
  const [rawCode, setRawCode] = useState<string>("");
  const [decoded, setDecoded] = useState<Decoded | null>(null);
  const [status, setStatus] = useState<string>("");

  // 新增：发送相关状态
  const [amountEth, setAmountEth] = useState<string>("0.01");
  const [memo, setMemo] = useState<string>("");
  const [addr, setAddr] = useState<string>("");
  const [Rhex, setRhex] = useState<string>("");
  const [tagHex, setTagHex] = useState<string>("");
  const [txHash, setTxHash] = useState<string>("");

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
          .catch((e) => setStatus(`解码失败: ${e?.message || String(e)}`));
        return;
      }
    }
    rafRef.current = requestAnimationFrame(tick);
  };

  const startScan = async () => {
    try {
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
      setStatus(`无法访问摄像头: ${e?.message || String(e)}`);
    }
  };

  // 第一步：基于收款码计算一次性地址与公告参数
  const deriveOnce = async () => {
    try {
      setStatus("");
      setAddr(""); setRhex(""); setTagHex(""); setTxHash("");
      if (!decoded) {
        setStatus("请先扫码获取收款码");
        return;
      }
      const spend = decoded.pubkeySpend;
      const view  = decoded.pubkeyView;

      // 简单校验长度
      if (!(spend?.startsWith("0x") && view?.startsWith("0x"))) {
        setStatus("收款码公钥格式错误");
        return;
      }
      if (spend.length !== 2 + 65 * 2 || view.length !== 2 + 33 * 2) {
        setStatus("公钥长度不符合（需要 65B 未压 spend + 33B 压缩 view）");
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
      setStatus("已生成一次性地址与公告参数");
    } catch (e: any) {
      setStatus(`派生失败: ${e?.message || String(e)}`);
    }
  };

  // 第二步：发送 ETH 到一次性地址
  const sendEth = async () => {
    try {
      setStatus("");
      if (!addr) {
        setStatus("请先生成一次性地址");
        return;
      }
      if (!(window as any).ethereum) {
        setStatus("未检测到钱包 (window.ethereum)");
        return;
      }
      const provider = new BrowserProvider((window as any).ethereum);
      const accounts = await (window as any).ethereum.request({ method: "eth_requestAccounts" });
      if (!accounts || accounts.length === 0) {
        setStatus("未连接钱包");
        return;
      }
      const signer = await provider.getSigner();
      const tx = await signer.sendTransaction({
        to: addr,
        value: parseEther(amountEth || "0.01"),
      });
      const receipt = await tx.wait();
      setTxHash(receipt?.hash || tx.hash);
      setStatus(`已转账到一次性地址 ${addr}`);
    } catch (e: any) {
      setStatus(`发送失败: ${e?.message || String(e)}`);
    }
  };

  // 第三步：把公告发给后端（后端去 publish()）
  const postAnnounce = async () => {
    try {
      setStatus("");
      if (!Rhex || !tagHex) {
        setStatus("缺少公告参数，请先生成一次性地址");
        return;
      }

      // 可选 commitment：这里 demo 先传全 0；也可以用 keccak(R||tag||txHash)
      const commitment = "0x" + "00".repeat(32);

      // 如果在 deriveOnce 里加密了 memo，这里应把 amountCipher 一并传给后端；
      // 这里为了简单，演示不附带密文
      const body = {
        R: Rhex,                           // 0x.. 33B
        tag: tagHex,                       // 0x.. 32B
        memoCipher: null as any,           // 或 {ephPub, iv, ct}
        commitment,
        txHash: txHash || null,            // 可选：方便后端做关联
      };

      const res = await fetch("http://127.0.0.1:8000/sender/announce", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const j = await res.json();
      if (!res.ok || j?.ok === false) {
        throw new Error(j?.error || `HTTP ${res.status}`);
      }
      setStatus("已提交公告给后端");
    } catch (e: any) {
      setStatus(`公告失败: ${e?.message || String(e)}`);
    }
  };

  return (
    <div className="min-h-screen bg-white text-[#0f172a] p-6">
      <div className="mx-auto max-w-3xl">
        <h1 className="text-2xl font-semibold mb-2">Scan & Send</h1>
        <p className="text-sm text-[#64748b] mb-6">
          扫描收款码 → 生成一次性地址 → 钱包转账 → 把公告发给后端（由后端上链 publish）
        </p>

        <div className="flex items-center gap-3 mb-6">
          {!scanning ? (
            <button onClick={startScan} className="rounded-xl bg-[#0ea5e9] text-white h-10 px-4 hover:bg-[#0284c7]">开始扫描</button>
          ) : (
            <button onClick={stopScan} className="rounded-xl bg-[#ef4444] text-white h-10 px-4 hover:bg-[#dc2626]">停止</button>
          )}
          {status && <span className="text-sm text-[#64748b]">{status}</span>}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-start">
          <div className="rounded-xl border border-[#e2e8f0] bg-white overflow-hidden">
            <video ref={videoRef} className="w-full h-[320px] object-cover bg-black/5" muted playsInline />
            <canvas ref={canvasRef} className="hidden" />
          </div>

          <div className="rounded-xl border border-[#e2e8f0] bg-white p-4 space-y-4">
            <h2 className="font-medium">识别结果</h2>
            {rawCode ? (
              <>
                <p className="text-xs break-all bg-gray-50 p-2 rounded">{rawCode}</p>
                {decoded ? (
                  <ul className="text-sm space-y-1">
                    <li>version: {decoded.version}</li>
                    <li>pubkeySpend: <span className="break-all font-mono">{decoded.pubkeySpend}</span></li>
                    <li>pubkeyView: <span className="break-all font-mono">{decoded.pubkeyView}</span></li>
                    <li>nonce: <span className="break-all font-mono">{decoded.nonce}</span></li>
                    <li>checksum: <span className="break-all font-mono">{decoded.checksum}</span></li>
                  </ul>
                ) : (
                  <p className="text-sm text-[#64748b]">正在解码...</p>
                )}
              </>
            ) : (
              <p className="text-sm text-[#64748b]">未检测到二维码</p>
            )}

            <div className="pt-2 border-t border-[#e2e8f0] space-y-3">
              <div className="flex items-center gap-2">
                <label className="text-sm w-20">金额(ETH)</label>
                <input
                  value={amountEth}
                  onChange={(e) => setAmountEth(e.target.value)}
                  className="flex-1 rounded border px-2 py-1 text-sm"
                  placeholder="0.01"
                />
              </div>
              <div className="flex items-center gap-2">
                <label className="text-sm w-20">备注(memo)</label>
                <input
                  value={memo}
                  onChange={(e) => setMemo(e.target.value)}
                  className="flex-1 rounded border px-2 py-1 text-sm"
                  placeholder="可选"
                />
              </div>

              <div className="flex gap-2">
                <button onClick={deriveOnce} className="rounded-lg bg-indigo-600 text-white px-3 py-2 text-sm hover:bg-indigo-700">
                  1) 生成一次性地址
                </button>
                <button onClick={sendEth} className="rounded-lg bg-emerald-600 text-white px-3 py-2 text-sm hover:bg-emerald-700" disabled={!addr}>
                  2) 转账到一次性地址
                </button>
                <button onClick={postAnnounce} className="rounded-lg bg-slate-700 text-white px-3 py-2 text-sm hover:bg-slate-800" disabled={!Rhex || !tagHex}>
                  3) 提交公告
                </button>
              </div>

              {addr && (
                <div className="text-xs bg-gray-50 p-2 rounded break-all">
                  <div>addr: <span className="font-mono">{addr}</span></div>
                  <div>R: <span className="font-mono">{Rhex}</span></div>
                  <div>tag: <span className="font-mono">{tagHex}</span></div>
                  {txHash && <div>txHash: <span className="font-mono">{txHash}</span></div>}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
