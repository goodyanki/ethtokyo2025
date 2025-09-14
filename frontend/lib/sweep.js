// frontend/lib/sweep.js
"use client";

import { keccak_256 } from "@noble/hashes/sha3";
import * as secp from "@noble/secp256k1";
import { BrowserProvider, JsonRpcProvider, Wallet, Contract } from "ethers";

// === secp256k1 阶（用常量替代 secp.CURVE.n） ===
const N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141n;

/* ---------- utils ---------- */
const hexToBytes = (hex) => {
  const s = hex.startsWith("0x") ? hex.slice(2) : hex;
  if (s.length % 2) throw new Error("hex length must be even");
  const out = new Uint8Array(s.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(s.slice(i * 2, i * 2 + 2), 16);
  return out;
};
const bytesToHex = (b) =>
  "0x" + Array.from(b).map((x) => x.toString(16).padStart(2, "0")).join("");

async function sha256(u8) {
  const d = await crypto.subtle.digest("SHA-256", u8);
  return new Uint8Array(d);
}

// noble 的 sharedSecret 统一取 X(32B)
function normalizeSharedSecret(bytes) {
  if (bytes.length === 32) return bytes;
  if (bytes.length === 33) return bytes.slice(1);
  if (bytes.length === 65) return bytes.slice(1, 33);
  throw new Error(`unexpected shared secret length=${bytes.length}`);
}

/* ---------- 从“基础地址”派生 spend/view 私钥（与现有逻辑一致） ---------- */
export function deriveSpendSkFromAddress(address) {
  const addrLower = address.toLowerCase();
  const h = keccak_256(new TextEncoder().encode(addrLower + ":spend"));
  let x = 0n;
  for (const v of h) x = (x << 8n) | BigInt(v);
  x = (x % (N - 1n)) + 1n;
  const out = new Uint8Array(32);
  for (let i = 31; i >= 0; i--) { out[i] = Number(x & 0xffn); x >>= 8n; }
  return bytesToHex(out);
}

export function deriveViewSkFromAddress(address) {
  const addrLower = address.toLowerCase();
  const h = keccak_256(new TextEncoder().encode(addrLower + ":view"));
  let x = 0n;
  for (const v of h) x = (x << 8n) | BigInt(v);
  x = (x % (N - 1n)) + 1n;
  const out = new Uint8Array(32);
  for (let i = 31; i >= 0; i--) { out[i] = Number(x & 0xffn); x >>= 8n; }
  return bytesToHex(out);
}

/* ---------- 由 R + 基础地址推导一次性私钥 p ---------- */
export async function deriveOneTimePrivKey(R_compressedHex, baseAddress) {
  // 1) shared = view_sk * R → 取 X(32B)
  const viewSk = deriveViewSkFromAddress(baseAddress);
  // v3 的 getSharedSecret 仍可用；返回 32/33/65，做规范化即可
  const sharedRaw = secp.getSharedSecret(hexToBytes(viewSk), hexToBytes(R_compressedHex), false);
  const sharedX = normalizeSharedSecret(sharedRaw);

  // 2) h = sha256(sharedX) mod N
  const sHash = await sha256(sharedX);
  let hBig = 0n; for (const x of sHash) hBig = (hBig << 8n) | BigInt(x);
  hBig %= N;

  // 3) p = (spend_sk + h) mod N
  let sBig = 0n;
  for (const x of hexToBytes(deriveSpendSkFromAddress(baseAddress))) sBig = (sBig << 8n) | BigInt(x);
  const pBig = (sBig + hBig) % N;

  // 输出 0x..32B
  let t = pBig;
  const out = new Uint8Array(32);
  for (let i = 31; i >= 0; i--) { out[i] = Number(t & 0xffn); t >>= 8n; }
  return bytesToHex(out);
}

/* ---------- sweep ETH ---------- */
export async function sweepNative({ rpcUrl, fromPrivHex, toAddress, leaveWei = 0n }) {
  const provider = (typeof window !== "undefined" && window.ethereum)
    ? new BrowserProvider(window.ethereum)
    : new JsonRpcProvider(rpcUrl);

  const wallet = new Wallet(fromPrivHex, provider);
  const from = await wallet.getAddress();

  const [balance, feeData, nonce] = await Promise.all([
    provider.getBalance(from),
    provider.getFeeData(),
    provider.getTransactionCount(from),
  ]);
  if (balance === 0n) throw new Error("no ETH to sweep");

  const maxFeePerGas = feeData.maxFeePerGas ?? feeData.gasPrice ?? 0n;
  const maxPriorityFeePerGas = feeData.maxPriorityFeePerGas ?? 0n;

  const gasLimit = await provider.estimateGas({ from, to: toAddress, value: balance })
    .catch(() => 21000n);
  const fee = gasLimit * (maxFeePerGas || 1n);

  let value = balance - fee - leaveWei;
  if (value <= 0n) throw new Error("insufficient ETH after gas");

  const tx = await wallet.sendTransaction({
    to: toAddress,
    value,
    maxFeePerGas: maxFeePerGas || undefined,
    maxPriorityFeePerGas: maxPriorityFeePerGas || undefined,
    nonce,
  });
  return tx.wait();
}

/* ---------- sweep ERC20 ---------- */
const ERC20_ABI = [
  "function balanceOf(address) view returns (uint256)",
  "function decimals() view returns (uint8)",
  "function transfer(address,uint256) returns (bool)"
];

export async function sweepERC20({ rpcUrl, tokenAddress, fromPrivHex, toAddress }) {
  const provider = (typeof window !== "undefined" && window.ethereum)
    ? new BrowserProvider(window.ethereum)
    : new JsonRpcProvider(rpcUrl);

  const wallet = new Wallet(fromPrivHex, provider);
  const token = new Contract(tokenAddress, ERC20_ABI, wallet);
  const from = await wallet.getAddress();
  const bal = await token.balanceOf(from);
  if (bal === 0n) throw new Error("no token to sweep");

  // 需要 from 地址上有少量 ETH 支付 gas
  const tx = await token.transfer(toAddress, bal);
  return tx.wait();
}
