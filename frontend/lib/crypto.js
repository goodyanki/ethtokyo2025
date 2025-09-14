// frontend/lib/crypto.js
import * as secp from "noble-secp256k1";
import { keccak_256 } from "@noble/hashes/sha3";

/* ------------------ 工具 ------------------ */
export const hexToBytes = (hex) => {
  const s = hex.startsWith("0x") ? hex.slice(2) : hex;
  if (s.length % 2) throw new Error("hex length must be even");
  const out = new Uint8Array(s.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(s.slice(i * 2, i * 2 + 2), 16);
  return out;
};
export const bytesToHex = (b) =>
  "0x" + Array.from(b).map((x) => x.toString(16).padStart(2, "0")).join("");

// 以太坊地址（未压 0x04||X||Y → keccak → 20B）
export const ethAddressFromUncompressed = (pubUncomp) => {
  if (pubUncomp.length !== 65 || pubUncomp[0] !== 0x04) throw new Error("expect uncompressed pubkey (65B)");
  const h = keccak_256(pubUncomp.slice(1));
  const addr = h.slice(-20);
  return "0x" + Array.from(addr).map((x) => x.toString(16).padStart(2, "0")).join("");
};

export const toCompressed = (pubUncompHex) => {
  const P = secp.Point.fromHex(pubUncompHex);
  return "0x" + P.toRawBytes(true).reduce((s, x) => s + x.toString(16).padStart(2, "0"), "");
};
export const toUncompressed = (pubCompressedHex) => {
  const P = secp.Point.fromHex(pubCompressedHex);
  return "0x" + P.toRawBytes(false).reduce((s, x) => s + x.toString(16).padStart(2, "0"), "");
};

// WebCrypto（仅浏览器）
const webcrypto = globalThis.crypto;

// TypedArray → 干净 ArrayBuffer
function toArrayBuffer(view) {
  return view.buffer.slice(view.byteOffset, view.byteOffset + view.byteLength);
}

export const sha256 = async (m) => {
  if (!webcrypto?.subtle) throw new Error("WebCrypto not available (use in client/browser)");
  const d = await webcrypto.subtle.digest("SHA-256", toArrayBuffer(m));
  return new Uint8Array(d);
};

// 随机 32B 私钥（1..n-1）
export const randomScalarHex = () => {
  let sk;
  while (true) {
    if (!webcrypto?.getRandomValues) throw new Error("WebCrypto RNG not available");
    sk = webcrypto.getRandomValues(new Uint8Array(32));
    const hex = bytesToHex(sk);
    if (secp.utils.isValidPrivateKey(hexToBytes(hex))) return hex;
  }
};

// 归一化 noble getSharedSecret 的返回：32 / 33 / 65 → 统一取 X(32B)
function normalizeSharedSecret(bytes) {
  if (bytes.length === 32) return bytes;           // 直接 X
  if (bytes.length === 33) return bytes.slice(1);  // 前缀+X
  if (bytes.length === 65) return bytes.slice(1, 33); // 0x04||X||Y
  throw new Error(`Unexpected ECDH shared length=${bytes.length}`);
}

/* ------------------ 一次性地址生成核心 ------------------ */
export async function deriveOneTimeAddress({ spendPubUncompressed, viewPubCompressed, rHex }) {
  const r = rHex ?? randomScalarHex();

  // R = r·G（压缩）
  const R = secp.Point.fromPrivateKey(hexToBytes(r));
  const R_compressed = "0x" + R.toRawBytes(true).reduce((s, x) => s + x.toString(16).padStart(2, "0"), "");

  // r·V → shared
  const sharedRaw = secp.getSharedSecret(
    hexToBytes(r),
    hexToBytes(viewPubCompressed),
    false // 不要求前缀，由 normalize 统一
  );
  const shared = normalizeSharedSecret(sharedRaw);

  // s = H(r·V)
  const s_bytes = await sha256(shared);

  // h = H(s) mod n
  const n = secp.CURVE.n;
  let hBig = 0n;
  for (const x of s_bytes) hBig = (hBig << 8n) | BigInt(x);
  hBig %= n;

  // P = h·G + S
  const hG = secp.Point.fromPrivateKey(hBig);
  const S  = secp.Point.fromHex(hexToBytes(spendPubUncompressed));
  const P  = hG.add(S);
  const P_uncompressed = P.toRawBytes(false);
  const P_uncompressedHex = "0x" + Array.from(P_uncompressed).map((x) => x.toString(16).padStart(2, "0")).join("");

  // addr
  const addr = ethAddressFromUncompressed(P_uncompressed);

  // tag = keccak256( sha256( r·V ) )
  const sHash   = await sha256(shared);
  const tagBytes = keccak_256(sHash);
  const tagHex  = "0x" + Array.from(tagBytes).map((x) => x.toString(16).padStart(2, "0")).join("");

  return {
    rHex: r,
    R_compressed,            // 33B
    P_uncompressed: P_uncompressedHex, // 65B
    addr,
    tag: tagHex,
  };
}

/* ------------------ 浏览器 ECIES 到 view 公钥 ------------------ */
export async function eciesEncryptToView(viewPubCompressed, plaintext) {
  if (!webcrypto?.subtle) throw new Error("WebCrypto not available");

  // 临时密钥
  const ephSk  = randomScalarHex();
  const ephPub = "0x" + secp.Point.fromPrivateKey(hexToBytes(ephSk))
    .toRawBytes(true).reduce((s, x) => s + x.toString(16).padStart(2, "0"), "");

  // ECDH
  const sharedRaw = secp.getSharedSecret(
    hexToBytes(ephSk),
    hexToBytes(viewPubCompressed),
    false
  );
  const shared = normalizeSharedSecret(sharedRaw);

  // HKDF → AES-CTR
  const keyMaterial = await webcrypto.subtle.importKey("raw", toArrayBuffer(shared), "HKDF", false, ["deriveKey"]);
  const key = await webcrypto.subtle.deriveKey(
    { name: "HKDF", hash: "SHA-256", salt: new Uint8Array([]), info: new TextEncoder().encode("ecies-secp256k1-key") },
    keyMaterial,
    { name: "AES-CTR", length: 256 },
    false,
    ["encrypt"]
  );

  const iv = webcrypto.getRandomValues(new Uint8Array(16));
  const ctBuf = await webcrypto.subtle.encrypt(
    { name: "AES-CTR", counter: toArrayBuffer(iv), length: 64 },
    key,
    toArrayBuffer(plaintext)
  );
  const ct = new Uint8Array(ctBuf);

  return { ephPub, iv: bytesToHex(iv), ct: bytesToHex(ct) };
}

/* ------------------ 组合接口 ------------------ */
export async function senderAssembleAnnouncement({ spendPubUncompressed, viewPubCompressed, memoPlaintext }) {
  const ot = await deriveOneTimeAddress({ spendPubUncompressed, viewPubCompressed });

  let amountCipher;
  if (memoPlaintext && memoPlaintext.length > 0) {
    amountCipher = await eciesEncryptToView(viewPubCompressed, memoPlaintext);
  }

  return {
    addr: ot.addr,
    R: ot.R_compressed,
    tag: ot.tag,
    amountCipher,
    rHex: ot.rHex,
  };
}

/* ------------------ （可选）PaymentProxy 路线工具 ------------------ */
export function buildPaymentDigest(paymentId, to, amount, tag) {
  const pid = hexToBytes(paymentId);
  if (pid.length !== 32) throw new Error("paymentId must be 32 bytes");
  const addrBytes = hexToBytes(to);
  if (addrBytes.length !== 20) throw new Error("to must be 20-byte address");

  const amt = BigInt(amount);
  const amtBytes = new Uint8Array(32);
  let x = amt;
  for (let i = 31; i >= 0; i--) { amtBytes[i] = Number(x & 0xffn); x >>= 8n; }

  const tagBytes = hexToBytes(tag);
  if (tagBytes.length !== 32) throw new Error("tag must be 32 bytes");

  const packed = new Uint8Array(32 + 20 + 32 + 32);
  packed.set(pid, 0);
  packed.set(addrBytes, 32);
  packed.set(amtBytes, 52);
  packed.set(tagBytes, 84);

  const digest = keccak_256(packed);
  return bytesToHex(digest);
}

export function splitSignature(sigHex) {
  const b = hexToBytes(sigHex);
  if (b.length !== 65) throw new Error("signature must be 65 bytes");
  const r = bytesToHex(b.slice(0, 32));
  const s = bytesToHex(b.slice(32, 64));
  const v = b[64];
  return { r, s, v };
}
