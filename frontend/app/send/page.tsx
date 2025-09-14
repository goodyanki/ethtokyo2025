"use client";

import { useEffect, useRef, useState } from "react";
import jsQR from "jsqr";
import { decodeReceiveCode } from "@/lib/receiveCode";

type Decoded = {
  version: number;
  pubkeySpend: string;
  pubkeyView: string;
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

  return (
    <div className="min-h-screen bg-white text-[#0f172a] p-6">
      <div className="mx-auto max-w-3xl">
        <h1 className="text-2xl font-semibold mb-4">Scan</h1>
        <p className="text-sm text-[#64748b] mb-6">使用摄像头扫描接收方生成的二维码</p>

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

          <div className="rounded-xl border border-[#e2e8f0] bg-white p-4">
            <h2 className="font-medium mb-2">识别结果</h2>
            {rawCode ? (
              <>
                <p className="text-xs break-all bg-gray-50 p-2 rounded mb-3">{rawCode}</p>
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
          </div>
        </div>
      </div>
    </div>
  );
}

