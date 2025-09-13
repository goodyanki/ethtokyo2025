"use client";
import { BrowserProvider, JsonRpcProvider, Contract, getAddress } from "ethers";

import { useEffect, useMemo, useState } from "react";
import { genProof, toSolidityCalldata, verifyOffchain } from "@/lib/zk";
import { SHIELD_ABI } from "@/lib/abi";

export default function ZkPage() {
  const [amount, setAmount] = useState("60000");
  const [threshold, setThreshold] = useState("50000");
  const [addr, setAddr] = useState<string>(process.env.NEXT_PUBLIC_SHIELD_ADDRESS || "");
  const [status, setStatus] = useState("");
  const [chainId, setChainId] = useState<string>("-");

  const rpcUrl = process.env.NEXT_PUBLIC_RPC_URL || "http://localhost:8545";
  const readonly = useMemo(() => new JsonRpcProvider(rpcUrl), [rpcUrl]);

  useEffect(() => {
    (async () => {
      try {
        const net = await readonly.getNetwork();
        setChainId(net.chainId.toString());
      } catch {}
    })();
  }, [readonly]);

  const run = async () => {
    try {
      setStatus("");
      // Normalize and validate address
      let target: string;
      try {
        target = getAddress(addr.trim());
      } catch {
        setStatus("Invalid verifier address; must be 0x-prefixed 20-byte hex.");
        return;
      }

      // Use fixed RPC to read chain and contract code
      const net = await readonly.getNetwork();
      setChainId(net.chainId.toString());
      const code = await readonly.getCode(target);
      if (!code || code === "0x") {
        setStatus("No contract code at this address on RPC network.");
        return;
      }

      setStatus("Generating proof...");
      const { proof, publicSignals } = await genProof({ amount, threshold });

      // 可选：在前端先本地验证（需要 public/zk/verification_key.json）
      try {
        const ok = await verifyOffchain(proof, publicSignals);
        setStatus((s) => s + `\nOffchain verify: ${ok}`);
      } catch {}

      setStatus((s) => s + "\nFormatting calldata...");
      const { a, b, c, input } = await toSolidityCalldata(proof, publicSignals);

      // 你的合约是 view 函数，直接 call 即可
      setStatus((s) => s + "\nCalling verifyIncome (static call via RPC)...");
      const shield = new Contract(target, SHIELD_ABI, readonly);
      // Shield.verifyIncome 接受动态数组 publicInputs，电路共有两个公开信号
      // 一些类型定义下 TS 可能对 staticCall 报红，这里用 any 规避编辑器误报
      const result: boolean = await (shield as any).verifyIncome.staticCall(a, b, c, input);
      setStatus((s) => s + `\nOnchain verifyIncome: ${result}`);
    } catch (e: any) {
      console.error(e);
      setStatus(`Error: ${e?.message || String(e)}`);
    }
  };

  return (
    <div style={{ maxWidth: 520 }}>
      <h2>Income Threshold ZK Demo</h2>
      <div style={{ display: 'grid', gap: 8 }}>
        <div>Chain ID: {chainId}</div>
        <label>
          Shield Address
          <input value={addr} onChange={(e) => setAddr(e.target.value)} placeholder="0x..." style={{ width: '100%' }} />
        </label>
        <label>
          Amount
          <input value={amount} onChange={(e) => setAmount(e.target.value)} style={{ width: '100%' }} />
        </label>
        <label>
          Threshold
          <input value={threshold} onChange={(e) => setThreshold(e.target.value)} style={{ width: '100%' }} />
        </label>
        <button onClick={run}>Generate & Verify</button>
        <button
          onClick={async () => {
            try {
              await (window as any).ethereum.request({
                method: "wallet_switchEthereumChain",
                params: [{ chainId: "0x7a69" }]
              });
              const provider = new BrowserProvider((window as any).ethereum);
              const net = await provider.getNetwork();
              setChainId(net.chainId.toString());
            } catch (e: any) {
              setStatus(
                "Switch network failed. Please add it manually in your wallet: RPC http://localhost:8545, Chain ID 31337, Name Anvil (Local), Symbol ETH."
              );
            }
          }}
        >
          Switch to Local (31337)
        </button>
      </div>
      <pre style={{ marginTop: 12, background: '#f6f8fa', padding: 12, borderRadius: 8, whiteSpace: 'pre-wrap' }}>{status}</pre>
      <p style={{ marginTop: 8 }}>Artifacts expected at /zk/income_threshold.wasm and /zk/income_threshold_final.zkey.</p>
    </div>
  );
}
