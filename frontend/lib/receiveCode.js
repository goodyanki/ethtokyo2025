// frontend/lib/receiveCode.js
// Browser-friendly: no Node 'crypto' APIs

import bs58 from "bs58";
import { keccak256, toUtf8Bytes, getAddress } from "ethers";
import * as secp from "noble-secp256k1";

/* ------------------ utils ------------------ */
function hexToBuf(hex) {
  const s = hex.startsWith("0x") ? hex.slice(2) : hex;
  if (s.length % 2) throw new Error("invalid hex length");
  const out = new Uint8Array(s.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(s.slice(i * 2, i * 2 + 2), 16);
  return out;
}

function bufToHex(buf) {
  return "0x" + Array.from(buf).map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function sha256(data) {
  const d = await crypto.subtle.digest(
    "SHA-256",
    data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength)
  );
  return new Uint8Array(d);
}

export function generateNonce16() {
  const n = new Uint8Array(16);
  crypto.getRandomValues(n);
  return n;
}

// 将 0x..32B 转为有效标量 (1..n-1) 并以 32B 大端返回
function scalarFromHex32ToBytes32ModN(hex32) {
  const n = secp.CURVE.n;
  const b = hexToBuf(hex32);
  let x = 0n;
  for (const v of b) x = (x << 8n) | BigInt(v);
  x = (x % (n - 1n)) + 1n; // [1, n-1]
  const out = new Uint8Array(32);
  for (let i = 31; i >= 0; i--) { out[i] = Number(x & 0xffn); x >>= 8n; }
  return out;
}

/* ------------------ 从地址派生 demo 公钥（65B 未压 + 33B 压缩） ------------------ */
export function derivePubkeysFromAddress(address) {
  const norm = getAddress(address);
  const seedSpend = keccak256(toUtf8Bytes(norm.toLowerCase() + ":spend"));
  const seedView  = keccak256(toUtf8Bytes(norm.toLowerCase() + ":view"));

  const skSpendBytes = scalarFromHex32ToBytes32ModN(seedSpend);
  const skViewBytes  = scalarFromHex32ToBytes32ModN(seedView);

  const spendUncompressed = secp.getPublicKey(skSpendBytes, false); // 65B
  const viewCompressed    = secp.getPublicKey(skViewBytes,  true); // 33B

  return {
    spend: bufToHex(spendUncompressed), // 0x04.. (65B)
    view:  bufToHex(viewCompressed),    // 0x02/03.. (33B)
  };
}

/* ------------------ 编码 / 解码 ------------------ */
// Base58: [ version:1 | spend(65) | view(33) | nonce(16) | checksum(4) ]
export async function encodeReceiveCode(spendPubUncompressedHex, viewPubCompressedHex, nonceOverride) {
  const version = new Uint8Array([1]);
  const spend = hexToBuf(spendPubUncompressedHex);
  const view  = hexToBuf(viewPubCompressedHex);
  if (spend.length !== 65) throw new Error("spend must be 65B uncompressed pubkey");
  if (view.length  !== 33) throw new Error("view must be 33B compressed pubkey");

  const nonce = nonceOverride ?? generateNonce16();
  if (!(nonce instanceof Uint8Array) || nonce.length !== 16) throw new Error("nonce must be 16 bytes");

  const payload = new Uint8Array(1 + 65 + 33 + 16);
  payload.set(version, 0);
  payload.set(spend,   1);
  payload.set(view,   66);
  payload.set(nonce,  99);

  const digest = await sha256(payload);
  const checksum = digest.slice(0, 4);

  const full = new Uint8Array(payload.length + 4);
  full.set(payload, 0);
  full.set(checksum, payload.length);

  return bs58.encode(full);
}

export async function decodeReceiveCode(code) {
  const buf = bs58.decode(code);
  if (buf.length !== 1 + 65 + 33 + 16 + 4) throw new Error("Invalid code length");
  const version = buf[0];
  if (version !== 1) throw new Error(`Unsupported version: ${version}`);

  const payload  = buf.slice(0, 1 + 65 + 33 + 16);
  const checksum = buf.slice(1 + 65 + 33 + 16);
  const expected = (await sha256(payload)).slice(0, 4);
  for (let i = 0; i < 4; i++) if (checksum[i] !== expected[i]) throw new Error("Invalid checksum");

  return {
      version,
      pubkeySpend: bufToHex(buf.slice(1, 66)),   // 65B uncompressed
      pubkeyView:  bufToHex(buf.slice(66, 99)),  // 33B compressed
      nonce:       bufToHex(buf.slice(99, 115)), // 16B
      checksum:    bufToHex(checksum),           // 4B
  };
}
